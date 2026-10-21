"""Explicit source acquisition. Offline lookups never invoke this tool."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from forge.market import NoRedirect
from forge.model import ForgeError
from forge.source_store import SourceStore, category_urls, validate_poe2db_url


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', default='local-data/sources')
    parser.add_argument('--bootstrap', default='local-data/bootstrap')
    parser.add_argument('--refresh', action='store_true', help='Explicitly refetch saved PoE2DB pages')
    parser.add_argument('--market-file', help='Import an existing poe.ninja refresh-currency JSON report')
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
                if 'no-store' in response.headers.get('Cache-Control', '').lower():
                    raise ValueError('Source disallows persistent response storage')
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
    index = acquire('https://poe2db.tw/us/Modifiers', 'Modifiers.html', page=True, validate=validate_index)
    urls = category_urls(index)
    for index, url in enumerate(urls, 1):
        try:
            acquire(url, url.rsplit('/', 1)[-1] + '.html')
            print(json.dumps({'progress': index, 'total': len(urls), 'source': url, 'saved': True}), flush=True)
        except (ForgeError, ValueError, OSError, urllib.error.URLError) as exc:
            failures.append({'url': url, 'error': str(exc)})
            print(json.dumps({'progress': index, 'total': len(urls), 'source': url, 'saved': False}), flush=True)
    if args.market_file:
        store.put_market(json.loads(Path(args.market_file).read_text(encoding='utf-8-sig')))
    report = {**store.coverage(), 'category_urls_discovered': len(urls), 'failures': failures}
    (Path(args.directory) / 'coverage.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2), flush=True)
    return 2 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
