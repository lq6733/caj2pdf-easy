# CAJ 转 PDF / caj2pdf-easy

把中国知网的 **CAJ / KDH / HN** 文件转成普通 PDF。提供中文图形界面：拖进去、点一下，就能转。

This is a Linux desktop wrapper around [caj2pdf](https://github.com/caj2pdf/caj2pdf). Drop CAJ files onto a window, or convert them from the terminal.

## 功能

- 图形界面，支持拖放、选文件、选文件夹、批量转换
- 转换后的 PDF 保存在原文件旁边
- 也可在文件管理器里右键「转成 PDF」
- 不需要联网（第一次安装 Python 依赖除外）
- 支持 CAJ、KDH、HN、C8，以及「后缀是 .caj、内容其实已经是 PDF」的文件

## 环境要求

目前只支持 **Linux 桌面**（Ubuntu / Debian / Fedora / Arch 等）。需要：

- Python 3.10+
- GTK 4 和 libadwaita（图形界面）
- `g++`、`mutool`、`libjbig2dec`
- 中文字体（如 Noto CJK）

### Ubuntu / Debian

```bash
sudo apt install python3 python3-venv python3-gi python3-cairo \
  gir1.2-gtk-4.0 gir1.2-adw-1 build-essential mupdf-tools \
  libjbig2dec0 fonts-noto-cjk
```

### Fedora

```bash
sudo dnf install python3 python3-pip python3-gobject gtk4 libadwaita \
  gcc-c++ mupdf jbig2dec google-noto-sans-cjk-fonts
```

### Arch

```bash
sudo pacman -S python python-gobject gtk4 libadwaita gcc \
  mupdf-tools jbig2dec noto-fonts-cjk
```

## 安装

```bash
git clone https://github.com/lq6733/caj2pdf-easy.git
cd caj2pdf-easy
chmod +x caj-to-pdf install-desktop.sh
./install-desktop.sh
```

然后双击桌面上的 **CAJ转PDF**。如果系统提示图标未信任，右键选「允许启动」。

不会用 Git 的人也可以：在 GitHub 页面点 **Code → Download ZIP**，解压后再运行 `./install-desktop.sh`。

## 使用

图形界面：

1. 打开「CAJ 转 PDF」
2. 把 CAJ 拖进去，或点「选择文件」
3. 点「开始转换」
4. PDF 会出现在原文件旁边

命令行：

```bash
./caj-to-pdf --headless 论文.caj
./caj-to-pdf --headless 某个文件夹
```

更白话的说明见 [`使用说明.txt`](使用说明.txt)。

## 限制

- 这不是官方转换器，极少数文件会失败（尤其是几乎没有图片的纯文字 HN）
- HN / C8 经常会转成「图片型 PDF」，不一定能复制文字
- 暂不支持 Windows / macOS

## 致谢

转换引擎来自 [caj2pdf](https://github.com/caj2pdf/caj2pdf) 以及 Hin-Tak Leung 的 JBIG 解码工作。本仓库在此基础上加了傻瓜式界面、批量处理和更稳妥的失败提示。第三方许可证见 [`NOTICE.md`](NOTICE.md)。

## License

本仓库自己写的代码使用 [MIT](LICENSE)。vendored 的 `caj2pdf` 及其组件保留原许可证。
