import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from forge.model import ForgeError
from forge.source_store import SourceStore, extract_poe2db, category_urls


PAGE = b'''<html><title>Amulets</title><script>new ModsView({"baseitem":{"href":"Amulets"},"gen":{"1":"Prefix","2":"Suffix"},"normal":[{"Name":"of Test Strength","Level":"11","DropChance":"1000","ModGenerationTypeID":"2","ModFamilyList":["Strength"],"str":"+9 to <a>Strength</a>","hover":"source-record-123"}],"essence":[]});</script></html>'''
URL = 'https://poe2db.tw/us/Amulets'
TIME = '2026-10-20T12:00:00+00:00'


class LocalSourceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = SourceStore(self.directory.name)

    def save(self, raw=PAGE):
        return self.store.put_poe2db(URL, raw, retrieved_at=TIME)

    def test_embedded_json_preserves_source_fields_without_guessing_tiers(self):
        data = extract_poe2db(PAGE)
        self.assertEqual('1000', data['records'][0]['source_record']['DropChance'])
        self.assertEqual('Suffix', data['records'][0]['reported_generation'])
        self.assertIsNone(data['records'][0]['tier'])
        self.assertEqual('UNKNOWN', data['records'][0]['weight_semantics'])
        self.assertEqual('INFERRED', data['records'][0]['evidence_status'])

    def test_restart_and_search_are_offline_and_pin_raw_provenance(self):
        saved = self.save()
        with patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('network forbidden')):
            reopened = SourceStore(self.directory.name)
            found = reopened.search('strength', source='poe2db')
            self.assertEqual(1, len(found['records']))
            row = found['records'][0]
            self.assertEqual(saved['sha256'], row['snapshot_sha256'])
            self.assertEqual(URL, row['source_url'])
            self.assertEqual(PAGE, reopened.raw(saved['sha256']))
            self.assertEqual(1, reopened.coverage()['poe2db_modifier_rows'])

    def test_identical_import_is_idempotent_and_new_revision_preserves_history(self):
        old = self.save()
        self.save()
        changed = PAGE.replace(b'+9 to', b'+10 to')
        new = self.save(changed)
        self.assertNotEqual(old['sha256'], new['sha256'])
        self.assertEqual(PAGE, self.store.raw(old['sha256']))
        self.assertEqual(2, len(self.store.snapshots(URL)))
        self.assertEqual(1, len(self.store.search('strength')['records']))
        self.assertIn('+10 to', self.store.search('strength')['records'][0]['text'])

    def test_corrupt_blob_fails_closed_on_search_and_raw_lookup(self):
        saved = self.save()
        (Path(self.directory.name) / 'blobs' / saved['sha256']).write_bytes(b'corrupt')
        with self.assertRaises(ForgeError):
            self.store.search('strength')
        with self.assertRaises(ForgeError):
            self.store.raw(saved['sha256'])

    def test_missing_or_changed_source_shape_does_not_replace_good_revision(self):
        old = self.save()
        with self.assertRaises(ForgeError):
            self.save(b'<html>Challenge instead of data</html>')
        self.assertEqual(old['sha256'], self.store.snapshots(URL)[0]['sha256'])

    def test_arbitrary_javascript_is_never_executed(self):
        with self.assertRaises(ForgeError):
            extract_poe2db(b'<script>new ModsView(runArbitraryCode());</script>')

    def test_jewel_class_ids_are_metadata_not_a_modifier_pool(self):
        page = PAGE.replace(b'"essence":[]', b'"essence":[],"ids":[0,3]')
        extracted = extract_poe2db(page)
        self.assertEqual(1, len(extracted['records']))
        self.assertEqual([0, 3], extracted['views'][0]['ids'])

    def test_source_urls_and_snapshot_ids_are_restricted(self):
        for url in ('https://poedb.tw/us/Amulets', 'https://example.com/Amulets', 'https://poe2db.tw/us/marked', 'https://poe2db.tw/us/markdown_history'):
            with self.assertRaises(ForgeError):
                self.store.put_poe2db(url, PAGE, retrieved_at=TIME)
        with self.assertRaises(ForgeError):
            self.store.raw('../outside')

    def test_category_discovery_uses_only_actual_poe2_links_and_deduplicates(self):
        page = b'<a href="/us/Rings#ModifiersCalc">Rings</a><a href="/us/Rings#ModifiersCalc">Again</a><a href="https://evil.test/us/X#ModifiersCalc">X</a>'
        self.assertEqual(['https://poe2db.tw/us/Rings'], category_urls(page))

    def test_market_import_retains_observation_time_and_exact_api_quote(self):
        from forge.data import normalize_ninja_exchange
        raw = {'core': {'primary': 'divine'}, 'lines': [{'id': 'test-currency', 'primaryValue': '0.125'}]}
        doc = normalize_ninja_exchange(raw, league='Standard', version='UNKNOWN', as_of=TIME,
            source_reference='https://poe.ninja/poe2/api/economy/exchange/current/overview?league=Standard&type=Currency')
        self.store.put_market(doc)
        row = self.store.search('test-currency', source='poe.ninja')['records'][0]
        self.assertEqual(TIME, row['observed_at'])
        self.assertEqual('0.125', row['source_record']['primaryValue'])
        self.assertEqual('UNKNOWN', row['version'])
        self.assertEqual('INFERRED', row['evidence_status'])
        self.assertEqual(0, self.store.coverage()['verified_solver_records'])
        doc['price_book']['quotes']['test-currency'] = '999'
        with self.assertRaises(ForgeError):
            self.store.put_market(doc)

    def test_cli_offline_lookup_requires_no_dataset_or_network(self):
        from forge.cli import dispatch
        self.save()
        result = dispatch('data-search', {'directory': self.directory.name, 'query': 'strength'})
        self.assertEqual(1, len(result['records']))
        self.assertEqual(1, dispatch('data-status', {'directory': self.directory.name})['poe2db_modifier_rows'])

    def market_document(self):
        from forge.data import normalize_ninja_exchange
        return normalize_ninja_exchange({'core': {'primary': 'divine'}, 'lines': [{'id': 'test', 'primaryValue': '0.25'}]},
            league='Standard', version='UNKNOWN', as_of=TIME,
            source_reference='https://poe.ninja/poe2/api/economy/exchange/current/overview?league=Standard&type=Currency')

    def test_legacy_market_receipt_preserves_observation_and_rejects_relabeling(self):
        doc = self.market_document()
        del doc['price_book']['source_observed_at']
        doc['receipt'] = {'observed_at': TIME}
        self.store.put_market(doc)
        self.assertEqual(TIME, self.store.search('test', source='poe.ninja')['records'][0]['observed_at'])
        doc['price_book']['as_of'] = '2026-10-20T13:00:00+00:00'
        doc['price_book']['evidence']['retrieved_at'] = '2026-10-20T14:00:00+00:00'
        with self.assertRaises(ForgeError):
            self.store.put_market(doc)

    def test_conflicting_market_receipt_and_future_observation_are_rejected(self):
        doc = self.market_document()
        doc['receipt'] = {'observed_at': '2026-10-20T11:00:00+00:00'}
        with self.assertRaises(ForgeError):
            self.store.put_market(doc)
        del doc['receipt']
        doc['price_book']['evidence']['retrieved_at'] = '2026-10-20T11:00:00+00:00'
        with self.assertRaises(ForgeError):
            self.store.put_market(doc)

    def test_sync_rejects_changed_index_before_replacing_saved_data(self):
        from tools.sync_sources import main
        index_url = 'https://poe2db.tw/us/Modifiers'
        index = b'<a href="/us/Rings#ModifiersCalc">Rings</a>'
        saved = self.store.put_page(index_url, index, retrieved_at=TIME)
        class Response:
            headers = {}
            def __init__(self, body): self.body = body
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, size): return self.body
        replies = [Response(b'User-agent: *\nDisallow: /*/marked\nDisallow: /*/markdown_history\n'),
                   Response(b'<html>Challenge or changed category index</html>')]
        with patch('sys.argv', ['sync_sources.py', '--directory', self.directory.name, '--refresh']), \
             patch('urllib.request.OpenerDirector.open', side_effect=replies), patch('tools.sync_sources.time.sleep'):
            with self.assertRaises(ValueError):
                main()
        self.assertEqual(saved['sha256'], self.store.snapshots(index_url)[0]['sha256'])


if __name__ == '__main__':
    unittest.main()
