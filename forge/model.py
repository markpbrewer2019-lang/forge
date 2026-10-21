from __future__ import annotations

from dataclasses import asdict, dataclass, fields, field
from datetime import datetime
from fractions import Fraction
import hashlib
import json


class ForgeError(Exception):
    def __init__(self, code, detail, status="BLOCKED", location=None):
        self.code, self.detail, self.status, self.location = code, detail, status, location
        super().__init__(f"{code}: {detail}")

    def report(self):
        return {"status": self.status, "code": self.code, "detail": self.detail,
                "location": self.location}


def require(condition, code, detail, status="BLOCKED"):
    if not condition:
        raise ForgeError(code, detail, status)


def rational(value):
    require(not isinstance(value, (float, bool)), "INVALID_NUMBER", "Use integer or rational/decimal string", "INVALID")
    try:
        return Fraction(value)
    except (ValueError, TypeError, ZeroDivisionError):
        raise ForgeError("INVALID_NUMBER", repr(value), "INVALID") from None


def jsonable(value):
    if isinstance(value, Fraction):
        return str(value)
    if hasattr(value, "__dataclass_fields__"):
        return {f.name: jsonable(getattr(value, f.name)) for f in fields(value)
                if not (f.metadata.get("omit_none") and getattr(value, f.name) is None)}
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [jsonable(v) for v in value]
    return value


def digest(value):
    return hashlib.sha256(json.dumps(jsonable(value), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class Evidence:
    source: str
    reference: str
    retrieved_at: str
    status: str
    domain: str
    version: str
    league: str
    notes: str
    category: str | None = field(default=None, metadata={"omit_none": True})
    supporting_fact: str | None = field(default=None, metadata={"omit_none": True})

    def provenance(self):
        category = self.category or ("MATHEMATICAL_ASSUMPTION" if self.domain == "SYNTHETIC" else "UNKNOWN")
        require(category in {"SOURCE_FACT", "VERIFIED_GAME_OBSERVATION", "SIMULATOR_OBSERVATION",
                             "MATHEMATICAL_ASSUMPTION", "UNKNOWN"}, "INVALID_PROVENANCE_CATEGORY", category, "INVALID")
        return {**jsonable(self), "category": category, "supporting_fact": self.supporting_fact or self.notes,
                "scope": {"domain": self.domain, "version": self.version, "league": self.league}}

    def verify_mechanic(self, domain, version, league):
        self.verify(domain, version, league)
        provenance = self.provenance()
        require(provenance["category"] != "UNKNOWN", "UNVERIFIED_MECHANIC_PROVENANCE", self.reference)
        if domain == "POE2":
            require(provenance["category"] in {"SOURCE_FACT", "VERIFIED_GAME_OBSERVATION"}
                    and bool(self.supporting_fact), "UNVERIFIED_MECHANIC_PROVENANCE",
                    {"category": provenance["category"], "reference": self.reference})

    def verify_state_fact(self, domain, version, league):
        self.verify(domain, version, league)
        if domain == "POE2":
            require(self.provenance()["category"] in {"SOURCE_FACT", "VERIFIED_GAME_OBSERVATION"}
                    and bool(self.supporting_fact), "UNVERIFIED_STATE_PROVENANCE", self.reference)

    def verify(self, domain, version, league):
        require(self.status in {"VERIFIED", "INFERRED", "HYPOTHESIS", "UNKNOWN", "CONFLICTED"},
                "INVALID_EVIDENCE", self.status, "INVALID")
        require(self.status == "VERIFIED", "INSUFFICIENT_VERIFIED_DATA", f"{self.reference}: {self.status}")
        require(self.domain == domain and self.version == version and self.league == league,
                "EVIDENCE_SCOPE_MISMATCH", self.reference)
        require(all((self.source, self.reference, self.notes, self.version, self.league)),
                "INSUFFICIENT_VERIFIED_DATA", "Incomplete provenance")
        try:
            stamp = datetime.fromisoformat(self.retrieved_at.replace("Z", "+00:00"))
            require(stamp.tzinfo is not None, "INVALID_EVIDENCE", "Timestamp must include timezone", "INVALID")
        except ValueError:
            raise ForgeError("INVALID_EVIDENCE", "Invalid retrieval timestamp", "INVALID") from None


@dataclass(frozen=True)
class Base:
    id: str
    item_class: str
    tags: tuple[str, ...]
    # Explicit limits by rarity; never assume universal PoE rules.
    limits: dict
    evidence: Evidence


@dataclass(frozen=True)
class Modifier:
    id: str
    side: str | None
    tier: int | None
    group: str | None
    ilvl: int | None
    weight: int | None
    bases: tuple[str, ...] | None
    classes: tuple[str, ...] | None
    tags: tuple[str, ...] | None
    conflicts: tuple[str, ...] | None
    evidence: Evidence


@dataclass(frozen=True)
class Item:
    base: str
    ilvl: int
    rarity: str
    quality: int = 0
    mods: tuple[str, ...] = ()
    fractured: tuple[str, ...] = ()
    protected: tuple[str, ...] = ()
    flags: tuple[str, ...] = ()
    sockets: int | None = field(default=None, metadata={"omit_none": True})

    def __post_init__(self):
        require(self.sockets is None or (type(self.sockets) is int and self.sockets >= 0),
                "INVALID_SOCKET_STATE", str(self.sockets), "INVALID")
        for name in ("mods", "fractured", "protected", "flags"):
            require(isinstance(getattr(self, name), (tuple, list))
                    and all(isinstance(v, str) and v for v in getattr(self, name)),
                    "INVALID_STATE_COLLECTION", name, "INVALID")
            value = tuple(getattr(self, name))
            require(len(value) == len(set(value)), "DUPLICATE_STATE_ENTRY", name, "INVALID")
            object.__setattr__(self, name, tuple(sorted(value)))
        require(type(self.ilvl) is int and self.ilvl >= 1 and type(self.quality) is int and self.quality >= 0,
                "INVALID_ITEM", "ilvl and quality must be nonnegative integers (ilvl >= 1)", "INVALID")

    @property
    def key(self):
        return digest(self)

    @classmethod
    def load(cls, data):
        require(set(data) <= {f.name for f in fields(cls)}, "UNKNOWN_STATE_FIELD", str(set(data)), "INVALID")
        return cls(**data)


@dataclass(frozen=True)
class Action:
    id: str
    operation: str
    evidence: Evidence
    rarities: tuple[str, ...]
    resources: dict
    side: str | None = None
    pool_tags: tuple[str, ...] = ()
    fixed_mod: str | None = None
    require_mods: tuple[str, ...] = ()
    forbid_mods: tuple[str, ...] = ()
    require_flags: tuple[str, ...] = ()
    forbid_flags: tuple[str, ...] = ()
    set_flags: tuple[str, ...] = ()
    clear_flags: tuple[str, ...] = ()
    resulting_rarity: str | None = None
    known_flags: tuple[str, ...] = ()
    display_name: str | None = field(default=None, metadata={"omit_none": True})
    mechanic_context: dict | None = field(default=None, metadata={"omit_none": True})
    socket_delta: int | None = field(default=None, metadata={"omit_none": True})
    irreversible: bool | None = field(default=None, metadata={"omit_none": True})


@dataclass(frozen=True)
class FlagRule:
    """Explicit evidenced physical semantics; absent fields remain unknown."""
    id: str
    evidence: Evidence
    permanent: bool | None = None
    capacity_delta: dict | None = None
    incompatible_flags: tuple[str, ...] | None = None
    forbidden_actions: tuple[str, ...] | None = None
    forbidden_operations: tuple[str, ...] | None = None
    occupied_sockets: int | None = None


@dataclass(frozen=True)
class PoolCertificate:
    base: str
    action: str
    min_ilvl: int
    max_ilvl: int
    modifier_ids: tuple[str, ...]
    evidence: Evidence


@dataclass
class Dataset:
    domain: str
    version: str
    league: str
    bases: dict[str, Base]
    modifiers: dict[str, Modifier]
    actions: dict[str, Action]
    pools: tuple[PoolCertificate, ...]
    flag_rules: dict[str, FlagRule] | None = field(default=None, metadata={"omit_none": True})

    def __post_init__(self):
        require(self.domain in {"SYNTHETIC", "POE2"}, "WRONG_GAME", self.domain, "INVALID")
        require(bool(self.version and self.league), "MISSING_SCOPE", "version/league required", "INVALID")
        self.validate_structure()

    def validate_structure(self):
        def sequence(value, label, nullable=False):
            if nullable and value is None:
                return
            require(isinstance(value, (list, tuple)) and all(isinstance(v, str) and v for v in value),
                    "INVALID_COLLECTION", label, "INVALID")
            require(len(value) == len(set(value)), "DUPLICATE_COLLECTION_ENTRY", label, "INVALID")
        for mid, m in self.modifiers.items():
            require(mid == m.id and bool(mid), "INVALID_RECORD_ID", mid, "INVALID")
            require(m.side in {None, "prefix", "suffix"}, "INVALID_AFFIX_SIDE", mid, "INVALID")
            for name in ("tier", "ilvl", "weight"):
                value = getattr(m, name)
                require(value is None or (type(value) is int and value >= (0 if name == "weight" else 1)),
                        "INVALID_MODIFIER_NUMBER", f"{mid}.{name}", "INVALID")
            for name in ("bases", "classes", "tags", "conflicts"):
                sequence(getattr(m, name), f"{mid}.{name}", True)
        for fid, rule in (self.flag_rules or {}).items():
            require(fid == rule.id and bool(fid), "INVALID_RECORD_ID", fid, "INVALID")
            require(rule.permanent is None or type(rule.permanent) is bool, "INVALID_FLAG_RULE", fid, "INVALID")
            require(rule.occupied_sockets is None or (type(rule.occupied_sockets) is int and rule.occupied_sockets >= 0),
                    "INVALID_FLAG_RULE", fid, "INVALID")
            if rule.capacity_delta is not None:
                require(set(rule.capacity_delta) <= {"prefix", "suffix"} and all(type(v) is int for v in rule.capacity_delta.values()),
                        "INVALID_FLAG_RULE", fid, "INVALID")
            for name in ("incompatible_flags", "forbidden_actions", "forbidden_operations"):
                sequence(getattr(rule, name), f"{fid}.{name}", True)
        for aid, a in self.actions.items():
            require(a.irreversible is None or type(a.irreversible) is bool, "INVALID_COMMITMENT", aid, "INVALID")
            require(a.socket_delta is None or type(a.socket_delta) is int, "INVALID_SOCKET_DELTA", aid, "INVALID")
            require(aid == a.id and bool(aid), "INVALID_RECORD_ID", aid, "INVALID")
            for name in ("rarities", "pool_tags", "require_mods", "forbid_mods", "require_flags",
                         "forbid_flags", "set_flags", "clear_flags", "known_flags"):
                sequence(getattr(a, name), f"{aid}.{name}")
            require(isinstance(a.resources, dict), "INVALID_RESOURCES", aid, "INVALID")
            for resource, quantity in a.resources.items():
                require(isinstance(resource, str) and bool(resource) and rational(quantity) >= 0,
                        "INVALID_RESOURCE", aid, "INVALID")
        for p in self.pools:
            sequence(p.modifier_ids, f"{p.action}.modifier_ids")
            require(type(p.min_ilvl) is int and type(p.max_ilvl) is int and 1 <= p.min_ilvl <= p.max_ilvl,
                    "INVALID_CERTIFICATE_SCOPE", p.action, "INVALID")

    def verify(self, evidence):
        evidence.verify(self.domain, self.version, self.league)

    @property
    def key(self):
        return digest(self)

    @classmethod
    def load(cls, data):
        def records(name, typ):
            result = {}
            for raw in data.get(name, []):
                raw = dict(raw)
                raw["evidence"] = Evidence(**raw["evidence"])
                record = typ(**raw)
                require(record.id not in result, "CONFLICTING_RECORD", f"{name}: {record.id}", "INVALID")
                result[record.id] = record
            return result
        pools = []
        for raw in data.get("pools", []):
            raw = dict(raw)
            raw["evidence"] = Evidence(**raw["evidence"])
            pools.append(PoolCertificate(**raw))
        return cls(data["domain"], data["version"], data["league"], records("bases", Base),
                   records("modifiers", Modifier), records("actions", Action), tuple(pools),
                   records("flag_rules", FlagRule) if "flag_rules" in data else None)


def dataset_document(data):
    return {"domain": data.domain, "version": data.version, "league": data.league,
            "bases": jsonable(list(data.bases.values())), "modifiers": jsonable(list(data.modifiers.values())),
            "actions": jsonable(list(data.actions.values())), "pools": jsonable(data.pools),
            **({"flag_rules": jsonable(list(data.flag_rules.values()))} if data.flag_rules is not None else {})}
