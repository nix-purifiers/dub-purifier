# SPDX-License-Identifier: MIT
"""Install only the captured native target; validate actual exported runtime APIs."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

mode, metadata, output, *tools = sys.argv[1:]
profile = json.loads(Path(metadata).read_text())["profile"]
root = Path.cwd().resolve()
relative = Path(profile["targetPath"]) / profile["targetFileName"]
if relative.is_absolute() or ".." in relative.parts:
    raise ValueError("DUB native target escapes project")
source = (root / relative).resolve(strict=True)
if not source.is_relative_to(root) or not source.is_file():
    raise ValueError("DUB native target must be a project-owned file")
output = Path(output).absolute()
destination = output / "lib" / profile["targetFileName"]
if mode == "install":
    shutil.copyfile(source, destination)
    destination.chmod(0o755)
elif mode in ("preflight", "validate"):
    resolved = source
    if mode == "validate":
        resolved = destination.resolve(strict=True)
        if not resolved.is_relative_to(output) or not resolved.is_file():
            raise ValueError("DUB installed native target escapes producer")
        if resolved.read_bytes() != source.read_bytes():
            raise ValueError(
                "DUB installed library differs from captured native target"
            )
    exported = {
        line.split()[-1].split("@")[0]
        for line in subprocess.check_output(
            [tools[0], "-D", "--defined-only", str(resolved)], text=True
        ).splitlines()
        if line.split()
    }
    product = json.loads(os.environ["nativeSpec"])[profile["rootName"]]
    for name, value in product["runtime"].items():
        if name.endswith("Symbol") and value not in exported:
            raise ValueError(
                "DUB native lifecycle symbol is not defined by selected library: "
                + value
            )
else:
    raise ValueError("unknown DUB native installation operation")
