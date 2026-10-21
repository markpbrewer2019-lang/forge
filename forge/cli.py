import argparse
import json
from pathlib import Path
import sys

from .model import Dataset, ForgeError, Item, jsonable, dataset_document
from .engine import Engine, explain
from .routes import replay, validate_route, golden6
from .economics import PriceBook, price_route, simulate, compare_routes
from .data import coverage, ingest_local, normalize_ninja_exchange
from .planner import plan_ladder, analyze_target
from .fixtures import universe, example_plans
from .failures import failure_tree, recover
from .regressions import store_case, run_cases


COMMANDS = ("inspect-item", "eligible-mods", "validate-action", "replay-route", "validate-route",
            "analyze-target", "plan-ladder", "calculate-probability", "simulate", "price-route",
            "compare-routes", "coverage", "future-conflicts", "explain-transition", "golden6",
            "ingest", "normalize-ninja", "demo", "failure-tree", "recover", "store-regression", "run-regressions",
            "market-leagues", "refresh-currency", "market-coverage", "currency-quote", "budget-distribution", "analyze-settle", "adversarial-test",
            "build-craft", "audit-ladder", "compile-golden6", "data-search", "data-status", "data-import",
            "catalog-build", "catalog-query", "catalog-audit", "catalog-rule")


def prices_input(request):
    if "prices_file" in request:
        payload = json.loads(Path(request["prices_file"]).read_text(encoding="utf-8-sig"))
        if "price_book" in payload and not payload["price_book"].get("source_observed_at"):
            preserved = payload.get("receipt", {}).get("observed_at")
            if preserved:
                payload["price_book"]["source_observed_at"] = preserved
        return PriceBook.load(payload.get("price_book", payload))
    return PriceBook.load(request["prices"])


def dispatch(command, request):
    if command.startswith('catalog-') or (command == 'build-craft' and 'dataset' not in request):
        from .source_store import SourceStore
        from .catalog import Catalog
        catalog = Catalog(SourceStore(request.get('directory', 'local-data/sources')))
        if command == 'catalog-build':
            return catalog.rebuild()
        if command == 'catalog-query':
            return catalog.query(**request.get('filters', {}))
        if command == 'catalog-audit':
            return catalog.audit()
        if command == 'catalog-rule':
            return catalog.property_rule(request['record_id'])
        return catalog.resolve_craft(request)
    if command in {'data-search', 'data-status', 'data-import'}:
        from .source_store import SourceStore
        store = SourceStore(request.get('directory', 'local-data/sources'))
        if command == 'data-search':
            return store.search(request['query'], source=request.get('source'), limit=request.get('limit', 20))
        if command == 'data-status':
            return store.coverage()
        raw = Path(request['file']).read_bytes()
        if request['source'] == 'poe.ninja':
            return store.put_market(json.loads(raw))
        if request['source'] == 'poe2db':
            return store.put_poe2db(request['url'], raw, retrieved_at=request['retrieved_at'],
                                   version=request.get('version', 'UNKNOWN'))
        raise ForgeError('UNKNOWN_DATA_SOURCE', request['source'], 'INVALID')
    if command in {"market-leagues", "refresh-currency", "market-coverage", "currency-quote"}:
        from .market import NinjaClient, market_coverage, currency_quote
        if command == "market-coverage":
            return market_coverage(prices_input(request))
        if command == "currency-quote":
            return currency_quote(prices_input(request), request["currency_id"])
        client = NinjaClient(request["cache_dir"], **request.get("client_options", {}))
        if command == "market-leagues":
            return client.leagues()
        return client.currency(request["league"], request["version"], request.get("category", "Currency"))
    if command == "store-regression":
        return store_case(request["case"], request["directory"])
    if command == "run-regressions":
        return run_cases(request["directory"])
    if command == "ingest":
        return ingest_local(request["source"], request["destination"])
    if command == "normalize-ninja":
        return normalize_ninja_exchange(request["raw"], **request["context"])
    if command == "demo":
        data, prices, start = universe()
        engine = Engine(data)
        plans = example_plans(data, start)
        comparison = compare_routes(engine, plans, prices)
        planning = plan_ladder(engine, start, ["power", "speed"], prices, base_resource="base")
        return {"warning": "SYNTHETIC ONLY. No real PoE2 claims.", "coverage": coverage(data),
                "comparison": comparison, "planner": {k: v for k, v in planning.items() if k != "candidates"},
                "simulation": simulate(engine, plans["C-recovery-loop"], prices,
                                       trials=request.get("trials", 20000), seed=42),
                "dataset": dataset_document(data), "plans": plans, "prices": jsonable(prices)}
    data = Dataset.load(request["dataset"])
    engine = Engine(data)
    if command == "build-craft":
        from .pipeline import build_craft
        return build_craft(engine, Item.load(request["item"]), request["target"], prices_input(request), **request.get("options", {}))
    if command in {"audit-ladder", "compile-golden6"}:
        from .ladder import audit_ladder, compile_golden6
        function = audit_ladder if command == "audit-ladder" else compile_golden6
        return function(engine, request["plan"], prices_input(request), **request.get("options", {}))
    if command == "adversarial-test":
        from .adversarial import adversarial_test
        return adversarial_test(engine, request["plan"])
    if command == "budget-distribution":
        from .distributions import budget_distribution
        return budget_distribution(engine, request["plan"], prices_input(request),
                                   request["budget"], **request.get("options", {}))
    if command == "analyze-settle":
        from .settles import analyze_settle
        return analyze_settle(engine, Item.load(request["item"]), request["required_modifiers"],
                              prices_input(request), request["continuation_plan"],
                              request["remaining_budget"], **request.get("options", {}))
    if command == "failure-tree":
        return failure_tree(engine, request["plan"])
    if command == "recover":
        return recover(engine, Item.load(request["item"]), request["target"], prices_input(request),
                       request.get("restart_plan"), **request.get("options", {}))
    if command == "coverage":
        return coverage(data)
    if command == "validate-route":
        return validate_route(engine, request["plan"])
    if command == "replay-route":
        r = replay(engine, request["plan"])
        return {"status": "VALIDATED", "fingerprint": r.fingerprint, "trace": r.trace,
                "states": {"|".join(k): v for k, v in r.states.items()},
                "terminals": {"|".join(k): v for k, v in r.terminals.items()}}
    if command in {"simulate", "price-route", "compare-routes", "plan-ladder", "golden6"}:
        prices = prices_input(request)
        options = request.get("options", {})
        if command == "simulate":
            return simulate(engine, request["plan"], prices, **options)
        if command == "price-route":
            return price_route(engine, request["plan"], prices, **options)
        if command == "compare-routes":
            return compare_routes(engine, request["plans"], prices, **options)
        if command == "golden6":
            return golden6(engine, request["plan"], prices)
        return plan_ladder(engine, Item.load(request["item"]), request["target"], prices, **options)
    item = Item.load(request["item"])
    if command == "inspect-item":
        return engine.inspect(item)
    if command == "eligible-mods":
        return engine.pool(item, request["action"])
    if command == "validate-action":
        return engine.legality(item, request["action"])
    if command == "calculate-probability":
        return {"probability": engine.probability(item, request["action"], request["target"])}
    if command == "analyze-target":
        return analyze_target(engine, item, request["modifier"])
    if command == "future-conflicts":
        return engine.future_conflicts(item, request["target"])
    if command == "explain-transition":
        after = Item.load(request["after"])
        outcomes = engine.transition(item, request["action"])
        if not any(o.state == after for o in outcomes):
            raise ForgeError("IMPOSSIBLE_AFTER_STATE", "Action does not produce supplied state", "INVALID")
        return explain(item, after, engine)
    raise ForgeError("UNKNOWN_COMMAND", command, "INVALID")


def main():
    parser = argparse.ArgumentParser(description="Forge crafting correctness harness; JSON input/output")
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("--input", help="JSON request file; otherwise reads stdin (demo needs no input)")
    parser.add_argument("--output", help="Write JSON report to file")
    args = parser.parse_args()
    try:
        request = json.loads(Path(args.input).read_text(encoding="utf-8-sig")) if args.input else (
            {} if args.command == "demo" else json.load(sys.stdin))
        result = dispatch(args.command, request)
    except ForgeError as exc:
        result = exc.report()
    except (KeyError, TypeError, ValueError, OSError) as exc:
        result = {"status": "INVALID", "code": "MALFORMED_INPUT", "detail": str(exc)}
    rendered = json.dumps(jsonable(result), indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 2 if result.get("status") in {"INVALID", "BLOCKED", "PARTIALLY_VALIDATED"} else 0
