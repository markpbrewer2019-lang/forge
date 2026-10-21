"""Planner intentions are constraints, not magical physical item protections."""
from dataclasses import dataclass, field

from .model import require


@dataclass(frozen=True)
class KeeperPolicy:
    initial: tuple[str, ...] = ()
    lock_on_acquire: bool = True
    max_fallback_rungs: int = 0
    restart_actions: tuple[str, ...] = ()
    allow_initial_loss_on_restart: bool = False
    lifecycle: list[dict] | None = field(default=None, metadata={"omit_none": True})

    @classmethod
    def load(cls, raw=None):
        raw = raw or {}
        require(set(raw) <= set(cls.__dataclass_fields__), "UNKNOWN_KEEPER_CONSTRAINT", str(raw), "INVALID")
        result = cls(**raw)
        for name in ("initial", "restart_actions"):
            value = getattr(result, name)
            require(isinstance(value, (list, tuple)) and all(isinstance(v, str) and v for v in value)
                    and len(value) == len(set(value)), "INVALID_KEEPER_CONSTRAINT", name, "INVALID")
        require(type(result.lock_on_acquire) is bool and type(result.allow_initial_loss_on_restart) is bool
                and type(result.max_fallback_rungs) is int and 0 <= result.max_fallback_rungs <= 1,
                "INVALID_KEEPER_CONSTRAINT", "Only zero or controlled one-rung fallback is supported", "INVALID")
        require(result.lifecycle is None or isinstance(result.lifecycle, (list, tuple)),
                "INVALID_LIFECYCLE", str(result.lifecycle), "INVALID")
        seen = set()
        for obligation in result.lifecycle or []:
            require(isinstance(obligation, dict) and set(obligation) <= {"modifier", "role", "release_mods", "release_flags",
                    "forbidden_actions", "forbidden_operations", "removal_actions", "replacement_mods"},
                    "INVALID_LIFECYCLE", str(obligation), "INVALID")
            require(obligation.get("role") in {"FINAL_KEEPER", "ACTIVE_BLOCKER", "TEMP_SETUP", "DISPOSABLE", "TARGETED_VICTIM"}
                    and isinstance(obligation.get("modifier"), str) and bool(obligation["modifier"])
                    and obligation["modifier"] not in seen, "INVALID_LIFECYCLE", str(obligation), "INVALID")
            seen.add(obligation["modifier"])
            for name in set(obligation) - {"modifier", "role"}:
                value = obligation[name]
                require(isinstance(value, (list, tuple)) and all(isinstance(v, str) and v for v in value),
                        "INVALID_LIFECYCLE", name, "INVALID")
        return result

    def validate_start(self, start, targets):
        require(set(self.initial) <= set(start.mods), "MISSING_INITIAL_KEEPER", str(self.initial), "INVALID")
        require(set(self.initial) <= set(targets), "KEEPER_TARGET_CONFLICT", str(self.initial), "INVALID")
        for rule in self.lifecycle or []:
            if rule["role"] == "FINAL_KEEPER":
                require(rule["modifier"] in targets, "KEEPER_TARGET_CONFLICT", rule["modifier"], "INVALID")

    def lifecycle_check(self, before, after, action, removed=()):
        for rule in self.lifecycle or []:
            mid = rule["modifier"]
            if mid not in before.mods:
                continue
            release_declared = bool(rule.get("release_mods") or rule.get("release_flags"))
            released = release_declared and set(rule.get("release_mods", ())) <= set(before.mods) and set(rule.get("release_flags", ())) <= set(before.flags)
            active = not released
            if active:
                require(action.id not in rule.get("forbidden_actions", ()) and action.operation not in rule.get("forbidden_operations", ()),
                        "LIFECYCLE_FORBIDDEN_ACTION", mid, "INVALID")
            if mid in after.mods and mid not in removed:
                continue
            require(rule["role"] != "FINAL_KEEPER" and not (active and rule["role"] in {"ACTIVE_BLOCKER", "TEMP_SETUP"}),
                    "LIFECYCLE_PREMATURE_REMOVAL", mid, "INVALID")
            if rule.get("removal_actions") or rule["role"] == "TARGETED_VICTIM":
                require(action.id in rule.get("removal_actions", ()), "LIFECYCLE_REMOVAL_ACTION", mid, "INVALID")
            if rule.get("replacement_mods"):
                require(set(rule["replacement_mods"]) <= set(after.mods), "LIFECYCLE_REPLACEMENT_REQUIRED", mid, "INVALID")

    def keepers(self, item, targets):
        return set(self.initial) | (set(item.mods) & set(targets) if self.lock_on_acquire else set())

    def classify(self, before, after, targets, action, terminal=None, removed=()):
        self.lifecycle_check(before, after, action, removed)
        restart = action.id in self.restart_actions
        if restart:
            require(action.operation == "reset", "UNPROVEN_RESTART", action.id, "INVALID")
        keepers = self.keepers(before, targets)
        lost = sorted((keepers - set(after.mods)) | (keepers & set(removed)))
        initial_lost = (set(self.initial) - set(after.mods)) | (set(self.initial) & set(removed))
        if restart:
            require(not initial_lost or self.allow_initial_loss_on_restart,
                    "INITIAL_KEEPER_LOSS", str(sorted(initial_lost)), "INVALID")
            return "RESTART", lost
        require(not initial_lost, "INITIAL_KEEPER_LOSS", str(sorted(initial_lost)), "INVALID")
        require(not (self.lock_on_acquire and lost), "EARNED_KEEPER_LOSS", str(lost), "INVALID")
        delta = len(set(after.mods) & set(targets)) - len(set(before.mods) & set(targets))
        require(delta >= -self.max_fallback_rungs, "UNCONTROLLED_REGRESSION", str(delta), "INVALID")
        if terminal == "settle":
            return "ACCEPT_SETTLE", lost
        if delta > 0:
            return "ADVANCE", lost
        return ("FALLBACK_ONE_RUNG" if delta < 0 else "RETRY_SAME_RUNG"), lost
