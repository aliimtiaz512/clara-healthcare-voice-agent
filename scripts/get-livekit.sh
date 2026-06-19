#!/usr/bin/env bash
# Download the LiveKit server binary for Linux into ./livekit-server/livekit-server
# (the committed livekit-server.exe is for the Windows demo machine).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/livekit-server/livekit-server"

ARCH="$(uname -m)"
case "$ARCH" in
  x86_64)  LKARCH=amd64 ;;
  aarch64|arm64) LKARCH=arm64 ;;
  *) echo "Unsupported arch: $ARCH" >&2; exit 1 ;;
esac

TAG="$(curl -s https://api.github.com/repos/livekit/livekit/releases/latest \
        | grep -oP '"tag_name":\s*"v\K[^"]+')"

echo "Downloading LiveKit server v$TAG (linux/$LKARCH) ..."
URL="https://github.com/livekit/livekit/releases/download/v${TAG}/livekit_${TAG}_linux_${LKARCH}.tar.gz"
TMP="$(mktemp -d)"
curl -sSL "$URL" -o "$TMP/lk.tar.gz"
tar xzf "$TMP/lk.tar.gz" -C "$TMP" livekit-server
mv "$TMP/livekit-server" "$DEST"
chmod +x "$DEST"
rm -rf "$TMP"
echo "Installed → $DEST"
