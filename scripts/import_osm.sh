#!/usr/bin/env bash
set -euo pipefail

MODE=${MODE:-focused}

if [ ! -f .env ]; then
  echo ".env not found; copy from .env.example" >&2
fi

make osm-download
make osm-import
make transform MODE=${MODE}
