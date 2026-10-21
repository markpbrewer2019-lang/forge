"""Source descriptions remain observations; invented rules prove execution only."""
import unittest
import tempfile
from forge.catalog import base_cards, raw_inventory


CURRENCY_CARD = b'''<div class="d-flex border-top rounded"><a class="item_currency StackableCurrency" href="Chaos_Orb" data-hover="https://cdn.poe2db.tw/cache2/us/Poe_Data_BaseItemTypes_hover/test">Chaos Orb</a><div class="explicitMod">Removes a random modifier and augments a Rare item with a new random modifier</div></div>'''


class SourceActionTests(unittest.TestCase):
    def test_currency_style_base_item_cards_are_not_dropped(self):
        rows = base_cards(CURRENCY_CARD, 'https://poe2db.tw/us/Stackable_Currency')
        self.assertEqual(1, len(rows))
        self.assertEqual('StackableCurrency', rows[0]['item_class'])
        self.assertEqual('Chaos_Orb', rows[0]['id'])
        self.assertEqual(1, raw_inventory(CURRENCY_CARD)['base'])

    def proposal(self, description, properties=None, item_class='StackableCurrency'):
        from forge.grammar import action_proposal
        row = base_cards(CURRENCY_CARD, 'https://poe2db.tw/us/Stackable_Currency')[0]
        row['explicit_modifiers'] = [description]
        row['item_class'] = item_class
        if properties is not None:
            row['properties'] = properties
        return action_proposal(row, {'url': 'https://poe2db.tw/us/Stackable_Currency',
            'sha256': 'a' * 64, 'retrieved_at': '2026-10-21T00:00:00+00:00', 'version': 'UNKNOWN', 'league': 'UNKNOWN'})

    def test_actual_chaos_wording_compiles_atomic_shape_without_uniform_guess(self):
        p = self.proposal('Removes a random modifier and augments a Rare item with a new random modifier')
        self.assertTrue(p['recognized'])
        self.assertEqual('remove_add', p['action']['operation'])
        self.assertIsNone(p['action']['removal_rule']['mode'])
        self.assertEqual('BLOCKED', p['status'])
        self.assertEqual('INFERRED', p['action']['evidence']['status'])
        self.assertTrue(p['action']['resources'])

    def test_explicit_source_level_floor_and_rarity_upgrade_are_retained(self):
        p = self.proposal('Upgrades a Normal item to a Magic item with 1 modifier', ['Minimum Modifier Level: 70'])
        self.assertEqual('magic', p['action']['resulting_rarity'])
        self.assertEqual(['normal'], p['action']['rarities'])
        self.assertEqual(70, p['action']['min_mod_ilvl'])
        self.assertIn('modifier_level_floor_application_scope', p['unresolved_fields'])

    def test_unsupported_description_suffix_never_partially_becomes_action(self):
        p = self.proposal('Augments a Rare item with a new random modifier, then removes all sockets')
        self.assertFalse(p['recognized'])
        self.assertIsNone(p['action'])

    def test_unsupported_multi_mod_action_does_not_become_single_addition(self):
        p = self.proposal('Upgrades a Normal or Magic item to a Rare item with 4 random modifiers')
        self.assertFalse(p['recognized'])

    def test_unresolved_source_rules_block_even_after_only_evidence_is_promoted(self):
        from forge.fixtures import universe
        from forge.model import Action, ForgeError
        from forge.engine import Engine
        p = self.proposal('Augments a Rare item with a new random modifier')
        data, _, _ = universe()
        raw = p['action'].copy()
        raw['evidence'] = next(iter(data.actions.values())).evidence
        data.actions = {raw['id']: Action(**raw)}
        with self.assertRaisesRegex(ForgeError, 'UNRESOLVED_SOURCE_RULE'):
            Engine(data).action(raw['id'])

    def test_omen_properties_are_not_lost_before_composition(self):
        p = self.proposal('While this item is active in your inventory your next Chaos Orb will remove the lowest level modifier',
            ['Only affects Prefix modifiers'], item_class='Omen')
        self.assertEqual(['Only affects Prefix modifiers'], p['unsupported_properties'])
        self.assertIn('unsupported_properties', p['unresolved_fields'])

    def test_catalog_build_craft_discovers_source_omen_variants_without_hints(self):
        from forge.source_store import SourceStore
        from forge.catalog import Catalog
        from forge.cli import dispatch
        omen = CURRENCY_CARD.replace(b'item_currency StackableCurrency', b'whiteitem Omen').replace(b'Chaos_Orb', b'Fixture_Omen').replace(
            b'Removes a random modifier and augments a Rare item with a new random modifier',
            b'While this item is active in your inventory your next Chaos Orb will remove the lowest level modifier')
        with tempfile.TemporaryDirectory() as directory:
            store = SourceStore(directory)
            store.put_page('https://poe2db.tw/us/Stackable_Currency', CURRENCY_CARD, retrieved_at='2026-10-21T00:00:00+00:00')
            store.put_page('https://poe2db.tw/us/Omen', omen, retrieved_at='2026-10-21T00:00:00+00:00')
            reference = CURRENCY_CARD.replace(b'<div class="explicitMod">Removes a random modifier and augments a Rare item with a new random modifier</div>', b'')
            store.put_page('https://poe2db.tw/us/Inscribed_Ultimatum', reference, retrieved_at='2026-10-21T00:00:00+00:00')
            Catalog(store).rebuild()
            rule = dispatch('catalog-action', {'directory': directory, 'record_id': 'Chaos_Orb'})
            self.assertEqual('remove_add', rule['action']['operation'])
            result = dispatch('build-craft', {'directory': directory, 'item': {'base': 'unknown', 'ilvl': 1}, 'target': ['unknown']})
            summary = result['source_grammar']
            self.assertEqual(2, summary['recognized_action_variants'])
            self.assertEqual(1, summary['recognized_interactions'])
            self.assertEqual('BLOCKED', result['status'])
            self.assertIsNone(result['golden6'])

    def test_descriptionless_reference_cannot_hide_conflicting_level_property(self):
        from forge.source_store import SourceStore
        from forge.catalog import Catalog
        from forge.model import ForgeError
        described = CURRENCY_CARD.replace(b'<div class="explicitMod">', b'<div class="property">Minimum Modifier Level: 50</div><div class="explicitMod">')
        reference = CURRENCY_CARD.replace(b'<div class="explicitMod">Removes a random modifier and augments a Rare item with a new random modifier</div>',
            b'<div class="property">Minimum Modifier Level: 70</div>')
        with tempfile.TemporaryDirectory() as directory:
            store = SourceStore(directory)
            for name, raw in [('Stackable_Currency', described), ('Inscribed_Ultimatum', reference)]:
                store.put_page('https://poe2db.tw/us/' + name, raw, retrieved_at='2026-10-21T00:00:00+00:00')
            catalog = Catalog(store)
            catalog.rebuild()
            with self.assertRaisesRegex(ForgeError, 'CONFLICTING_SOURCE_PROPERTIES'):
                catalog.action_rule('Chaos_Orb')
