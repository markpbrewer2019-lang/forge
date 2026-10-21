from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import tempfile
import unittest

from forge.market import NinjaClient, LEAGUES, market_coverage
from forge.model import ForgeError


class MarketTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.time = datetime(2026, 10, 20, tzinfo=timezone.utc)
        self.calls = []
        self.reply = (200, {"Content-Type": "application/json", "ETag": "snapshot-v1", "Cache-Control": "max-age=300"},
                      json.dumps([{"id": "Standard", "name": "Standard"}]).encode())
        def transport(url, headers, timeout):
            self.calls.append((url, headers, timeout))
            return self.reply
        self.client = NinjaClient(self.directory.name, transport=transport, now=lambda: self.time)

    def assertCode(self, code, function, *args):
        with self.assertRaises(ForgeError) as caught:
            function(*args)
        self.assertEqual(code, caught.exception.code)

    def test_shared_cache_prevents_duplicate_network_requests(self):
        first = self.client.leagues()
        second = self.client.leagues()
        self.assertEqual(1, len(self.calls))
        self.assertTrue(second["from_cache"])
        self.assertEqual(first["data"], second["data"])
        self.assertEqual(self.reply[2], Path(first["raw_snapshot"]).read_bytes())

    def test_conditional_refresh_does_not_freshen_old_prices(self):
        first = self.client.leagues()
        self.time += timedelta(seconds=301)
        self.reply = (304, {}, b"")
        refreshed = self.client.leagues()
        self.assertEqual("snapshot-v1", self.calls[-1][1]["If-None-Match"])
        self.assertEqual(first["observed_at"], refreshed["observed_at"])
        self.assertNotEqual(first["validated_at"], refreshed["validated_at"])

    def test_retry_after_is_respected_without_stale_fallback(self):
        self.reply = (429, {"Retry-After": "1200"}, b"")
        self.assertCode("MARKET_HTTP_ERROR", self.client.leagues)
        self.time += timedelta(seconds=400)
        self.assertCode("MARKET_RETRY_LATER", self.client.leagues)
        self.assertEqual(1, len(self.calls))

    def test_currency_endpoint_snapshot_and_normalization(self):
        self.client.leagues()
        self.reply = (200, {"Content-Type": "application/json"},
                      b'{"core":{"primary":"divine"},"lines":[{"id":"test","primaryValue":0.125}]}')
        result = self.client.currency("Standard", "fixture")
        self.assertIn("/poe2/api/economy/exchange/current/overview?", self.calls[-1][0])
        self.assertEqual("1/8", result["price_book"]["quotes"]["test"])
        self.assertEqual("INFERRED", result["price_book"]["evidence"]["status"])
        self.assertEqual(1, market_coverage(result["price_book"])["known_quotes"])

    def test_unknown_league_never_requests_currency(self):
        self.assertCode("UNKNOWN_LEAGUE", self.client.currency, "invented-league", "fixture")
        self.assertEqual(1, len(self.calls))

    def test_transport_failure_throttles_followup(self):
        def failure(*args):
            raise ForgeError("MARKET_UNAVAILABLE", "offline")
        self.client.transport = failure
        self.assertCode("MARKET_UNAVAILABLE", self.client.leagues)
        self.assertCode("MARKET_RETRY_LATER", self.client.leagues)

    def test_malformed_json_and_non_json_are_rejected(self):
        self.reply = (200, {"Content-Type": "application/json"}, b"invalid")
        self.assertCode("INVALID_MARKET_RESPONSE", self.client.leagues)
        self.assertCode("MARKET_RETRY_LATER", self.client.leagues)

    def test_no_store_never_persists_response_body(self):
        status, _, body = self.reply
        self.reply = status, {"Cache-Control": "no-store"}, body
        self.client.leagues()
        self.assertFalse((Path(self.directory.name) / "snapshots").exists())
        cache = next(Path(self.directory.name).glob("*.json"))
        self.assertIsNone(json.loads(cache.read_text())["data"])
        self.assertCode("MARKET_RETRY_LATER", self.client.leagues)

    def test_invalid_source_cannot_be_requested(self):
        self.assertCode("CURRENCY_SOURCE_REQUIRED", self.client._get, "https://poe.ninja/poe1/api/economy/leagues")
        self.assertEqual([], self.calls)

    def test_no_cache_requires_revalidation_without_excess_polling(self):
        status, _, body = self.reply
        self.reply = status, {"Cache-Control": "no-cache", "ETag": "one"}, body
        self.client.leagues()
        self.assertCode("MARKET_REVALIDATION_THROTTLED", self.client.leagues)
        self.time += timedelta(seconds=301)
        self.reply = (304, {}, b"")
        self.client.leagues()
        self.assertEqual("one", self.calls[-1][1]["If-None-Match"])

    def test_quote_lookup_preserves_source_and_unknown_confidence(self):
        from forge.data import normalize_ninja_exchange
        from forge.market import currency_quote
        raw = {"core": {"primary": "divine"}, "lines": [{"id": "test", "primaryValue": "0.25"}]}
        book = normalize_ninja_exchange(raw, league="Standard", version="fixture", as_of=self.time.isoformat(),
                    source_reference="https://poe.ninja/poe2/api/economy/exchange/current/overview?league=Standard&type=Currency")["price_book"]
        quote = currency_quote(book, "test")
        self.assertEqual("1/4", quote["price"])
        self.assertEqual("UNKNOWN", quote["confidence"])
        self.assertCode("UNKNOWN_CURRENCY", currency_quote, book, "unknown")

    def test_composite_coverage_and_quote_lookup(self):
        from forge.data import normalize_ninja_exchange
        from forge.market import currency_quote
        from forge.economics import PriceBook
        raw = {"core": {"primary": "divine"}, "lines": [{"id": "test", "primaryValue": "0.25"}]}
        book = normalize_ninja_exchange(raw, league="Standard", version="fixture", as_of=self.time.isoformat(),
                    source_reference="https://poe.ninja/poe2/api/economy/exchange/current/overview?league=Standard&type=Currency")["price_book"]
        combined = PriceBook.load({"books": [book, book]})
        self.assertEqual(1, market_coverage(combined)["known_quotes"])
        self.assertEqual(2, len(currency_quote(combined, "test")["observations"]))


if __name__ == "__main__":
    unittest.main()
