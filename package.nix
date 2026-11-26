{
  lib,
  stdenv,
  fetchurl,
}: let
  version = "0.6.0";

  hashes = {
    x86_64-linux = "sha256-T6sUBwAHqyW9C31FRIaHivI1GDaWbt7kT5T1W7QoQqY=";
    aarch64-linux = "sha256-tiI7Eui4xNR4T8pKOkdQcsY396pMo98abrj/2POdv9c=";
  };

  archSuffix = {
    x86_64-linux = "x86_64";
    aarch64-linux = "arm64";
  };

  system = stdenv.hostPlatform.system;
in
  stdenv.mkDerivation rec {
    pname = "chatto";
    inherit version;

    src = fetchurl {
      url = "https://github.com/chattocorp/chatto/releases/download/v${version}/chatto_Linux_${archSuffix.${system}}.tar.gz";
      hash = hashes.${system};
    };

    # Static Go binary; no patching needed.
    dontConfigure = true;
    dontBuild = true;
    dontStrip = true;

    sourceRoot = ".";

    installPhase = ''
      runHook preInstall
      install -Dm755 chatto $out/bin/chatto
      runHook postInstall
    '';

    meta = with lib; {
      description = "Self-hostable team and group chat application";
      homepage = "https://docs.chatto.run";
      license = licenses.agpl3Plus;
      mainProgram = "chatto";
      platforms = builtins.attrNames hashes;
      sourceProvenance = with sourceTypes; [binaryNativeCode];
    };
  }
