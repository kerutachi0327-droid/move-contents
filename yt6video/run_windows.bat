@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo ============================================
echo  YouTube -^> 6本のコンテンツ動画 を起動します
echo ============================================
where python >nul 2>nul
if errorlevel 1 (
  echo [エラー] Pythonが見つかりません。python.org からインストールしてください。
  pause
  exit /b 1
)
python -c "import edge_tts, PIL" 2>nul
if errorlevel 1 (
  echo 初回セットアップ: 必要ライブラリをインストールします...
  python -m pip install -r requirements.txt
)
where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo [警告] ffmpeg が見つかりません。動画の書き出しに必須です。
  echo        例:  winget install Gyan.FFmpeg   を実行後、このウィンドウを開き直してください。
  pause
)
python app.py --gui
pause
