# nix-chatto

Nix flake for the [Chatto](https://github.com/chattocorp/chatto) release binary (linux x86_64 and aarch64).

```nix
{
  inputs.chatto.url = "github:abl/nix-chatto";
  inputs.chatto.inputs.nixpkgs.follows = "nixpkgs";
}
```

`chatto.packages.<system>.default` is the package. `chatto.overlays.default` adds `pkgs.chatto`.

`.github/workflows/update-chatto.yml` opens a pull request when GitHub publishes a new stable release. Pre-releases, including the 0.5 beta line, are ignored. Those pull requests are not auto-merged.

The Nix expressions in this repository are MIT. The Chatto binary they install is AGPL-3.0-or-later, from the upstream release.
