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
  gnutar,
  gzip,
}:
{
  src,
  lockFile ? src + "/dub-purifier.lock.json",
  dubLock ? src + "/dub.selections.json",
  configuration ? "",
  buildType ? "debug",
  fetchers ? { },
  nativeBuildInputs ? [ ],
  doCheck ? true,
  buildCommand ? "dub build --compiler=ldc2 --deep --build=${lib.escapeShellArg buildType} ${
    lib.optionalString (configuration != "") "--config=${lib.escapeShellArg configuration}"
  }",
  installCommand ? ''
    mkdir -p "$out/bin"
    target=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["profile"]["targetFileName"])' $DUB_PURIFIER_ENVIRONMENT/metadata.json)
    install -m755 "$target" "$out/bin/"
  '',
  srcFilter ?
    path: type:
    !(builtins.elem (baseNameOf path) [
      ".git"
      ".dub"
      ".dub-purifier"
      "result"
      "__pycache__"
    ]),
}:
let
  lock = purifier.checkLock (
    import ./read-lock.nix { inherit lib; } { inherit src lockFile dubLock; }
  );
  makeEnv = import ./environment.nix {
    inherit
      lib
      runCommand
      fetchgit
      python3
      writeText
      nativeDub
      toolchain
      ldc
      stdenv
      purifier
      ;
  };
  environment = makeEnv {
    inherit
      lock
      configuration
      buildType
      fetchers
      nativeBuildInputs
      ;
  };
  testEnvironment = makeEnv {
    inherit lock fetchers nativeBuildInputs;
    configuration = "unittest";
    buildType = "unittest";
  };
  binaries = lib.unique (map (p: p.targetFileName) (builtins.attrValues lock.data.profiles));
  source = lib.cleanSourceWith {
    inherit src;
    filter =
      path: type:
      srcFilter path type
      && !(lib.hasSuffix ".log" (baseNameOf path))
      && !(type == "regular" && builtins.elem (baseNameOf path) binaries);
  };
  setup = env: ''
    export DUB_HOME="$TMPDIR/dub" DUB_PURIFIER_HOME="$TMPDIR/dub"
    export DUB_PURIFIER_PACKAGES=$(readlink -f ${env}/packages) DUB_PURIFIER_DEP_CACHE=${env}/cache
    export DUB_PURIFIER_ROOT_NAME=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["profile"]["rootName"])' ${env}/metadata.json)
    export DUB_PURIFIER_ENVIRONMENT=${env}
    export DUB_PURIFIER_SELECTIONS="$DUB_HOME/dub.selections.json"
    mkdir -p "$DUB_HOME"
    python3 -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1]))["profile"]["nativeSelections"]))' ${env}/metadata.json > "$DUB_PURIFIER_SELECTIONS"
  '';
  project =
    runCommand "purified-dub-project"
      {
        nativeBuildInputs = [
          toolchain
          python3
        ]
        ++ nativeBuildInputs;
      }
      ''
        export HOME="$TMPDIR/home" SOURCE_DATE_EPOCH=1
        mkdir -p "$HOME" project
        cp -r ${source}/. project/
        chmod -R u+w project
        cd project
        ${setup environment}
        ${buildCommand}
        ${installCommand}
        ${lib.optionalString doCheck ''
          ${setup testEnvironment}
          dub test --compiler=ldc2
        ''}
      '';
  release =
    runCommand "dub-project-release"
      {
        nativeBuildInputs = [
          gnutar
          gzip
        ];
      }
      ''
        mkdir source "$out"
        cp -r ${source}/. source/
        chmod -R u+w source
        cp ${lockFile} source/dub-purifier.lock.json
        cp ${dubLock} source/dub.selections.json
        tar --sort=name --mtime=@1 --owner=0 --group=0 --numeric-owner -C source -cf - . | gzip -n > "$out/project.tar.gz"
      '';
in
{
  packages = {
    inherit environment project;
    default = project;
  };
  tests = project;
  inherit release;
  fetches = lock.entries;
}
