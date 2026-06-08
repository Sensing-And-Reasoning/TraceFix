#!/usr/bin/env bash
# Download the pinned tla2tools.jar (v1.8.0) into lib/ and verify its checksum.
# TraceFix's verification toolchain (pcal.trans + TLC) runs from this jar.
#
# Usage:  bash scripts/download_tla2tools.sh
# Idempotent: if lib/tla2tools.jar already matches the expected checksum, it is left alone.
set -euo pipefail

VERSION="1.8.0"
URL="https://github.com/tlaplus/tlaplus/releases/download/v${VERSION}/tla2tools.jar"
EXPECTED_SHA256="237332bdcc79a35c7d26efa7b82c77c85c2744591c5598673a8a45085ff2a4fb"

# Resolve repo root (this script lives in <repo>/scripts/).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEST="${REPO_ROOT}/lib/tla2tools.jar"

# Cross-platform sha256: prefer sha256sum (Linux), fall back to shasum (macOS).
sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    echo "ERROR: need sha256sum or shasum to verify the download" >&2
    exit 1
  fi
}

if [ -f "${DEST}" ] && [ "$(sha256_of "${DEST}")" = "${EXPECTED_SHA256}" ]; then
  echo "tla2tools.jar v${VERSION} already present and verified at ${DEST}"
  exit 0
fi

mkdir -p "${REPO_ROOT}/lib"
echo "Downloading tla2tools.jar v${VERSION} ..."
if command -v curl >/dev/null 2>&1; then
  curl -fsSL "${URL}" -o "${DEST}"
elif command -v wget >/dev/null 2>&1; then
  wget -q "${URL}" -O "${DEST}"
else
  echo "ERROR: need curl or wget to download ${URL}" >&2
  exit 1
fi

ACTUAL="$(sha256_of "${DEST}")"
if [ "${ACTUAL}" != "${EXPECTED_SHA256}" ]; then
  echo "ERROR: checksum mismatch for ${DEST}" >&2
  echo "  expected ${EXPECTED_SHA256}" >&2
  echo "  got      ${ACTUAL}" >&2
  echo "Delete the file and retry, or download v${VERSION} manually from:" >&2
  echo "  ${URL}" >&2
  exit 1
fi

echo "OK — tla2tools.jar v${VERSION} verified at ${DEST}"
