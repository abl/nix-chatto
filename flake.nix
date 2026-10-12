{
  description = "Nix package for the Chatto release binary";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = {self, nixpkgs}: let
    systems = ["x86_64-linux" "aarch64-linux"];
    forAllSystems = nixpkgs.lib.genAttrs systems;
  in {
    packages = forAllSystems (system: let
      pkgs = nixpkgs.legacyPackages.${system};
    in {
      chatto = pkgs.callPackage ./package.nix {};
      default = self.packages.${system}.chatto;
    });

    overlays.default = final: _prev: {
      chatto = final.callPackage ./package.nix {};
    };
  };
}
