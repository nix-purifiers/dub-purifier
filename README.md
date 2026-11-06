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
The default installation expects an executable target. `nativeProducts` installs
an explicitly selected dynamic C ABI target under `lib/`; `installCommand` can
customize other layouts.

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

## Native C ABI projections

`buildDubProject` accepts an opt-in `nativeProducts` declaration for the root
DUB `dynamicLibrary` target. Run `dub-purifier lock` again to capture its native
target type and path before enabling it. Older locks and ordinary executable
builds retain their existing behavior and expose empty projections.

```nix
pkgs.dub-purifier.buildDubProject {
  src = ./.;
  nativeProducts.my-library = {
    abi = "c";
    runtime = {
      kind = "druntime";
      lifecycle = "same-thread";
      initializeSymbol = "my_library_init";
      terminateSymbol = "my_library_term";
      attachThreadSymbol = "my_library_thread_enter";
      detachThreadSymbol = "my_library_thread_leave";
    };
  };
}
```

The key must match the native root package name. The product supplies these
four distinct C ABI functions; the purifier does not generate runtime wrappers
or infer a C ABI from a filename. Initialization and termination return an `int`
(success is 1); foreign-thread entry and exit return `void`. Call the declared
initialization function before using D module state or the GC, attach foreign
threads before D calls, detach them afterwards, and terminate on the initializing
thread after all calls and attached threads finish. Consumers supply compatible
signatures for the product's other exported functions.

The selected native target is installed under `lib/`. Both the result and
`packages.project` expose `projections.native`, `projections.python-ffi` and
`projections.java-ffi`. Each view contains `catalog.json` with exact library paths,
the compiler identity and the declared lifecycle, `purifier_native.py` for lazy
ctypes loading, and `java.args` for the library search path. These views retain
the installed producer and its linked runtime closure. Loading does not run the
declared initialization function automatically.

Only the captured dynamic root is selectable. Static libraries, executables,
missing metadata or outputs, escaping paths, duplicate or malformed lifecycle
symbols, and symbols not defined by the selected library are rejected. A custom
`installCommand` must preserve the selected library's bytes inside the output.

The native test captures profiles on its actual runner and exercises C,
Python ctypes/CFFI, GC allocation, module initialization, TLS and an attached
foreign thread. Java FFM uses same-thread confined lookup, initialization,
calls, termination and close, then exits naturally. Global Java lookup produced
D runtime warnings during shutdown in the native controls; this does not
establish a general safe-unloading contract. ARM runtime support for these views
requires the corresponding native CI run.

## Credits

The purifier idea was inspired by nixcloud's
[cargo (libnix)](https://github.com/nixcloud/cargo).
