#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
chmod +x "$ROOT/caj-to-pdf" "$ROOT/install-desktop.sh" "$ROOT/开始转换.sh" "$ROOT/安装到桌面.sh" 2>/dev/null || true
if ! command -v python3 >/dev/null 2>&1; then
  echo "还没有安装 Python 3。"
  exit 1
fi
exec python3 -m app --install
