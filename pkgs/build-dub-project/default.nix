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
  binutils,
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
  nativeProducts ? { },
  buildCommand ? "dub build --compiler=ldc2 --deep --build=${lib.escapeShellArg buildType} ${
    lib.optionalString (configuration != "") "--config=${lib.escapeShellArg configuration}"
  }",
  installCommand ?
    if nativeProducts == { } then
      ''
        mkdir -p "$out/bin"
        target=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["profile"]["targetFileName"])' $DUB_PURIFIER_ENVIRONMENT/metadata.json)
        install -m755 "$target" "$out/bin/"
      ''
    else
      ''
        mkdir -p "$out/lib"
        python3 ${./install-native.py} install "$DUB_PURIFIER_ENVIRONMENT/metadata.json" "$out"
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
    import ../../lib-overlays/default/read-lock.nix { inherit lib; } { inherit src lockFile dubLock; }
  );
  profile =
    lock.data.profiles."${stdenv.hostPlatform.system}:${configuration}:${buildType}"
      or (throw "dub-purifier: native profile missing");
  symbol = s: builtins.isString s && builtins.match "[A-Za-z_][A-Za-z0-9_]*" s != null;
  symbols =
    runtime:
    map (name: runtime.${name} or null) [
      "initializeSymbol"
      "terminateSymbol"
      "attachThreadSymbol"
      "detachThreadSymbol"
    ];
  validProduct =
    product:
    builtins.isAttrs product
    &&
      builtins.attrNames product == [
        "abi"
        "runtime"
      ]
    && product.abi == "c"
    && builtins.isAttrs product.runtime
    &&
      builtins.attrNames product.runtime == [
        "attachThreadSymbol"
        "detachThreadSymbol"
        "initializeSymbol"
        "kind"
        "lifecycle"
        "terminateSymbol"
      ]
    && product.runtime.kind == "druntime"
    && product.runtime.lifecycle == "same-thread"
    && builtins.all symbol (symbols product.runtime)
    && builtins.length (lib.unique (symbols product.runtime)) == 4;
  nativeSelected = nativeProducts != { };
  safeTargetPath =
    s:
    builtins.isString s
    && s != ""
    && !(lib.hasPrefix "/" s)
    && !(lib.hasInfix "\\" s)
    && builtins.all (part: part != "" && part != "..") (lib.splitString "/" s);
  nativeValid =
    builtins.isAttrs nativeProducts
    && builtins.attrNames nativeProducts == [ profile.rootName ]
    && validProduct nativeProducts.${profile.rootName}
    && (profile.targetType or null) == "dynamicLibrary"
    && safeTargetPath (profile.targetPath or null)
    && lib.hasSuffix stdenv.hostPlatform.extensions.sharedLibrary profile.targetFileName;
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
  builtProject =
    runCommand "purified-dub-project"
      {
        nativeBuildInputs = [
          toolchain
          python3
        ]
        ++ nativeBuildInputs;
        nativeSpec = builtins.toJSON nativeProducts;
      }
      ''
        export HOME="$TMPDIR/home" SOURCE_DATE_EPOCH=1
        mkdir -p "$HOME" project
        cp -r ${source}/. project/
        chmod -R u+w project
        cd project
        ${setup environment}
        ${buildCommand}
        ${lib.optionalString nativeSelected ''
          python3 ${./install-native.py} preflight ${environment}/metadata.json "$out" ${binutils}/bin/nm
        ''}
        ${installCommand}
        ${lib.optionalString nativeSelected ''
          python3 ${./install-native.py} validate ${environment}/metadata.json "$out" ${binutils}/bin/nm
        ''}
        ${lib.optionalString doCheck ''
          ${setup testEnvironment}
          dub test --compiler=ldc2
        ''}
      '';
  projections = lib.optionalAttrs nativeSelected (
    purifier.nativeProjections {
      producer = builtProject;
      libraries.${profile.rootName} = "lib/${profile.targetFileName}";
      targetMetadata.${profile.rootName} = nativeProducts.${profile.rootName} // {
        type = "dynamicLibrary";
        nativeTargetPath = profile.targetPath;
        nativeTargetFileName = profile.targetFileName;
        compiler = {
          name = "ldc";
          version = ldc.version;
          path = toString ldc;
        };
      };
      system = stdenv.hostPlatform.system;
      inherit runCommand python3;
    }
  );
  project = builtProject // {
    inherit projections;
  };
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
assert
  (!nativeSelected || nativeValid)
  || throw "dub-purifier: nativeProducts requires one captured dynamic root C ABI target and distinct explicit druntime lifecycle symbols";
{
  packages = {
    inherit environment project;
    default = project;
  };
  tests = project;
  inherit release projections;
  fetches = lock.entries;
}
