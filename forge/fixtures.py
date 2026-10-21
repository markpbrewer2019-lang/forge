"""Invented mechanics by definition. None of these records describe Path of Exile."""
from dataclasses import replace
from datetime import datetime, timezone

from .model import Evidence, Base, Modifier, Action, PoolCertificate, Dataset, Item, jsonable
from .economics import PriceBook


def universe():
    timestamp = datetime.now(timezone.utc).isoformat()
    ev = Evidence("Forge synthetic specification", "fixtures.py:v1", timestamp, "VERIFIED", "SYNTHETIC",
                  "fixture-v1", "laboratory", "Invented rules, established by definition, never real PoE2 evidence.")
    base = Base("test-base", "test-class", ("test",), {"rare": {"prefix": 1, "suffix": 1},
                "normal": {"prefix": 0, "suffix": 0}}, ev)
    def mod(mid, side, weight, group=None):
        return Modifier(mid, side, 1, group or mid, 1, weight, (base.id,), (base.item_class,),
                        ("test",), (), ev)
    mods = {m.id: m for m in [mod("power", "prefix", 1), mod("junk", "prefix", 1), mod("speed", "suffix", 1)]}
    def fixed(aid, mid, price, **kw):
        return Action(aid, "add_fixed", ev, ("rare",), {aid: 1}, side=mods[mid].side, fixed_mod=mid, **kw)
    actions = [fixed("power-first", "power", 1, forbid_mods=("speed",)),
               fixed("speed-first", "speed", 5, forbid_mods=("power",)),
               fixed("power-after-speed", "power", 1, require_mods=("speed",)),
               fixed("speed-after-power", "speed", 100, require_mods=("power",)),
               Action("roll-prefix", "add_pool", ev, ("rare",), {"roll-prefix": 1}, side="prefix"),
               Action("remove-prefix", "remove", ev, ("rare",), {"remove-prefix": 1}, side="prefix")]
    data = Dataset("SYNTHETIC", ev.version, ev.league, {base.id: base}, mods, {a.id: a for a in actions},
                   (PoolCertificate(base.id, "roll-prefix", 1, 100, ("power", "junk"), ev),))
    prices = PriceBook(data.domain, data.version, data.league, "test-credit", timestamp,
                       {"power-first": "1", "speed-first": "5", "power-after-speed": "1",
                        "speed-after-power": "100", "roll-prefix": "1", "remove-prefix": "2", "base": "10"}, ev)
    return data, prices, Item(base.id, 1, "rare")


def example_plans(data, start):
    common = {"schema_version": 1, "dataset_id": data.key, "starting_state": jsonable(start),
              "target": ["power", "speed"], "base_resource": "base", "entry": "first"}
    def node(action, branches, rung):
        return {"objective": "Acquire exact target without losing previous progress", "action": action,
                "branches": branches, "rung": rung}
    a = {**common, "nodes": {"first": node("power-first", {"power": "second"}, "power"),
         "second": node("speed-after-power", {"speed": "done"}, "speed"),
         "done": {"objective": "Exact target", "terminal": "success"}}}
    b = {**common, "nodes": {"first": node("speed-first", {"speed": "second"}, "speed"),
         "second": node("power-after-speed", {"power": "done"}, "power"),
         "done": {"objective": "Exact target", "terminal": "success"}}}
    loop = {**common, "nodes": {"first": node("speed-first", {"speed": "roll"}, "speed"),
         "roll": node("roll-prefix", {"power": "done", "junk": "recover"}, "power"),
         "recover": node("remove-prefix", {"junk": "roll"}, "power"),
         "done": {"objective": "Exact target", "terminal": "success"}}}
    return {"A-cheap-first": a, "B-lower-total": b, "C-recovery-loop": loop}
