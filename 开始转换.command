#!/bin/bash
cd "$(dirname "$0")"
export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"
if ! command -v python3 >/dev/null 2>&1; then
  osascript -e 'display dialog "还没有安装 Python 3。请打开 python.org 下载安装，安装时勾选 Add to PATH。" buttons {"好"} default button 1 with title "CAJ 转 PDF"'
  open "https://www.python.org/downloads/"
  exit 1
fi
python3 -m app "$@"
status=$?
if [[ $status -ne 0 ]]; then
  echo
  echo "出错了。可以把上面的文字截图发给帮你安装的人。"
  read -r -p "按回车键关闭…"
fi
exit $status
