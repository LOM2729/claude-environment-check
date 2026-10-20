#!/usr/bin/env python3
"""Build a portable customer kit from an explicit allowlist, never runtime records."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
COMMON_REFS = ('billing-checks.md', 'change-confirmation.md', 'customer-setup.md',
               'evidence-sources.md', 'execution-paths.md', 'guided-workflow.md',
               'locale-and-language.md', 'proxy-import.md', 'score-check.md', 'automation.md', 'automatic-configuration.md', 'ai-dedicated-routing.md', 'lifecycle-checks.md', 'five-step-setup.md', 'unified-ipv4.md', 'domestic-video-udp.md', 'shadowrocket-domestic.md', 'service-routing-checks.md')
ROOT_FILES = ('START-HERE.md', '启动提示词.txt', '自动配置启动提示词.txt', 'AGENTS.md', 'README.md', 'requirements.txt',
              'VERSION', '客户配置/放置说明.txt', '交付记录/记录说明.txt')


def files():
    result = list(ROOT_FILES)
    for system in ('mac', 'windows'):
        base = f'.agents/skills/claude-{system}-readiness/'
        extras = ('article-claims.md', 'mac-checks.md', 'related-source-review.md') if system == 'mac' else ('claim-review.md', 'windows-checks.md')
        result += [base + x for x in ('SKILL.md', 'assets/customer-checklist.md', 'assets/report-template.md',
                                     'scripts/claude_setup.py', 'scripts/ai_routing.py', 'scripts/claude_group.py', 'scripts/ai_domains.json', 'scripts/network_checks.py', 'scripts/dns_readiness.py', 'scripts/shadow_domestic.py', 'scripts/domestic_policy.py', 'scripts/domestic_cn.list', 'scripts/domestic_video.list', 'scripts/domestic_sources.json', 'scripts/DOMESTIC-DATA-LICENSE.txt', 'scripts/unified_policy.py', 'scripts/contact_checks.py', 'scripts/ipv6_scope.py', 'scripts/check_ipv6_binding.ps1', 'scripts/readiness_lifecycle.py', 'scripts/collect_dns_identity.ps1', 'scripts/collect_windows.ps1', 'scripts/requirements.txt')]
        result.append(base + ('scripts/check-env.zsh' if system == 'mac' else 'scripts/check-env.ps1'))
        result += [base + 'references/' + x for x in COMMON_REFS + extras]
    return result


def synchronize():
    for system in ('mac', 'windows'):
        scripts = ROOT / f'.agents/skills/claude-{system}-readiness/scripts'
        for name in ('claude_setup.py', 'ai_routing.py', 'claude_group.py', 'ai_domains.json', 'network_checks.py', 'dns_readiness.py', 'shadow_domestic.py', 'domestic_policy.py', 'domestic_cn.list', 'domestic_video.list', 'domestic_sources.json', 'DOMESTIC-DATA-LICENSE.txt', 'unified_policy.py', 'contact_checks.py', 'ipv6_scope.py', 'check_ipv6_binding.ps1', 'readiness_lifecycle.py', 'collect_dns_identity.ps1', 'collect_windows.ps1'):
            shutil.copyfile(ROOT / 'src' / name, scripts / name)
        shutil.copyfile(ROOT / 'requirements.txt', scripts / 'requirements.txt')


def validate():
    allowed = set(files())
    for relative in allowed:
        p = ROOT / relative
        assert p.is_file() and not p.is_symlink(), relative
        text = p.read_text(encoding='utf-8')
        assert '/Users/lingyu/' not in text and '/var/folders/' not in text, relative
        if p.suffix == '.md':
            for target in re.findall(r'\]\(([^)]+)\)', text):
                if target.startswith(('https://', 'http://', '#')):
                    continue
                dest = (p.parent / target.split('#')[0]).resolve()
                assert dest.is_file() or dest.is_dir(), (relative, target)
                if dest.is_file():
                    assert dest.relative_to(ROOT).as_posix() in allowed, (relative, target, 'not bundled')
    for system in ('mac', 'windows'):
        skill = ROOT / f'.agents/skills/claude-{system}-readiness'
        for name in ('claude_setup.py', 'ai_routing.py', 'claude_group.py', 'ai_domains.json', 'network_checks.py', 'dns_readiness.py', 'shadow_domestic.py', 'domestic_policy.py', 'domestic_cn.list', 'domestic_video.list', 'domestic_sources.json', 'DOMESTIC-DATA-LICENSE.txt', 'unified_policy.py', 'contact_checks.py', 'ipv6_scope.py', 'check_ipv6_binding.ps1', 'readiness_lifecycle.py', 'collect_dns_identity.ps1', 'collect_windows.ps1'):
            assert (ROOT / 'src' / name).read_bytes() == (skill / 'scripts' / name).read_bytes(), 'out-of-sync tools'
        assert (ROOT / 'requirements.txt').read_bytes() == (skill / 'scripts/requirements.txt').read_bytes()
        import yaml
        header = (skill / 'SKILL.md').read_text(encoding='utf-8').split('---', 2)[1]
        meta = yaml.safe_load(header)
        assert meta['name'] == f'claude-{system}-readiness' and isinstance(meta['description'], str)
    return allowed


def build():
    synchronize()
    allowed = validate()
    version = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
    dist = ROOT / 'dist'
    dist.mkdir(exist_ok=True)
    archive = dist / 'Claude-Setup-Kit.zip'
    with tempfile.TemporaryDirectory() as temporary:
        kit = Path(temporary) / 'Claude-Setup-Kit'
        for relative in sorted(allowed):
            target = kit / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        info = {'name': 'Claude 环境检测', 'version': version,
                'repository': 'https://github.com/LOM2729/claude-environment-check',
                'capabilities': ['baseline_drift_review', 'opt_in_network_probes', 'fresh_preflight_and_opt_in_launch', 'ai_proxy_only_candidate_and_audit', 'codex_batch_configuration_workflow', 'local_metadata_collection', 'offline_reports', 'private_config_diff', 'content_readback_verification'],
                'system_config_apply': False, 'active_network_probes': 'explicit_plan_and_opt_in_only',
                'customer_machine_acceptance': 'requires_target_machine_verification'}
        (kit / 'PACKAGE-INFO.json').write_text(json.dumps(info, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        manifest = ''.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.relative_to(kit).as_posix() + '\n'
                           for p in sorted(kit.rglob('*')) if p.is_file())
        (kit / 'SHA256SUMS.txt').write_text(manifest, encoding='utf-8')
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for p in sorted(kit.rglob('*')):
                if p.is_file():
                    entry = zipfile.ZipInfo('Claude-Setup-Kit/' + p.relative_to(kit).as_posix(), (2026, 10, 20, 0, 0, 0))
                    entry.create_system = 0
                    entry.external_attr = 0x20
                    entry.compress_type = zipfile.ZIP_DEFLATED
                    z.writestr(entry, p.read_bytes())
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None
            for name in z.namelist():
                assert '..' not in PurePosixPath(name).parts and not PurePosixPath(name).is_absolute()
                local = kit / PurePosixPath(name).relative_to('Claude-Setup-Kit')
                assert z.read(name) == local.read_bytes()
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (dist / 'Claude-Setup-Kit.zip.sha256').write_text(digest + '  Claude-Setup-Kit.zip\n', encoding='utf-8')
    shutil.copyfile(archive, dist / f'Claude-Setup-Kit-v{version}.zip')
    print(json.dumps({'version': version, 'files': len(allowed) + 2, 'bytes': archive.stat().st_size, 'sha256': digest}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--sync', action='store_true')
    args = parser.parse_args()
    if args.sync:
        synchronize()
    elif args.check:
        print('Package sources verified:', len(validate()))
    else:
        build()
