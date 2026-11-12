# SPDX-License-Identifier: MIT
{
  lib,
  runCommand,
  fetchgit,
  python3,
  writeText,
  nativeDub,
  toolchain,
  ldc,
  stdenv,
  purifier,
}:
{
  lock,
  configuration ? "",
  buildType ? "debug",
  fetchers ? { },
  nativeBuildInputs ? [ ],
}:
let
  checked = purifier.checkLock lock;
  profile =
    checked.data.profiles."${stdenv.hostPlatform.system}:${configuration}:${buildType}"
      or (throw "dub-purifier: profile missing; run dub-purifier lock --configuration NAME on this system");
  sources = purifier.tree (
    {
      name = "locked-dub-archives";
      entries = profile.entries;
      inherit
        runCommand
        fetchgit
        python3
        writeText
        ;
    }
    // fetchers
  );
  registryMetadata = writeText "dub-native-registry-metadata.json" (
    builtins.toJSON profile.registryMetadata
  );
  metadata = writeText "dub-build-metadata.json" (
    builtins.toJSON {
      inherit profile;
      inherit (checked.data) manifests;
    }
  );
  packages = runCommand "purified-dub-packages" { nativeBuildInputs = [ toolchain ]; } ''
    mkdir -p "$out/packages" "$TMPDIR/home"
    export HOME="$TMPDIR/home" DUB_HOME="$out"
    export DUB_PURIFIER_FETCH_METADATA=${registryMetadata}
    export DUB_PURIFIER_FETCH_BLOBS=${sources}
    ${lib.concatMapStringsSep "\n" (
      name:
      "dub fetch ${lib.escapeShellArg name} --version=${
        lib.escapeShellArg profile.nativeSelections.versions.${name}
      }"
    ) (builtins.attrNames profile.nativeSelections.versions)}
  '';
in
assert lib.assertMsg (
  checked.data.toolVersions.dub == nativeDub.version
  && checked.data.toolVersions.ldc == ldc.version
  && checked.data.toolVersions.sdk == builtins.hashFile "sha256" ../native-dub/dub.patch
) "dub-purifier: SDK changed; run dub-purifier lock";
runCommand "purified-dub-environment"
  {
    nativeBuildInputs = [
      toolchain
      python3
    ]
    ++ nativeBuildInputs;
  }
  ''
    mkdir -p "$out/cache" work/source "$TMPDIR/home"
    export HOME="$TMPDIR/home" DUB_HOME="$TMPDIR/dub"
    export DUB_PURIFIER_ROOT_NAME=${lib.escapeShellArg profile.rootName}
    export DUB_PURIFIER_PACKAGES=${packages}/packages
    export DUB_PURIFIER_DEP_CACHE="$out/cache" DUB_PURIFIER_DEPS_ONLY=1
    python3 ${../../dub_purifier/build.py} ${metadata} "$PWD/work"
    dub build --root="$PWD/work" --compiler=ldc2 --deep --build=${lib.escapeShellArg buildType} ${
      lib.optionalString (configuration != "") "--config=${lib.escapeShellArg configuration}"
    }
    ln -s ${packages}/packages "$out/packages"
    ln -s ${toolchain} "$out/sdk"
    ln -s ${sources} "$out/archives"
    cp ${metadata} "$out/metadata.json"
  ''
