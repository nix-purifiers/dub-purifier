# dub-purifier

Locked, Nix-resolved dependencies for DUB. Build, run and test D code in your
working tree with native DUB and LDC.

## Quickstart

From a project with `dub.json` or `dub.sdl`:

```sh
nix shell 'github:nix-purifiers/dub-purifier'
dub-purifier lock
dub-purifier prefetch
dub run
dub test
```

The shell provides a `dub` wrapper, LDC and serve-d. The wrapper selects the
prepared dependency environment; native DUB compiles your application outside
the Nix sandbox. Without a companion lockfile it warns and runs ordinary,
impure DUB. Install the wrapper using your usual installation method if you
want it available beyond the shell.

`dub.selections.json` retains DUB's version selections.
`dub-purifier.lock.json` records the native registry metadata, exact archive
hashes, manifests and compiler profiles. Commit both files.

## Resolution and updates

`dub-purifier lock` uses native DUB resolution and retains existing selections.
It prepares debug and release builds of the default configuration and DUB's
unittest configuration. Dependencies are fetched and compiled in Nix; application
source edits reuse that environment.

```sh
dub-purifier lock --update semver
dub-purifier prefetch
dub run --build=release
```

For another root configuration:

```sh
dub-purifier lock --configuration server
dub-purifier prefetch --configuration server
dub run --config=server
```

Generate profiles natively on each supported system: `x86_64-linux` and
`aarch64-linux`. Locking on one system preserves the other system's profiles
when the manifests and SDK match. An unprepared configuration, stale lock or
missing dependency build fails instead of resolving or compiling dependencies
impurely.

## Editors and shells

Run `serve-d` from the same shell as DUB. Its wrapper activates the locked
source paths and completion tools. A project session in `.dub-purifier/sessions/` holds writable
application caches and GC roots for its immutable dependencies and SDK.

```sh
dub-purifier shell
serve-d
```

Ignore `.dub/`, `.dub-purifier/` and generated application binaries in Git.
There is no generated Nix devshell.

## Build the project in Nix

Optionally add a Nix definition using the overlay's
`pkgs.dub-purifier.buildDubProject`:

```nix
pkgs.dub-purifier.buildDubProject {
  src = ./.;
}
```

It returns `packages.environment`, `packages.project`, `packages.default`,
`tests`, `release` and `fetches`. Output names are known during evaluation.
`release` is a source tarball containing the native and companion locks.
`dub-purifier publish --repo OWNER/REPO --tag vVERSION` uploads that artifact
to a GitHub release.
`configuration`, `buildType`, `fetchers`, `nativeBuildInputs`, `doCheck`,
`buildCommand`, `installCommand` and `srcFilter` customize the build.
The default installation expects an executable target; override `installCommand`
for libraries or other layouts.

## Current scope

DUB 1.42.0 and LDC 1.42.0 on Linux. Registry release archives and transitive
subpackages are supported. Local/path dependencies, Git selections, dependency
generation/build hooks and dependency `copyFiles` need further integration.
The editor integration provides source navigation; run DUB build actions from
the terminal. Dependencies build separately; combined/rdmd modes and compiler, architecture,
recipe or registry overrides are rejected in a locked session. The compiler and
build settings must match a prepared profile.

Registry packages remain immutable. Ordinary global and local package caches,
local overrides, custom search paths and registry suppliers cannot replace the
prepared dependency packages. The unwrapped SDK retains ordinary DUB behavior
when its purifier environment is absent.

## Credits

The purifier idea was inspired by nixcloud's
[cargo (libnix)](https://github.com/nixcloud/cargo).
