"""Explicit source acquisition. Offline lookups never invoke this tool."""
import argparse
from datetime import datetime, timezone
import json
import re
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from forge.market import NoRedirect
from forge.model import ForgeError
from forge.source_store import SourceStore, category_urls, validate_poe2db_url


class SourceUnavailable(ValueError):
    pass


def failure_class(exc):
    return 'SOURCE_UNAVAILABLE' if isinstance(exc, (urllib.error.URLError, SourceUnavailable)) else 'INGESTION_FAILURE'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', default='local-data/sources')
    parser.add_argument('--bootstrap', default='local-data/bootstrap')
    parser.add_argument('--refresh', action='store_true', help='Explicitly refetch saved PoE2DB pages')
    parser.add_argument('--market-file', help='Import an existing poe.ninja refresh-currency JSON report')
    parser.add_argument('--all-items', action='store_true', help='Include every Items/Modifiers index category, base cards and auxiliary source pages')
    parser.add_argument('--catalog', action='store_true', help='Build and audit the offline modifier/base projection after acquisition')
    parser.add_argument('--archive-public-pages', action='store_true',
                        help='Explicitly archive public PoE2DB pages as source data, independently of HTTP response caching')
    args = parser.parse_args()
    store = SourceStore(args.directory)
    opener = urllib.request.build_opener(NoRedirect())
    failures = []

    def acquire(url, bootstrap=None, page=False, validate=None):
        validate_poe2db_url(url)
        existing = store.snapshots(url)
        if existing and not args.refresh:
            raw = store.raw(existing[0]['sha256'])
            if validate:
                validate(raw)
            return raw
        local = Path(args.bootstrap) / bootstrap if bootstrap else None
        if local and local.is_file() and not args.refresh:
            raw = local.read_bytes()
            retrieved = datetime.fromtimestamp(local.stat().st_mtime, timezone.utc).isoformat()
        else:
            time.sleep(1)
            request = urllib.request.Request(url, headers={'User-Agent': 'Forge/0.3 (local PoE2 source library)',
                                                          'Accept': 'text/html,text/plain'})
            with opener.open(request, timeout=30) as response:
                raw = response.read(12_000_001)
                if len(raw) > 12_000_000:
                    raise ValueError('Source exceeds 12 MB limit')
                cache_control = response.headers.get('Cache-Control', '')
                if 'no-store' in cache_control.lower() and not args.archive_public_pages:
                    raise SourceUnavailable('HTTP no-store: automatic caching disabled; explicit public source archival is required')
                if not url.endswith('/robots.txt') and not re.search(rb'<title>[^<]*PoE2DB', raw):
                    raise ValueError('Expected a public PoE2DB source document, not a challenge or error page')
            retrieved = datetime.now(timezone.utc).isoformat()
        if validate:
            validate(raw)
        if page:
            store.put_page(url, raw, retrieved_at=retrieved)
        else:
            store.put_poe2db(url, raw, retrieved_at=retrieved)
        return raw

    # These exact public paths were checked before this source adapter was written.
    # Fail closed if the publisher changes its rules; Python RobotFileParser does not
    # implement the wildcard rules used by this site, so check the observed contract.
    robots = acquire('https://poe2db.tw/robots.txt', 'robots.txt', page=True).decode('utf-8')
    directives = [line.strip() for line in robots.splitlines() if line.strip() and not line.startswith('#')]
    if set(directives) != {'User-agent: *', 'Disallow: /*/marked', 'Disallow: /*/markdown_history'}:
        raise ValueError('PoE2DB robots rules changed; review before source acquisition')
    def validate_index(raw):
        if not category_urls(raw):
            raise ValueError('PoE2DB category index changed or unavailable; preserving previous index')
    modifier_index = acquire('https://poe2db.tw/us/Modifiers', 'Modifiers.html', page=True, validate=validate_index)
    urls = category_urls(modifier_index)
    for index, url in enumerate(urls, 1):
        try:
            acquire(url, url.rsplit('/', 1)[-1] + '.html')
            print(json.dumps({'progress': index, 'total': len(urls), 'source': url, 'saved': True}), flush=True)
        except (ForgeError, ValueError, OSError, urllib.error.URLError) as exc:
            failures.append({'url': url, 'error': str(exc), 'classification': failure_class(exc)})
            print(json.dumps({'progress': index, 'total': len(urls), 'source': url, 'saved': False}), flush=True)
    item_urls, auxiliary_urls = [], []
    if args.all_items:
        from forge.catalog import item_category_urls
        def validate_items(raw):
            if not item_category_urls(raw):
                raise ValueError('Items source index changed; no class inventory found')
        items = acquire('https://poe2db.tw/us/Items', 'Items.html', page=True, validate=validate_items)
        item_urls = item_category_urls(items)
        auxiliary_urls = item_category_urls(modifier_index)
        extra = sorted((set(item_urls) | set(auxiliary_urls)) - set(urls) - {'https://poe2db.tw/us/Modifiers', 'https://poe2db.tw/us/Items'})
        for number, url in enumerate(extra, 1):
            try:
                acquire(url, page=True)
                print(json.dumps({'extra_progress': number, 'total': len(extra), 'source': url, 'saved': True}), flush=True)
            except (ForgeError, ValueError, OSError, urllib.error.URLError) as exc:
                failures.append({'url': url, 'error': str(exc), 'classification': failure_class(exc)})
                print(json.dumps({'extra_progress': number, 'total': len(extra), 'source': url, 'saved': False}), flush=True)
    if args.market_file:
        store.put_market(json.loads(Path(args.market_file).read_text(encoding='utf-8-sig')))
    inventory_urls = sorted(set(urls) | set(item_urls) | set(auxiliary_urls))
    inventory = {'modifier_calculator_categories': urls, 'modifier_index_categories': auxiliary_urls,
                 'item_categories': item_urls, 'source_urls': inventory_urls,
                 'saved_urls': [url for url in inventory_urls if store.snapshots(url)], 'failures': failures}
    (Path(args.directory) / 'inventory.json').write_text(json.dumps(inventory, indent=2), encoding='utf-8')
    report = {**store.coverage(), 'category_urls_discovered': len(urls),
              'inventory_urls': len(inventory_urls), 'saved_inventory_urls': len(inventory['saved_urls']), 'failures': failures}
    if args.catalog:
        from forge.catalog import Catalog
        catalog = Catalog(store)
        catalog.rebuild()
        report['catalog_audit'] = catalog.audit()
        (Path(args.directory) / 'catalog-audit.json').write_text(json.dumps(report['catalog_audit'], indent=2), encoding='utf-8')
    (Path(args.directory) / 'coverage.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2), flush=True)
    return 2 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
