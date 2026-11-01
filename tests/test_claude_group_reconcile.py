"""Opt-in reconciliation uses synthetic sources; never operates a proxy client."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import ai_routing as ai
import claude_group as cg
import claude_setup as c
import domestic_policy as domestic
from test_ai_routing import BASE, SHADOW, SECRET


class Context:
    def __init__(self, binding):
        self.app_node_binding = binding

    def __getattr__(self, key):
        return getattr(c, key)


class ClaudeGroupReconciliation(unittest.TestCase):
    formats = ('json', 'shadowrocket')
    node = 'Customer Node'
    group = 'Customer AI'

    def source(self, fmt):
        obj = c.parse_config(SHADOW.encode(), fmt) if fmt == 'shadowrocket' else copy.deepcopy(BASE)
        key = 'rule' if fmt == 'shadowrocket' else 'rules'
        gkey = 'proxy group' if fmt == 'shadowrocket' else 'proxy-groups'
        for label in (self.group, cg.name(self.group)):
            obj[gkey].append(f'{label} = select, {self.node}' if fmt == 'shadowrocket'
                             else ai.expected_group(self.node, label))
        # A partial canonical block with customer rules surrounding it is never
        # accepted implicitly by normalize; explicit preparation can prove this.
        guards = cg.guarded_rules(ai.catalog(c), fmt, self.group)
        obj[key] = [obj[key][0]] + guards[:3] + [
            'DOMAIN,custom-business.test,Foreign', 'GEOIP,CN,DIRECT',
            ('FINAL' if fmt == 'shadowrocket' else 'MATCH') + ',' + self.group]
        return obj

    def attempt(self, obj, fmt, aliases=None, context=c):
        before = copy.deepcopy(obj)
        prepared, report = cg.reconcile(context, obj, fmt, self.node, self.group,
                                        ai.catalog(c), action_aliases=aliases)
        self.assertEqual(obj, before)
        self.assertNotIn(SECRET, json.dumps(report))
        self.assertNotIn(self.node, json.dumps(report))
        return prepared, report

    def conflict(self, obj, fmt, code, **kwargs):
        prepared, report = self.attempt(obj, fmt, **kwargs)
        self.assertIsNone(prepared)
        self.assertEqual(report['status'], 'reconciliation_conflict')
        self.assertIn(code, [x['code'] for x in report['conflicts']])

    def test_opt_in_prepared_source_builds_with_unknown_rules_and_denies_preserved(self):
        for fmt in self.formats:
            with self.subTest(fmt=fmt):
                obj = self.source(fmt)
                with self.assertRaisesRegex(c.SetupError, 'CLAUDE_GROUP_MANAGED_BLOCK_CHANGED'):
                    cg.normalize(c, obj, fmt, self.node, self.group, ai.catalog(c))
                prepared, report = self.attempt(obj, fmt)
                self.assertIsNotNone(prepared, report)
                self.assertEqual(report['status'], 'prepared_requires_policy_build')
                self.assertTrue(report['canonical_regeneration_required'])
                self.assertEqual(report['replaced_udp_rule_indices'], [1])
                self.assertEqual(report['unreachable_reject_indices'], [3])
                self.assertEqual(report['rebound_rule_indices'], [2, 6])
                self.assertEqual(report['source_semantic_sha256'], c.sha(c.encode(obj)))
                self.assertEqual(report['prepared_semantic_sha256'], c.sha(c.encode(prepared)))
                key = 'rule' if fmt == 'shadowrocket' else 'rules'
                self.assertEqual(prepared[key][0], obj[key][0])
                self.assertEqual(prepared[key][-3:-1], obj[key][-3:-1])
                result = domestic.build_semantics(c, prepared, fmt, self.node, self.group)
                guards = cg.guarded_rules(ai.catalog(c), fmt, self.group)
                self.assertEqual(result[key][:len(guards)], guards)
                self.assertIn(obj[key][0], result[key])
                self.assertIn('DOMAIN,custom-business.test,' + self.group, result[key])
                self.assertEqual(domestic.build_semantics(c, result, fmt, self.node, self.group), result)

    def test_reject_before_equivalent_allow_is_not_deleted(self):
        for fmt in self.formats:
            obj = self.source(fmt)
            key = 'rule' if fmt == 'shadowrocket' else 'rules'
            obj[key][2], obj[key][3] = obj[key][3], obj[key][2]
            self.conflict(obj, fmt, 'CLAUDE_RECONCILE_REACHABLE_DENY')

    def test_allow_to_different_node_does_not_prove_reject_unreachable(self):
        for fmt in self.formats:
            obj = self.source(fmt)
            key = 'rule' if fmt == 'shadowrocket' else 'rules'
            obj[key][2] = obj[key][2].replace(cg.name(self.group), 'Foreign')
            self.conflict(obj, fmt, 'CLAUDE_RECONCILE_REACHABLE_DENY')

    def test_unknown_later_deny_is_not_moved_or_deleted(self):
        for fmt in self.formats:
            obj = self.source(fmt)
            key = 'rule' if fmt == 'shadowrocket' else 'rules'
            obj[key].insert(-1, 'DOMAIN,custom-blocked.test,REJECT')
            self.conflict(obj, fmt, 'AI_LATER_REJECT_REVIEW_REQUIRED')

    def test_only_exact_unconditional_native_udp_is_replaced_under_reported_obligation(self):
        for rule in ('AND,((PROTOCOL,UDP)),REJECT', ' and, ((protocol, udp)), reject '):
            obj = self.source('shadowrocket')
            obj['rule'].insert(-1, rule)
            prepared, report = self.attempt(obj, 'shadowrocket')
            self.assertIsNotNone(prepared, report)
            self.assertEqual(report['replaced_global_udp_rule_indices'], [6])
            self.assertTrue(report['global_udp_regeneration_required'])
            self.assertNotIn(rule, prepared['rule'])
            result = domestic.build_semantics(c, prepared, 'shadowrocket', self.node, self.group)
            import shadow_domestic
            self.assertEqual(result['rule'].count(shadow_domestic.UDP_RULE), 1)
        for rule in ('AND,((PROTOCOL,UDP),(DOMAIN,customer.test)),REJECT',
                     'AND,((PROTOCOL,UDP)),REJECT-DROP'):
            obj = self.source('shadowrocket')
            obj['rule'].insert(-1, rule)
            self.conflict(obj, 'shadowrocket', 'AI_LATER_REJECT_REVIEW_REQUIRED')

    def test_existing_deny_overlapping_protected_scope_is_not_bypassed(self):
        for fmt in self.formats:
            obj = self.source(fmt)
            key = 'rule' if fmt == 'shadowrocket' else 'rules'
            obj[key][0] = 'DOMAIN-SUFFIX,com,REJECT'
            self.conflict(obj, fmt, 'DOMESTIC_EXISTING_DENY_REVIEW_REQUIRED')

    def test_group_binding_fallback_options_and_collisions_fail_closed(self):
        for fmt in self.formats:
            for mutation in ('other_node', 'fallback', 'options', 'duplicate', 'node_collision', 'case_collision'):
                with self.subTest(fmt=fmt, mutation=mutation):
                    obj = self.source(fmt)
                    gkey = 'proxy group' if fmt == 'shadowrocket' else 'proxy-groups'
                    if mutation in ('duplicate', 'case_collision'):
                        extra = copy.deepcopy(obj[gkey][-1])
                        if mutation == 'case_collision':
                            extra = extra.replace(cg.name(self.group), cg.name(self.group).upper()) if fmt == 'shadowrocket' else dict(extra, name=cg.name(self.group).upper())
                        obj[gkey].append(extra)
                    elif mutation == 'node_collision':
                        if fmt == 'shadowrocket':
                            obj['proxy'].append(self.group + ' = socks5, 192.0.2.11, 1080')
                        else:
                            obj['proxies'].append(dict(obj['proxies'][0], name=self.group))
                    elif fmt == 'shadowrocket':
                        obj[gkey][-1] = cg.name(self.group) + ' = select, ' + {
                            'other_node': 'Other Node', 'fallback': self.node + ', DIRECT',
                            'options': self.node + ', policy-select-name=other'}[mutation]
                    else:
                        if mutation == 'options':
                            obj[gkey][-1]['use'] = ['external']
                        else:
                            obj[gkey][-1]['proxies'] = ['Other Node'] if mutation == 'other_node' else [self.node, 'DIRECT']
                    prepared, report = self.attempt(obj, fmt)
                    self.assertIsNone(prepared)
                    self.assertTrue(report['conflicts'])

    def test_nested_and_recursive_groups_are_not_flattened(self):
        for fmt in self.formats:
            for recursive in (False, True):
                obj = self.source(fmt)
                gkey = 'proxy group' if fmt == 'shadowrocket' else 'proxy-groups'
                member = 'Foreign' if recursive else self.group
                if fmt == 'shadowrocket':
                    obj[gkey][0] = 'Foreign = select, ' + member
                else:
                    obj[gkey][0]['proxies'] = [member]
                self.conflict(obj, fmt, 'CLAUDE_RECONCILE_NESTED_GROUP_REVIEW_REQUIRED')

    def test_external_and_unknown_group_members_are_not_inferred(self):
        obj = self.source('shadowrocket')
        obj['proxy group'][0] += ', include-other-group=external'
        self.conflict(obj, 'shadowrocket', 'CLAUDE_RECONCILE_EXTERNAL_GROUP_REVIEW_REQUIRED')
        obj = self.source('json')
        obj['proxy-groups'][0]['use'] = ['external']
        self.conflict(obj, 'json', 'CLAUDE_RECONCILE_EXTERNAL_GROUP_REVIEW_REQUIRED')
        for fmt in self.formats:
            obj = self.source(fmt)
            if fmt == 'shadowrocket':
                obj['proxy group'][0] = 'Foreign = select, Missing Node'
            else:
                obj['proxy-groups'][0]['proxies'] = ['Missing Node']
            self.conflict(obj, fmt, 'CLAUDE_RECONCILE_UNRESOLVED_GROUP_MEMBER')

    def test_scripts_and_includes_are_refused(self):
        for fmt in self.formats:
            obj = self.source(fmt)
            obj['script'] = ['opaque'] if fmt == 'shadowrocket' else {'code': 'opaque'}
            self.conflict(obj, fmt, 'AI_SCRIPT_REVIEW_REQUIRED')
        obj = self.source('shadowrocket')
        obj['general'].append('include = local-private.conf')
        self.conflict(obj, 'shadowrocket', 'AI_INCLUDE_REVIEW_REQUIRED')

    def test_unresolved_actions_require_explicit_narrow_case_aliases(self):
        for fmt in self.formats:
            obj = self.source(fmt)
            key = 'rule' if fmt == 'shadowrocket' else 'rules'
            old = cg.name(self.group).upper()
            obj[key][2] = obj[key][2].replace(cg.name(self.group), old)
            self.conflict(obj, fmt, 'CLAUDE_RECONCILE_UNRESOLVED_ACTION')
            prepared, report = self.attempt(obj, fmt, {old: cg.name(self.group)})
            self.assertIsNotNone(prepared, report)
            self.assertEqual(report['aliased_rule_indices'], [2])
            self.conflict(obj, fmt, 'CLAUDE_RECONCILE_ALIAS_INVALID', aliases={'Arbitrary': self.group})
            self.conflict(obj, fmt, 'CLAUDE_RECONCILE_ALIAS_INVALID', aliases={'Foreign': self.group})

    def test_proxy_alias_requires_explicit_app_binding_and_keeps_options(self):
        fmt = 'shadowrocket'
        obj = self.source(fmt)
        obj['rule'].insert(-1, 'IP-CIDR,192.0.2.0/24,PROXY,no-resolve')
        self.conflict(obj, fmt, 'CLAUDE_RECONCILE_APP_BINDING_REQUIRED', aliases={'PROXY': self.node})
        context = Context({'schema': 'shadowrocket-app-node/1', 'name': self.node,
                           'type': 'socks5', 'server_family': 'ipv4', 'port': 1080, 'chain': 'none',
                           'client_version': '1.0.0', 'observation_source': 'native_ui'})
        prepared, report = self.attempt(obj, fmt, {'PROXY': self.node}, context)
        self.assertIsNotNone(prepared, report)
        self.assertIn('IP-CIDR,192.0.2.0/24,' + self.node + ',no-resolve', prepared['rule'])
        self.assertEqual(report['aliased_rule_indices'], [6])
        invalid = Context(dict(context.app_node_binding, chain='unreviewed'))
        self.conflict(obj, fmt, 'APP_NODE_METADATA_INVALID',
                      aliases={'PROXY': self.node}, context=invalid)
        self.conflict(obj, fmt, 'CLAUDE_RECONCILE_ALIAS_INVALID', aliases={'DIRECT': self.node})


if __name__ == '__main__':
    unittest.main()
