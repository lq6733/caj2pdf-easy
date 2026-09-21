# CAJ 转 PDF / caj2pdf-easy

把中国知网的 **CAJ / KDH / HN / C8** 文件转成普通 PDF。给完全不熟悉电脑的人用：选文件、点一下，就能转。

This is a desktop wrapper around [caj2pdf](https://github.com/caj2pdf/caj2pdf) for **Windows, macOS, and Linux**.

## 功能

- 图形界面：选文件、选文件夹、批量转换
- Linux 还支持拖放，以及文件管理器右键「转成 PDF」
- 转换后的 PDF 保存在原文件旁边
- 不需要知网客户端，也不需要一直联网（第一次安装 Python 组件时需要）
- 支持 CAJ、KDH、HN、C8，以及「后缀是 .caj、内容其实已经是 PDF」的文件
- 自动识别扫描件（无法选中文字）。这类文件会生成图片版 PDF，并在结果里标明

## 你需要先有什么

三套系统都只需要 **Python 3.10 或更新**。第一次运行时，程序会自己创建本地环境并安装依赖。

| 系统 | 额外说明 |
| --- | --- |
| Windows | 从 [python.org](https://www.python.org/downloads/windows/) 安装，**务必勾选 Add python.exe to PATH** |
| macOS | 可用 python.org 安装包，或先运行 `xcode-select --install` |
| Linux | 再装 GTK 界面更美观；没有 GTK 时会尝试 tkinter |

含扫描页的 HN / C8 需要编译一个很小的解码库。程序会在第一次运行时自动编译：

- Windows：安装 [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)，勾选「使用 C++ 的桌面开发」；或安装 MinGW 的 `g++`
- macOS：运行 `xcode-select --install`
- Linux：Debian/Ubuntu 执行 `sudo apt install build-essential`

没有编译器时，普通 CAJ / KDH 通常仍能转换。也可以到 GitHub Actions 的 Artifacts 下载对应系统的 `libjbigdec` / `libjbig2codec`，放到 `vendor/caj2pdf/` 目录。

### Linux 可选软件包（更漂亮的界面）

Ubuntu / Debian：

```bash
sudo apt install python3 python3-venv python3-pip python3-gi python3-cairo \
  gir1.2-gtk-4.0 gir1.2-adw-1 build-essential
```

Fedora：

```bash
sudo dnf install python3 python3-pip python3-gobject gtk4 libadwaita gcc-c++
```

Arch：

```bash
sudo pacman -S python python-pip python-gobject gtk4 libadwaita gcc
```

## 安装

不会用 Git 的人：在 GitHub 页面点 **Code → Download ZIP**，解压后按下面做。

### Windows

1. 安装 Python，勾选 **Add python.exe to PATH**
2. 双击 `开始转换.bat`
3. 第一次会弹出黑窗口下载组件，等它结束
4. 也可以双击 `安装到桌面.bat`，之后从桌面启动

若 SmartScreen 提示「已保护你的电脑」，点「更多信息」→「仍要运行」。

### macOS

1. 双击 `开始转换.command`
2. 若提示无法打开，右键该文件 →「打开」
3. 也可以双击 `安装到桌面.command`，把图标放到桌面

### Linux

```bash
git clone https://github.com/lq6733/caj2pdf-easy.git
cd caj2pdf-easy
chmod +x caj-to-pdf install-desktop.sh
./install-desktop.sh
```

然后双击桌面上的 **CAJ转PDF**。如果系统提示图标未信任，右键选「允许启动」。

## 使用

1. 打开「CAJ 转 PDF」
2. 点「选择文件」或「选择文件夹」
3. 点「开始转换」
4. PDF 会出现在原文件旁边

命令行：

```bash
python3 -m app --headless 论文.caj
python3 -m app --headless 某个文件夹
python3 -m app --selftest 某个文件夹 --out /tmp/caj2pdf-selftest
```

`--selftest` 会把 PDF 写到临时目录，不覆盖原文件旁边的 PDF。它检查：PDF 能否打开、页数是否和 CAJ 一致、页面是否空白；如果文件其实已经是 PDF，还会对照原文文字。

Windows 可以用 `开始转换.bat --headless 论文.caj`。

更白话的说明见 [`使用说明.txt`](使用说明.txt)。

## 限制

- 这不是官方转换器，极少数文件会失败（尤其是几乎没有图片的纯文字 HN）
- HN / C8 以及本身就是扫描件的文件，会转成图片版 PDF，无法选中文字（界面会标明「扫描件」）
- 纯文字 HN 在抽得出足够正文时，会生成可阅读的文字版 PDF，版面和原文不同

## 致谢

转换引擎来自 [caj2pdf](https://github.com/caj2pdf/caj2pdf) 以及 Hin-Tak Leung 的 JBIG 解码工作。JBIG2 解码使用 [jbig2dec](https://github.com/ArtifexSoftware/jbig2dec) 0.20。本仓库加了傻瓜式界面、批量处理和跨平台启动方式。第三方许可证见 [`NOTICE.md`](NOTICE.md)。

## License

本仓库自己写的代码使用 [MIT](LICENSE)。vendored 的 `caj2pdf`、`jbig2dec` 及其组件保留原许可证。其中 `jbig2dec` 为 AGPL-3.0。
