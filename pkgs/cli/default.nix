# SPDX-License-Identifier: MIT
{
  lib,
  stdenvNoCC,
  stdenv,
  makeWrapper,
  python3,
  nix,
  gh,
  nativeDub,
  nativeServeD,
  toolchain,
  cacert,
  ldc,
  nixpkgsSrc,
  purifierSrc,
}:
let
  python = python3;
in
stdenvNoCC.mkDerivation {
  pname = "dub-purifier";
  version = "0.1.0";
  src = ../..;
  nativeBuildInputs = [ makeWrapper ];
  dontBuild = true;
  installPhase = ''
    mkdir -p "$out/bin" "$out/lib/dub-purifier"
    cp -r dub_purifier lib-overlays pkgs "$out/lib/dub-purifier/"
    install -m755 bin/dub-purifier "$out/bin/dub-purifier"
    substituteInPlace "$out/lib/dub-purifier/pkgs/cli/realize.nix" \
      --replace-fail '@nixpkgs@' '${nixpkgsSrc}' \
      --replace-fail '@purifier@' '${purifierSrc}'
    wrapProgram "$out/bin/dub-purifier" \
      --prefix PATH : ${
        lib.makeBinPath [
          python
          nix
          gh
          toolchain
        ]
      } \
      --set-default SSL_CERT_FILE ${cacert}/etc/ssl/certs/ca-bundle.crt \
      --set DUB_PURIFIER_NATIVE ${nativeDub}/bin/dub \
      --set DUB_PURIFIER_NATIVE_EDITOR ${nativeServeD}/bin/serve-d \
      --set DUB_PURIFIER_INCLUDE ${ldc.include}/include/d \
      --set DUB_PURIFIER_SYSTEM ${stdenv.hostPlatform.system} \
      --set DUB_PURIFIER_LDC_VERSION ${ldc.version} \
      --set DUB_PURIFIER_DUB_VERSION ${nativeDub.version} \
      --set DUB_PURIFIER_SDK_VERSION ${builtins.hashFile "sha256" ../native-dub/dub.patch} \
      --set DUB_PURIFIER_WRAPPER_BIN "$out/bin"
    makeWrapper "$out/bin/dub-purifier" "$out/bin/dub" --add-flags '--native --'
    makeWrapper "$out/bin/dub-purifier" "$out/bin/serve-d" --add-flags '--editor --'
    for program in ${toolchain}/bin/*; do
      name=$(basename "$program")
      if [ ! -e "$out/bin/$name" ]; then ln -s "$program" "$out/bin/$name"; fi
    done
  '';
  meta = {
    description = "Native Dub workflow with locked Nix-resolved dependencies";
    homepage = "https://nix-purifiers.github.io/";
    license = lib.licenses.mit;
    platforms = [
      "x86_64-linux"
      "aarch64-linux"
    ];
    mainProgram = "dub-purifier";
  };
}
