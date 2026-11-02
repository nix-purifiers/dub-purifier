#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Import actual native ARM profiles captured by the first CI run."""

import json
from pathlib import Path
import sys

path = Path(__file__).resolve().parents[1] / "examples/minimal/dub-purifier.lock.json"
current = json.loads(path.read_text())
incoming = json.loads(Path(sys.argv[1]).read_text())
assert current["manifests"] == incoming["manifests"]
assert current["toolVersions"] == incoming["toolVersions"]
arm = {
    name: p
    for name, p in incoming["profiles"].items()
    if p["system"] == "aarch64-linux"
}
assert len(arm) == 3
current["profiles"].update(arm)
path.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")
