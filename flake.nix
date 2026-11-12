# SPDX-License-Identifier: MIT
{
  description = "Locked, Nix-resolved dependencies for Dub";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  inputs.purifier = {
    url = "github:nix-purifiers/purifier";
    flake = false;
  };
  outputs =
    {
      self,
      nixpkgs,
      purifier,
    }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAll = nixpkgs.lib.genAttrs systems;
      overlay = final: prev: {
        dub-purifier = final.lib.makeScope final.newScope (scope: {
          nativeDub = scope.callPackage ./pkgs/native-dub/default.nix { };
          nativeServeD = scope.callPackage ./pkgs/native-serve-d/default.nix { };
          nativeDcd = scope.callPackage ./pkgs/native-dcd/default.nix { };
          toolchain = scope.callPackage ./pkgs/toolchain/default.nix { };
          cli = scope.callPackage ./pkgs/cli/default.nix {
            nixpkgsSrc = nixpkgs;
            purifierSrc = purifier;
          };
          buildDubProject = scope.callPackage ./pkgs/build-dub-project/default.nix {
            purifier = import (purifier + "/nix/lib") { inherit (final) lib; };
          };
        });
      };
      pkgsFor =
        system:
        import nixpkgs {
          inherit system;
          overlays = [ overlay ];
        };
    in
    {
      overlays.default = overlay;
      packages = forAll (system: {
        native = (pkgsFor system).dub-purifier.nativeDub;
        default = (pkgsFor system).dub-purifier.cli;
        cli = self.packages.${system}.default;
      });
      lib.dub-purifier = (nixpkgs.lib.extend (import ./lib-overlays/default { }).overlay).dub-purifier;
      apps = forAll (system: {
        default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/dub-purifier";
          meta.description = "Lock and prefetch Dub dependencies";
        };
      });
      checks = forAll (
        system:
        import ./tests {
          pkgs = pkgsFor system;
          inherit self;
        }
      );
      formatter = forAll (system: (pkgsFor system).nixfmt-tree);
    };
}
