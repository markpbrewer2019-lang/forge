"""Offline, source-bound modifier/base reference and planning preflight.

Projection fields describe PoE2DB's presentation, not an automatic game-mechanic
certification. Raw source bodies remain the authority for coverage comparison.
"""
from contextlib import closing
from fractions import Fraction
from html.parser import HTMLParser
import hashlib
import json
import re
from urllib.parse import urljoin, urlsplit

from .model import require, ForgeError
from .source_store import SourceStore, extract_poe2db, plain, validate_poe2db_url

CATALOG_VERSION = 'poe2db-reference-v4'


class Node:
    def __init__(self, tag='', attrs=None, parent=None, start=0):
        self.tag, self.attrs, self.parent, self.start = tag, dict(attrs or []), parent, start
        self.children, self.end = [], start

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()

    def text(self):
        if self.tag in {'script', 'style'}:
            return ''
        return ''.join(c.text() if isinstance(c, Node) else c for c in self.children)

    def has(self, name):
        return name in self.attrs.get('class', '').split()


class Tree(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.root, self.raw = Node(), text
        self.stack = [self.root]
        self.lines = [0]
        self.lines.extend(m.end() for m in re.finditer('\n', text))
        self.feed(text)

    def position(self):
        line, col = self.getpos()
        return self.lines[line - 1] + col

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.stack[-1], self.position())
        self.stack[-1].children.append(node)
        node.end = node.start + len(self.get_starttag_text())
        if tag not in {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if self.stack[-1].tag == tag:
            self.stack.pop()

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                for node in self.stack[i:]:
                    node.end = self.position() + len(tag) + 3
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def item_category_urls(raw):
    urls = set()
    tree = Tree(raw.decode('utf-8'))
    for section in tree.root.walk():
        if not section.has('itemList'):
            continue
        for node in section.walk():
            if node.tag != 'a' or not node.attrs.get('href'):
                continue
            url = urljoin('https://poe2db.tw/us/Items', node.attrs['href']).split('#')[0]
            try:
                validate_poe2db_url(url)
            except ForgeError:
                continue
            urls.add(url)
    return sorted(urls)


def base_cards(raw, source_url):
    text = raw.decode('utf-8')
    tree, seen, records = Tree(text), set(), []
    for link in tree.root.walk():
        if link.tag != 'a' or not link.text().strip():
            continue
        if '/Poe_Data_BaseItemTypes_hover/' not in link.attrs.get('data-hover', ''):
            continue
        card = link.parent
        while card and not (card.has('d-flex') and card.has('border-top') and card.has('rounded')):
            card = card.parent
        if card is None or card.start in seen:
            continue
        url = urljoin(source_url, link.attrs.get('href', ''))
        try:
            validate_poe2db_url(url)
        except ForgeError:
            continue
        seen.add(card.start)
        properties, requirements, implicit, enchants, explicit = [], [], [], [], []
        for node in card.walk():
            value = ' '.join(node.text().split())
            if node.has('property'): properties.append(value)
            if node.has('requirements'): requirements.append(value)
            if node.has('implicitMod'): implicit.append(value)
            if node.has('enchantMod') or node.has('bondedMod'): enchants.append(value)
            if node.has('explicitMod'): explicit.append(value)
        stats = {}
        for value in properties:
            if ':' in value:
                key, val = value.split(':', 1)
                if key.strip() in stats and stats[key.strip()] != val.strip():
                    # Retain every occurrence instead of selecting a convenient duplicate.
                    prior = stats[key.strip()]
                    stats[key.strip()] = (prior if isinstance(prior, list) else [prior]) + [val.strip()]
                else:
                    stats[key.strip()] = val.strip()
        requirement_text = ' '.join(requirements)
        level = re.search(r'\bLevel\s+(\d+)\b', requirement_text)
        attributes = {name: int(value) for value, name in re.findall(r'\b(\d+)\s+(Str|Dex|Int)\b', requirement_text)}
        classes = link.attrs.get('class', '').split()
        records.append({'kind': 'base', 'id': urlsplit(url).path.rsplit('/', 1)[-1], 'url': url,
            'name': ' '.join(link.text().split()), 'item_class': classes[1] if len(classes) == 2 else None,
            'source_display_classes': classes,
            'required_character_level': int(level.group(1)) if level else None,
            'minimum_drop_item_level': None, 'attribute_requirements': attributes,
            'stats': stats, 'properties': properties, 'implicit_modifiers': implicit,
            'enchantments': enchants, 'explicit_modifiers': explicit,
            'socket_bound': any('Socket-bound' in value for value in enchants),
            'evidence_status': 'INFERRED', 'source_record': {'hover': link.attrs['data-hover'],
                'html': text[card.start:card.end], 'requirements': requirements}})
    return records


def integer(value):
    if isinstance(value, bool) or value is None or not re.fullmatch(r'\d+', str(value)):
        return None
    return int(value)


def static_modifiers(raw, source_url):
    """Retain source-only tables too; an absent Weight column means unavailable."""
    tree = Tree(raw.decode('utf-8'))
    records = []
    for table_index, table in enumerate(n for n in tree.root.walk() if n.tag == 'table'):
        rows = [node for node in table.walk() if node.tag == 'tr']
        if not rows:
            continue
        headers = [' '.join(c.text().split()) for c in rows[0].children if isinstance(c, Node) and c.tag == 'th']
        if 'Description' not in headers or not ({'Level', 'Pre/Suf', 'Domain'} & set(headers)):
            continue
        scope = table.parent
        while scope and not scope.has('card'):
            scope = scope.parent
        heading = next((' '.join(n.text().split()) for n in scope.walk() if n.tag in ('h4', 'h5')), '') if scope else ''
        for ordinal, row in enumerate(rows[1:]):
            cells = [c for c in row.children if isinstance(c, Node) and c.tag in ('td', 'th')]
            require(len(cells) == len(headers), 'POE2DB_TABLE_SCHEMA_CHANGED', f'{source_url} table {table_index} row {ordinal}')
            fields = {key: ' '.join(cell.text().split()) for key, cell in zip(headers, cells)}
            weight_cell = cells[headers.index('Weight')] if 'Weight' in headers else None
            entries, unresolved = [], []
            if weight_cell and integer(fields.get('Weight')) is None and fields.get('Weight'):
                # Conditional source tables use ordered <i>tag</i> value<br>
                # entries. Preserve their conditions; do not choose one by guess.
                segments = re.split(r'<br\s*/?>', tree.raw[weight_cell.start:weight_cell.end], flags=re.I)
                for segment in segments:
                    if not plain(segment):
                        continue
                    match = re.search(r'<i>([^<]+)</i>\s*(\d+)\s*(?:</td>)?\s*$', segment)
                    if match:
                        entries.append({'condition': plain(match.group(1)), 'weight': int(match.group(2))})
                    else:
                        unresolved.append('weight_cell_normalization')
                unresolved.append('conditional_weight_evaluation' if entries else 'weight_cell_normalization')
            hover = next((n.attrs['data-hover'] for n in row.walk() if '/Poe_Data_Mods_hover/' in n.attrs.get('data-hover', '')), None)
            source_id = hover or hashlib.sha256(packed(fields).encode()).hexdigest()
            side = fields.get('Pre/Suf', '').lower()
            records.append({'kind': 'modifier', 'id': f"{urlsplit(source_url).path.rsplit('/', 1)[-1]}::table-{table_index}::{source_id}",
                'source_id': source_id, 'source_mod_code': None, 'name': fields.get('Name', ''),
                'text': fields['Description'], 'item_class': None, 'pool': 'table:' + heading,
                'source_table': table_index, 'ordinal': ordinal, 'ilvl': integer(fields.get('Level')),
                'weight': integer(fields.get('Weight')), 'side': side if side in {'prefix', 'suffix'} else None,
                'weight_entries': entries, 'planner_unresolved_fields': sorted(set(unresolved)),
                'tier': None, 'families': None, 'crafting_tags': None, 'spawn_tags': None,
                'field_semantics': 'POE2DB_DISPLAY', 'game_probability_certified': False,
                'weight_semantics': 'POE2DB_DISPLAY_RELATIVE_WEIGHT', 'evidence_status': 'INFERRED',
                'source_record': fields, 'source_row_html': tree.raw[row.start:row.end],
                'source_unavailable_fields': [field for field, key in (('ilvl', 'Level'), ('weight', 'Weight'), ('text', 'Description')) if not fields.get(key)]})
    return records


def project(raw, url):
    records = []
    if re.search(rb'\bnew\s+ModsView\s*\(', raw):
        parsed = extract_poe2db(raw)
        contexts = [index for index, view in enumerate(parsed['views'])
                    for key, values in view.items() if key != 'ids' and isinstance(values, list) for _ in values]
        for view_index, row in zip(contexts, parsed['records']):
            source = row['source_record']
            source_id = source.get('Code') or source.get('hover') or hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()
            view_scope = f'::view-{view_index}' if len(parsed['views']) > 1 else ''
            record = {**row, 'id': f"{urlsplit(url).path.rsplit('/', 1)[-1]}{view_scope}::{row['pool']}::{source_id}",
                'source_view': view_index,
                'source_id': source_id, 'source_mod_code': source.get('Code'),
                'ilvl': integer(source.get('Level')), 'weight': integer(source.get('DropChance')),
                'side': row.get('reported_generation', '').lower() if row.get('reported_generation') in ('Prefix', 'Suffix') else None,
                'families': source.get('ModFamilyList'), 'crafting_tags': None, 'source_filter_tags': source.get('fossil_no'),
                'spawn_tags': None, 'source_spawn_filters': source.get('spawn_no'), 'field_semantics': 'POE2DB_DISPLAY',
                'game_probability_certified': False, 'weight_semantics': 'POE2DB_DISPLAY_RELATIVE_WEIGHT',
                'source_unavailable_fields': [field for field, key in (('ilvl', 'Level'), ('weight', 'DropChance'))
                                              if source.get(key) is None]}
            records.append(record)
        # Match the site's *display* tier algorithm: descending distinct levels,
        # separately for pool, generation type and first family. This is not a
        # new assertion about eligibility or conditional in-game weighting.
        groups = {}
        for row in records:
            families = row.get('families')
            if row['ilvl'] is not None and families:
                key = (row['source_view'], row['pool'], row.get('item_class'), row['source_record'].get('ModGenerationTypeID'), families[0])
                groups.setdefault(key, set()).add(row['ilvl'])
        for row in records:
            families = row.get('families')
            if row['ilvl'] is not None and families:
                key = (row['source_view'], row['pool'], row.get('item_class'), row['source_record'].get('ModGenerationTypeID'), families[0])
                row['display_tier'] = sorted(groups[key], reverse=True).index(row['ilvl']) + 1
            else:
                row['display_tier'] = None
    records.extend(static_modifiers(raw, url))
    records.extend(base_cards(raw, url))
    return records


def packed(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def raw_inventory(raw):
    """Count source structures without invoking the row projection under audit."""
    text = raw.decode('utf-8')
    counts = {'modifier': 0, 'base': 0}
    for match in re.finditer(r'\bnew\s+ModsView\s*\(', text):
        document, _ = json.JSONDecoder().raw_decode(text[match.end():].lstrip())
        counts['modifier'] += sum(len(value) for key, value in document.items() if key != 'ids' and isinstance(value, list))
    tree, cards = Tree(text), set()
    for node in tree.root.walk():
        if node.tag == 'table':
            rows = [r for r in node.walk() if r.tag == 'tr']
            if not rows:
                continue
            headers = {' '.join(c.text().split()) for c in rows[0].children if isinstance(c, Node) and c.tag == 'th'}
            if 'Description' in headers and headers & {'Level', 'Pre/Suf', 'Domain'}:
                counts['modifier'] += len(rows) - 1
        if node.tag == 'a' and node.text().strip() and '/Poe_Data_BaseItemTypes_hover/' in node.attrs.get('data-hover', ''):
            parent = node.parent
            while parent:
                if {'d-flex', 'border-top', 'rounded'} <= set(parent.attrs.get('class', '').split()):
                    cards.add(parent.start)
                    break
                parent = parent.parent
    counts['base'] = len(cards)
    return counts


class Catalog:
    def __init__(self, source_store):
        self.sources = source_store
        with closing(self.sources._connect()) as db, db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS catalog_rows (
                    source_url TEXT NOT NULL, snapshot_sha256 TEXT NOT NULL, ordinal INTEGER NOT NULL,
                    kind TEXT NOT NULL, record_id TEXT NOT NULL, item_class TEXT, pool TEXT,
                    ilvl INTEGER, weight INTEGER, payload TEXT NOT NULL,
                    PRIMARY KEY(source_url, ordinal));
                CREATE INDEX IF NOT EXISTS catalog_lookup ON catalog_rows(kind,record_id,item_class,ilvl);
                CREATE TABLE IF NOT EXISTS catalog_meta (name TEXT PRIMARY KEY, value TEXT NOT NULL);
            ''')

    def documents(self):
        with closing(self.sources._connect()) as db:
            return [dict(row) for row in db.execute('''SELECT s.* FROM snapshots s JOIN heads h ON h.snapshot_id=s.id
                                                      WHERE s.source='poe2db' AND s.parser!='source-asset-v1' ORDER BY s.url''')]

    def fingerprint(self):
        return hashlib.sha256(packed([CATALOG_VERSION, [(r['url'], r['sha256']) for r in self.documents()]]).encode()).hexdigest()

    def rebuild(self):
        total = 0
        # Capture the source inventory before opening the write transaction. A large
        # rollback-journal write can take an exclusive lock and block nested readers.
        documents = self.documents()
        fingerprint = hashlib.sha256(packed([CATALOG_VERSION, [(r['url'], r['sha256']) for r in documents]]).encode()).hexdigest()
        with closing(self.sources._connect()) as db, db:
            db.execute('DELETE FROM catalog_rows')
            for document in documents:
                rows = project(self.sources.raw(document['sha256']), document['url'])
                for ordinal, row in enumerate(rows):
                    db.execute('INSERT INTO catalog_rows VALUES(?,?,?,?,?,?,?,?,?,?)',
                        (document['url'], document['sha256'], ordinal, row['kind'], row['id'], row.get('item_class'),
                         row.get('pool'), row.get('ilvl'), row.get('weight'), packed(row)))
                total += len(rows)
            db.execute('INSERT OR REPLACE INTO catalog_meta VALUES(?,?)', ('source_fingerprint', fingerprint))
            db.execute('INSERT OR REPLACE INTO catalog_meta VALUES(?,?)', ('version', CATALOG_VERSION))
        return {'status': 'OBSERVED', 'projected_rows': total, 'catalog_version': CATALOG_VERSION}

    def query(self, *, kind='modifier', text=None, record_id=None, item_class=None, pool=None,
              min_ilvl=None, max_ilvl=None, limit=50):
        require(kind in {'modifier', 'base'} and type(limit) is int and 1 <= limit <= 1000,
                'INVALID_CATALOG_QUERY', 'kind modifier/base; limit 1..1000', 'INVALID')
        with closing(self.sources._connect()) as db:
            meta = db.execute("SELECT value FROM catalog_meta WHERE name='source_fingerprint'").fetchone()
            require(meta is not None and meta[0] == self.fingerprint(), 'STALE_CATALOG', 'Rebuild against current saved sources')
            sql, args = 'SELECT * FROM catalog_rows WHERE kind=?', [kind]
            for column, value in [('record_id', record_id), ('item_class', item_class), ('pool', pool)]:
                if value is not None:
                    sql += f' AND {column}=?'
                    args.append(value)
            if text is not None:
                sql += ' AND instr(lower(payload),lower(?))>0'
                args.append(text)
            for comparator, value in [('>=', min_ilvl), ('<=', max_ilvl)]:
                if value is not None:
                    require(type(value) is int and value >= 1, 'INVALID_CATALOG_QUERY', 'ilvl must be positive', 'INVALID')
                    sql += ' AND ilvl' + comparator + '?'
                    args.append(value)
            sql += ' ORDER BY record_id,source_url,ordinal LIMIT ?'
            args.append(limit)
            result, checked = [], set()
            for row in db.execute(sql, args):
                if row['snapshot_sha256'] not in checked:
                    self.sources.raw(row['snapshot_sha256'])
                    checked.add(row['snapshot_sha256'])
                result.append({**json.loads(row['payload']), 'source_url': row['source_url'],
                               'snapshot_sha256': row['snapshot_sha256']})
        return {'status': 'OBSERVED', 'offline': True, 'records': result,
                'note': 'Source display levels and weights; full engine eligibility/interaction proof still required.'}

    def audit(self):
        available = matched = missing = mismatched = extra = 0
        by_kind, gaps, unavailable, unresolved, base_ids = {}, [], {}, {}, set()
        with closing(self.sources._connect()) as db:
            actual = {(r['source_url'], r['ordinal']): dict(r) for r in db.execute('SELECT * FROM catalog_rows')}
        expected_keys = set()
        for document in self.documents():
            raw = self.sources.raw(document['sha256'])
            inventory = raw_inventory(raw)
            available += sum(inventory.values())
            for kind, count in inventory.items():
                by_kind.setdefault(kind, {'available': 0, 'matched': 0})['available'] += count
            rows = project(raw, document['url'])
            for kind, count in inventory.items():
                projected = sum(row['kind'] == kind for row in rows)
                if projected != count:
                    missing += max(0, count - projected)
                    gaps.append({'classification': 'INGESTION_FAILURE', 'source': document['url'],
                                 'issue': 'projection_count', 'kind': kind, 'available': count, 'projected': projected})
            for ordinal, row in enumerate(rows):
                if row['kind'] == 'base':
                    base_ids.add(row['id'])
                for field in row.get('planner_unresolved_fields', []):
                    unresolved[field] = unresolved.get(field, 0) + 1
                key = (document['url'], ordinal)
                expected_keys.add(key)
                counts = by_kind.setdefault(row['kind'], {'available': 0, 'matched': 0})
                for field in row.get('source_unavailable_fields', []):
                    unavailable[field] = unavailable.get(field, 0) + 1
                if key not in actual:
                    missing += 1
                    gaps.append({'classification': 'INGESTION_FAILURE', 'source': document['url'], 'ordinal': ordinal, 'issue': 'missing'})
                elif (actual[key]['snapshot_sha256'] != document['sha256'] or actual[key]['payload'] != packed(row)
                      or any(actual[key][column] != value for column, value in {
                          'kind': row['kind'], 'record_id': row['id'], 'item_class': row.get('item_class'),
                          'pool': row.get('pool'), 'ilvl': row.get('ilvl'), 'weight': row.get('weight')}.items())):
                    mismatched += 1
                    gaps.append({'classification': 'INGESTION_FAILURE', 'source': document['url'], 'ordinal': ordinal, 'issue': 'mismatched'})
                else:
                    matched += 1
                    counts['matched'] += 1
        extra = len(set(actual) - expected_keys)
        return {'status': 'OBSERVED' if available and not (missing or mismatched or extra or gaps) else 'BLOCKED',
                'scope': 'Every literal ModsView row, explicit modifier table row and exposed base-type card in current saved source documents; source discovery inventory is reported separately.',
                'available_source_rows': available, 'local_matched_rows': matched, 'missing_rows': missing,
                'mismatched_rows': mismatched, 'extra_rows': extra,
                'coverage_percent': str(Fraction(100 * matched, available)) if available else None,
                'by_kind': by_kind, 'distinct_source_base_ids': len(base_ids),
                'source_unavailable_fields': unavailable, 'planner_unresolved_fields': unresolved, 'gaps': gaps,
                'verified_game_pools': 0, 'source_documents': len(self.documents())}

    def resolve_craft(self, request):
        item = request['item']
        bases = self.query(kind='base', record_id=item['base'])['records']
        targets, blockers = [], []
        if not bases:
            blockers.append({'code': 'BASE_NOT_FOUND', 'base': item['base']})
        for target in request['target']:
            rid = target if isinstance(target, str) else target.get('modifier')
            found = self.query(record_id=rid)['records']
            if not found:
                blockers.append({'code': 'MODIFIER_NOT_FOUND', 'modifier': rid})
                continue
            targets.extend(found)
            for row in found:
                for field in row.get('planner_unresolved_fields', []):
                    blockers.append({'code': 'UNRESOLVED_SOURCE_INTERPRETATION', 'modifier': rid, 'field': field})
                for field in row['source_unavailable_fields']:
                    blockers.append({'code': 'SOURCE_UNAVAILABLE', 'modifier': rid, 'field': field})
                if row['ilvl'] is not None and item['ilvl'] < row['ilvl']:
                    blockers.append({'code': 'MODIFIER_ILVL_REQUIREMENT_NOT_MET', 'modifier': rid, 'required': row['ilvl']})
        blockers.extend([{'code': 'VERIFIED_ACTION_SEMANTICS', 'detail': 'No reviewed source-to-transition grammar is installed for this real craft.'},
            {'code': 'CERTIFIED_SCOPED_POOLS', 'detail': 'Source rows alone do not certify complete action/base/item-level pools or conditional weighting.'},
            {'code': 'VERIFIED_PHYSICAL_STATE_RULES', 'detail': 'Rarity capacities, sockets, fractures and special-state interactions must be evidenced for the requested base.'},
            {'code': 'VERIFIED_GAME_VERSION', 'detail': 'The local source inventory is not yet mapped to a reviewed game version.'},
            {'code': 'CURRENT_SELECTED_LEAGUE_PRICES', 'detail': 'Real recommendations require current matching poe.ninja API quotes; historical observations cannot authorize spend.'}])
        return {'status': 'BLOCKED', 'phase': 'SOURCE_TO_PLANNER', 'bases': bases, 'targets': targets,
                'source_grammar': self.action_inventory(),
                'blockers': blockers, 'golden6': None, 'note': 'References resolved offline. No currency action is recommended without full proof.'}

    def action_rule(self, record_id):
        from .grammar import action_proposal
        records = self.query(kind='base', record_id=record_id, limit=1000)['records']
        require(bool(records), 'BASE_NOT_FOUND', record_id)
        require(len(records) < 1000, 'SOURCE_REFERENCE_LIMIT', record_id)
        for field in ('name', 'item_class'):
            require(len({r[field] for r in records if r[field]}) <= 1, 'CONFLICTING_SOURCE_PROPERTIES', f'{record_id}.{field}')
        properties, observed = set(), {}
        for record in records:
            for value in record['properties']:
                key, separator, content = value.partition(':')
                observed.setdefault(key, set()).add(content.strip() if separator else value)
                properties.add(value)
        require(all(len(values) == 1 for values in observed.values()), 'CONFLICTING_SOURCE_PROPERTIES', record_id)
        described = [r for r in records if r['explicit_modifiers'] or r['implicit_modifiers'] or r['enchantments']]
        references = [r for r in records if r not in described]
        # A reward-list link supplies no description; absence there is not an
        # assertion that the fully described item's effects do not exist.
        records = described or records
        signatures = {packed([r['implicit_modifiers'], r['explicit_modifiers'], r['enchantments']]) for r in records}
        require(len(signatures) == 1, 'CONFLICTING_SOURCE_PROPERTIES', record_id)
        complete = [r for r in records if set(r['properties']) == properties]
        require(bool(complete), 'SOURCE_PROPERTIES_REQUIRE_REVIEW', record_id)
        records = complete
        document = next(d for d in self.documents() if d['url'] == records[0]['source_url'])
        return {**action_proposal(records[0], document), 'descriptionless_references': [
            {'url': r['source_url'], 'sha256': r['snapshot_sha256']} for r in references]}

    def action_inventory(self):
        from .grammar import compose_omen
        # query performs the saved-source/version staleness gate. Collect every ID
        # directly instead of silently truncating a paginated source inventory.
        self.query(kind='base', limit=1)
        with closing(self.sources._connect()) as db:
            ids = [r[0] for r in db.execute("SELECT DISTINCT record_id FROM catalog_rows WHERE kind='base' AND item_class IN ('StackableCurrency','Omen') ORDER BY record_id")]
        proposals, conflicts = [], []
        for rid in ids:
            try:
                proposals.append(self.action_rule(rid))
            except ForgeError as exc:
                if exc.code not in {'CONFLICTING_SOURCE_PROPERTIES', 'SOURCE_PROPERTIES_REQUIRE_REVIEW'}:
                    raise
                conflicts.append({'id': rid, 'code': exc.code})
        interactions = [p for p in proposals if p['interaction'] is not None]
        actions = [p for p in proposals if p['action'] is not None]
        variants = list(actions)
        for action in actions:
            for omen in interactions:
                if action['action']['operation'] == 'remove_add' and omen['interaction']['applies_to_name'] == action['source_name']:
                    variants.append(compose_omen(action, omen))
        return {'status': 'BLOCKED', 'scope': 'StackableCurrency and Omen source cards; no automatic verification.',
            'source_items': len(ids), 'recognized_action_variants': len(variants), 'recognized_interactions': len(interactions),
            'unrecognized_items': [p['source_id'] for p in proposals if not p['recognized']], 'conflicts': conflicts,
            'candidates': [{'id': p['source_id'], 'operation': p['action']['operation'],
                            'unresolved_fields': p['unresolved_fields']} for p in variants]}

    def property_rule(self, record_id):
        """Expose a reviewable physical-rule candidate, never a certified rule.

        Parsing an equipment description does not establish application legality,
        socket consumption, incompatible states, or the scope of removal rules.
        Those fields deliberately retain the engine's fail-closed None values.
        """
        records = self.query(kind='base', record_id=record_id, limit=1000)['records']
        require(bool(records), 'BASE_NOT_FOUND', record_id)
        signatures = {packed([r['implicit_modifiers'], r['enchantments'], r['explicit_modifiers']]) for r in records}
        require(len(signatures) == 1, 'CONFLICTING_SOURCE_PROPERTIES', record_id)
        row = records[0]
        document = next(d for d in self.documents() if d['url'] == row['source_url'])
        capacity, unparsed = {}, [v for v in row['enchantments'] if v != 'Socket-bound'] + row['explicit_modifiers']
        for text in row['implicit_modifiers']:
            match = re.fullmatch(r'All Equipment: \+(\d+) (Prefix|Suffix) Modifier allowed(?:, local maximum mods allowed \+ \[(\d+)\])?', text)
            if match and (match.group(3) is None or match.group(3) == match.group(1)) and match.group(2).lower() not in capacity:
                capacity[match.group(2).lower()] = int(match.group(1))
            else:
                unparsed.append(text)
        rule = {'id': 'installed:' + record_id,
                'evidence': {'status': 'INFERRED', 'source': 'poe2db', 'reference': row['source_url'],
                             'version': 'UNKNOWN', 'league': 'UNKNOWN', 'category': 'SOURCE_FACT',
                             'retrieved_at': document['retrieved_at'], 'domain': 'POE2',
                             'notes': 'Unreviewed description-derived physical-property proposal.',
                             'supporting_fact': '; '.join(row['implicit_modifiers'] + row['enchantments'])},
                'permanent': True if row['socket_bound'] else None,
                'capacity_delta': capacity if capacity and not unparsed else None,
                'occupied_sockets': None, 'incompatible_flags': None,
                'forbidden_actions': None, 'forbidden_operations': None}
        return {'status': 'BLOCKED', 'proposed_flag_rule': rule,
                'unresolved_fields': [key for key, value in rule.items() if value is None] + ['verified_evidence', 'application_legality'],
                'unparsed_effects': unparsed, 'sources': [{'url': r['source_url'], 'sha256': r['snapshot_sha256']} for r in records],
                'note': 'Unreviewed description-derived proposal; missing physical semantics block engine execution.'}
