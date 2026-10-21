from dataclasses import dataclass, field
from datetime import datetime, timezone
from fractions import Fraction
import math
import random
from collections import Counter

from .model import Evidence, require, rational
from .routes import replay


@dataclass
class PriceBook:
    domain: str
    version: str
    league: str
    unit: str
    as_of: str
    quotes: dict
    evidence: Evidence
    # Freshness is a caller decision, explicit and reproducible via valuation_at.
    max_age_seconds: int = 86400
    source_snapshot: dict | None = None
    snapshot_sha256: str | None = None
    source_observed_at: str | None = field(default=None, metadata={"omit_none": True})

    @classmethod
    def load(cls, data):
        data = dict(data)
        if "books" in data:
            require(set(data) == {"books"}, "INVALID_COMPOSITE_PRICE_BOOK", "Only books may be supplied", "INVALID")
            return CompositePriceBook([cls.load(book) for book in data["books"]])
        data["evidence"] = Evidence(**data["evidence"])
        return cls(**data)

    def verify(self, engine, valuation_at=None):
        data = engine.data
        require((self.domain, self.version, self.league) == (data.domain, data.version, data.league),
                "PRICE_SCOPE_MISMATCH", "Prices must match dataset")
        if self.domain == "POE2":
            from .currency_source import validate_currency_source
            from .data import normalize_ninja_exchange
            from .model import digest
            require(self.evidence.source == "poe.ninja", "CURRENCY_SOURCE_REQUIRED",
                    "Real currency data must come exclusively from the poe.ninja PoE2 API")
            validate_currency_source(self.evidence.reference, self.league)
            require(bool(self.source_observed_at), "CURRENCY_OBSERVATION_TIME_REQUIRED",
                    "A preserved source observation timestamp is required, not a mutable valuation timestamp")
            observed = datetime.fromisoformat(self.source_observed_at.replace("Z", "+00:00"))
            claimed = datetime.fromisoformat(self.as_of.replace("Z", "+00:00"))
            retrieved = datetime.fromisoformat(self.evidence.retrieved_at.replace("Z", "+00:00"))
            require(observed.tzinfo is not None and claimed.tzinfo is not None and retrieved.tzinfo is not None
                    and claimed == observed and observed <= retrieved,
                    "PRICE_OBSERVATION_MISMATCH", "Quote as-of must match the preserved observation and cannot exceed retrieval")
            require(self.source_snapshot is not None and self.snapshot_sha256 == digest(self.source_snapshot),
                    "CURRENCY_SNAPSHOT_REQUIRED", "Preserve the API response and its content hash")
            normalized = normalize_ninja_exchange(self.source_snapshot, league=self.league, version=self.version,
                        as_of=self.as_of, source_reference=self.evidence.reference)["price_book"]
            quotes = {key: None if value is None else str(rational(value)) for key, value in self.quotes.items()}
            require(quotes == normalized["quotes"] and self.unit == normalized["unit"],
                    "CURRENCY_SNAPSHOT_MISMATCH", "Manual quote/unit overrides and fallback values are forbidden")
        data.verify(self.evidence)
        require(bool(self.unit), "MISSING_PRICE_UNIT", "Quote unit required")
        stamp = datetime.fromisoformat(self.as_of.replace("Z", "+00:00"))
        now = datetime.fromisoformat(valuation_at.replace("Z", "+00:00")) if valuation_at else datetime.now(timezone.utc)
        require(stamp.tzinfo is not None and now.tzinfo is not None and self.max_age_seconds >= 0,
                "INVALID_PRICE_TIMESTAMP", self.as_of, "INVALID")
        require(0 <= (now - stamp).total_seconds() <= self.max_age_seconds, "STALE_OR_FUTURE_PRICE", self.as_of)

    def price(self, resource):
        require(resource in self.quotes and self.quotes[resource] is not None, "MISSING_PRICE", resource)
        amount = rational(self.quotes[resource])
        require(amount >= 0, "INVALID_PRICE", resource, "INVALID")
        return amount


class CompositePriceBook:
    """Combine API categories without manual prices, currency conversion, or silent conflicts."""
    def __init__(self, books):
        require(bool(books) and all(isinstance(book, PriceBook) for book in books),
                "INVALID_COMPOSITE_PRICE_BOOK", "Nonempty flat price-book list required", "INVALID")
        self.books = books
        first = books[0]
        self.domain, self.version, self.league, self.unit = first.domain, first.version, first.league, first.unit
        require(all((b.domain, b.version, b.league, b.unit) == (self.domain, self.version, self.league, self.unit) for b in books),
                "PRICE_SCOPE_MISMATCH", "Combined books require identical domain/version/league/unit")
        self.as_of = min((b.as_of for b in books), key=lambda v: datetime.fromisoformat(v.replace("Z", "+00:00")))
        self.quotes = {}
        for book in books:
            for resource, value in book.quotes.items():
                if value is None:
                    continue
                amount = rational(value)
                require(resource not in self.quotes or self.quotes[resource] == amount,
                        "CONFLICTING_PRICE", resource)
                self.quotes[resource] = amount

    def verify(self, engine, valuation_at=None):
        for book in self.books:
            book.verify(engine, valuation_at)

    def price(self, resource):
        values = [book.price(resource) for book in self.books if book.quotes.get(resource) is not None]
        require(bool(values), "MISSING_PRICE", resource)
        require(len(set(values)) == 1, "CONFLICTING_PRICE", resource)
        return values[0]


def solve(matrix, rhs):
    """Exact Gaussian elimination; singular systems are never silently estimated."""
    n = len(rhs)
    a = [[Fraction(v) for v in row] + [Fraction(b)] for row, b in zip(matrix, rhs)]
    for col in range(n):
        pivot = next((r for r in range(col, n) if a[r][col]), None)
        require(pivot is not None, "NONABSORBING_POLICY", "Singular transition system", "INVALID")
        a[col], a[pivot] = a[pivot], a[col]
        divisor = a[col][col]
        a[col] = [v / divisor for v in a[col]]
        for row in range(n):
            if row != col:
                multiple = a[row][col]
                if multiple:
                    a[row] = [v - multiple * w for v, w in zip(a[row], a[col])]
    return [row[-1] for row in a]


def route_values(result, cost):
    keys = list(result.edges)
    idx = {k: i for i, k in enumerate(keys)}
    n = len(keys)
    matrix = [[Fraction(int(i == j)) for j in range(n)] for i in range(n)]
    for key, outgoing in result.edges.items():
        for p, dest, _ in outgoing:
            if dest in idx:
                matrix[idx[key]][idx[dest]] -= p
    rhs = [cost(k) for k in keys]
    ev = solve(matrix, rhs)
    successes = solve(matrix, [sum((p for p, d, _ in result.edges[k] if result.terminals.get(d) == "success"), Fraction()) for k in keys])
    settles = solve(matrix, [sum((p for p, d, _ in result.edges[k] if result.terminals.get(d) == "settle"), Fraction()) for k in keys])
    # Expected visit counts: transpose fundamental system.
    visits = solve([list(row) for row in zip(*matrix)], [Fraction(int(k == result.start)) for k in keys])
    def initial(values, terminal):
        return values[idx[result.start]] if result.start in idx else Fraction(int(result.terminals[result.start] == terminal))
    return keys, ev, visits, initial(ev, "__none__"), initial(successes, "success"), initial(settles, "settle")


def price_route(engine, plan, prices, valuation_at=None):
    result = replay(engine, plan)  # Validation precedes economic output.
    prices.verify(engine, valuation_at)
    def cost(key):
        action = engine.action(result.actions[key])
        return sum((rational(q) * prices.price(r) for r, q in action.resources.items()), Fraction())
    keys, values, visits, expected, success, settle = route_values(result, cost)
    base_cost = prices.price(plan["base_resource"]) if plan.get("base_resource") else Fraction()
    # Explicitly require either purchase or an already-owned base, no hidden zero assumption.
    require(bool(plan.get("base_resource")) or plan.get("base_owned") is True,
            "MISSING_BASE_COST", "Specify base_resource or base_owned=true")
    rung_costs, resources = {}, {}
    for key, count in zip(keys, visits):
        node = plan["nodes"][key[0]]
        rung = node.get("rung", key[0])
        rung_costs[rung] = rung_costs.get(rung, Fraction()) + count * cost(key)
        for resource, quantity in engine.action(result.actions[key]).resources.items():
            resources[resource] = resources.get(resource, Fraction()) + count * rational(quantity)
    total = expected + base_cost
    if "claimed_total_cost" in plan:
        require(rational(plan["claimed_total_cost"]) == total, "FALSE_CLAIMED_COST", str(total), "INVALID")
    return {"status": "VALIDATED", "scope": "MECHANICS_AND_PRICES", "domain": engine.data.domain,
            "fingerprint": result.fingerprint, "unit": prices.unit, "price_as_of": prices.as_of,
            "base_cost": base_cost, "expected_total_cost": total, "rung_expected_costs": rung_costs,
            "expected_resource_consumption": resources, "completion_probability": success,
            "expected_action_visits": {"|".join(key): count for key, count in zip(keys, visits)},
            "expected_actions": sum(visits, Fraction()),
            "settle_probability": settle, "failure_probability": 1 - success - settle,
            "expected_cost_per_completion_with_external_restart": total / success if success else None,
            "note": "Total is expected spend until a declared terminal. External restart repeats the entire route and base purchase."}


def simulate(engine, plan, prices, trials=20000, seed=0, max_steps=10000, budget=None, valuation_at=None):
    require(type(trials) is int and trials > 0 and type(max_steps) is int and max_steps > 0,
            "INVALID_SIMULATION_LIMIT", "Positive integer limits required", "INVALID")
    analytical = price_route(engine, plan, prices, valuation_at)
    result = replay(engine, plan)
    rng = random.Random(seed)
    samples, terminal_counts, state_counts = [], Counter(), Counter()
    censored = 0
    base = analytical["base_cost"]
    for _ in range(trials):
        key, spent = result.start, base
        for step in range(max_steps):
            if key in result.terminals:
                break
            state_counts["|".join(key)] += 1
            action = engine.action(result.actions[key])
            spent += sum((rational(q) * prices.price(r) for r, q in action.resources.items()), Fraction())
            # Integer-weight sampling is exact for the shared transition distribution.
            outgoing = result.edges[key]
            denominator = math.lcm(*(p.denominator for p, _, _ in outgoing))
            roll = rng.randrange(denominator)
            cumulative = 0
            for p, dest, _ in outgoing:
                cumulative += p.numerator * (denominator // p.denominator)
                if roll < cumulative:
                    key = dest
                    break
        if key not in result.terminals:
            censored += 1
            terminal_counts["censored"] += 1
        else:
            terminal_counts[result.terminals[key]] += 1
        samples.append(float(spent))
    ordered = sorted(samples)
    mean = sum(samples) / trials
    variance = sum((x - mean) ** 2 for x in samples) / max(1, trials - 1)
    tolerance = 5 * math.sqrt(variance / trials)
    observed_success = terminal_counts["success"] / trials
    expected_success = float(analytical["completion_probability"])
    probability_tolerance = 5 * math.sqrt(expected_success * (1 - expected_success) / trials)
    return {"status": "PARTIALLY_VALIDATED" if censored else "VALIDATED", "domain": engine.data.domain,
            "trials": trials, "seed": seed, "max_steps": max_steps, "censored": censored,
            "terminal_counts": dict(terminal_counts), "completion_frequency": terminal_counts["success"] / trials,
            "mean_spend": mean, "median_spend": ordered[(trials - 1) // 2],
            "p95_spend": ordered[math.ceil(trials * .95) - 1], "p99_spend": ordered[math.ceil(trials * .99) - 1],
            "budget_exceed_frequency": sum(x > float(rational(budget)) for x in samples) / trials if budget is not None else None,
            "state_visits": dict(state_counts), "analytical": analytical,
            "analytical_disagreement": bool(censored or abs(mean - float(analytical["expected_total_cost"])) > tolerance + 1e-9
                                             or abs(observed_success - expected_success) > probability_tolerance + 1e-9),
            "five_standard_error_tolerance": tolerance,
            "note": "Censored spend is a lower bound; quantiles include all terminal types, not only completions."}


def compare_routes(engine, plans, prices, min_completion="1", budget=None, valuation_at=None,
                   min_budget_completion="1"):
    threshold = rational(min_completion)
    require(0 <= threshold <= 1, "INVALID_COMPLETION_THRESHOLD", str(threshold), "INVALID")
    candidates, rejected = [], []
    from .model import ForgeError
    for name, plan in plans.items():
        try:
            summary = price_route(engine, plan, prices, valuation_at)
            if summary["completion_probability"] < threshold:
                rejected.append({"name": name, "reason": "COMPLETION_CONSTRAINT", "economics": summary})
                continue
            if budget is not None:
                from .distributions import budget_distribution
                budget_threshold = rational(min_budget_completion)
                require(0 <= budget_threshold <= 1, "INVALID_COMPLETION_THRESHOLD", str(budget_threshold), "INVALID")
                distribution = budget_distribution(engine, plan, prices, budget, valuation_at)
                if distribution["completion_within_budget"] < budget_threshold:
                    rejected.append({"name": name, "reason": "BUDGET_COMPLETION_CONSTRAINT",
                                     "completion_within_budget": distribution["completion_within_budget"]})
                    continue
                summary["budget_analysis"] = {k: v for k, v in distribution.items() if k != "cost_cdf"}
            candidates.append({"name": name, "economics": summary})
        except ForgeError as exc:
            rejected.append({"name": name, **exc.report()})
    candidates.sort(key=lambda c: (c["economics"]["expected_total_cost"], c["name"]))
    return {"status": "VALIDATED" if candidates else "BLOCKED", "winner": candidates[0]["name"] if candidates else None,
            "reason": "Lowest full-route expected spend among routes meeting completion and, when supplied, exact budget-completion constraints.",
            "candidates": candidates, "rejected": rejected}
