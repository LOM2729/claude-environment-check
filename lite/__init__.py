"""Lightweight native configuration-copy app; never controls active proxies."""
from pathlib import Path
import sys

_source = Path(__file__).resolve().parents[1] / 'src'
if _source.is_dir() and str(_source) not in sys.path:
    sys.path.insert(0, str(_source))
