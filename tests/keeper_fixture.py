"""Six-mod synthetic contract universe, not a recipe or PoE2 mechanic claim."""
from dataclasses import replace

from forge.fixtures import universe
from forge.model import Action, Modifier, PoolCertificate, Item


def six_mod_universe():
    data, prices, start = universe()
    ev = replace(next(iter(data.actions.values())).evidence, category="MATHEMATICAL_ASSUMPTION",
                 supporting_fact="These are invented, exhaustive laboratory rules; they establish no real-game mechanic.")
    base = replace(data.bases[start.base], limits={"rare": {"prefix": 3, "suffix": 3}}, evidence=ev)
    data.bases = {base.id: base}
    for name, side in (("power2", "prefix"), ("power3", "prefix"), ("speed2", "suffix"), ("speed3", "suffix")):
        data.modifiers[name] = Modifier(name, side, 1, name, 1, 1, (base.id,), (base.item_class,), ("test",), (), ev)
    data.modifiers["junk"] = replace(data.modifiers["junk"], group="power2", evidence=ev)
    for aid, action in list(data.actions.items()):
        data.actions[aid] = replace(action, evidence=ev, display_name="Synthetic " + aid)
    # First two modifiers can be acquired in either order. Later actions form a reusable prerequisite chain.
    data.actions["roll-prefix"] = replace(data.actions["roll-prefix"], require_mods=("power", "speed"),
        forbid_mods=("power2",), display_name="Synthetic Prefix Lottery")
    data.actions["remove-prefix"] = replace(data.actions["remove-prefix"], display_name="Synthetic Uniform Removal")
    data.actions["remove-junk"] = Action("remove-junk", "remove_fixed", ev, ("rare",), {"remove-junk": 1},
        side="prefix", fixed_mod="junk", require_mods=("junk",), display_name="Synthetic Exact Junk Removal")
    for mid, prerequisite, cost in (("power2", "speed", "8"), ("power3", "power2", "1"),
                                    ("speed2", "power3", "1"), ("speed3", "speed2", "1")):
        aid = "add-" + mid
        data.actions[aid] = Action(aid, "add_fixed", ev, ("rare",), {aid: 1},
            side=data.modifiers[mid].side, fixed_mod=mid, require_mods=("power", prerequisite) if prerequisite != "power" else ("power",),
            display_name="Synthetic " + mid.title() + " Sigil")
        prices.quotes[aid] = cost
    prices.quotes["remove-junk"] = "2"
    data.pools = (PoolCertificate(base.id, "roll-prefix", 1, 100, ("power2", "junk"), ev),)
    target = ["power", "power2", "power3", "speed", "speed2", "speed3"]
    return data, prices, start, target
