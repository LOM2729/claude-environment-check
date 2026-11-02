"""Per-operation, data-only rule snapshots. Legacy callers keep bundled data."""
from contextlib import contextmanager
from contextvars import ContextVar
from types import MappingProxyType
from dataclasses import dataclass

FILES = frozenset(('ai_domains.json', 'community_snapshot.json',
                   'domestic_sources.json', 'domestic_cn.list', 'domestic_video.list'))
_CURRENT = ContextVar('clash_rule_snapshot', default=None)


@dataclass(frozen=True, eq=False)
class Snapshot:
    revision: int
    files: object

    def __post_init__(self):
        if set(self.files) != FILES or not all(type(v) is bytes for v in self.files.values()):
            raise ValueError('Invalid rule files')
        object.__setattr__(self, 'files', MappingProxyType(dict(self.files)))


def current():
    return _CURRENT.get()


def override(name):
    snapshot = current()
    return None if snapshot is None else snapshot.files[name]


@contextmanager
def using(snapshot):
    token = _CURRENT.set(snapshot)
    try:
        yield
    finally:
        _CURRENT.reset(token)
