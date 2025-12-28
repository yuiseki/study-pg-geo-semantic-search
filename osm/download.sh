#!/usr/bin/env bash
set -euo pipefail

DEST="${1:-osm/kanto-latest.osm.pbf}"
URL="https://download.geofabrik.de/asia/japan/kanto-latest.osm.pbf"

mkdir -p "$(dirname "$DEST")"

echo "Downloading ${URL} -> ${DEST}"
if command -v curl >/dev/null 2>&1; then
  curl -L -o "$DEST" "$URL"
elif command -v wget >/dev/null 2>&1; then
  wget -O "$DEST" "$URL"
else
  echo "curl or wget is required" >&2
  exit 1
fi
