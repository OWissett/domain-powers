"""Put the assessment tools and test helpers on sys.path."""

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parents[1] / "scripts"
_TOOLS = _SCRIPTS / "assess"

for _p in (_SCRIPTS, _TOOLS, _HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
