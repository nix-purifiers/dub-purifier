# SPDX-License-Identifier: MIT
import json
from pathlib import Path
import sys

metadata = json.loads(Path(sys.argv[1]).read_text())
root = Path(sys.argv[2])
root.mkdir(parents=True, exist_ok=True)
for name, value in metadata["manifests"].items():
    (root / name).write_text(value["content"])
(root / "dub.selections.json").write_text(
    json.dumps(metadata["profile"]["nativeSelections"])
)
# Native DUB derives configurations and dependency build settings from the recipe.
# The application's sources do not contribute to a dependency environment.
(root / "source").mkdir(exist_ok=True)
(root / "source/app.d").write_text("void main() {}\n")
