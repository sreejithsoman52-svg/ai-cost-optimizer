#!/usr/bin/env bash
# Packages each Lambda folder into a .zip that terraform/main.tf expects
# at ../lambdas/<name>.zip. Run from the repo root.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/lambdas"

for dir in cost_collector waste_detector bill_forecaster claude_analyser report_generator alerter; do
  echo "== Packaging $dir =="
  build="$(mktemp -d)"
  cp "$dir/handler.py" "$build/"
  if [ -s "$dir/requirements.txt" ]; then
    # --platform/--only-binary ensures compiled deps (e.g. claude_analyser's
    # anthropic -> pydantic-core) are Lambda-compatible even when building
    # on macOS/Windows.
    pip install -r "$dir/requirements.txt" -t "$build" \
      --platform manylinux2014_x86_64 --only-binary=:all: \
      --python-version 3.12 --no-deps 2>/dev/null || \
    pip install -r "$dir/requirements.txt" -t "$build" \
      --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.12
  fi
  rm -f "$dir.zip"
  (cd "$build" && zip -qr "$ROOT_DIR/lambdas/$dir.zip" .)
  rm -rf "$build"
  echo "   -> lambdas/$dir.zip"
done

echo ""
echo "All Lambdas packaged. Terraform expects them at lambdas/<name>.zip"
echo "relative to the repo root (main.tf references ../lambdas/<name>.zip"
echo "from inside the terraform/ directory) — already correct, no move needed."
