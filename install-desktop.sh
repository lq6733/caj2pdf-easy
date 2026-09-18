#!/usr/bin/env bash
# Install a desktop icon and a Files/Nautilus right-click action.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
chmod +x "$ROOT/caj-to-pdf" "$ROOT/install-desktop.sh" "$ROOT/开始转换.sh" "$ROOT/安装到桌面.sh" 2>/dev/null || true

BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
mkdir -p "$BIN_DIR"
LAUNCHER="$BIN_DIR/caj-to-pdf"
cat > "$LAUNCHER" <<INNER
#!/usr/bin/env bash
exec "$ROOT/caj-to-pdf" "\$@"
INNER
chmod +x "$LAUNCHER"

APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$APP_DIR"
DESKTOP_FILE="$APP_DIR/caj2pdf-easy.desktop"
cat > "$DESKTOP_FILE" <<INNER
[Desktop Entry]
Type=Application
Version=1.0
Name=CAJ 转 PDF
Name[en]=CAJ to PDF
Comment=把知网 CAJ 文件一键转成 PDF
Comment[en]=Convert CNKI CAJ files to PDF
Exec=$LAUNCHER %F
Icon=$ROOT/share/caj2pdf-easy.svg
Terminal=false
Categories=Office;Utility;
StartupNotify=true
Keywords=CAJ;PDF;知网;CNKI;convert;
MimeType=application/octet-stream;
INNER
chmod +x "$DESKTOP_FILE"

DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
if [[ -z "${DESKTOP_DIR:-}" || ! -d "$DESKTOP_DIR" ]]; then
  if [[ -d "$HOME/桌面" ]]; then
    DESKTOP_DIR="$HOME/桌面"
  else
    DESKTOP_DIR="$HOME/Desktop"
  fi
fi
if [[ -d "$DESKTOP_DIR" ]]; then
  cp "$DESKTOP_FILE" "$DESKTOP_DIR/CAJ转PDF.desktop"
  chmod +x "$DESKTOP_DIR/CAJ转PDF.desktop"
  if command -v gio >/dev/null 2>&1; then
    gio set "$DESKTOP_DIR/CAJ转PDF.desktop" metadata::trusted true >/dev/null 2>&1 || true
  fi
fi

NAUTILUS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/nautilus/scripts"
mkdir -p "$NAUTILUS_DIR"
cat > "$NAUTILUS_DIR/转成 PDF" <<INNER
#!/usr/bin/env bash
set -euo pipefail
if [[ -n "\${NAUTILUS_SCRIPT_SELECTED_FILE_PATHS:-}" ]]; then
  mapfile -t FILES < <(printf '%s' "\$NAUTILUS_SCRIPT_SELECTED_FILE_PATHS")
  exec "$LAUNCHER" --auto "\${FILES[@]}"
fi
exec "$LAUNCHER" --auto "\$@"
INNER
chmod +x "$NAUTILUS_DIR/转成 PDF"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
fi

echo "安装完成 / Installed."
echo "1. 桌面图标：CAJ转PDF"
echo "2. 应用菜单里也可以搜到“CAJ 转 PDF”"
echo "3. 文件管理器中可右键 -> 脚本 -> 转成 PDF"
echo "If the desktop icon is marked untrusted, right-click it and choose Allow Launching."
