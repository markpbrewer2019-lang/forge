"""Invented atomic operations; no real-game mechanic is verified by these tests."""
import json
import unittest
from dataclasses import replace
from fractions import Fraction

from forge.engine import Engine
from forge.fixtures import universe
from forge.model import Action, PoolCertificate, ForgeError, jsonable, Dataset, dataset_document
from forge.planner import plan_ladder
from forge.routes import replay


class CompoundActionTests(unittest.TestCase):
    def setUp(self):
        self.data, self.prices, self.start = universe()
        self.ev = next(iter(self.data.actions.values())).evidence

    def install(self, *, mode='uniform', side='prefix', ties=None):
        rule = {'mode': mode, 'scope': 'eligible', 'side': side, 'ties': ties, 'evidence': jsonable(self.ev)}
        self.data.actions = {'reroll': Action('reroll', 'remove_add', self.ev, ('rare',), {'reroll': 1},
            side='prefix', removal_rule=rule)}
        self.data.pools = (PoolCertificate(self.start.base, 'reroll', 1, 100, ('power', 'junk'), self.ev),)
        self.prices.quotes['reroll'] = '3'
        return Engine(self.data)

    def test_atomic_remove_then_add_uses_pool_after_removal(self):
        engine = self.install()
        before = replace(self.start, mods=('junk', 'speed'))
        outcomes = engine.transition(before, 'reroll')
        self.assertEqual({('junk', 'power'), ('junk', 'junk')}, {tuple(json.loads(o.label)) for o in outcomes})
        self.assertEqual([Fraction(1, 2)] * 2, [o.probability for o in outcomes])
        self.assertTrue(all(len(o.state.mods) == 2 for o in outcomes))
        self.assertTrue(all(o.removed == ('junk',) for o in outcomes))
        self.assertEqual(self.data.key, Dataset.load(dataset_document(self.data)).key)

    def test_invalid_removal_branch_is_not_discarded_or_renormalized(self):
        engine = self.install(side=None)
        with self.assertRaisesRegex(ForgeError, 'EMPTY_COMPOUND_BRANCH'):
            engine.transition(replace(self.start, mods=('junk', 'speed')), 'reroll')

    def test_lowest_level_tie_requires_explicit_tie_rule(self):
        engine = self.install(mode='lowest_ilvl', side=None)
        with self.assertRaisesRegex(ForgeError, 'UNKNOWN_REMOVAL_TIE_RULE'):
            engine.transition(replace(self.start, mods=('junk', 'speed')), 'reroll')

    def test_rare_upgrade_uses_resulting_rarity_slots_and_explicit_level_floor(self):
        self.data.modifiers['power'] = replace(self.data.modifiers['power'], ilvl=50)
        self.data.actions = {'upgrade': Action('upgrade', 'add_pool', self.ev, ('normal',), {},
            resulting_rarity='rare', min_mod_ilvl=50)}
        self.data.pools = (PoolCertificate(self.start.base, 'upgrade', 1, 100, ('power', 'junk'), self.ev),)
        outcomes = Engine(self.data).transition(replace(self.start, ilvl=80, rarity='normal'), 'upgrade')
        self.assertEqual(1, len(outcomes))
        self.assertEqual(('power',), outcomes[0].state.mods)
        self.assertEqual('rare', outcomes[0].state.rarity)

    def test_planner_derives_final_rarity_when_target_does_not_prescribe_it(self):
        self.data.actions = {'upgrade': Action('upgrade', 'add_pool', self.ev, ('normal',), {}, resulting_rarity='rare')}
        self.data.pools = (PoolCertificate(self.start.base, 'upgrade', 1, 100, ('power',), self.ev),)
        engine = Engine(self.data)
        start = replace(self.start, rarity='normal')
        for optimizer in ('enumerate', 'policy_iteration'):
            result = plan_ladder(engine, start, ['power'], self.prices, base_owned=True, optimizer=optimizer)
            self.assertIsNotNone(result['winner'], result)
            proof = replay(engine, result['winner']['plan'])
            self.assertEqual({'rare'}, {proof.states[k].rarity for k in proof.terminals})
        with self.assertRaisesRegex(ForgeError, 'AFFIX_CAPACITY_EXCEEDED'):
            plan_ladder(engine, start, ['power'], self.prices, base_owned=True, target_state={'rarity': 'normal'})

    def test_full_route_ev_charges_atomic_action_once_per_attempt(self):
        engine = self.install()
        start = replace(self.start, mods=('junk', 'speed'))
        result = plan_ladder(engine, start, ['power', 'speed'], self.prices, base_owned=True,
            optimizer='policy_iteration', keeper_policy={'lock_on_acquire': True})
        winner = result['winner']
        self.assertIsNotNone(winner, result)
        self.assertEqual(Fraction(6), winner['economics']['expected_total_cost'])
        proof = replay(engine, winner['plan'])
        self.assertTrue(all(len(state.mods) == 2 for state in proof.states.values()))

    def test_rerolling_a_keeper_is_loss_even_if_same_modifier_returns(self):
        from forge.keepers import KeeperPolicy
        policy = KeeperPolicy.load({'initial': ['power'], 'lock_on_acquire': True})
        item = replace(self.start, mods=('power', 'speed'))
        action = Action('reroll', 'remove_add', self.ev, ('rare',), {})
        with self.assertRaisesRegex(ForgeError, 'INITIAL_KEEPER_LOSS'):
            policy.classify(item, item, ['power', 'speed'], action, removed=('power',))

    def test_standalone_lowest_level_removal_provenance_names_actual_rule(self):
        engine = self.install(mode='lowest_ilvl', side=None, ties='uniform')
        self.data.actions['reroll'] = replace(self.data.actions['reroll'], operation='remove')
        self.data.modifiers['junk'] = replace(self.data.modifiers['junk'], ilvl=2)
        item = replace(self.start, ilvl=10, mods=('junk', 'speed'))
        self.assertEqual('speed', engine.transition(item, 'reroll')[0].label)
        p = engine.transition_provenance(item, 'reroll')
        self.assertEqual('lowest_ilvl', p['removal_rule']['mode'])
        self.assertIn('lowest_ilvl', p['probability_rule']['supporting_fact'])

    def test_tied_uniform_selector_keeps_distinct_victims_even_for_same_final_state(self):
        engine = self.install(mode='lowest_ilvl', side=None, ties='uniform')
        self.data.actions['reroll'] = replace(self.data.actions['reroll'], side=None)
        self.data.pools = (replace(self.data.pools[0], modifier_ids=('power', 'junk', 'speed')),)
        start = replace(self.start, mods=('junk', 'speed'))
        outcomes = engine.transition(start, 'reroll')
        self.assertEqual([Fraction(1, 4), Fraction(1, 4), Fraction(1, 2)], [o.probability for o in outcomes])
        self.assertEqual(3, len({o.label for o in outcomes}))
        for optimizer in ('enumerate', 'policy_iteration'):
            result = plan_ladder(engine, start, ['power', 'speed'], self.prices, base_owned=True,
                optimizer=optimizer, keeper_policy={'lock_on_acquire': True})
            self.assertIsNone(result['winner'], result)

    def test_replay_detects_destroyed_keeper_even_when_exact_same_id_returns(self):
        engine = self.install()
        self.data.pools = (replace(self.data.pools[0], modifier_ids=('power',)),)
        start = replace(self.start, mods=('power', 'speed'))
        plan = {'schema_version': 1, 'dataset_id': self.data.key, 'starting_state': jsonable(start),
            'target': ['power', 'speed'], 'entry': 'roll', 'keeper_policy': {'initial': ['power']},
            'nodes': {'roll': {'objective': 'Invalid keeper reroll', 'action': 'reroll',
                              'branches': {'["power","power"]': 'done'}},
                      'done': {'objective': 'Target', 'terminal': 'success'}}}
        with self.assertRaisesRegex(ForgeError, 'INITIAL_KEEPER_LOSS'):
            replay(engine, plan)

    def test_lowest_selector_uses_declared_eligible_scope_and_preserves_protection(self):
        engine = self.install(mode='lowest_ilvl', side=None)
        self.data.modifiers['junk'] = replace(self.data.modifiers['junk'], ilvl=2)
        before = replace(self.start, ilvl=10, mods=('junk', 'speed'), protected=('speed',))
        outcomes = engine.transition(before, 'reroll')
        self.assertTrue(all(o.removed == ('junk',) and o.state.protected == ('speed',) for o in outcomes))
