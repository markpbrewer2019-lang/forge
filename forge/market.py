"""PoE2 economy ingestion worker. Source access is outside crafting/solver code."""
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
import hashlib
import json
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

from .model import ForgeError, require, digest
from .data import normalize_ninja_exchange


ORIGIN = "https://poe.ninja"
LEAGUES = ORIGIN + "/poe2/api/economy/leagues"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ForgeError("UNEXPECTED_API_REDIRECT", newurl)


def http_get(url, headers, timeout):
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(urllib.request.Request(url, headers=headers), timeout=timeout) as response:
            body = response.read(8_000_001)
            require(len(body) <= 8_000_000, "API_RESPONSE_TOO_LARGE", "Maximum response is 8 MB")
            return response.status, dict(response.headers), body
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), b""
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ForgeError("MARKET_UNAVAILABLE", str(exc)) from None


def utc_now():
    return datetime.now(timezone.utc)


def write_json(path, document):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


class NinjaClient:
    """One shared cache per ingestion worker. Never instantiate per player/request."""
    def __init__(self, cache_dir, user_agent="Forge/0.2 (PoE2 economy ingestion; local development)",
                 timeout=20, transport=http_get, now=utc_now):
        require(user_agent.startswith("Forge/") and len(user_agent) >= 15,
                "INVALID_USER_AGENT", "Identify Forge and its deployment/contact")
        require(0 < timeout <= 60, "INVALID_TIMEOUT", str(timeout), "INVALID")
        self.cache = Path(cache_dir)
        self.user_agent, self.timeout, self.transport, self.now = user_agent, timeout, transport, now

    def _get(self, url):
        require(url == LEAGUES or url.startswith(ORIGIN + "/poe2/api/economy/exchange/current/overview?"),
                "CURRENCY_SOURCE_REQUIRED", url)
        key = hashlib.sha256(url.encode()).hexdigest()
        cache_file = self.cache / (key + ".json")
        now = self.now()
        require(now.tzinfo is not None, "INVALID_CLOCK", "Timezone required", "INVALID")
        cached = None
        if cache_file.exists():
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            require(cached["url"] == url and digest(cached["data"]) == cached["data_sha256"],
                    "CORRUPT_MARKET_CACHE", str(cache_file))
            wait_until = datetime.fromisoformat(cached["next_request_at"])
            if now < wait_until:
                require(not cached.get("error"), "MARKET_RETRY_LATER", cached["next_request_at"])
                require(not cached.get("requires_revalidation"), "MARKET_REVALIDATION_THROTTLED",
                        "Source requires revalidation; retry after " + cached["next_request_at"])
                return {**cached, "from_cache": True}
        headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
        if cached:
            if cached.get("etag"):
                headers["If-None-Match"] = cached["etag"]
            if cached.get("last_modified"):
                headers["If-Modified-Since"] = cached["last_modified"]
        try:
            status, raw_headers, body = self.transport(url, headers, self.timeout)
        except ForgeError:
            write_json(cache_file, {"url": url, "data": None, "data_sha256": digest(None), "error": "transport",
                                   "next_request_at": (now + timedelta(seconds=300)).isoformat()})
            raise
        response_headers = {k.lower(): v for k, v in raw_headers.items()}
        # A minimum five-minute interval also applies to error responses.
        max_age = re.search(r"(?:^|,)\s*max-age=(\d+)", response_headers.get("cache-control", ""))
        delay = max(300, int(max_age.group(1)) if max_age else 300)
        retry = response_headers.get("retry-after")
        if retry:
            try:
                retry_delay = int(retry)
            except ValueError:
                try:
                    retry_delay = int((parsedate_to_datetime(retry) - now).total_seconds())
                except (ValueError, TypeError):
                    retry_delay = 300
            delay = max(delay, retry_delay)
        # Reserve the next request time before parsing, so malformed responses cannot cause tight retry loops.
        write_json(cache_file, {"url": url, "data": None, "data_sha256": digest(None), "error": "unvalidated-response",
                               "next_request_at": (now + timedelta(seconds=delay)).isoformat()})
        if status == 304:
            require(cached is not None and not cached.get("error"), "INVALID_NOT_MODIFIED", url)
            record = {**cached, "validated_at": now.isoformat(),
                      "next_request_at": (now + timedelta(seconds=delay)).isoformat()}
            # Do not advance the source observation timestamp on a 304.
        elif status == 200:
            try:
                data = json.loads(body.decode("utf-8"), parse_float=str)
            except (ValueError, UnicodeError):
                raise ForgeError("INVALID_MARKET_RESPONSE", "Expected JSON") from None
            content_type = response_headers.get("content-type", "application/json").lower()
            require("json" in content_type, "INVALID_MARKET_RESPONSE", content_type)
            observed_at = now
            if response_headers.get("date"):
                try:
                    age = int(response_headers.get("age", "0"))
                    observed_at = min(now, parsedate_to_datetime(response_headers["date"]) - timedelta(seconds=max(0, age)))
                except (ValueError, TypeError, OverflowError):
                    raise ForgeError("INVALID_MARKET_TIMESTAMP", "Invalid Date/Age header") from None
            record = {"url": url, "retrieved_at": now.isoformat(), "observed_at": observed_at.isoformat(),
                      "validated_at": now.isoformat(), "next_request_at": (now + timedelta(seconds=delay)).isoformat(),
                      "etag": response_headers.get("etag"), "last_modified": response_headers.get("last-modified"),
                      "data": data, "data_sha256": digest(data), "http_status": status,
                      "response_headers": response_headers,
                      "requires_revalidation": "no-cache" in response_headers.get("cache-control", "").lower()}
            # Preserve exact API bytes separately from normalized decimal strings.
            raw_sha = hashlib.sha256(body).hexdigest()
            if "no-store" not in response_headers.get("cache-control", "").lower():
                self.cache.mkdir(parents=True, exist_ok=True)
                snapshot = self.cache / "snapshots" / (raw_sha + ".json")
                snapshot.parent.mkdir(exist_ok=True)
                if not snapshot.exists():
                    snapshot.write_bytes(body)
                record.update(raw_sha256=raw_sha, raw_snapshot=str(snapshot.resolve()))
        else:
            record = {"url": url, "data": None, "data_sha256": digest(None), "error": status,
                      "next_request_at": (now + timedelta(seconds=delay)).isoformat()}
            write_json(cache_file, record)
            raise ForgeError("MARKET_HTTP_ERROR", {"status": status, "retry_at": record["next_request_at"]})
        if "no-store" not in response_headers.get("cache-control", "").lower():
            write_json(cache_file, record)
        else:
            # Store only a rate-limit timestamp, never the no-store response body or validators.
            write_json(cache_file, {"url": url, "data": None, "data_sha256": digest(None), "error": "no-store",
                                   "next_request_at": (now + timedelta(seconds=delay)).isoformat()})
        return {**record, "from_cache": status == 304}

    def leagues(self):
        response = self._get(LEAGUES)
        rows = response["data"]
        require(isinstance(rows, list) and bool(rows) and all(isinstance(r, dict) and isinstance(r.get("id"), str)
                and r["id"] and isinstance(r.get("name"), str) for r in rows),
                "INVALID_LEAGUE_RESPONSE", "Expected nonempty documented league array")
        require(len({r["id"] for r in rows}) == len(rows), "CONFLICTING_LEAGUE_RECORDS", "Duplicate IDs")
        return response

    def currency(self, league, version, category="Currency"):
        from .currency_source import EXCHANGE_CATEGORIES
        require(category in EXCHANGE_CATEGORIES, "UNSUPPORTED_EXCHANGE_CATEGORY", category, "INVALID")
        require(isinstance(league, str) and bool(league) and isinstance(version, str) and bool(version),
                "MISSING_MARKET_SCOPE", "Explicit league and game-data version required", "INVALID")
        leagues = self.leagues()
        require(league in {r["id"] for r in leagues["data"]}, "UNKNOWN_LEAGUE", league)
        url = ORIGIN + "/poe2/api/economy/exchange/current/overview?" + urllib.parse.urlencode({"league": league, "type": category})
        response = self._get(url)
        normalized = normalize_ninja_exchange(response["data"], league=league, version=version,
                                               as_of=response["observed_at"], source_reference=url)
        normalized["price_book"]["evidence"]["retrieved_at"] = response["retrieved_at"]
        return {"status": "PARTIALLY_VALIDATED", "domain": "POE2", **normalized,
                "receipt": {k: v for k, v in response.items() if k != "data"},
                "note": "Live source observation ingested. Pricing confidence remains UNKNOWN; review before authoritative route economics."}


def market_coverage(book):
    from .economics import PriceBook, CompositePriceBook
    if isinstance(book, dict):
        book = PriceBook.load(book)
    if isinstance(book, CompositePriceBook):
        return {"domain": book.domain, "league": book.league, "unit": book.unit, "as_of": book.as_of,
                "known_quotes": len(book.quotes), "books": [market_coverage(b) for b in book.books]}
    return {"domain": book.domain, "league": book.league, "version": book.version,
            "source": book.evidence.source, "as_of": book.as_of, "unit": book.unit,
            "currency_records": len(book.quotes), "known_quotes": sum(v is not None for v in book.quotes.values()),
            "missing_quotes": sorted(k for k, v in book.quotes.items() if v is None),
            "verification_status": book.evidence.status, "snapshot_sha256": book.snapshot_sha256}


def currency_quote(book, currency_id):
    """Inspect sourced observations without bypassing evidence gates for route pricing."""
    from .economics import PriceBook, CompositePriceBook
    if isinstance(book, dict):
        book = PriceBook.load(book)
    if isinstance(book, CompositePriceBook):
        matching = [b for b in book.books if b.quotes.get(currency_id) is not None]
        require(bool(matching), "UNKNOWN_CURRENCY", currency_id)
        observations = [currency_quote(b, currency_id) for b in matching]
        require(len({str(row["price"]) for row in observations}) == 1, "CONFLICTING_PRICE", currency_id)
        return {"status": "PARTIALLY_VALIDATED", "currency_id": currency_id, "observations": observations}
    require(book.domain == "POE2" and book.evidence.source == "poe.ninja",
            "CURRENCY_SOURCE_REQUIRED", "Expected a PoE2 API price book")
    from .currency_source import validate_currency_source
    from .model import rational
    validate_currency_source(book.evidence.reference, book.league)
    require(book.source_snapshot is not None and digest(book.source_snapshot) == book.snapshot_sha256,
            "CURRENCY_SNAPSHOT_REQUIRED", "API snapshot is absent or modified")
    original = normalize_ninja_exchange(book.source_snapshot, league=book.league, version=book.version,
                    as_of=book.as_of, source_reference=book.evidence.reference)["price_book"]
    require(book.unit == original["unit"] and {k: None if v is None else str(rational(v)) for k, v in book.quotes.items()} == original["quotes"],
            "CURRENCY_SNAPSHOT_MISMATCH", "Prices must match API response")
    require(currency_id in book.quotes, "UNKNOWN_CURRENCY", currency_id)
    line = next(row for row in book.source_snapshot["lines"] if row["id"] == currency_id)
    return {"status": "PARTIALLY_VALIDATED", "currency_id": currency_id, "price": book.quotes[currency_id],
            "unit": book.unit, "league": book.league, "as_of": book.as_of,
            "source": book.evidence.reference, "verification_status": book.evidence.status,
            "volume_primary_value": line.get("volumePrimaryValue"), "confidence": "UNKNOWN",
            "note": "Sourced market observation. Route pricing still requires evidence and freshness validation."}
