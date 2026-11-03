"""Put the assessment tools and test helpers on sys.path."""

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_TOOLS = _HERE.parents[1] / "skills" / "assessing-domain-migration" / "tools"

for _p in (_TOOLS, _HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
