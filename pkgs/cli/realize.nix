# SPDX-License-Identifier: MIT
{
  project,
  nativeLock,
  companion,
  target,
  configuration ? "",
  buildType ? "debug",
}:
let
  pkgs = import (/. + "@nixpkgs@") { };
  purifier = import (/. + "@purifier@/nix/lib") { inherit (pkgs) lib; };
  nativeDub = pkgs.callPackage ../native-dub/default.nix { };
  nativeServeD = pkgs.callPackage ../native-serve-d/default.nix { };
  nativeDcd = pkgs.callPackage ../native-dcd/default.nix { };
  toolchain = pkgs.callPackage ../toolchain/default.nix { inherit nativeDub nativeDcd nativeServeD; };
  args = {
    src = /. + project;
    lockFile = /. + companion;
    dubLock = /. + nativeLock;
  };
  lock = import ../../lib-overlays/default/read-lock.nix { inherit (pkgs) lib; } args;
in
if target == "environment" then
  pkgs.callPackage ../build-dub-project/environment.nix { inherit purifier nativeDub toolchain; } {
    inherit lock configuration buildType;
  }
else if target == "release" then
  (pkgs.callPackage ../build-dub-project/default.nix { inherit purifier nativeDub toolchain; } (
    args // { inherit configuration buildType; }
  )).release
else
  throw "dub-purifier: unknown target"
