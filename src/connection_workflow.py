"""Offline connection candidate/report orchestration; no client launch or activation."""
from pathlib import Path


def run(c, args):
    import connection_reuse
    import readiness_lifecycle as lifecycle
    import unified_policy

    source = c.read_bytes(args.config)
    fmt = c.config_format(args.config, args.format)
    original = c.parse_config(source, fmt)
    c.config_summary(source, fmt)
    options = {'core': args.core, 'version': args.core_version,
               'node': args.node, 'chrome': args.chrome_fingerprint}
    changed = False
    if args.command == 'connection-plan':
        candidate, rows = connection_reuse.build(c, original, fmt, **options)
        changed = candidate != original
        if not changed:
            rendered = source
        elif fmt == 'json':
            rendered = c.encode(candidate)
        else:
            renderer = unified_policy.render_shadow if fmt == 'shadowrocket' else unified_policy.render_yaml
            text = renderer(c, c.decode(source), candidate)
            rendered = (b'\xef\xbb\xbf' if source.startswith(b'\xef\xbb\xbf') else b'') + text.encode('utf-8')
        c.require(c.parse_config(rendered, fmt) == candidate, 'CONNECTION_RENDER_MISMATCH')
        c.new_dir(args.out)
        output = Path(args.out)
        target = output / ('candidate.' + {'json': 'json', 'yaml': 'yaml', 'shadowrocket': 'conf'}[fmt])
        c.write_new(target, rendered)
        if changed:
            c.prepare_plan(args.config, target, fmt, output / 'plan')
            c.require(c.read_bytes(output / 'plan/original.bin') == source, 'CONNECTION_BASELINE_CHANGED')
    else:
        rows = connection_reuse.audit(c, original, fmt, **options)
    result = lifecycle.save_report(c, args.out, args.command, rows,
        extra={'content_changed': changed, 'apply_supported': False, 'runtime_verified': False,
               'source_sha256': c.sha(source)}, create=args.command != 'connection-plan')
    result.update(content_changed=changed, apply_supported=False)
    return result
