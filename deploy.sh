#!/usr/bin/env bash
# Deploy ev_assistant from dev clone to live HA installation
set -e

SRC="/root/ev_assistant_dev/custom_components/ev_assistant"
DEST="/homeassistant/custom_components/ev_assistant"

rsync -av --delete \
  --exclude='.git' \
  --exclude='deploy.sh' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  "$SRC/" "$DEST/"

echo ""
echo "Deployed to $DEST"
echo "Run: ha core restart --no-progress --raw-json"
