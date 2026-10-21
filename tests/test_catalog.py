import json
from pathlib import Path
import tempfile
import unittest
import contextlib
import io
from unittest.mock import patch
from contextlib import closing

from forge.source_store import SourceStore, category_urls
from forge.catalog import Catalog, base_cards, item_category_urls, project
from tests.test_local_sources import PAGE, URL, TIME


CARD = b'''<div class="col"><div class="d-flex border-top rounded"><div class="flex-shrink-0"><a class="whiteitem BodyArmour" data-hover="https://cdn.poe2db.tw/cache2/us/Poe_Data_BaseItemTypes_hover/base123" href="Rusted_Cuirass"><img src="example.webp"></a></div><div class="flex-grow-1 ms-2"><a class="whiteitem BodyArmour" data-hover="https://cdn.poe2db.tw/cache2/us/Poe_Data_BaseItemTypes_hover/base123" href="Rusted_Cuirass">Rusted Cuirass</a><div><div class="property"><a>Armour</a>: <span>45</span></div><div class="property">Base Movement Speed: <span>-0.05</span></div><div class="requirements">Requires: <span>Level 4</span>, <span>10 Str</span></div><div class="implicitMod">+10 to maximum Life</div></div></div></div></div>'''


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = SourceStore(self.temp.name)
        self.store.put_poe2db(URL, PAGE + CARD, retrieved_at=TIME)
        self.catalog = Catalog(self.store)

    def test_relative_and_absolute_modifier_inventory_links_are_equivalent(self):
        raw = b'<a href="Urn_Relic#ModifiersCalc">Urn</a><a href="/us/Rings#ModifiersCalc">Rings</a><a href="https://poe2db.tw/us/Wands#ModifiersCalc">Wand</a>'
        self.assertEqual(['https://poe2db.tw/us/Rings', 'https://poe2db.tw/us/Urn_Relic', 'https://poe2db.tw/us/Wands'], category_urls(raw))

    def test_base_stats_and_requirements_are_distinct_from_modifier_ilvl(self):
        rows = base_cards(CARD, URL)
        self.assertEqual(1, len(rows))
        row = rows[0]
        self.assertEqual('Rusted Cuirass', row['name'])
        self.assertEqual({'Armour': '45', 'Base Movement Speed': '-0.05'}, row['stats'])
        self.assertEqual(4, row['required_character_level'])
        self.assertEqual({'Str': 10}, row['attribute_requirements'])
        self.assertEqual(['+10 to maximum Life'], row['implicit_modifiers'])
        self.assertIsNone(row['minimum_drop_item_level'])

    def test_query_exposes_exact_reported_ilvl_weight_and_scope(self):
        self.catalog.rebuild()
        found = self.catalog.query(kind='modifier', text='strength')['records']
        self.assertEqual(1, len(found))
        self.assertEqual(11, found[0]['ilvl'])
        self.assertEqual(1000, found[0]['weight'])
        self.assertEqual('suffix', found[0]['side'])
        self.assertEqual('normal', found[0]['pool'])
        self.assertEqual('POE2DB_DISPLAY', found[0]['field_semantics'])
        self.assertEqual('INFERRED', found[0]['evidence_status'])
        self.assertEqual([], self.catalog.query(kind='modifier', max_ilvl=10)['records'])
        self.assertEqual(1, len(self.catalog.query(kind='base', text='cuirass')['records']))

    def test_audit_compares_source_rows_with_local_projection_and_detects_damage(self):
        self.catalog.rebuild()
        audit = self.catalog.audit()
        self.assertEqual((2, 2, 0, 0, '100'), tuple(audit[k] for k in ('available_source_rows', 'local_matched_rows', 'missing_rows', 'mismatched_rows', 'coverage_percent')))
        with closing(self.store._connect()) as db, db:
            db.execute("DELETE FROM catalog_rows WHERE kind='base'")
            db.execute("UPDATE catalog_rows SET payload='{}' WHERE kind='modifier'")
        audit = self.catalog.audit()
        self.assertEqual((1, 1, '0'), (audit['missing_rows'], audit['mismatched_rows'], audit['coverage_percent']))
        self.assertEqual('INGESTION_FAILURE', audit['gaps'][0]['classification'])

    def test_missing_weight_remains_unavailable_not_zero_or_ingestion_failure(self):
        raw = PAGE.replace(b'"DropChance":"1000",', b'')
        self.store.put_poe2db(URL, raw, retrieved_at=TIME)
        self.catalog.rebuild()
        row = self.catalog.query(kind='modifier')['records'][0]
        self.assertIsNone(row['weight'])
        self.assertIn('weight', row['source_unavailable_fields'])
        self.assertEqual(0, self.catalog.audit()['missing_rows'])

    def test_audit_validates_columns_that_drive_eligibility_queries(self):
        self.catalog.rebuild()
        with closing(self.store._connect()) as db, db:
            db.execute("UPDATE catalog_rows SET ilvl=100 WHERE kind='modifier'")
        self.assertEqual(1, self.catalog.audit()['mismatched_rows'])

    def test_rebuild_does_not_open_readers_after_large_write_spills(self):
        document = {'baseitem': {}, 'gen': {'2': 'Suffix'}, 'normal': [
            {'Name': 'stress'+str(i), 'Level': '1', 'DropChance': '1', 'ModGenerationTypeID': '2', 'str': 'x'*2000}
            for i in range(80)]}
        self.store.put_poe2db(URL, ('<script>new ModsView('+json.dumps(document)+');</script>').encode(), retrieved_at=TIME)
        connect = self.store._connect
        def tiny_cache():
            db = connect()
            db.execute('PRAGMA cache_size=1')
            db.execute('PRAGMA busy_timeout=30')
            return db
        with patch.object(self.store, '_connect', tiny_cache):
            self.assertEqual(80, self.catalog.rebuild()['projected_rows'])

    def test_item_inventory_only_follows_itemlist_sources(self):
        raw = b'<a href="Account">No</a><div class="itemList"><a href="Body_Armours">Body</a><a href="https://poedb.tw/us/Rings">Wrong game</a></div>'
        self.assertEqual(['https://poe2db.tw/us/Body_Armours'], item_category_urls(raw))

    def test_static_modifier_tables_preserve_available_and_unavailable_weights(self):
        page = b'<div class="card"><h5>Desecrated Mods /2</h5><table><tr><th>Name</th><th>Level</th><th>Pre/Suf</th><th>Description</th><th>Weight</th></tr><tr><td>Test</td><td>63</td><td>Suffix</td><td>+5 maximum Life</td><td>250</td></tr><tr><td>Unknown</td><td>72</td><td>Prefix</td><td>Test stat</td><td></td></tr></table></div>'
        rows = project(page, URL)
        self.assertEqual(2, len(rows))
        self.assertEqual((63, 250, 'suffix'), (rows[0]['ilvl'], rows[0]['weight'], rows[0]['side']))
        self.assertIsNone(rows[1]['weight'])
        self.assertIn('weight', rows[1]['source_unavailable_fields'])

    def test_audit_denominator_counts_raw_rows_even_if_projection_misses_one(self):
        self.catalog.rebuild()
        actual_project = project
        with patch('forge.catalog.project', side_effect=lambda raw, url: actual_project(raw, url)[:-1]):
            audit = self.catalog.audit()
        self.assertEqual(2, audit['available_source_rows'])
        self.assertEqual('BLOCKED', audit['status'])
        self.assertTrue(any(g.get('issue') == 'projection_count' for g in audit['gaps']))

    def test_conditional_weight_entries_are_retained_and_not_flattened(self):
        page = b'<table><tr><th>Level</th><th>Description</th><th>Weight</th></tr><tr><td>50</td><td>Test</td><td><i>medium_sanctum_relic</i> 1<br><i>default</i> 0<br></td></tr></table>'
        row = project(page, URL)[0]
        self.assertIsNone(row['weight'])
        self.assertEqual([{'condition': 'medium_sanctum_relic', 'weight': 1}, {'condition': 'default', 'weight': 0}], row['weight_entries'])
        self.assertEqual([], row['source_unavailable_fields'])
        self.assertIn('conditional_weight_evaluation', row['planner_unresolved_fields'])

    def test_display_tiers_are_scoped_to_each_literal_source_view(self):
        document = {'baseitem': {'href': 'Wands'}, 'gen': {'1': 'Prefix'}, 'normal': [
            {'str': 'Test stat', 'Level': 11, 'DropChance': 1000, 'ModGenerationTypeID': 1, 'ModFamilyList': ['test']}]}
        first = json.dumps(document)
        document['normal'][0]['Level'] = 85
        rows = project(('new ModsView(' + first + ');new ModsView(' + json.dumps(document) + ');').encode(), URL)
        self.assertEqual([1, 1], [r['display_tier'] for r in rows])

    def test_source_socket_capacity_proposal_cannot_become_verified_by_parsing(self):
        card = CARD.replace(b'+10 to maximum Life', b'All Equipment: +1 Suffix Modifier allowed').replace(b'<div class="implicitMod">', b'<div class="enchantMod">Socket-bound</div><div class="implicitMod">')
        self.store.put_poe2db(URL, PAGE + card, retrieved_at=TIME)
        self.catalog.rebuild()
        proposal = self.catalog.property_rule('Rusted_Cuirass')
        self.assertEqual('BLOCKED', proposal['status'])
        self.assertTrue(proposal['proposed_flag_rule']['permanent'])
        self.assertEqual({'suffix': 1}, proposal['proposed_flag_rule']['capacity_delta'])
        self.assertEqual('INFERRED', proposal['proposed_flag_rule']['evidence']['status'])
        self.assertIn('occupied_sockets', proposal['unresolved_fields'])
        from forge.model import Evidence, FlagRule, ForgeError
        fields = proposal['proposed_flag_rule'].copy()
        fields['evidence'] = Evidence(**fields['evidence'])
        candidate = FlagRule(**fields)
        with self.assertRaises(ForgeError):
            candidate.evidence.verify_state_fact('POE2', 'UNKNOWN', 'UNKNOWN')

    def test_full_inventory_reuses_saved_indexes_without_network(self):
        from tools.sync_sources import main
        self.store.put_page('https://poe2db.tw/robots.txt', b'User-agent: *\nDisallow: /*/marked\nDisallow: /*/markdown_history\n', retrieved_at=TIME)
        self.store.put_page('https://poe2db.tw/us/Modifiers', b'<div class="itemList"><a href="Amulets#ModifiersCalc">A</a></div>', retrieved_at=TIME)
        self.store.put_page('https://poe2db.tw/us/Items', b'<div class="itemList"><a href="Amulets">A</a></div>', retrieved_at=TIME)
        with patch('sys.argv', ['sync_sources.py', '--directory', self.temp.name, '--all-items', '--catalog']), \
             patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('network forbidden')), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, main())
        report = json.loads((Path(self.temp.name) / 'coverage.json').read_text())
        self.assertEqual('100', report['catalog_audit']['coverage_percent'])

    def test_build_craft_resolves_local_records_and_blocks_missing_mechanics(self):
        from forge.cli import dispatch
        self.catalog.rebuild()
        mod = self.catalog.query(kind='modifier')['records'][0]
        result = dispatch('build-craft', {'directory': self.temp.name,
            'item': {'base': 'Rusted_Cuirass', 'ilvl': 83, 'rarity': 'rare'}, 'target': [mod['id']]})
        self.assertEqual('BLOCKED', result['status'])
        self.assertIsNone(result['golden6'])
        self.assertIn('VERIFIED_ACTION_SEMANTICS', [x['code'] for x in result['blockers']])
        self.assertEqual(11, result['targets'][0]['ilvl'])
        self.assertEqual('Rusted Cuirass', result['bases'][0]['name'])


if __name__ == '__main__':
    unittest.main()
