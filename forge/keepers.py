"""Planner intentions are constraints, not magical physical item protections."""
from dataclasses import dataclass

from .model import require


@dataclass(frozen=True)
class KeeperPolicy:
    initial: tuple[str, ...] = ()
    lock_on_acquire: bool = True
    max_fallback_rungs: int = 0
    restart_actions: tuple[str, ...] = ()
    allow_initial_loss_on_restart: bool = False

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
        return result

    def validate_start(self, start, targets):
        require(set(self.initial) <= set(start.mods), "MISSING_INITIAL_KEEPER", str(self.initial), "INVALID")
        require(set(self.initial) <= set(targets), "KEEPER_TARGET_CONFLICT", str(self.initial), "INVALID")

    def keepers(self, item, targets):
        return set(self.initial) | (set(item.mods) & set(targets) if self.lock_on_acquire else set())

    def classify(self, before, after, targets, action, terminal=None):
        restart = action.id in self.restart_actions
        if restart:
            require(action.operation == "reset", "UNPROVEN_RESTART", action.id, "INVALID")
        keepers = self.keepers(before, targets)
        lost = sorted(keepers - set(after.mods))
        initial_lost = set(self.initial) - set(after.mods)
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
