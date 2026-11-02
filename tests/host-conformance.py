#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]


def run(args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, text=True, **kwargs)


case = sys.argv[1]
with tempfile.TemporaryDirectory(prefix="dub-conformance-") as temporary:
    temp = Path(temporary)
    cli = temp / "cli"
    run(["nix", "build", str(REPO) + "#cli", "--out-link", cli])
    helper, dub = cli / "bin/dub-purifier", cli / "bin/dub"
    root = temp / "project"
    shutil.copytree(
        REPO / "examples/minimal",
        root,
        ignore=shutil.ignore_patterns(
            ".dub",
            ".dub-purifier",
            "*.lock.json",
            "dub.selections.json",
            "purifier-example*",
        ),
    )
    recipe = root / "dub.json"
    data = json.loads(recipe.read_text())
    if case == "update":
        data["dependencies"]["semver"] = "==0.3.3"
        recipe.write_text(json.dumps(data))
    if case == "tasks":
        data["dependencies"]["automem"] = "==0.6.9"
        data["configurations"] = [
            {
                "name": "server",
                "targetType": "executable",
                "mainSourceFile": "source/app.d",
                "versions": ["Server"],
            }
        ]
        recipe.write_text(json.dumps(data))
    env = {k: v for k, v in os.environ.items() if not k.startswith("DUB_PURIFIER_")}
    env["DUB_HOME"] = str(temp / "ordinary-cache")
    args = [helper, "--project", root]
    if case == "external":
        args += [
            "--lock-file",
            temp / "external.json",
            "--selections",
            temp / "external-selections.json",
        ]
    companion = (
        temp / "external.json"
        if case == "external"
        else root / "dub-purifier.lock.json"
    )
    selections = (
        temp / "external-selections.json"
        if case == "external"
        else root / "dub.selections.json"
    )
    lockopts = ["--configuration", "server"] if case == "tasks" else []
    run([*args, "lock", *lockopts], env=env)
    if case == "tasks":
        pins = json.loads(selections.read_text())["versions"]
        assert pins["automem"] == "0.6.9" and "unit-threaded" in pins and len(pins) >= 3
    initial = companion.read_bytes(), selections.read_bytes()
    run([*args, "lock", *lockopts], env=env)
    assert initial == (companion.read_bytes(), selections.read_bytes())
    if case == "update":
        data["dependencies"]["semver"] = "~>0.3.0"
        recipe.write_text(json.dumps(data))
        run([*args, "lock"], env=env)
        assert json.loads(selections.read_text())["versions"]["semver"] == "0.3.3"
        run([*args, "lock", "--update", "semver"], env=env)
        assert json.loads(selections.read_text())["versions"]["semver"] == "0.3.4"
    opts = ["--configuration", "server"] if case == "tasks" else []
    environment = Path(
        run([*args, "prefetch", *opts], env=env, stdout=subprocess.PIPE).stdout.strip()
    )
    offline = env | {
        "http_proxy": "http://127.0.0.1:9",
        "https_proxy": "http://127.0.0.1:9",
        "HTTP_PROXY": "http://127.0.0.1:9",
        "HTTPS_PROXY": "http://127.0.0.1:9",
    }
    assert (
        Path(
            run(
                [*args, "prefetch", *opts], env=offline, stdout=subprocess.PIPE
            ).stdout.strip()
        )
        == environment
    )
    if case in {"native", "tasks", "external"}:
        if case == "native":
            run(["nix", "build", str(REPO) + "#native", "--out-link", temp / "native"])
            sdk = temp / "native/bin/dub"
            decoy = temp / "poison-semver"
            (decoy / "source").mkdir(parents=True)
            (decoy / "dub.json").write_text(
                '{"name":"semver","version":"0.3.4","targetType":"library"}'
            )
            (decoy / "source/semver.d").write_text("this is invalid D source")
            for cache in ("local", "user"):
                run(
                    [sdk, "add-local", decoy, "0.3.4", "--cache=" + cache],
                    cwd=root,
                    env=env,
                )
        native = [helper, "--project", root, "--native"]
        if case == "external":
            native += ["--lock-file", companion, "--selections", selections]
        native += ["--"]
        config = ["--config=server"] if case == "tasks" else []
        output = run(
            [*native, "run", *config], cwd=root, env=offline, stdout=subprocess.PIPE
        )
        assert "locked DUB" in output.stdout
        desc = json.loads(
            run(
                [*native, "describe", *config],
                cwd=root,
                env=offline,
                stdout=subprocess.PIPE,
            ).stdout
        )
        semver = next(p for p in desc["packages"] if p["name"] == "semver")
        assert Path(semver["path"]).is_relative_to(Path("/nix/store"))
        assert str(Path(semver["path"]).resolve()).startswith(
            str((environment / "packages").resolve())
        )
        if case == "external":
            child_description = json.loads(
                run(
                    [*args, "shell", "--", "dub", "describe"],
                    env=offline,
                    stdout=subprocess.PIPE,
                ).stdout
            )
            assert (
                next(p for p in child_description["packages"] if p["name"] == "semver")[
                    "path"
                ]
                == semver["path"]
            )
        source = root / "source/app.d"
        source.write_text(source.read_text().replace("locked DUB", "edited DUB"))
        assert (
            Path(
                run(
                    [*args, "prefetch", *opts], env=offline, stdout=subprocess.PIPE
                ).stdout.strip()
            )
            == environment
        )
        assert (
            "edited DUB"
            in run(
                [*native, "run", "--force", *config],
                cwd=root,
                env=offline,
                stdout=subprocess.PIPE,
            ).stdout
        )
        run([*native, "test"], cwd=root, env=offline)
        bad = subprocess.run(
            list(map(str, [*native, "build", "--build=plain", *config])),
            cwd=root,
            env=offline,
            text=True,
            capture_output=True,
        )
        assert bad.returncode and "profile missing" in bad.stderr
        recipe.write_text(recipe.read_text() + "\n")
        bad = subprocess.run(
            list(map(str, [*native, "build"])),
            cwd=root,
            env=offline,
            text=True,
            capture_output=True,
        )
        assert bad.returncode and "manifest changed" in bad.stderr
    if case == "native":
        import tarfile

        fake = temp / "gh"
        record = temp / "calls"
        fake.write_text(
            "#!/usr/bin/env python3\nimport json,sys\nfrom pathlib import Path\np=Path("
            + repr(str(record))
            + ')\na=sys.argv[1:]\nwith p.open("a") as f:f.write(json.dumps(a)+"\\n")\nif a[:2]==["release","view"]:sys.exit(0 if len(p.read_text().splitlines())>2 else 1)\n'
        )
        fake.chmod(0o755)
        # Restore the manifest after the deliberate stale-lock test.
        recipe.write_bytes((REPO / "examples/minimal/dub.json").read_bytes())
        import editor

        editor.check(cli, root, environment, offline, cli)
        for _ in range(2):
            run(
                [*args, "publish", "--repo", "fixture/project", "--tag", "v0.1.0"],
                env=env | {"DUB_PURIFIER_GH": str(fake)},
            )
        calls = [json.loads(line) for line in record.read_text().splitlines()]
        assert calls[1][:2] == ["release", "create"] and calls[3][:2] == [
            "release",
            "upload",
        ]
        with tarfile.open(
            next(v for v in calls[1] if v.endswith("/project.tar.gz"))
        ) as release:
            files = set(release.getnames())
            assert {
                "./dub.json",
                "./dub.selections.json",
                "./dub-purifier.lock.json",
            } <= files
            assert "./purifier-example" not in files
    if case == "native":
        empty_graph = temp / "empty-graph"
        (empty_graph / "source").mkdir(parents=True)
        (empty_graph / "dub.json").write_text('{"name":"empty-example"}')
        (empty_graph / "source/app.d").write_text("void main() {}")
        run([helper, "--project", empty_graph, "lock"], env=env)
        empty_environment = Path(
            run(
                [helper, "--project", empty_graph, "prefetch"],
                env=offline,
                stdout=subprocess.PIPE,
            ).stdout.strip()
        )
        assert list((empty_environment / "packages").iterdir()) == []
        empty = temp / "unlocked"
        empty.mkdir()
        run(["nix", "build", str(REPO) + "#native", "--out-link", temp / "native"])
        sdk = temp / "native/bin/dub"
        baseline = run([sdk, "--version"], cwd=empty, env=env, capture_output=True)
        fallback = run([dub, "--version"], cwd=empty, env=env, capture_output=True)
        assert (
            baseline.stdout == fallback.stdout
            and "ordinary impure DUB" in fallback.stderr
        )
        (empty / "dub.json").write_text('{"name":"fallback-example"}')
        (empty / "source").mkdir()
        (empty / "source/app.d").write_text(
            'import std.stdio; int main() { write(readln()); stderr.write("native-stderr"); return 7; }'
        )
        for program in [sdk, dub]:
            result = subprocess.run(
                [str(program), "run", "--compiler=ldc2"],
                cwd=empty,
                env=env | {"PATH": str(cli / "bin") + os.pathsep + env["PATH"]},
                input="native-stdin\n",
                text=True,
                capture_output=True,
            )
            assert (
                result.returncode == 2
                and "native-stdin" in result.stdout
                and "native-stderr" in result.stderr
            ), result
    print("DUB conformance passed:", case)
