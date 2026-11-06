#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actual native capture on this runner, installed projections and boundaries."""

import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

REPO = Path(__file__).resolve().parents[1]
PRODUCT = {
    "abi": "c",
    "runtime": {
        "kind": "druntime",
        "lifecycle": "same-thread",
        "initializeSymbol": "purifier_init",
        "terminateSymbol": "purifier_term",
        "attachThreadSymbol": "purifier_thread_enter",
        "detachThreadSymbol": "purifier_thread_leave",
    },
}
PRODUCTS = {"purifier-native-proof": PRODUCT}


def run(args, *, success=True, timeout=600, env=None):
    result = subprocess.run(
        list(map(str, args)), text=True, capture_output=True, timeout=timeout, env=env
    )
    if success and result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    return result


with tempfile.TemporaryDirectory(prefix="dub-native-projections-") as temporary:
    temp = Path(temporary)
    root = temp / "project"
    shutil.copytree(REPO / "tests/fixtures/native", root)
    cli = (
        Path(
            run(
                [
                    "nix",
                    "build",
                    "path:" + str(REPO) + "#cli",
                    "--no-link",
                    "--print-out-paths",
                ]
            ).stdout.strip()
        )
        / "bin/dub-purifier"
    )
    env = dict(os.environ, HOME=str(temp / "home"), DUB_HOME=str(temp / "dub"))
    Path(env["HOME"]).mkdir()

    def capture():
        run([cli, "--project", root, "lock"], env=env)
        return json.loads((root / "dub-purifier.lock.json").read_text())

    original = capture()
    companion = root / "dub-purifier.lock.json"
    current_system = run(
        ["nix", "eval", "--impure", "--raw", "--expr", "builtins.currentSystem"]
    ).stdout.strip()
    profile_key = current_system + "::debug"
    assert original["profiles"][profile_key]["targetType"] == "dynamicLibrary"
    assert original["profiles"][profile_key]["targetPath"] == "lib"
    assert all(p["system"] == current_system for p in original["profiles"].values())

    def expression(
        products=PRODUCTS, extra="", result="built.packages.project.drvPath"
    ):
        return f"""
let
 f = builtins.getFlake {json.dumps('path:' + str(REPO))};
 pkgs = import f.inputs.nixpkgs {{ system = builtins.currentSystem; overlays = [ f.overlays.default ]; }};
 built = pkgs.dub-purifier.buildDubProject {{
   src = {root};
   nativeProducts = builtins.fromJSON {json.dumps(json.dumps(products))};
   {extra}
 }};
in {result}
"""

    def evaluate(products=PRODUCTS):
        return run(
            [
                "nix",
                "eval",
                "--impure",
                "--json",
                "--option",
                "allow-import-from-derivation",
                "false",
                "--expr",
                expression(products),
            ],
            success=False,
        )

    assert evaluate().returncode == 0
    empty = run(
        [
            "nix",
            "eval",
            "--impure",
            "--json",
            "--expr",
            expression({}, result="built.projections"),
        ]
    )
    assert json.loads(empty.stdout) == {}
    # Real per-runner lock, native compile, installation, shared helper and consumers.
    consumer = expression(
        result=f"import {REPO}/tests/native-consumer.nix {{ inherit pkgs built; product = builtins.fromJSON {json.dumps(json.dumps(PRODUCT))}; }}"
    )
    output = run(
        [
            "nix",
            "build",
            "--impure",
            "--no-link",
            "--print-out-paths",
            "--expr",
            consumer,
        ],
        timeout=1800,
    ).stdout.strip()
    assert (
        json.loads((Path(output) / "catalog.json").read_text())["system"]
        == current_system
    )

    rejected = 0
    invalid = []
    for key, value in [("abi", "c++"), ("runtime", {})]:
        p = copy.deepcopy(PRODUCT)
        p[key] = value
        invalid.append({"purifier-native-proof": p})
    for key, value in [
        ("initializeSymbol", 123),
        ("initializeSymbol", "../bad"),
        ("terminateSymbol", "purifier_init"),
        ("lifecycle", "global"),
        ("kind", "none"),
    ]:
        p = copy.deepcopy(PRODUCT)
        p["runtime"][key] = value
        invalid.append({"purifier-native-proof": p})
    invalid += [{"wrong-root": PRODUCT}, PRODUCTS | {"duplicate-root": PRODUCT}]
    for products in invalid:
        result = evaluate(products)
        assert (
            result.returncode and "nativeProducts requires" in result.stderr
        ), result.stderr
        rejected += 1

    # Old companion locks keep working by default, but cannot invent native metadata.
    data = copy.deepcopy(original)
    for profile in data["profiles"].values():
        profile.pop("targetType")
        profile.pop("targetPath")
    companion.write_text(json.dumps(data))
    assert evaluate({}).returncode == 0
    assert evaluate().returncode != 0
    rejected += 1
    for target_path in ("../outside", "/absolute", "lib/../outside", "lib\\outside"):
        data = copy.deepcopy(original)
        data["profiles"][profile_key]["targetPath"] = target_path
        companion.write_text(json.dumps(data))
        assert evaluate().returncode != 0
        rejected += 1
    companion.write_text(json.dumps(original))

    # Valid identifiers that are not actual defined exports fail before installation.
    p = copy.deepcopy(PRODUCT)
    p["runtime"]["initializeSymbol"] = "missing_native_export"
    missing = run(
        [
            "nix",
            "build",
            "--impure",
            "--no-link",
            "--expr",
            expression(
                {"purifier-native-proof": p},
                extra='installCommand = "echo UNEXPECTED_INSTALL >&2; exit 99";',
                result="built.packages.project",
            ),
        ],
        success=False,
    )
    assert (
        missing.returncode and "symbol is not defined" in missing.stderr
    ), missing.stderr
    assert "UNEXPECTED_INSTALL" not in missing.stderr
    rejected += 1
    for command, expected in [
        (
            "dub build --compiler=ldc2 --deep; rm lib/libpurifier_native_proof.so",
            "FileNotFoundError",
        ),
        (
            "dub build --compiler=ldc2 --deep; rm lib/libpurifier_native_proof.so; ln -s /etc/hosts lib/libpurifier_native_proof.so",
            "project-owned file",
        ),
    ]:
        extra = "buildCommand = " + json.dumps(command) + ";"
        missing = run(
            [
                "nix",
                "build",
                "--impure",
                "--no-link",
                "--expr",
                expression(extra=extra, result="built.packages.project"),
            ],
            success=False,
        )
        assert missing.returncode and expected in missing.stderr, missing.stderr
        rejected += 1

    for command, expected in [
        (
            'mkdir -p "$out/lib"; ln -s /etc/hosts "$out/lib/libpurifier_native_proof.so"',
            "escapes producer",
        ),
        (
            'mkdir -p "$out/lib"; cp /etc/hosts "$out/lib/libpurifier_native_proof.so"',
            "differs from captured native target",
        ),
    ]:
        extra = "installCommand = " + json.dumps(command) + ";"
        bad = run(
            [
                "nix",
                "build",
                "--impure",
                "--no-link",
                "--expr",
                expression(extra=extra, result="built.packages.project"),
            ],
            success=False,
        )
        assert bad.returncode and expected in bad.stderr, bad.stderr
        rejected += 1

    extra = (
        "installCommand = "
        + json.dumps(
            'mkdir -p replacement/lib; cp lib/libpurifier_native_proof.so replacement/lib/; ln -s "$PWD/replacement" "$out"'
        )
        + ";"
    )
    bad = run(
        [
            "nix",
            "build",
            "--impure",
            "--no-link",
            "--expr",
            expression(extra=extra, result="built.packages.project"),
        ],
        success=False,
    )
    assert bad.returncode and "escapes producer" in bad.stderr, bad.stderr
    rejected += 1

    # Native SDK describes these as static/executable even with library-like names.
    recipe_path = root / "dub.json"
    recipe = json.loads(recipe_path.read_text())
    for target_type in ("staticLibrary", "executable"):
        updated = recipe | {"targetType": target_type}
        if target_type == "executable":
            (root / "source/main.d").write_text("void main() {}\n")
        recipe_path.write_text(json.dumps(updated))
        native = capture()
        assert native["profiles"][profile_key]["targetType"] == target_type
        result = evaluate()
        assert (
            result.returncode and "nativeProducts requires" in result.stderr
        ), result.stderr
        rejected += 1
    print(
        json.dumps(
            {
                "system": current_system,
                "consumerOutput": output,
                "nativeCapture": True,
                "rejected": rejected,
            }
        )
    )
