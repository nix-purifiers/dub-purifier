#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

REPO = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="dub-eval-") as directory:
    root = Path(directory) / "project"
    shutil.copytree(
        REPO / "examples/minimal",
        root,
        ignore=shutil.ignore_patterns(
            ".dub", ".dub-purifier", "*.log", "purifier-example*"
        ),
    )
    companion = root / "dub-purifier.lock.json"
    original = json.loads(companion.read_text())
    profile = next(iter(original["profiles"]))

    def evaluate():
        expression = f"let lib = (import /nix/store/cm5m4hjjh37s6z82rwa0vhkbcga3m8bq-source {{}}).lib; in (import {REPO}/nix/read-lock.nix {{ inherit lib; }} {{ src = {root}; }}).problems"
        # Use the flake pin on runners, where the local development store path is absent.
        expression = f"let f = builtins.getFlake {json.dumps(str(REPO))}; lib = f.inputs.nixpkgs.lib; in (import {REPO}/nix/read-lock.nix {{ inherit lib; }} {{ src = {root}; }}).problems"
        return json.loads(
            subprocess.check_output(
                ["nix", "eval", "--impure", "--json", "--expr", expression], text=True
            )
        )

    assert evaluate() == []
    mutations = [
        lambda d: d.update(version=99),
        lambda d: d.update(profiles={}),
        lambda d: d["profiles"][profile].update(rootName="../escape"),
        lambda d: d["profiles"][profile].update(system="wrong"),
        lambda d: d["profiles"][profile].update(buildType="plain"),
        lambda d: d["profiles"][profile]["entries"][0].update(path="../escape.zip"),
        lambda d: d["profiles"][profile]["entries"][0].update(hash="not-a-hash"),
        lambda d: d["profiles"][profile]["entries"][0].update(
            url="https://user:secret@example.com/a.zip"
        ),
        lambda d: d["profiles"][profile]["entries"][0].update(
            mirrors=["https://example.com"]
        ),
        lambda d: d.update(nativeSelectionsHash="wrong"),
    ]
    for mutation in mutations:
        data = copy.deepcopy(original)
        mutation(data)
        companion.write_text(json.dumps(data))
        assert evaluate()
    companion.write_text(json.dumps(original))
    (root / "dub.json").write_text("{}")
    assert evaluate()
print("DUB malformed/stale locks rejected before fetching")
