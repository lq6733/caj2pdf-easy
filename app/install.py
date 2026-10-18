"""Install a one-click desktop shortcut on Windows, macOS, and Linux."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _desktop_dir() -> Path:
    home = Path.home()
    if sys.platform == "win32":
        desktop = home / "Desktop"
        if desktop.is_dir():
            return desktop
        return home / "桌面"
    xdg = shutil.which("xdg-user-dir")
    if xdg:
        try:
            out = subprocess.check_output([xdg, "DESKTOP"], text=True).strip()
            if out:
                path = Path(out)
                if path.is_dir():
                    return path
        except Exception:
            pass
    for name in ("桌面", "Desktop"):
        candidate = home / name
        if candidate.is_dir():
            return candidate
    return home / "Desktop"


def _chmod_exec(path: Path) -> None:
    try:
        path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    except OSError:
        pass


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n" if os.name != "nt" else "\r\n")


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _create_windows_shortcut(lnk: Path, target: str, workdir: str, icon: str, args: str = "") -> None:
    command = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut(%s); "
        "$s.TargetPath = %s; "
        "$s.WorkingDirectory = %s; "
        "$s.WindowStyle = 7; "
        "$s.IconLocation = %s; "
        % (_ps_quote(str(lnk)), _ps_quote(target), _ps_quote(workdir), _ps_quote(icon))
    )
    if args:
        command += "$s.Arguments = %s; " % _ps_quote(args)
    command += "$s.Save()"
    subprocess.run(
        ["powershell", "-NoProfile", "-STA", "-Command", command],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _install_windows() -> list[str]:
    desktop = _desktop_dir()
    desktop.mkdir(parents=True, exist_ok=True)
    bat = desktop / "CAJ转PDF.bat"
    _write(
        bat,
        "\n".join(
            [
                "@echo off",
                "chcp 65001 >nul",
                f'cd /d "{ROOT}"',
                "call \"开始转换.bat\" %*",
            ]
        )
        + "\n",
    )
    notes = [f"桌面启动脚本：{bat}"]
    try:
        from app.icon import ICO_PATH, ensure_icons

        ensure_icons()
        icon = str(ICO_PATH) if ICO_PATH.is_file() else ""
    except Exception:
        icon = ""
    lnk = desktop / "CAJ转PDF.lnk"
    if icon:
        try:
            _create_windows_shortcut(lnk, str(bat), str(ROOT), icon)
            notes.insert(0, f"桌面图标：{lnk}")
        except Exception:
            pass
    start_menu = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    try:
        start_menu.mkdir(parents=True, exist_ok=True)
        menu_bat = start_menu / "CAJ转PDF.bat"
        shutil.copyfile(bat, menu_bat)
        notes.append(f"开始菜单：{menu_bat}")
        if icon:
            try:
                _create_windows_shortcut(start_menu / "CAJ转PDF.lnk", str(bat), str(ROOT), icon)
            except Exception:
                pass
    except OSError:
        pass
    return notes


def _install_macos() -> list[str]:
    desktop = _desktop_dir()
    desktop.mkdir(parents=True, exist_ok=True)
    command = desktop / "CAJ转PDF.command"
    _write(
        command,
        "\n".join(
            [
                "#!/bin/bash",
                f'cd "{ROOT}"',
                'exec "' + str(ROOT / "开始转换.command") + '" "$@"',
            ]
        )
        + "\n",
    )
    _chmod_exec(command)
    _chmod_exec(ROOT / "开始转换.command")
    notes = [f"桌面脚本：{command}", "若系统提示无法打开，请右键该图标选择「打开」。"]
    app = desktop / "CAJ转PDF.app"
    try:
        from app import __version__
        from app.icon import ICNS_PATH, ensure_icons

        ensure_icons()
        macos = app / "Contents" / "MacOS"
        resources = app / "Contents" / "Resources"
        macos.mkdir(parents=True, exist_ok=True)
        resources.mkdir(parents=True, exist_ok=True)
        launcher = macos / "CAJ转PDF"
        _write(
            launcher,
            "\n".join(
                [
                    "#!/bin/bash",
                    'export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"',
                    f'cd "{ROOT}"',
                    'exec "' + str(ROOT / "开始转换.command") + '" "$@"',
                    "",
                ]
            ),
        )
        _chmod_exec(launcher)
        if ICNS_PATH.is_file():
            shutil.copyfile(ICNS_PATH, resources / "caj2pdf-easy.icns")
        plist = app / "Contents" / "Info.plist"
        plist.write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>CAJ 转 PDF</string>
  <key>CFBundleDisplayName</key><string>CAJ 转 PDF</string>
  <key>CFBundleIdentifier</key><string>io.github.caj2pdf.easy</string>
  <key>CFBundleVersion</key><string>%s</string>
  <key>CFBundleShortVersionString</key><string>%s</string>
  <key>CFBundleExecutable</key><string>CAJ转PDF</string>
  <key>CFBundleIconFile</key><string>caj2pdf-easy</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSMinimumSystemVersion</key><string>10.13</string>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
"""
            % (__version__, __version__),
            encoding="utf-8",
        )
        notes.insert(0, f"桌面图标：{app}")
    except Exception as exc:
        notes.append(f"未能创建带图标的应用（可用桌面脚本）：{exc}")
    return notes


def _install_linux() -> list[str]:
    notes: list[str] = []
    bin_dir = Path(os.environ.get("XDG_BIN_HOME", str(Path.home() / ".local" / "bin")))
    bin_dir.mkdir(parents=True, exist_ok=True)
    launcher = bin_dir / "caj-to-pdf"
    _write(
        launcher,
        "\n".join(["#!/usr/bin/env bash", f'exec "{ROOT / "caj-to-pdf"}" "$@"', ""]) ,
    )
    _chmod_exec(launcher)
    _chmod_exec(ROOT / "caj-to-pdf")
    notes.append(f"命令：{launcher}")

    app_dir = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "applications"
    app_dir.mkdir(parents=True, exist_ok=True)
    desktop_file = app_dir / "caj2pdf-easy.desktop"
    icon = ROOT / "share" / "caj2pdf-easy.svg"
    _write(
        desktop_file,
        "\n".join(
            [
                "[Desktop Entry]",
                "Type=Application",
                "Version=1.0",
                "Name=CAJ 转 PDF",
                "Name[en]=CAJ to PDF",
                "Comment=把知网 CAJ 或 EPUB 电子书一键转成 PDF",
                "Comment[en]=Convert CNKI CAJ files and EPUB books to PDF",
                f"Exec={launcher} %F",
                f"Icon={icon}",
                "Terminal=false",
                "Categories=Office;Utility;",
                "StartupNotify=true",
                "Keywords=CAJ;PDF;EPUB;知网;CNKI;convert;",
                "MimeType=application/octet-stream;application/epub+zip;",
                "",
            ]
        ),
    )
    _chmod_exec(desktop_file)
    notes.append(f"应用菜单：{desktop_file}")

    desktop_dir = _desktop_dir()
    if desktop_dir.is_dir():
        dest = desktop_dir / "CAJ转PDF.desktop"
        shutil.copyfile(desktop_file, dest)
        _chmod_exec(dest)
        gio = shutil.which("gio")
        if gio:
            subprocess.run([gio, "set", str(dest), "metadata::trusted", "true"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        notes.append(f"桌面图标：{dest}")

    nautilus = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "nautilus" / "scripts"
    nautilus.mkdir(parents=True, exist_ok=True)
    script = nautilus / "转成 PDF"
    _write(
        script,
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                'if [[ -n "${NAUTILUS_SCRIPT_SELECTED_FILE_PATHS:-}" ]]; then',
                '  mapfile -t FILES < <(printf "%s" "$NAUTILUS_SCRIPT_SELECTED_FILE_PATHS")',
                f'  exec "{launcher}" --auto "${{FILES[@]}}"',
                "fi",
                f'exec "{launcher}" --auto "$@"',
                "",
            ]
        ),
    )
    _chmod_exec(script)
    notes.append("文件管理器右键：脚本 → 转成 PDF")

    update = shutil.which("update-desktop-database")
    if update:
        subprocess.run([update, str(app_dir)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return notes


def install_shortcuts() -> int:
    if sys.platform == "win32":
        notes = _install_windows()
    elif sys.platform == "darwin":
        notes = _install_macos()
    else:
        notes = _install_linux()

    print("安装完成。")
    for note in notes:
        print(" -", note)
    if sys.platform.startswith("linux"):
        print("如果桌面图标显示未信任，请右键选择「允许启动」。")
    return 0


if __name__ == "__main__":
    from app.bootstrap import create_venv, ensure_native, in_project_venv, install_deps, venv_python

    print("正在准备运行环境并安装快捷方式…")
    create_venv()
    if not in_project_venv():
        py = venv_python()
        os.execv(str(py), [str(py), str(Path(__file__).resolve()), *sys.argv[1:]])
    try:
        install_deps()
        ensure_native(optional=True)
    except Exception as exc:
        print(f"环境准备出错（仍会安装快捷方式）：{exc}")
    raise SystemExit(install_shortcuts())
