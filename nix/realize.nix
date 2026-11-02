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
  nativeDub = pkgs.callPackage ./dub.nix { };
  nativeServeD = pkgs.callPackage ./serve-d.nix { };
  nativeDcd = pkgs.callPackage ./dcd.nix { };
  toolchain = pkgs.callPackage ./toolchain.nix { inherit nativeDub nativeDcd nativeServeD; };
  args = {
    src = /. + project;
    lockFile = /. + companion;
    dubLock = /. + nativeLock;
  };
  lock = import ./read-lock.nix { inherit (pkgs) lib; } args;
in
if target == "environment" then
  pkgs.callPackage ./environment.nix { inherit purifier nativeDub toolchain; } {
    inherit lock configuration buildType;
  }
else if target == "release" then
  (pkgs.callPackage ./build-project.nix { inherit purifier nativeDub toolchain; } (
    args // { inherit configuration buildType; }
  )).release
else
  throw "dub-purifier: unknown target"
