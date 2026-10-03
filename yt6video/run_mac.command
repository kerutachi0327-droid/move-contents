#!/bin/bash
cd "$(dirname "$0")" || exit 1
echo "============================================"
echo " YouTube → 6本のコンテンツ動画 を起動します"
echo "============================================"
if ! command -v python3 >/dev/null 2>&1; then
  echo "[エラー] python3 が見つかりません。python.org からインストールしてください。"; read -r; exit 1
fi
if ! python3 -c "import edge_tts, PIL" >/dev/null 2>&1; then
  echo "初回セットアップ: 必要ライブラリをインストールします..."
  python3 -m pip install --user -r requirements.txt || { echo "インストールに失敗しました"; read -r; exit 1; }
fi
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "[警告] ffmpeg が見つかりません。動画の書き出しに必須です。"
  echo "        例:  brew install ffmpeg   を実行後にこのファイルをダブルクリックし直してください。"
  read -r
fi
python3 app.py --gui
