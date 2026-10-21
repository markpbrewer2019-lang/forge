from dataclasses import dataclass, replace
from fractions import Fraction

from .model import ForgeError, Item, require, jsonable, rational


@dataclass(frozen=True)
class Outcome:
    label: str
    probability: Fraction
    state: Item


class Engine:
    def __init__(self, data):
        data.validate_structure()
        self.data = data

    def flag_rule(self, flag):
        rule = (self.data.flag_rules or {}).get(flag)
        require(rule is not None, "UNKNOWN_PROPERTY_RULE", flag)
        rule.evidence.verify_mechanic(self.data.domain, self.data.version, self.data.league)
        for name in ("permanent", "capacity_delta", "incompatible_flags", "forbidden_actions",
                     "forbidden_operations", "occupied_sockets"):
            require(getattr(rule, name) is not None, "UNKNOWN_PROPERTY_RULE", f"{flag}.{name}")
        return rule

    def physical_rules(self, item):
        # Legacy datasets retain their existing action-specific known_flags gate.
        return [self.flag_rule(flag) for flag in item.flags] if self.data.flag_rules is not None else []

    def is_commitment(self, before, after, action_id=None):
        if action_id is not None and self.action(action_id).irreversible:
            return True
        return (after.sockets != before.sockets or any(self.flag_rule(f).permanent or self.flag_rule(f).occupied_sockets
                for f in set(after.flags) - set(before.flags))) if self.data.flag_rules is not None else after.sockets != before.sockets

    def modifier(self, mod_id):
        require(mod_id in self.data.modifiers, "UNKNOWN_MODIFIER", mod_id)
        m = self.data.modifiers[mod_id]
        m.evidence.verify_state_fact(self.data.domain, self.data.version, self.data.league)
        for name in ("side", "tier", "group", "ilvl", "bases", "classes", "tags", "conflicts"):
            require(getattr(m, name) is not None, "INSUFFICIENT_VERIFIED_DATA", f"{mod_id}.{name}")
        require(m.side in ("prefix", "suffix") and type(m.tier) is int and m.tier >= 1
                and type(m.ilvl) is int and m.ilvl >= 1 and bool(m.group),
                "INVALID_MODIFIER", mod_id, "INVALID")
        return m

    def base(self, item):
        require(item.base in self.data.bases, "UNSUPPORTED_BASE", item.base)
        base = self.data.bases[item.base]
        base.evidence.verify_state_fact(self.data.domain, self.data.version, self.data.league)
        require(item.rarity in base.limits, "UNKNOWN_RARITY_LIMITS", item.rarity)
        limits = base.limits[item.rarity]
        require(set(limits) == {"prefix", "suffix"} and all(type(v) is int and v >= 0 for v in limits.values()),
                "INVALID_LIMITS", base.id, "INVALID")
        return base

    def inspect(self, item):
        base = self.base(item)
        rules = self.physical_rules(item)
        for rule in rules:
            require(not set(rule.incompatible_flags) & set(item.flags), "INCOMPATIBLE_PROPERTIES", rule.id, "INVALID")
        occupied = sum(rule.occupied_sockets for rule in rules)
        if occupied:
            require(item.sockets is not None, "UNKNOWN_SOCKET_STATE", item.base)
            require(occupied <= item.sockets, "SOCKET_CAPACITY_EXCEEDED", str(occupied), "INVALID")
        mods = [self.modifier(mid) for mid in item.mods]
        require(set(item.fractured) <= set(item.mods) and set(item.protected) <= set(item.mods),
                "INVALID_PROTECTION", "Protected/fractured modifier absent", "INVALID")
        for m in mods:
            require(item.ilvl >= m.ilvl, "MODIFIER_ILVL_REQUIREMENT_NOT_MET", m.id, "INVALID")
            require(item.base in m.bases and base.item_class in m.classes,
                    "MODIFIER_NOT_APPLICABLE", m.id, "INVALID")
        for i, m in enumerate(mods):
            for other in mods[i + 1:]:
                require(m.group != other.group and other.id not in m.conflicts and m.id not in other.conflicts,
                        "MODIFIER_GROUP_CONFLICT", f"{m.id} / {other.id}", "INVALID")
        opened = {side: base.limits[item.rarity][side] + sum(r.capacity_delta.get(side, 0) for r in rules) - sum(m.side == side for m in mods)
                  for side in ("prefix", "suffix")}
        require(all(v >= 0 for v in opened.values()), "AFFIX_CAPACITY_EXCEEDED", str(opened), "INVALID")
        return {"state": jsonable(item), "state_id": item.key, "item_class": base.item_class,
                "base_tags": base.tags, "modifiers": [dict(jsonable(m), fractured=m.id in item.fractured,
                protected=m.id in item.protected) for m in mods], "open_slots": opened}

    def action(self, action_id):
        require(action_id in self.data.actions, "UNVERIFIED_MECHANIC", action_id)
        action = self.data.actions[action_id]
        action.evidence.verify_mechanic(self.data.domain, self.data.version, self.data.league)
        require(action.operation in {"add_pool", "add_fixed", "remove", "remove_fixed", "reset", "flags"},
                "UNSUPPORTED_MECHANIC", action.operation)
        if action.mechanic_context:
            context = action.mechanic_context
            require(not context.get("special_pool"), "UNSUPPORTED_SPECIAL_POOL", str(context.get("special_pool")))
            if context.get("omens") or context.get("essence"):
                from .model import Evidence
                require(bool(context.get("interaction_evidence")), "UNKNOWN_INTERACTION", action.id)
                Evidence(**context["interaction_evidence"]).verify_mechanic(self.data.domain, self.data.version, self.data.league)
        require(action.side in {None, "prefix", "suffix"}, "INVALID_ACTION", action.id, "INVALID")
        for resource, quantity in action.resources.items():
            require(bool(resource) and rational(quantity) >= 0, "INVALID_RESOURCE", action.id, "INVALID")
        return action

    def transition_provenance(self, item, action_id):
        action = self.action(action_id)
        evidence = {"mechanic": action.evidence.provenance(),
                    "base": self.base(item).evidence.provenance(),
                    "existing_modifiers": {mid: self.modifier(mid).evidence.provenance() for mid in item.mods}}
        if self.data.flag_rules is not None:
            evidence["physical_properties"] = {flag: self.flag_rule(flag).evidence.provenance()
                for flag in sorted(set(item.flags) | set(action.set_flags))}
        if action.operation == "add_pool":
            pool = self.pool(item, action_id)
            certificate = next(p for p in self.data.pools if p.base == item.base and p.action == action_id
                               and p.min_ilvl <= item.ilvl <= p.max_ilvl)
            evidence["pool_completeness"] = certificate.evidence.provenance()
            evidence["eligible_modifiers"] = {m["modifier"]: self.modifier(m["modifier"]).evidence.provenance()
                                               for m in pool["eligible"]}
            evidence["probability_rule"] = {"category": "MATHEMATICAL_ASSUMPTION",
                "supporting_fact": "Normalize the verified eligible source weights; this arithmetic does not establish the mechanic."}
        elif action.operation == "add_fixed":
            evidence["added_modifier"] = self.modifier(action.fixed_mod).evidence.provenance()
        elif action.operation in {"remove", "remove_fixed"}:
            evidence["probability_rule"] = {"category": "MATHEMATICAL_ASSUMPTION",
                "supporting_fact": "Selection follows the declared uniform or exact-victim removal rule; mechanic evidence must establish applicability."}
        if action.mechanic_context and action.mechanic_context.get("interaction_evidence"):
            from .model import Evidence
            evidence["interaction"] = Evidence(**action.mechanic_context["interaction_evidence"]).provenance()
        return evidence

    def excluded(self, item, action, modifier):
        m, base = modifier, self.base(item)
        reasons = []
        if item.ilvl < m.ilvl:
            reasons.append("MODIFIER_ILVL_REQUIREMENT_NOT_MET")
        if item.base not in m.bases or base.item_class not in m.classes:
            reasons.append("BASE_OR_CLASS_RESTRICTION")
        if action.side and m.side != action.side:
            reasons.append("AFFIX_SIDE_RESTRICTION")
        if action.pool_tags and not set(action.pool_tags) <= set(m.tags):
            reasons.append("ACTION_TAG_RESTRICTION")
        if m.id in item.mods:
            reasons.append("ALREADY_PRESENT")
        for existing_id in item.mods:
            existing = self.modifier(existing_id)
            if m.group == existing.group or existing.id in m.conflicts or m.id in existing.conflicts:
                reasons.append("MODIFIER_GROUP_CONFLICT")
        if self.inspect(item)["open_slots"][m.side] == 0:
            reasons.append("NO_OPEN_" + m.side.upper())
        return sorted(set(reasons))

    def pool(self, item, action_id):
        self.inspect(item)
        action = self.action(action_id)
        require(action.operation == "add_pool", "NOT_POOL_ACTION", action_id, "INVALID")
        certificates = [p for p in self.data.pools if p.base == item.base and p.action == action_id
                        and p.min_ilvl <= item.ilvl <= p.max_ilvl]
        require(len(certificates) == 1, "INSUFFICIENT_VERIFIED_DATA",
                "Exactly one complete pool certificate required for base/action/ilvl")
        cert = certificates[0]
        cert.evidence.verify_state_fact(self.data.domain, self.data.version, self.data.league)
        require(len(cert.modifier_ids) == len(set(cert.modifier_ids)), "INVALID_POOL_CERTIFICATE", action_id, "INVALID")
        # Certificate is an explicit external assertion of completeness, not an inference from loaded rows.
        eligible, excluded, missing = [], {}, []
        for mid in cert.modifier_ids:
            m = self.modifier(mid)
            reasons = self.excluded(item, action, m)
            if reasons:
                excluded[mid] = reasons
                continue
            if m.weight is None:
                missing.append(mid)
                continue
            require(type(m.weight) is int and m.weight >= 0, "INVALID_WEIGHT", mid, "INVALID")
            if m.weight == 0:
                excluded[mid] = ["ZERO_WEIGHT"]
            else:
                eligible.append({"modifier": mid, "weight": m.weight})
        require(not missing, "INSUFFICIENT_VERIFIED_DATA", f"Missing eligible weights: {missing}")
        return {"eligible": eligible, "excluded": excluded, "total_weight": sum(m["weight"] for m in eligible),
                "certificate": jsonable(cert)}

    def legality(self, item, action_id):
        info = self.inspect(item)
        action = self.action(action_id)
        for rule in self.physical_rules(item):
            require(action.id not in rule.forbidden_actions and action.operation not in rule.forbidden_operations,
                    "PROPERTY_FORBIDDEN_ACTION", {"flag": rule.id, "action": action.id}, "INVALID")
            require(not ((rule.permanent or rule.occupied_sockets) and rule.id in action.clear_flags),
                    "PERMANENT_PROPERTY_REMOVAL", rule.id, "INVALID")
        if self.data.flag_rules is not None:
            for flag in action.set_flags:
                self.flag_rule(flag)
        if action.socket_delta is not None:
            require(item.sockets is not None, "UNKNOWN_SOCKET_STATE", item.base)
            require(item.sockets + action.socket_delta >= 0, "SOCKET_CAPACITY_EXCEEDED", action.id, "INVALID")
        require(set(item.flags) <= set(action.known_flags), "UNKNOWN_INTERACTION",
                {"action": action_id, "unhandled_flags": sorted(set(item.flags) - set(action.known_flags))})
        require(item.rarity in action.rarities, "WRONG_ITEM_RARITY", action_id, "INVALID")
        require(set(action.require_mods) <= set(item.mods) and not set(action.forbid_mods) & set(item.mods)
                and set(action.require_flags) <= set(item.flags) and not set(action.forbid_flags) & set(item.flags),
                "ACTION_REQUIREMENT_NOT_SATISFIED", action_id, "INVALID")
        if action.operation in {"add_fixed", "add_pool"} and action.side:
            require(info["open_slots"][action.side] > 0, "NO_OPEN_" + action.side.upper(), action_id, "INVALID")
        if action.operation == "add_fixed":
            m = self.modifier(action.fixed_mod)
            reasons = self.excluded(item, action, m)
            require(not reasons, reasons[0] if reasons else "", str(reasons), "INVALID")
        if action.operation in {"remove", "remove_fixed"}:
            if action.operation == "remove_fixed":
                require(bool(action.fixed_mod), "MISSING_DETERMINISTIC_VICTIM", action_id, "INVALID")
            require(bool(self.removable(item, action)), "NO_ELIGIBLE_REMOVAL", action_id, "INVALID")
        if action.operation == "reset":
            require(not item.fractured and not item.protected, "UNKNOWN_INTERACTION", "Reset with protections unsupported")
        if action.operation == "add_pool":
            require(self.pool(item, action_id)["total_weight"] > 0, "EMPTY_POOL", action_id, "INVALID")
        return {"status": "VALIDATED", "action": action_id, "state_id": item.key}

    def removable(self, item, action):
        return [mid for mid in item.mods if mid not in item.fractured and mid not in item.protected
                and (action.operation != "remove_fixed" or mid == action.fixed_mod)
                and (action.side is None or self.modifier(mid).side == action.side)]

    def transition(self, item, action_id):
        self.legality(item, action_id)
        a = self.action(action_id)
        common = {"flags": tuple((set(item.flags) - set(a.clear_flags)) | set(a.set_flags)),
                  "rarity": a.resulting_rarity or item.rarity}
        if a.socket_delta is not None:
            common["sockets"] = item.sockets + a.socket_delta
        outcomes = []
        if a.operation == "add_pool":
            pool = self.pool(item, action_id)
            for m in pool["eligible"]:
                outcomes.append(Outcome(m["modifier"], Fraction(m["weight"], pool["total_weight"]),
                                        replace(item, mods=item.mods + (m["modifier"],), **common)))
        elif a.operation == "add_fixed":
            outcomes.append(Outcome(a.fixed_mod, Fraction(1), replace(item, mods=item.mods + (a.fixed_mod,), **common)))
        elif a.operation in {"remove", "remove_fixed"}:
            removable = self.removable(item, a)
            for mid in removable:
                outcomes.append(Outcome(mid, Fraction(1, len(removable)),
                                        replace(item, mods=tuple(m for m in item.mods if m != mid), **common)))
        elif a.operation == "reset":
            outcomes.append(Outcome("reset", Fraction(1), replace(item, mods=(), **common)))
        else:
            outcomes.append(Outcome("flags", Fraction(1), replace(item, **common)))
        for outcome in outcomes:
            self.inspect(outcome.state)
        require(sum(o.probability for o in outcomes) == 1, "INVALID_DISTRIBUTION", action_id, "INVALID")
        return tuple(outcomes)

    def probability(self, item, action_id, targets):
        outcomes = self.transition(item, action_id)
        return sum((o.probability for o in outcomes if set(targets) <= set(o.state.mods)), Fraction())

    def future_conflicts(self, item, targets):
        self.inspect(item)
        target_mods = [self.modifier(mid) for mid in targets]
        reasons = []
        for m in target_mods:
            if m.id in item.mods:
                continue
            if item.ilvl < m.ilvl:
                reasons.append({"modifier": m.id, "reason": "ILVL_UNREACHABLE_WITH_CURRENT_BASE"})
            for existing in item.mods:
                other = self.modifier(existing)
                if m.group == other.group or m.id in other.conflicts or other.id in m.conflicts:
                    reasons.append({"modifier": m.id, "reason": "CONFLICT_REQUIRES_REMOVAL", "existing": existing,
                                    "protected": existing in item.protected or existing in item.fractured})
        opened = self.inspect(item)["open_slots"]
        for side in ("prefix", "suffix"):
            needed = sum(m.side == side and m.id not in item.mods for m in target_mods)
            if needed > opened[side]:
                reasons.append({"reason": "FUTURE_SLOT_DEFICIT", "side": side, "needed": needed, "open": opened[side]})
        return {"state_id": item.key, "issues": reasons,
                "note": "Structural warnings; route replay proves whether removal/recovery resolves them."}


def explain(before, after, engine):
    b, a = engine.inspect(before), engine.inspect(after)
    added, removed = sorted(set(after.mods) - set(before.mods)), sorted(set(before.mods) - set(after.mods))
    changes = {name: {"before": getattr(before, name), "after": getattr(after, name)}
               for name in ("base", "ilvl", "rarity", "quality", "fractured", "protected", "flags", "sockets")
               if getattr(before, name) != getattr(after, name)}
    return {"added": added, "removed": removed, "preserved": sorted(set(before.mods) & set(after.mods)),
            "open_slots": {side: [b["open_slots"][side], a["open_slots"][side]] for side in ("prefix", "suffix")},
            "changes": changes, "human": f"Added {added}; removed {removed}; slots {b['open_slots']} -> {a['open_slots']}"}
