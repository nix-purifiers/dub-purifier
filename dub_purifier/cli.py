# SPDX-License-Identifier: MIT
"""Native DUB selection capture and isolated working-tree execution."""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse

PREFIX = "DUB_PURIFIER_"
NAME = re.compile(r"[a-z][a-z0-9_-]*\Z")
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?\Z")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic(path, data):
    data = data.encode() if isinstance(data, str) else data
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() == data:
        return
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".dub-purifier-")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def dump(data):
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def clean_env():
    return {k: v for k, v in os.environ.items() if not k.startswith(PREFIX)}


def versions():
    return {
        key: os.environ[PREFIX + key.upper() + "_VERSION"]
        for key in ("dub", "ldc", "sdk")
    }


def manifests(root):
    recipes = [p for p in (root / "dub.json", root / "dub.sdl") if p.is_file()]
    if len(recipes) != 1:
        raise ValueError("expected exactly one dub.json or dub.sdl")
    files = recipes + [p for p in (root / "dub.settings.json",) if p.is_file()]
    return {
        p.name: {"sha256": digest(p.read_bytes()), "content": p.read_text()}
        for p in files
    }


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def native():
    return os.environ[PREFIX + "NATIVE"]


def key(config, build):
    return os.environ[PREFIX + "SYSTEM"] + ":" + config + ":" + build


def selected_versions(data):
    if data.get("fileVersion") != 1 or not isinstance(data.get("versions"), dict):
        raise ValueError("unsupported native DUB selections format")
    for name, version in data["versions"].items():
        if (
            not NAME.fullmatch(name)
            or not isinstance(version, str)
            or not VERSION.fullmatch(version)
        ):
            raise ValueError(
                "initial DUB support requires registry packages with release versions"
            )
    return data["versions"]


def lock_project(root, companion, selections, configurations, updates):
    inputs = manifests(root)
    previous = json.loads(companion.read_text()) if companion.exists() else {}
    profiles = (
        previous.get("profiles", {})
        if previous.get("manifests") == inputs
        and previous.get("toolVersions") == versions()
        else {}
    )
    configurations = configurations or [""]
    requests = [
        (config, build) for config in configurations for build in ("debug", "release")
    ]
    requests += [("unittest", "unittest")]
    with tempfile.TemporaryDirectory(prefix="dub-lock-") as scratch:
        scratch = Path(scratch)
        project = scratch / "project"
        shutil.copytree(
            root,
            project,
            ignore=shutil.ignore_patterns(
                ".git", ".dub", ".dub-purifier", "result", "__pycache__"
            ),
        )
        staged = project / "dub.selections.json"
        if selections.exists():
            staged.write_bytes(selections.read_bytes())
        home, capture = scratch / "home", scratch / "capture"
        home.mkdir()
        env = clean_env() | {"DUB_HOME": str(home), PREFIX + "CAPTURE": str(capture)}
        base = [native(), "--root=" + str(project)]
        if updates is not None or not staged.exists():
            run(base + ["upgrade"] + (updates or []), env=env)
        last = None
        for config, build in requests:
            args = base + ["describe", "--compiler=ldc2", "--build=" + build]
            if config:
                args.append("--config=" + config)
            desc = json.loads(run(args, env=env, stdout=subprocess.PIPE).stdout)
            native_lock = json.loads(staged.read_text())
            pins = selected_versions(native_lock)
            entries, metadata = [], {}
            for name, version in sorted(pins.items()):
                blob = capture / (name + "-" + version + ".zip")
                if not blob.is_file():
                    run(base + ["fetch", name, "--version=" + version], env=env)
                if not blob.is_file():
                    raise ValueError(
                        "native DUB did not capture selected archive: " + name
                    )
                url = blob.with_suffix(blob.suffix + ".url").read_text()
                parsed = urllib.parse.urlsplit(url)
                if (
                    parsed.scheme != "https"
                    or parsed.username
                    or parsed.password
                    or parsed.query
                    or parsed.fragment
                ):
                    raise ValueError(
                        "registry archives require public HTTPS URLs without credentials or queries"
                    )
                entries.append(
                    {
                        "path": blob.name,
                        "url": url,
                        "hash": "sha256-"
                        + base64.b64encode(
                            hashlib.sha256(blob.read_bytes()).digest()
                        ).decode(),
                        "mirrors": [],
                    }
                )
                info = json.loads(
                    (capture / ("metadata-" + name + ".json")).read_text()
                )
                info["versions"] = [
                    v for v in info["versions"] if v["version"] == version
                ]
                if len(info["versions"]) != 1:
                    raise ValueError(
                        "native registry metadata does not identify selected version"
                    )
                metadata[name] = info
            for package in desc["packages"]:
                if package["name"] == desc["rootPackage"]:
                    continue
                if any(
                    package[n]
                    for n in (
                        "preGenerateCommands",
                        "postGenerateCommands",
                        "preBuildCommands",
                        "postBuildCommands",
                        "copyFiles",
                    )
                ):
                    raise ValueError(
                        "dependency generation hooks and copyFiles are not yet supported"
                    )
            root_pkg = next(
                p for p in desc["packages"] if p["name"] == desc["rootPackage"]
            )
            profiles[key(config, build)] = {
                "system": os.environ[PREFIX + "SYSTEM"],
                "configuration": config,
                "buildType": build,
                "rootName": desc["rootPackage"],
                "targetFileName": root_pkg["targetFileName"],
                "targetType": root_pkg["targetType"],
                "targetPath": root_pkg["targetPath"],
                "entries": entries,
                "registryMetadata": metadata,
                "nativeSelections": native_lock,
            }
            last = staged.read_bytes()
        data = {
            "version": 1,
            "manifests": inputs,
            "toolVersions": versions(),
            "nativeSelectionsHash": digest(last),
            "profiles": profiles,
        }
        atomic(selections, last)
        atomic(companion, dump(data))


def validate(root, companion, selections):
    data = json.loads(companion.read_text())
    if data.get("version") != 1 or data.get("manifests") != manifests(root):
        raise ValueError("DUB manifest changed; run dub-purifier lock")
    if data.get("toolVersions") != versions():
        raise ValueError("DUB SDK changed; run dub-purifier lock")
    if not selections.exists() or digest(selections.read_bytes()) != data.get(
        "nativeSelectionsHash"
    ):
        raise ValueError("native DUB selections changed; run dub-purifier lock")
    return data


def realize(root, companion, selections, config, build, target="environment"):
    validate(root, companion, selections)
    expression = Path(__file__).resolve().parent.parent / "nix" / "realize.nix"
    args = [
        "nix",
        "build",
        "--impure",
        "--file",
        str(expression),
        "--no-link",
        "--print-out-paths",
    ]
    for name, value in {
        "project": root,
        "nativeLock": selections,
        "companion": companion,
        "configuration": config,
        "buildType": build,
        "target": target,
    }.items():
        args += ["--argstr", name, str(value)]
    return Path(
        run(args, stdout=subprocess.PIPE, text=True).stdout.strip().splitlines()[-1]
    )


def session(root, environment, companion, selections):
    folder = root / ".dub-purifier" / "sessions" / environment.name
    folder.mkdir(parents=True, exist_ok=True)
    for name, target in {
        "environment": environment,
        "sdk": environment / "sdk",
    }.items():
        link = folder / name
        if not link.is_symlink():
            link.symlink_to(target)
    metadata = json.loads((environment / "metadata.json").read_text())
    atomic(
        folder / "dub.selections.json", dump(metadata["profile"]["nativeSelections"])
    )
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(PREFIX)
        or k
        in {
            PREFIX + n
            for n in (
                "NATIVE",
                "NATIVE_EDITOR",
                "INCLUDE",
                "SYSTEM",
                "DUB_VERSION",
                "LDC_VERSION",
                "SDK_VERSION",
                "WRAPPER_BIN",
            )
        }
    } | {
        "DUB_HOME": str(folder),
        PREFIX + "HOME": str(folder),
        PREFIX + "PACKAGES": str((environment / "packages").resolve()),
        PREFIX + "DEP_CACHE": str(environment / "cache"),
        PREFIX + "ROOT_NAME": metadata["profile"]["rootName"],
        PREFIX + "SELECTIONS": str(folder / "dub.selections.json"),
        PREFIX + "ENVIRONMENT": str(environment),
        PREFIX + "PUBLIC_PROJECT": str(root),
        PREFIX + "PUBLIC_LOCKFILE": str(companion),
        PREFIX + "PUBLIC_SELECTIONS": str(selections),
    }
    # Retain the realization and compiler even when a shell has no running process.
    run(
        [
            "nix-store",
            "--add-root",
            str(folder / "gcroot"),
            "--indirect",
            "--realise",
            str(environment),
        ],
        stdout=subprocess.DEVNULL,
    )
    return env


def native_options(args):
    command = next((a for a in args if not a.startswith("-")), "build")
    config, build = ("unittest", "unittest") if command == "test" else ("", "debug")
    forbidden = (
        "--compiler",
        "--arch",
        "--build-mode",
        "--combined",
        "--rdmd",
        "--recipe",
        "--override-config",
        "--nodeps",
        "--coverage",
        "--root",
        "--registry",
        "--skip-registry",
        "--bare",
    )
    for i, arg in enumerate(args):
        if arg == "--":
            break
        if any(arg == x or arg.startswith(x + "=") for x in forbidden):
            raise ValueError("unsupported locked DUB override: " + arg)
        for short, long, name in [
            ("-c", "--config", "config"),
            ("-b", "--build", "build"),
        ]:
            value = None
            if arg in (short, long):
                value = args[i + 1]
            elif arg.startswith(long + "="):
                value = arg.split("=", 1)[1]
            if value is not None:
                if name == "config":
                    config = value
                else:
                    build = value
    if command not in {"build", "run", "test", "describe", "generate"}:
        if command not in {"--help", "--version"} and args not in (
            ["--help"],
            ["--version"],
        ):
            raise ValueError(
                "use dub-purifier lock for dependency changes; unsupported locked command: "
                + command
            )
    return config, build


def main():
    try:
        parser = argparse.ArgumentParser(
            add_help=not any(a in sys.argv for a in ("--native", "--editor"))
        )
        parser.add_argument("--project", default=".")
        parser.add_argument("--lock-file")
        parser.add_argument("--selections")
        parser.add_argument("--native", action="store_true")
        parser.add_argument("--editor", action="store_true")
        options, args = parser.parse_known_args()
        if args[:1] == ["--"]:
            args = args[1:]
        root = Path(options.project).resolve()
        companion = (
            Path(options.lock_file).resolve()
            if options.lock_file
            else root / "dub-purifier.lock.json"
        )
        selections = (
            Path(options.selections).resolve()
            if options.selections
            else root / "dub.selections.json"
        )
        if os.environ.get(PREFIX + "PUBLIC_PROJECT") == str(root):
            if not options.lock_file:
                companion = Path(os.environ[PREFIX + "PUBLIC_LOCKFILE"])
            if not options.selections:
                selections = Path(os.environ[PREFIX + "PUBLIC_SELECTIONS"])
        if options.native or options.editor:
            program = (
                os.environ[PREFIX + "NATIVE_EDITOR"] if options.editor else native()
            )
            if not companion.exists():
                print(
                    "dub-purifier: no lockfile; using ordinary impure "
                    + ("serve-d" if options.editor else "DUB")
                    + " resolution",
                    file=sys.stderr,
                )
                os.execvpe(program, [program] + args, clean_env())
            if args in (["--version"], ["--help"]):
                validate(root, companion, selections)
                os.execvpe(program, [program] + args, clean_env())
            config, build = ("", "debug") if options.editor else native_options(args)
            environment = realize(root, companion, selections, config, build)
            env = session(root, environment, companion, selections)
            os.chdir(root)
            if options.editor:
                os.execvpe(program, [program] + args, env)
            split = args.index("--") if "--" in args else len(args)
            os.execvpe(
                native(),
                [native()]
                + args[:split]
                + ["--compiler=ldc2"]
                + (["--deep"] if not args or args[0] in {"build", "run"} else [])
                + args[split:],
                env,
            )
        action = args.pop(0) if args else "help"
        if action == "lock":
            p = argparse.ArgumentParser()
            p.add_argument("--configuration", action="append")
            p.add_argument("--update", nargs="*", default=None)
            lockargs = p.parse_args(args)
            lock_project(
                root, companion, selections, lockargs.configuration, lockargs.update
            )
        elif action == "publish":
            p = argparse.ArgumentParser()
            p.add_argument("--repo", required=True)
            p.add_argument("--tag", required=True)
            opts = p.parse_args(args)
            artifact = (
                realize(root, companion, selections, "", "debug", "release")
                / "project.tar.gz"
            )
            gh = os.environ.get(PREFIX + "GH", "gh")
            exists = (
                subprocess.run(
                    [gh, "release", "view", opts.tag, "--repo", opts.repo],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                ).returncode
                == 0
            )
            if exists:
                run(
                    [
                        gh,
                        "release",
                        "upload",
                        opts.tag,
                        str(artifact),
                        "--repo",
                        opts.repo,
                        "--clobber",
                    ]
                )
            else:
                run(
                    [
                        gh,
                        "release",
                        "create",
                        opts.tag,
                        str(artifact),
                        "--repo",
                        opts.repo,
                        "--title",
                        opts.tag,
                        "--notes",
                        "Locked DUB project source release",
                    ]
                )
        elif action in {"prefetch", "shell", "release"}:
            p = argparse.ArgumentParser()
            p.add_argument("--configuration", default="")
            p.add_argument("--build-type", default="debug")
            opts, command = p.parse_known_args(args)
            environment = realize(
                root,
                companion,
                selections,
                opts.configuration,
                opts.build_type,
                "release" if action == "release" else "environment",
            )
            if action in {"prefetch", "release"}:
                print(environment)
            else:
                if command[:1] == ["--"]:
                    command = command[1:]
                env = session(root, environment, companion, selections)
                env["PATH"] = (
                    os.environ[PREFIX + "WRAPPER_BIN"] + os.pathsep + env["PATH"]
                )
                os.chdir(root)
                os.execvpe(
                    command[0] if command else os.environ.get("SHELL", "sh"),
                    command or [os.environ.get("SHELL", "sh")],
                    env,
                )
        else:
            parser.error("expected lock, prefetch, shell, or release")
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        print("dub-purifier: " + str(error), file=sys.stderr)
        sys.exit(1)
