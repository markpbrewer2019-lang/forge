from dataclasses import replace
from datetime import datetime, timezone
import unittest

from forge.model import Dataset, ForgeError
from forge.engine import Engine
from forge.economics import PriceBook
from forge.data import normalize_ninja_exchange
from forge.fixtures import universe


class CurrencySourceTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc).isoformat()
        self.reference = "https://poe.ninja/poe2/api/economy/exchange/current/overview?league=Standard&type=Currency"
        self.raw = {"core": {"primary": "divine"}, "lines": [{"id": "test-currency", "primaryValue": "0.25"}]}
        normalized = normalize_ninja_exchange(self.raw, league="Standard", version="test-version", as_of=self.now,
                                             source_reference=self.reference)
        self.book = PriceBook.load(normalized["price_book"])
        # Contract fixture only: the evidence status below does not verify any real market value.
        self.book.evidence = replace(self.book.evidence, status="VERIFIED")
        self.engine = Engine(Dataset("POE2", "test-version", "Standard", {}, {}, {}, ()))

    def assertCode(self, code, function, *args):
        with self.assertRaises(ForgeError) as caught:
            function(*args)
        self.assertEqual(code, caught.exception.code)

    def test_api_snapshot_and_scope_pass_source_gate(self):
        self.book.verify(self.engine, self.now)

    def test_alternative_provider_rejected(self):
        self.book.evidence = replace(self.book.evidence, source="manual spreadsheet")
        self.assertCode("CURRENCY_SOURCE_REQUIRED", self.book.verify, self.engine, self.now)

    def test_wrong_game_spoofed_host_and_non_api_rejected(self):
        for reference in (self.reference.replace("/poe2/", "/poe1/"),
                          self.reference.replace("poe.ninja/", "poe.ninja.example/"),
                          self.reference.replace("/poe2/api/", "/poe2/"),
                          self.reference + "#Currency"):
            with self.subTest(reference=reference):
                self.book.evidence = replace(self.book.evidence, reference=reference)
                self.assertCode("CURRENCY_SOURCE_REQUIRED", self.book.verify, self.engine, self.now)

    def test_wrong_league_and_duplicate_parameters_rejected(self):
        for reference in (self.reference.replace("Standard", "Other"), self.reference + "&type=Currency"):
            self.book.evidence = replace(self.book.evidence, reference=reference)
            self.assertCode("PRICE_SCOPE_MISMATCH", self.book.verify, self.engine, self.now)

    def test_missing_snapshot_rejected(self):
        self.book.source_snapshot = None
        self.assertCode("CURRENCY_SNAPSHOT_REQUIRED", self.book.verify, self.engine, self.now)

    def test_manual_prices_and_unit_overrides_rejected(self):
        self.book.quotes["test-currency"] = "500"
        self.assertCode("CURRENCY_SNAPSHOT_MISMATCH", self.book.verify, self.engine, self.now)
        self.book.quotes["test-currency"] = "1/4"
        self.book.unit = "other-unit"
        self.assertCode("CURRENCY_SNAPSHOT_MISMATCH", self.book.verify, self.engine, self.now)

    def test_synthetic_prices_remain_isolated(self):
        data, book, _ = universe()
        book.verify(Engine(data))

    def test_market_observations_still_need_review(self):
        self.book.evidence = replace(self.book.evidence, status="INFERRED")
        self.assertCode("INSUFFICIENT_VERIFIED_DATA", self.book.verify, self.engine, self.now)

    def test_supported_crafting_material_category_uses_same_api(self):
        reference = self.reference.replace("type=Currency", "type=Essences")
        normalized = normalize_ninja_exchange(self.raw, league="Standard", version="test-version",
                                              as_of=self.now, source_reference=reference)
        self.assertEqual(reference, normalized["price_book"]["evidence"]["reference"])

    def test_composite_categories_preserve_source_validation(self):
        from copy import deepcopy
        other = deepcopy(self.book)
        other.evidence = replace(other.evidence, reference=self.reference.replace("type=Currency", "type=Ritual"))
        from forge.model import jsonable
        combined = PriceBook.load({"books": [jsonable(self.book), jsonable(other)]})
        combined.verify(self.engine, self.now)
        self.assertEqual(self.book.price("test-currency"), combined.price("test-currency"))

    def test_composite_rejects_conflicting_quotes(self):
        from copy import deepcopy
        from forge.model import jsonable
        other = deepcopy(self.book)
        other.quotes["test-currency"] = "999"
        self.assertCode("CONFLICTING_PRICE", PriceBook.load, {"books": [jsonable(self.book), jsonable(other)]})

    def test_asof_edit_cannot_refresh_old_source_observation(self):
        from datetime import timedelta
        old = (datetime.fromisoformat(self.now) - timedelta(days=10)).isoformat()
        self.book.as_of = old
        self.book.evidence = replace(self.book.evidence, retrieved_at=old)
        if hasattr(self.book, "source_observed_at"):
            self.book.source_observed_at = old
        self.assertCode("STALE_OR_FUTURE_PRICE", self.book.verify, self.engine, self.now)
        self.book.as_of = self.now
        self.assertCode("PRICE_OBSERVATION_MISMATCH", self.book.verify, self.engine, self.now)


if __name__ == "__main__":
    unittest.main()
