#!/bin/bash
# クラウド環境（Linux）用セットアップ：日本語フォント・ffmpeg・Pythonライブラリ（オフライン音声込み）
set -e
cd "$(dirname "$0")"
if ! fc-list 2>/dev/null | grep -q "Noto Sans CJK" || ! command -v ffmpeg >/dev/null 2>&1; then
  SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"
  $SUDO apt-get update -q >/dev/null 2>&1 || true
  $SUDO apt-get install -y -q fonts-noto-cjk ffmpeg >/dev/null
fi
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements-cloud.txt
echo "セットアップ完了。実行例:"
echo '  .venv/bin/python app.py --url "https://www.youtube.com/watch?v=XXXX" --out ./output'
echo '  （YouTubeに接続できない場合は --transcript-file 文字起こし.txt を追加）'
