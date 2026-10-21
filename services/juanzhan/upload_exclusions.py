"""Conservative filename-only upload exclusions, shared with the browser."""
import json
from pathlib import Path
import re

RULES=json.loads(Path(__file__).with_suffix('.json').read_text())
FILES={name.lower() for name in RULES['files']}
PATTERNS=[re.compile(pattern) for pattern in RULES['patterns']]

def excluded_file(name):
    return name.lower() in FILES or any(pattern.search(name.lower()) for pattern in PATTERNS)
