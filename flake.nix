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
          nativeDub = scope.callPackage ./nix/dub.nix { };
          nativeServeD = scope.callPackage ./nix/serve-d.nix { };
          nativeDcd = scope.callPackage ./nix/dcd.nix { };
          toolchain = scope.callPackage ./nix/toolchain.nix { };
          cli = scope.callPackage ./nix/cli.nix {
            nixpkgsSrc = nixpkgs;
            purifierSrc = purifier;
          };
          buildDubProject = scope.callPackage ./nix/build-project.nix {
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
      lib.dub-purifier.readLock = import ./nix/read-lock.nix { lib = nixpkgs.lib; };
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
