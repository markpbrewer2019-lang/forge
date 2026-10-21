"""Narrow PoE2DB description-to-canonical proposals; parsing never verifies rules."""
from dataclasses import replace
import re

from .model import Action, Evidence, jsonable, require


def source_evidence(row, document):
    return Evidence('poe2db', document['url'], document['retrieved_at'], 'INFERRED', 'POE2',
        document['version'], document['league'], 'Unreviewed source description; not a complete game-mechanic certificate.',
        category='SOURCE_FACT', supporting_fact='; '.join(row['explicit_modifiers'] + row['properties']))


def action_proposal(row, document):
    evidence = source_evidence(row, document)
    result = {'status': 'BLOCKED', 'recognized': False, 'action': None, 'interaction': None,
        'source_id': row['id'], 'source_name': row['name'],
        'source': {'url': document['url'], 'sha256': document['sha256']},
        'unresolved_fields': ['verified_scoped_evidence', 'application_and_special_state_interactions', 'poe_ninja_resource_mapping']}
    floor, unsupported = None, []
    for value in row['properties']:
        match = re.fullmatch(r'Minimum Modifier Level: (\d+)', value)
        if match and int(match.group(1)) >= 1 and floor is None:
            floor = int(match.group(1))
        elif not re.fullmatch(r'Stack Size: \d+ / \d+', value):
            unsupported.append(value)
    if unsupported:
        result['unresolved_fields'].append('unsupported_properties')
        result['unsupported_properties'] = unsupported
    if floor is not None:
        result['source_minimum_modifier_level'] = floor
        result['unresolved_fields'].append('modifier_level_floor_application_scope')
    # Match complete descriptions only. Additional effects must never disappear
    # just because an initial clause happens to match a familiar currency.
    if len(row['explicit_modifiers']) != 1 or row['implicit_modifiers'] or row['enchantments']:
        result['unresolved_fields'].append('unsupported_description')
        return result
    text = row['explicit_modifiers'][0]
    relation = re.fullmatch(r'While this item is active in your inventory your next (.+) will remove the lowest level modifier', text)
    if relation and row['item_class'] == 'Omen':
        result.update(recognized=True, interaction={'applies_to_name': relation.group(1),
            'removal_mode': 'lowest_ilvl', 'evidence': jsonable(evidence)})
        result['unresolved_fields'] += ['activation_consumption_and_compatibility', 'removal_scope', 'removal_tie_rule']
        return result
    if row['item_class'] != 'StackableCurrency':
        result['unresolved_fields'].append('unsupported_source_item_class')
        return result
    operation = None
    rarities, resulting = (), None
    if text == 'Upgrades a Normal item to a Magic item with 1 modifier':
        operation, rarities, resulting = 'add_pool', ('normal',), 'magic'
    elif text == 'Upgrades a Magic item to a Rare item, adding 1 modifier':
        operation, rarities, resulting = 'add_pool', ('magic',), 'rare'
    else:
        match = re.fullmatch(r'Augments a (Magic|Rare) item with a new random modifier', text)
        if match:
            operation, rarities = 'add_pool', (match.group(1).lower(),)
        elif text == 'Removes a random modifier and augments a Rare item with a new random modifier':
            operation, rarities = 'remove_add', ('rare',)
        elif text == 'Removes a random modifier from an item':
            operation = 'remove'
            result['unresolved_fields'].append('allowed_input_rarities')
    if operation is None:
        result['unresolved_fields'].append('unsupported_description')
        return result
    removal = None
    if operation in {'remove', 'remove_add'}:
        # "Random" does not establish a uniform distribution or protection scope.
        removal = {'mode': None, 'scope': None, 'side': None, 'ties': None, 'evidence': jsonable(evidence)}
        result['unresolved_fields'] += ['removal_distribution', 'removal_scope']
    if operation in {'add_pool', 'remove_add'}:
        result['unresolved_fields'].append('certified_action_pool_and_weighting')
    action = Action('source:' + row['id'], operation, evidence, rarities,
        {'UNMAPPED_SOURCE_RESOURCE:' + row['id']: 1}, resulting_rarity=resulting,
        display_name=row['name'], removal_rule=removal, min_mod_ilvl=floor,
        mechanic_context={'unresolved_rules': list(result['unresolved_fields'])})
    result.update(recognized=True, action=jsonable(action))
    return result


def compose_omen(proposal, omen):
    """Produce a whole-action variant; the planner need not be told an omen order."""
    require(proposal['action'] is not None and omen['interaction'] is not None,
            'UNSUPPORTED_SOURCE_COMPOSITION', proposal['source_id'])
    require(omen['interaction']['applies_to_name'] == proposal['source_name']
            and proposal['action']['operation'] == 'remove_add', 'UNKNOWN_OMEN_COMPATIBILITY', omen['source_id'])
    raw = proposal['action'].copy()
    raw['id'] += '+source:' + omen['source_id']
    raw['resources'] = {**raw['resources'], 'UNMAPPED_SOURCE_RESOURCE:' + omen['source_id']: 1}
    raw['removal_rule'] = {**raw['removal_rule'], 'mode': omen['interaction']['removal_mode'],
                           'evidence': omen['interaction']['evidence']}
    unresolved = sorted((set(proposal['unresolved_fields']) - {'removal_distribution'}) | set(omen['unresolved_fields']))
    raw['mechanic_context'] = {'omens': [omen['source_id']], 'interaction_evidence': omen['interaction']['evidence'],
                               'unresolved_rules': unresolved}
    return {**proposal, 'action': raw, 'source_id': raw['id'], 'sources': [proposal['source'], omen['source']],
        'unresolved_fields': unresolved}
