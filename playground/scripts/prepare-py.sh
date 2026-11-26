#!/usr/bin/env bash
# Put what the page needs to run Python next to it:
# - the Pyodide runtime, from the npm package;
# - pyarrow and numpy built for Pyodide (WebAssembly), from the Pyodide distribution;
# - the leakcheck wheel built from this checkout;
# - the two sample splits.
# Set PYODIDE_WHEELS to a directory that already holds the Pyodide wheels to skip the
# download.
set -euo pipefail

HERE=$(cd "$(dirname "$0")/.." && pwd)
REPO=$(cd "$HERE/.." && pwd)
PY=${PYTHON:-python3}
VERSION=$(node -p "require('$HERE/node_modules/pyodide/package.json').version")
CDN="https://cdn.jsdelivr.net/pyodide/v$VERSION/full"
NATIVE=(
  numpy-2.0.2-cp312-cp312-pyodide_2024_0_wasm32.whl
  pyarrow-18.1.0-cp312-cp312-pyodide_2024_0_wasm32.whl
  pyodide_unix_timezones-1.0.0-py3-none-any.whl
)

rm -rf "$HERE/public/pyodide" "$HERE/public/py" "$HERE/public/samples"
mkdir -p "$HERE/public/pyodide" "$HERE/public/py"

for f in pyodide.mjs pyodide.asm.js pyodide.asm.wasm python_stdlib.zip pyodide-lock.json; do
  cp "$HERE/node_modules/pyodide/$f" "$HERE/public/pyodide/"
done

for f in "${NATIVE[@]}"; do
  if [ -n "${PYODIDE_WHEELS:-}" ]; then
    cp "$PYODIDE_WHEELS/$f" "$HERE/public/py/"
  else
    curl -fsSL --retry 3 -o "$HERE/public/py/$f" "$CDN/$f"
  fi
done

"$PY" -m pip wheel -q --no-deps -w "$HERE/public/py" "$REPO"
LEAKCHECK=$(cd "$HERE/public/py" && ls leakcheck-*.whl)
printf '{"native": ["%s", "%s", "%s"], "pure": ["%s"]}\n' "${NATIVE[@]}" "$LEAKCHECK" \
  > "$HERE/public/py/manifest.json"

"$PY" "$HERE/scripts/make_samples.py" "$HERE/public/samples"
echo "prepared: $(cat "$HERE/public/py/manifest.json")"
