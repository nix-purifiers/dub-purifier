# SPDX-License-Identifier: MIT
{
  buildDubPackage,
  importDubLock,
  path,
}:
let
  lock = path + "/pkgs/by-name/se/serve-d/dub-lock.json";
  deps = importDubLock {
    pname = "dcd";
    version = "0.13.6";
    inherit lock;
  };
in
buildDubPackage {
  pname = "dub-purifier-dcd";
  version = "0.13.6";
  src = "${deps}/.dub/packages/dcd/0.13.6/dcd";
  dubLock = ./dcd-lock.json;
  postUnpack = ''
    mv dcd dcd-0.13.6
    sourceRoot=dcd-0.13.6
  '';
  postPatch = ''
    substituteInPlace common/dub.sdl --replace-fail 'rdmd ' 'ldc2 -run '
    substituteInPlace src/dcd/client/client.d src/dcd/server/main.d \
      --replace-fail 'sharedLog.fatalHandler' '(cast(Logger)sharedLog).fatalHandler'
  '';
  buildPhase = ''
    runHook preBuild
    dub build --compiler=ldc2 --config=client --skip-registry=all
    dub build --compiler=ldc2 --config=server --skip-registry=all
    runHook postBuild
  '';
  doCheck = true;
  installPhase = ''
    mkdir -p "$out/bin"
    install -m755 bin/dcd-client bin/dcd-server "$out/bin/"
  '';
}
