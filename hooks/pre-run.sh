#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f pyproject.toml ]]; then
  echo "pyproject.toml missing" >&2
  exit 1
fi

echo "pre-run checks passed"
