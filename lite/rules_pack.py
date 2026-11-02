"""Build and validate a data-only channel asset from this checked-out source."""
import argparse
import datetime as dt
import hashlib
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lite import rule_updates
import claude_setup as c


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--revision', type=int)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    revision = args.revision or int(dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d%H%M%S'))
    data = rule_updates.build_pack(Path(__file__).resolve().parents[1] / 'src', revision)
    c.write_new(args.output, data)
    print('Validated rule pack:', revision, len(data), hashlib.sha256(data).hexdigest())


if __name__ == '__main__':
    main()
