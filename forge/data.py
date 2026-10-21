"""Local normalization and auditing. No solver calls a network source."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from .model import Dataset, ForgeError, require, dataset_document, jsonable


def coverage(data):
    mods = list(data.modifiers.values())
    missing = {field: [m.id for m in mods if getattr(m, field) is None]
               for field in ("weight", "ilvl", "side", "tier", "group", "bases", "classes", "tags", "conflicts")}
    issues = []
    for kind, records in (("base", data.bases), ("modifier", data.modifiers), ("action", data.actions)):
        for rid, record in records.items():
            try:
                data.verify(record.evidence)
            except ForgeError as exc:
                issues.append({"kind": kind, "id": rid, **exc.report()})
    supported, unsupported = [], []
    from .engine import Engine
    engine = Engine(data)
    for aid in data.actions:
        try:
            engine.action(aid)
            supported.append(aid)
        except ForgeError as exc:
            unsupported.append({"action": aid, **exc.report()})
    pool_issues = []
    for p in data.pools:
        try:
            data.verify(p.evidence)
            require(all(mid in data.modifiers for mid in p.modifier_ids), "MISSING_CERTIFIED_MODIFIER", p.action)
        except ForgeError as exc:
            pool_issues.append({"base": p.base, "action": p.action, **exc.report()})
    return {"domain": data.domain, "dataset_id": data.key, "version": data.version, "league": data.league,
            "total_bases": len(data.bases), "item_classes": sorted({b.item_class for b in data.bases.values()}),
            "total_modifiers": len(mods), "known_weights": sum(m.weight is not None for m in mods),
            "verified_weight_records": sum(m.weight is not None and m.evidence.status == "VERIFIED" for m in mods),
            "missing": missing, "verification_counts": dict(Counter(m.evidence.status for m in mods)),
            "supported_action_ids": supported, "unsupported_mechanics": unsupported,
            "pool_certificates": len(data.pools), "pool_issues": pool_issues,
            "provenance_issues": issues,
            "conflicting_records": [m.id for m in mods if m.evidence.status == "CONFLICTED"],
            "unsupported_item_classes": "UNKNOWN: no authoritative class inventory loaded",
            "warning": "Coverage counts are not proof of pool completeness. Only scoped certificates authorize probability."}


def ingest_local(source, destination):
    """Refresh from a reviewed normalized JSON export, preserving raw bytes and evidence statuses."""
    source, destination = Path(source), Path(destination)
    raw = source.read_bytes()
    parsed = json.loads(raw)
    data = Dataset.load(parsed)
    # Structural validator rejects ambiguous references; unknown fields stay unknown.
    for p in data.pools:
        require(p.base in data.bases and p.action in data.actions, "INVALID_POOL_REFERENCE", p.action, "INVALID")
        require(all(mid in data.modifiers for mid in p.modifier_ids), "MISSING_CERTIFIED_MODIFIER", p.action, "INVALID")
    destination.mkdir(parents=True, exist_ok=True)
    sha = hashlib.sha256(raw).hexdigest()
    snapshots = destination / "snapshots"
    snapshots.mkdir(exist_ok=True)
    snapshot = snapshots / f"{sha}.json"
    snapshot.write_bytes(raw)
    normalized = destination / "dataset.json"
    temp = destination / "dataset.tmp"
    temp.write_text(json.dumps(dataset_document(data), indent=2), encoding="utf-8")
    temp.replace(normalized)
    receipt = {"source_file": str(source.resolve()), "sha256": sha,
               "ingested_at": datetime.now(timezone.utc).isoformat(),
               "snapshot": str(snapshot.resolve()), "dataset_id": data.key, "coverage": coverage(data)}
    (destination / "receipt.json").write_text(json.dumps(jsonable(receipt), indent=2), encoding="utf-8")
    return receipt


def normalize_ninja_exchange(raw, *, league, version, as_of, source_reference):
    """Normalize a saved supported PoE2 exchange response. Market observations remain INFERRED until reviewed."""
    from .currency_source import validate_currency_source
    from .model import digest
    validate_currency_source(source_reference, league)
    core = raw.get("core", {})
    require(isinstance(core.get("primary"), str) and bool(core["primary"]),
            "UNKNOWN_PRICE_UNIT", "Expected documented core.primary currency ID")
    quotes, availability = {}, {}
    from .model import rational
    require(isinstance(raw.get("lines"), list) and bool(raw["lines"]), "INVALID_MARKET_RESPONSE", "Nonempty lines required")
    for line in raw["lines"]:
        rid = line["id"]
        require(isinstance(rid, str) and bool(rid), "INVALID_CURRENCY_ID", str(rid), "INVALID")
        require(rid not in quotes, "CONFLICTING_PRICE", rid, "INVALID")
        value = line.get("primaryValue")
        require(value is None or (not isinstance(value, bool) and rational(str(value)) >= 0),
                "INVALID_PRICE", rid, "INVALID")
        quotes[rid] = None if value is None else str(rational(str(value)))
        availability[rid] = {"volume_primary_value": line.get("volumePrimaryValue"), "confidence": "UNKNOWN"}
    return {"price_book": {"domain": "POE2", "version": version, "league": league, "unit": core["primary"],
            "as_of": as_of, "source_observed_at": as_of, "quotes": quotes, "source_snapshot": raw, "snapshot_sha256": digest(raw),
            "evidence": {"source": "poe.ninja", "reference": source_reference,
            "retrieved_at": as_of, "status": "INFERRED", "domain": "POE2", "version": version, "league": league,
            "notes": "Saved public exchange observation; snapshot age, units, liquidity and league require review."}},
            "availability": availability}
