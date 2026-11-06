{
  pkgs,
  built,
  product,
  diagnosticGlobal ? false,
}:
let
  view = built.projections.native;
in
pkgs.runCommand "dub-native-projection-consumers"
  {
    nativeBuildInputs = [
      pkgs.gcc
      (pkgs.python3.withPackages (ps: [ ps.cffi ]))
      pkgs.jdk25
      pkgs.coreutils
    ];
  }
  ''
      set -euo pipefail
      mkdir -p "$out"
      export PYTHONPATH=${view}
      python3 - <<'PY'
    import json
    from pathlib import Path
    catalog=json.loads(Path('${view}/catalog.json').read_text())
    assert catalog['targets']['purifier-native-proof']['runtime']==json.loads('${builtins.toJSON product.runtime}')
    assert catalog['prefix']=='${built.packages.project}'
    assert set(catalog['libraries'])=={'purifier-native-proof'}
    assert Path(catalog['libraries']['purifier-native-proof']).parent==Path(catalog['prefix'])/'lib'
    Path('library-path').write_text(catalog['libraries']['purifier-native-proof'])
    PY
      lib=$(cat library-path)
      gcc ${./native-consumer.c} -ldl -o c-consumer
      ./c-consumer "$lib" > "$out/c.txt" 2> "$out/c.stderr"
      python3 ${./native-ctypes.py} "$lib" > "$out/ctypes.json" 2> "$out/ctypes.stderr"
      python3 ${./native-cffi.py} "$lib" > "$out/cffi.json" 2> "$out/cffi.stderr"
      cp ${./NativeConsumer.java} NativeConsumer.java
      javac NativeConsumer.java
      timeout 25s java --enable-native-access=ALL-UNNAMED @${view}/java.args NativeConsumer "$lib" confined > "$out/java.txt" 2> "$out/java.stderr"
      test ! -s "$out/c.stderr"
      test ! -s "$out/ctypes.stderr"
      test ! -s "$out/cffi.stderr"
      test ! -s "$out/java.stderr"
      ${pkgs.lib.optionalString diagnosticGlobal ''
        # Preserve unsupported global-lifetime controls as diagnostics, without suppressing warnings.
        timeout 25s java --enable-native-access=ALL-UNNAMED @${view}/java.args NativeConsumer "$lib" > "$out/java-global.txt" 2> "$out/java-global.stderr"
        timeout 25s java --enable-native-access=ALL-UNNAMED @${view}/java.args NativeConsumer "$lib" retain > "$out/java-global-retain.txt" 2> "$out/java-global-retain.stderr"
      ''}
      cp ${view}/catalog.json "$out/catalog.json"
  ''
