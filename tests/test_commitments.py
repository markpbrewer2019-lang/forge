"""Invented mathematical rules, never evidence of real-game mechanics."""
import unittest
from dataclasses import replace

from forge.fixtures import universe
from forge.model import Action, FlagRule, ForgeError, jsonable, Dataset, dataset_document
from forge.engine import Engine
from forge.keepers import KeeperPolicy
from forge.planner import plan_ladder
from forge.routes import replay


class CommitmentTests(unittest.TestCase):
    def setUp(self):
        self.data, self.prices, self.start = universe()
        self.ev = next(iter(self.data.actions.values())).evidence
        self.data.flag_rules = {"installed": FlagRule("installed", self.ev, permanent=True,
            capacity_delta={"prefix": -1}, occupied_sockets=1, incompatible_flags=(),
            forbidden_actions=(), forbidden_operations=())}
        self.data.actions["clear"] = Action("clear", "flags", self.ev, ("rare",), {},
            clear_flags=("installed",), known_flags=("installed",))
        self.engine = Engine(self.data)

    def test_permanent_flag_cannot_be_removed(self):
        item = replace(self.start, flags=("installed",), sockets=1)
        with self.assertRaisesRegex(ForgeError, "PERMANENT_PROPERTY_REMOVAL"):
            self.engine.transition(item, "clear")

    def test_capacity_and_unknown_sockets(self):
        with self.assertRaisesRegex(ForgeError, "UNKNOWN_SOCKET_STATE"):
            self.engine.inspect(replace(self.start, flags=("installed",)))
        item = replace(self.start, flags=("installed",), sockets=1)
        self.assertEqual(0, self.engine.inspect(item)["open_slots"]["prefix"])
        with self.assertRaisesRegex(ForgeError, "AFFIX_CAPACITY_EXCEEDED"):
            self.engine.inspect(replace(item, mods=("power",)))

    def test_blocker_release_and_forbidden_action(self):
        policy = KeeperPolicy.load({"lifecycle": [{"modifier": "junk", "role": "ACTIVE_BLOCKER",
            "release_flags": ["released"], "forbidden_actions": ["clear"]}]})
        before = replace(self.start, mods=("junk",))
        after = replace(before, mods=())
        action = self.data.actions["clear"]
        with self.assertRaisesRegex(ForgeError, "LIFECYCLE_FORBIDDEN_ACTION"):
            policy.classify(before, before, ["power"], action)
        action = replace(action, id="remove")
        with self.assertRaisesRegex(ForgeError, "LIFECYCLE_PREMATURE_REMOVAL"):
            policy.classify(before, after, ["power"], action)
        policy.classify(replace(before, flags=("released",)), replace(after, flags=("released",)), ["power"], action)

    def test_unknown_property_semantics_and_replacement(self):
        self.data.flag_rules["installed"] = replace(self.data.flag_rules["installed"], capacity_delta=None)
        with self.assertRaisesRegex(ForgeError, "UNKNOWN_PROPERTY_RULE"):
            self.engine.inspect(replace(self.start, flags=("installed",), sockets=1))
        self.data.flag_rules["installed"] = replace(self.data.flag_rules["installed"], capacity_delta={})
        self.data.actions["clear"] = replace(self.data.actions["clear"], set_flags=("replacement",))
        with self.assertRaisesRegex(ForgeError, "PERMANENT_PROPERTY_REMOVAL"):
            self.engine.transition(replace(self.start, flags=("installed",), sockets=1), "clear")

    def test_flag_rule_dataset_roundtrip_and_socket_occupation(self):
        self.assertEqual(self.data.key, Dataset.load(dataset_document(self.data)).key)
        with self.assertRaisesRegex(ForgeError, "SOCKET_CAPACITY_EXCEEDED"):
            self.engine.inspect(replace(self.start, flags=("installed",), sockets=0))

    def test_search_rejects_dead_commitment_and_proves_viable_suffix(self):
        self.data.flag_rules["installed"] = replace(self.data.flag_rules["installed"], capacity_delta={})
        self.data.flag_rules["bad"] = replace(self.data.flag_rules["installed"], id="bad",
            capacity_delta={"prefix": -1}, forbidden_actions=("commit-good",))
        self.data.actions = {
            "commit-good": Action("commit-good", "flags", self.ev, ("rare",), {},
                set_flags=("installed",), forbid_flags=("installed",), known_flags=("installed", "bad")),
            "commit-bad": Action("commit-bad", "flags", self.ev, ("rare",), {},
                set_flags=("bad",), forbid_flags=("bad",), known_flags=("installed", "bad")),
            "finish": Action("finish", "add_fixed", self.ev, ("rare",), {}, fixed_mod="power",
                require_flags=("installed",), known_flags=("installed", "bad"))}
        start = replace(self.start, sockets=1)
        for optimizer in ("enumerate", "policy_iteration"):
            result = plan_ladder(self.engine, start, ["power"], self.prices, base_owned=True,
                optimizer=optimizer, target_state={"flags": ["installed"], "sockets": 1})
            self.assertIsNotNone(result["winner"], result)
            route = replay(self.engine, result["winner"]["plan"])
            self.assertEqual({"commit-good", "finish"}, set(route.actions.values()))

    def test_replay_rejects_commitment_with_failure_suffix(self):
        self.data.flag_rules["installed"] = replace(self.data.flag_rules["installed"], capacity_delta={})
        self.data.actions["roll-prefix"] = replace(self.data.actions["roll-prefix"], set_flags=("installed",))
        plan = {"schema_version": 1, "dataset_id": self.data.key,
            "starting_state": jsonable(replace(self.start, sockets=1)), "target": ["power"],
            "entry": "commit", "nodes": {
                "commit": {"objective": "Synthetic commitment", "action": "roll-prefix",
                           "branches": {"power": "win", "junk": "lose"}},
                "win": {"objective": "Exact target", "terminal": "success"},
                "lose": {"objective": "Dead suffix", "terminal": "failure"}}}
        with self.assertRaisesRegex(ForgeError, "UNPROVEN_COMMITMENT_SUFFIX"):
            replay(self.engine, plan)

    def test_search_and_replay_preserve_blocker_until_release(self):
        self.data.flag_rules = None
        self.data.actions = {
            "release": Action("release", "flags", self.ev, ("rare",), {},
                set_flags=("released",), forbid_flags=("released",), known_flags=("released",)),
            "remove": Action("remove", "remove_fixed", self.ev, ("rare",), {},
                fixed_mod="junk", known_flags=("released",)),
            "finish": Action("finish", "add_fixed", self.ev, ("rare",), {},
                fixed_mod="power", known_flags=("released",))}
        policy = {"lifecycle": [{"modifier": "junk", "role": "ACTIVE_BLOCKER", "release_flags": ["released"]}]}
        result = plan_ladder(self.engine, replace(self.start, mods=("junk",)), ["power"], self.prices,
            base_owned=True, keeper_policy=policy, optimizer="policy_iteration")
        route = replay(self.engine, result["winner"]["plan"])
        self.assertEqual(["release", "remove", "finish"], list(route.actions.values()))
        self.assertTrue(any(r["code"] == "LIFECYCLE_PREMATURE_REMOVAL" for r in result["rejected_actions"]))

    def test_physical_action_restrictions_and_socket_unknown(self):
        self.data.flag_rules["installed"] = replace(self.data.flag_rules["installed"], forbidden_operations=("flags",))
        with self.assertRaisesRegex(ForgeError, "PROPERTY_FORBIDDEN_ACTION"):
            self.engine.transition(replace(self.start, flags=("installed",), sockets=1), "clear")
        self.data.actions["socket"] = Action("socket", "flags", self.ev, ("rare",), {}, socket_delta=1)
        with self.assertRaisesRegex(ForgeError, "UNKNOWN_SOCKET_STATE"):
            self.engine.transition(self.start, "socket")

    def test_search_discovers_capacity_commitment_without_final_flag_hint(self):
        self.data.flag_rules = {"capacity": replace(self.data.flag_rules["installed"], id="capacity",
            capacity_delta={"prefix": 1})}
        self.data.actions = {
            "expand": Action("expand", "flags", self.ev, ("rare",), {}, set_flags=("capacity",),
                forbid_flags=("capacity",), known_flags=("capacity",)),
            **{mid: Action(mid, "add_fixed", self.ev, ("rare",), {}, fixed_mod=mid,
                          known_flags=("capacity",)) for mid in ("power", "junk")}}
        for optimizer in ("enumerate", "policy_iteration"):
            result = plan_ladder(self.engine, replace(self.start, sockets=1), ["power", "junk"],
                self.prices, base_owned=True, optimizer=optimizer)
            self.assertIsNotNone(result["winner"], result)
            route = replay(self.engine, result["winner"]["plan"])
            self.assertIn("expand", route.actions.values())
            self.assertTrue(all("capacity" in route.states[k].flags
                for k, terminal in route.terminals.items() if terminal == "success"))
        with self.assertRaisesRegex(ForgeError, "AFFIX_CAPACITY_EXCEEDED"):
            plan_ladder(self.engine, replace(self.start, sockets=1), ["power", "junk"],
                self.prices, base_owned=True, target_state={"flags": []})
        self.data.modifiers["junk"] = replace(self.data.modifiers["junk"], group=self.data.modifiers["power"].group)
        with self.assertRaisesRegex(ForgeError, "MODIFIER_GROUP_CONFLICT"):
            plan_ladder(self.engine, replace(self.start, sockets=1), ["power", "junk"],
                self.prices, base_owned=True)
