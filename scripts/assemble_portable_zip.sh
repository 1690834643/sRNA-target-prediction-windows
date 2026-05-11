#!/bin/bash
# Assemble srna-win-target-portable.zip from:
#   dist/srna-win-target-web.exe (built by scripts/build_windows_exe.py on Windows Python)
#   bundled_tools/ (miranda/, rnahybrid/, pita/)
#   examples/
#   LICENSES/
#   README.txt
#
# Output: srna-win-target-portable.zip in repo root.

set -euo pipefail

ROOT=${ROOT:-/home/nee/srna-win-target}
# Default to the repo-local dist/ that build_windows_exe.py and the manual
# Windows-side PyInstaller flow both leave their artefact in. Override with
# BUILD_ROOT=/path/to/build-tree if you keep the exe elsewhere.
BUILD_ROOT=${BUILD_ROOT:-"$ROOT"}
EXE_NAME=srna-win-target-web.exe

STAGE=$(mktemp -d)
RELEASE="$STAGE/srna-win-target-portable"
mkdir -p "$RELEASE/bundled_tools"

echo "[1/6] copy exe from $BUILD_ROOT/dist/$EXE_NAME"
if [ ! -f "$BUILD_ROOT/dist/$EXE_NAME" ]; then
  echo "ERROR: $BUILD_ROOT/dist/$EXE_NAME not found"
  exit 2
fi
cp "$BUILD_ROOT/dist/$EXE_NAME" "$RELEASE/"

echo "[2/6] bundled_tools (tar pipe for speed; perl/ is many small files)"
# Using tar streaming avoids per-file stat overhead vs cp -r on /mnt/c
tar c -C "$ROOT/bundled_tools" miranda rnahybrid pita | tar x -C "$RELEASE/bundled_tools/"

echo "[3/6] examples"
cp -r "$ROOT/examples" "$RELEASE/examples"

echo "[4/6] LICENSES"
cp -r "$ROOT/LICENSES" "$RELEASE/LICENSES"

echo "[5/6] portable README"
cat > "$RELEASE/README.txt" <<'EOF'
sRNA Target Predictor — Portable Windows release
================================================

Quickstart:
  1. Extract this zip anywhere (no installer needed).
  2. Double-click srna-win-target-web.exe.
  3. Your browser opens at http://127.0.0.1:5173 .
  4. Top status banner should show "已就绪 · 3/3 工具自动检测到" (all green).
  5. Click "💡 一键跑示例数据" to verify in 10 seconds, or pick your own
     miRNA / Targets FASTA via the file pickers and hit "开始预测 · Run".

Layout:
  srna-win-target-web.exe       FastAPI server + browser UI (~46 MB)
  bundled_tools/
    miranda/miranda.exe         miRanda 3.3a Win64 static
    rnahybrid/RNAhybrid.exe     RNAhybrid 2.1.2 Win64 static
    pita/
      pita_prediction.pl        PITA driver (Linux paths rewritten to relative)
      lib/                      PITA helper Perl scripts
      RNAduplex.exe             PITA-patched Vienna-1.6 (supports -5 N + force_binding)
      RNAddG.exe / RNAddG4.exe  PITA-bundled ddG computers (Vienna-1.6 source)
      default.par               ViennaRNA thermodynamic parameter file
      bin/                      busybox/MSYS coreutils: cat/sed/sort/tr/cut/...
      perl/                     Strawberry Perl 5.42.2.1 portable (stripped)
  examples/input/
    mirna.fa, targets.fa        ready-to-use demo inputs
  LICENSES/NOTICE.txt           third-party license notices

Settings:
  Default output folder        %USERPROFILE%\Desktop\srna-target-results
  Default port                 127.0.0.1:5173 (loopback only)
  Override port                set SRNA_WEB_PORT=5180 before launching
  Skip browser auto-open       set SRNA_WEB_NO_BROWSER=1

PITA ΔG values are bit-exact with the upstream Linux PITA reference (all 13
result columns verified). The perl driver still pipes through POSIX shell
tools; we ship MSYS / busybox builds in bundled_tools/pita/bin/. If your
output folder path contains non-ASCII characters or spaces, the wrapper
will refuse early with a clear message — pick an ASCII path or switch
Backend to "wsl" in Advanced settings.

Reporting issues: please include the exact "log" pane content (last 30
lines) and the screenshot of the top status banner.
EOF

echo "[6/6] zip"
cd "$STAGE"
ZIP_OUT="$ROOT/srna-win-target-portable.zip"
rm -f "$ZIP_OUT"
zip -q -r "$ZIP_OUT" srna-win-target-portable/
SIZE=$(stat -c '%s' "$ZIP_OUT")
SHA=$(sha256sum "$ZIP_OUT" | awk '{print $1}')

echo ""
echo "DONE"
echo "  output: $ZIP_OUT"
echo "  size:   $(numfmt --to=iec --suffix=B "$SIZE")"
echo "  sha256: $SHA"

# Cleanup
rm -rf "$STAGE"

# Also write sha256 sidecar
echo "$SHA  srna-win-target-portable.zip" > "${ZIP_OUT}.sha256"
echo "  sidecar: ${ZIP_OUT}.sha256"
