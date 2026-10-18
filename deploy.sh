#!/usr/bin/env bash
# Deploy ev_assistant from this clone to a live Home Assistant installation.
#
# Standard: die Komponente aus DIESEM Klon (Ordner dieses Skripts) nach
# /homeassistant/custom_components/ev_assistant. Beides per Umgebungsvariable
# ueberschreibbar, z.B. fuer eine andere HA-Instanz oder einen Probelauf:
#   DEST=/tmp/probe/ev_assistant ./deploy.sh
#   DRY_RUN=1 ./deploy.sh          # zeigt nur, was kopiert/geloescht wuerde
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="${SRC:-$REPO_DIR/custom_components/ev_assistant}"
DEST="${DEST:-/homeassistant/custom_components/ev_assistant}"

if [[ ! -f "$SRC/manifest.json" ]]; then
  echo "Quelle nicht gefunden (kein manifest.json in $SRC)" >&2
  exit 1
fi

RSYNC_FLAGS=(-av --delete --exclude='.git' --exclude='__pycache__' --exclude='*.pyc')
[[ -n "${DRY_RUN:-}" ]] && RSYNC_FLAGS+=(--dry-run)

[[ -n "${DRY_RUN:-}" ]] || mkdir -p "$DEST"
rsync "${RSYNC_FLAGS[@]}" "$SRC/" "$DEST/"

echo ""
if [[ -n "${DRY_RUN:-}" ]]; then
  echo "Probelauf (DRY_RUN) -- nichts veraendert: $SRC -> $DEST"
else
  echo "Deployed $SRC -> $DEST"
  echo "Run: ha core restart --no-progress --raw-json"
fi
