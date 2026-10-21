"""Persistent, offline source observations. Never promotes observations into solver facts."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit, urljoin

from .model import ForgeError, require

PARSER_VERSION = 'poe2db-modsview-json-v1'


class Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.hidden += 1
        if tag in ('br', 'div', 'tr', 'td', 'p'):
            self.parts.append(' ')

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain(html):
    parser = Text()
    parser.feed(html)
    return ' '.join(''.join(parser.parts).split())


def validate_poe2db_url(url):
    parsed = urlsplit(url)
    require(parsed.scheme == 'https' and parsed.netloc == 'poe2db.tw'
            and not parsed.query and not parsed.fragment
            and (parsed.path == '/robots.txt' or re.fullmatch(r'/us/[A-Za-z0-9_().%~-]+', parsed.path))
            and parsed.path.rsplit('/', 1)[-1] not in {'marked', 'markdown_history'},
            'INVALID_POE2DB_SOURCE', url, 'INVALID')


def category_urls(raw):
    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.urls = set()

        def handle_starttag(self, tag, attrs):
            href = dict(attrs).get('href', '')
            if tag == 'a' and urlsplit(href).fragment == 'ModifiersCalc':
                url = urljoin('https://poe2db.tw/us/Modifiers', href).split('#')[0]
                try:
                    validate_poe2db_url(url)
                except ForgeError:
                    return
                self.urls.add(url)
    parser = Links()
    parser.feed(raw.decode('utf-8'))
    return sorted(parser.urls)


def extract_poe2db(raw):
    text = raw.decode('utf-8')
    views, records = [], []
    for match in re.finditer(r'\bnew\s+ModsView\s*\(', text):
        try:
            document, end = json.JSONDecoder().raw_decode(text[match.end():].lstrip())
        except ValueError:
            raise ForgeError('POE2DB_SCHEMA_CHANGED', 'ModsView argument is not literal JSON') from None
        require(isinstance(document, dict) and isinstance(document.get('baseitem'), dict)
                and isinstance(document.get('gen'), dict) and isinstance(document.get('normal'), list),
                'POE2DB_SCHEMA_CHANGED', 'Missing baseitem/gen/normal')
        views.append(document)
        for pool, rows in document.items():
            if pool == 'ids':
                require(isinstance(rows, list) and all(isinstance(value, int) for value in rows),
                        'POE2DB_SCHEMA_CHANGED', 'Unexpected item-class ids metadata')
                continue
            if not isinstance(rows, list):
                continue
            for ordinal, row in enumerate(rows):
                require(isinstance(row, dict) and isinstance(row.get('str'), str),
                        'POE2DB_SCHEMA_CHANGED', f'Unexpected modifier row: {pool}/{ordinal}')
                records.append({'kind': 'modifier', 'pool': pool, 'ordinal': ordinal,
                    'item_class': document['baseitem'].get('href'),
                    'name': plain(str(row.get('Name', ''))), 'text': plain(row['str']),
                    'reported_generation': document['gen'].get(str(row.get('ModGenerationTypeID'))),
                    'tier': row.get('Tier'), 'weight_semantics': 'UNKNOWN',
                    'evidence_status': 'INFERRED', 'source_record': row})
    require(bool(views), 'POE2DB_SCHEMA_CHANGED', 'No literal ModsView payload found')
    return {'parser': PARSER_VERSION, 'views': views, 'records': records}


def timestamp(value):
    require(isinstance(value, str), 'INVALID_SOURCE_TIME', 'Timestamp required', 'INVALID')
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ForgeError('INVALID_SOURCE_TIME', value, 'INVALID') from None
    require(parsed.tzinfo is not None, 'INVALID_SOURCE_TIME', 'Timezone required', 'INVALID')
    return value


class SourceStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.db = self.directory / 'sources.sqlite3'
        with closing(self._connect()) as db, db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY, url TEXT NOT NULL, sha256 TEXT NOT NULL,
                    source TEXT NOT NULL, retrieved_at TEXT NOT NULL, observed_at TEXT,
                    version TEXT NOT NULL, league TEXT NOT NULL, parser TEXT NOT NULL,
                    UNIQUE(url, sha256, version, league));
                CREATE TABLE IF NOT EXISTS heads (url TEXT PRIMARY KEY, snapshot_id INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS records (
                    snapshot_id INTEGER NOT NULL, ordinal INTEGER NOT NULL,
                    kind TEXT NOT NULL, search_text TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(snapshot_id, ordinal));
                CREATE INDEX IF NOT EXISTS records_snapshot ON records(snapshot_id);
            ''')

    def _connect(self):
        db = sqlite3.connect(self.db, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    def _put(self, url, raw, *, source, retrieved_at, observed_at=None, version='UNKNOWN',
             league='UNKNOWN', parser, records):
        timestamp(retrieved_at)
        if observed_at is not None:
            timestamp(observed_at)
        require(isinstance(raw, bytes) and bool(raw), 'EMPTY_SOURCE', url, 'INVALID')
        sha = hashlib.sha256(raw).hexdigest()
        blobs = self.directory / 'blobs'
        blobs.mkdir(exist_ok=True)
        blob = blobs / sha
        if blob.exists():
            require(blob.read_bytes() == raw, 'CORRUPT_SOURCE_BLOB', sha)
        else:
            # Exclusive immutable blob creation. SQLite switches the head only after all rows exist.
            with blob.open('xb') as out:
                out.write(raw)
        with closing(self._connect()) as db, db:
            db.execute('INSERT OR IGNORE INTO snapshots(url,sha256,source,retrieved_at,observed_at,version,league,parser) VALUES(?,?,?,?,?,?,?,?)',
                       (url, sha, source, retrieved_at, observed_at, version, league, parser))
            sid = db.execute('SELECT id FROM snapshots WHERE url=? AND sha256=? AND version=? AND league=?',
                             (url, sha, version, league)).fetchone()[0]
            for index, row in enumerate(records):
                search = ' '.join(str(row.get(key, '')) for key in ('name', 'text', 'item_class', 'pool', 'currency_id'))
                db.execute('INSERT OR IGNORE INTO records VALUES(?,?,?,?,?)',
                           (sid, index, row['kind'], search, json.dumps(row, ensure_ascii=False, sort_keys=True)))
            db.execute('INSERT OR REPLACE INTO heads VALUES(?,?)', (url, sid))
        return {'source_url': url, 'sha256': sha, 'records': len(records), 'retrieved_at': retrieved_at,
                'evidence_status': 'INFERRED', 'version': version, 'parser': parser}

    def put_poe2db(self, url, raw, *, retrieved_at, version='UNKNOWN'):
        validate_poe2db_url(url)
        parsed = extract_poe2db(raw)
        return self._put(url, raw, source='poe2db', retrieved_at=retrieved_at, version=version,
                         parser=PARSER_VERSION, records=parsed['records'])

    def put_page(self, url, raw, *, retrieved_at):
        validate_poe2db_url(url)
        return self._put(url, raw, source='poe2db', retrieved_at=retrieved_at, parser='html-text-v1',
                         records=[{'kind': 'source_page', 'text': plain(raw.decode('utf-8')),
                                   'evidence_status': 'INFERRED'}])

    def put_market(self, document):
        from .market import currency_quote
        book = document.get('price_book', document)
        receipt_time = document.get('receipt', {}).get('observed_at')
        observed = book.get('source_observed_at') or receipt_time or book['as_of']
        timestamp(observed)
        timestamp(book['evidence']['retrieved_at'])
        require((receipt_time is None or receipt_time == observed) and book['as_of'] == observed,
                'MARKET_OBSERVATION_MISMATCH', 'Preserved receipt, observation and as_of must agree')
        require(datetime.fromisoformat(observed) <= datetime.fromisoformat(book['evidence']['retrieved_at']),
                'INVALID_MARKET_OBSERVATION', 'Observation cannot follow retrieval')
        rows = book['source_snapshot']['lines']
        # Existing source enforcement checks provider, URL, snapshot hash, units and every quote.
        for row in rows:
            currency_quote(book, row['id'])
        raw = json.dumps(book['source_snapshot'], ensure_ascii=False, sort_keys=True).encode('utf-8')
        records = [{'kind': 'currency', 'currency_id': row['id'], 'name': row['id'],
                    'source_record': row, 'unit': book['unit'], 'evidence_status': 'INFERRED'} for row in rows]
        return self._put(book['evidence']['reference'], raw, source='poe.ninja',
            retrieved_at=book['evidence']['retrieved_at'],
            observed_at=observed, version=book['version'],
            league=book['league'], parser='ninja-exchange-v1', records=records)

    def raw(self, sha):
        require(bool(re.fullmatch(r'[0-9a-f]{64}', sha)), 'INVALID_SNAPSHOT_ID', sha, 'INVALID')
        path = self.directory / 'blobs' / sha
        require(path.is_file(), 'MISSING_SOURCE_BLOB', sha)
        raw = path.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == sha, 'CORRUPT_SOURCE_BLOB', sha)
        return raw

    def snapshots(self, url):
        with closing(self._connect()) as db:
            return [dict(row) for row in db.execute('SELECT * FROM snapshots WHERE url=? ORDER BY id DESC', (url,))]

    def search(self, query, *, source=None, limit=20):
        require(isinstance(query, str) and query.strip() and isinstance(limit, int) and 1 <= limit <= 200,
                'INVALID_SOURCE_QUERY', 'Nonempty query; limit 1..200', 'INVALID')
        # Literal substring search: parameterized SQL, no wildcard or FTS expression evaluation.
        sql = '''SELECT r.payload,s.* FROM records r JOIN snapshots s ON s.id=r.snapshot_id
                 JOIN heads h ON h.snapshot_id=s.id WHERE instr(lower(r.search_text),lower(?))>0'''
        args = [query]
        if source is not None:
            sql += ' AND s.source=?'
            args.append(source)
        sql += ' ORDER BY s.url,r.ordinal LIMIT ?'
        args.append(limit)
        result, checked = [], set()
        with closing(self._connect()) as db:
            for row in db.execute(sql, args):
                if row['sha256'] not in checked:
                    self.raw(row['sha256'])
                    checked.add(row['sha256'])
                result.append({**json.loads(row['payload']), 'source_url': row['url'],
                    'snapshot_sha256': row['sha256'], 'retrieved_at': row['retrieved_at'],
                    'observed_at': row['observed_at'], 'version': row['version'], 'league': row['league']})
        return {'status': 'OBSERVED', 'offline': True, 'records': result,
                'note': 'Local source observations; not verified solver inputs. Prices retain their original age.'}

    def coverage(self):
        with closing(self._connect()) as db:
            counts = dict(db.execute('''SELECT r.kind,COUNT(*) FROM records r JOIN heads h ON h.snapshot_id=r.snapshot_id GROUP BY r.kind'''))
            sources = db.execute('SELECT COUNT(*) FROM heads').fetchone()[0]
            versions = db.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0]
        return {'status': 'OBSERVED', 'offline': True, 'directory': str(self.directory.resolve()),
                'source_documents': sources, 'preserved_revisions': versions,
                'poe2db_modifier_rows': counts.get('modifier', 0), 'currency_observations': counts.get('currency', 0),
                'verified_solver_records': 0, 'note': 'Observation coverage is not certified pool or mechanic coverage.'}
