#!/usr/bin/env bash
set -Eeuo pipefail
cd -- "$(dirname -- "$0")/.."
if (( $# == 0 )); then set -- build; fi
exec "${VOCALISMETA_RELEASE_PYTHON:-python3}" scripts/release.py "$@"
