# SPDX-License-Identifier: MIT
{ lib }:
{
  src,
  lockFile ? src + "/dub-purifier.lock.json",
  dubLock ? src + "/dub.selections.json",
}:
let
  exists = builtins.pathExists lockFile && builtins.pathExists dubLock;
  raw = if exists then builtins.fromJSON (builtins.readFile lockFile) else { };
  data = if builtins.isAttrs raw then raw else { };
  safeName = s: builtins.isString s && builtins.match "[a-z][a-z0-9_-]*" s != null;
  safeFile = s: builtins.isString s && builtins.match "[a-z][a-z0-9_.+-]*\\.zip" s != null;
  profiles = data.profiles or { };
  validEntry =
    e:
    builtins.isAttrs e
    && safeFile (e.path or null)
    && builtins.isString (e.url or null)
    && lib.hasPrefix "https://" e.url
    && builtins.match "https://[^/@?#]+/[^@?#]+" e.url != null
    && builtins.isString (e.hash or null)
    && builtins.match "sha256-[A-Za-z0-9+/]{43}=" e.hash != null
    && (e.mirrors or null) == [ ];
  validProfile =
    p:
    builtins.isAttrs p
    && safeName (p.rootName or null)
    && builtins.elem (p.system or null) [
      "x86_64-linux"
      "aarch64-linux"
    ]
    && builtins.elem (p.buildType or null) [
      "debug"
      "release"
      "unittest"
    ]
    && builtins.isString (p.configuration or null)
    && builtins.match "[A-Za-z0-9_-]*" p.configuration != null
    && builtins.isString (p.targetFileName or null)
    && baseNameOf p.targetFileName == p.targetFileName
    && builtins.isList (p.entries or null)
    && builtins.all validEntry p.entries
    && builtins.isAttrs (p.registryMetadata or null)
    && builtins.isAttrs (p.nativeSelections or null)
    && (p.nativeSelections.fileVersion or null) == 1
    && builtins.isAttrs (p.nativeSelections.versions or null)
    && builtins.all safeName (builtins.attrNames p.nativeSelections.versions)
    && builtins.all (
      v: builtins.isString v && builtins.match "[0-9]+\\.[0-9]+\\.[0-9]+([-+][A-Za-z0-9.-]+)?" v != null
    ) (builtins.attrValues p.nativeSelections.versions);
  manifests = data.manifests or { };
  validManifests =
    builtins.isAttrs manifests
    && manifests != { }
    &&
      builtins.attrNames manifests == builtins.filter (name: builtins.pathExists (src + "/${name}")) [
        "dub.json"
        "dub.sdl"
        "dub.settings.json"
      ]
    && builtins.all (
      name:
      builtins.elem name [
        "dub.json"
        "dub.sdl"
        "dub.settings.json"
      ]
      && builtins.isAttrs manifests.${name}
      && builtins.isString (manifests.${name}.content or null)
      && builtins.pathExists (src + "/${name}")
      && builtins.hashFile "sha256" (src + "/${name}") == (manifests.${name}.sha256 or null)
      && builtins.hashString "sha256" manifests.${name}.content == manifests.${name}.sha256
    ) (builtins.attrNames manifests);
  structure =
    (data.version or null) == 1
    && builtins.isAttrs profiles
    && profiles != { }
    && builtins.all (
      name:
      let
        p = profiles.${name};
      in
      validProfile p && name == "${p.system}:${p.configuration}:${p.buildType}"
    ) (builtins.attrNames profiles)
    && builtins.isAttrs (data.toolVersions or null)
    && builtins.all (name: builtins.isString (data.toolVersions.${name} or null)) [
      "dub"
      "ldc"
      "sdk"
    ];
  problems =
    lib.optional (!exists) "DUB selections and companion lockfile are required"
    ++ lib.optional (!structure) "Unsupported or invalid DUB companion lock"
    ++ lib.optional (!validManifests) "DUB manifest changed; run dub-purifier lock"
    ++ lib.optional (
      exists && builtins.hashFile "sha256" dubLock != (data.nativeSelectionsHash or null)
    ) "DUB selections changed; run dub-purifier lock";
  entries =
    if structure then lib.unique (lib.concatMap (p: p.entries) (builtins.attrValues profiles)) else [ ];
in
{
  purifier = "dub";
  inherit data entries problems;
  outputs = {
    packages = [
      "default"
      "environment"
      "project"
    ];
    tests = [ "default" ];
    release = [ "default" ];
  };
}
