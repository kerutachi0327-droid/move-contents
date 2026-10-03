# yt6video — YouTube動画URL → 6本のコンテンツ動画

これまでの制作（序章＋第1〜4話＋総括の6本 / 各8スライド・1280×720・右上にエピソードバッジ・**スライド下の説明バーなし**・
日本語ナレーション付き）を**テンプレート化**して、誰でも再現できるアプリにしました。

```
入力 : YouTube動画のURL（1本）
出力 : 出力先/<YYYYMMDD_HHMMSS>_<動画タイトル>/EP0_序章.mp4 〜 EP5_第5話.mp4（毎回 新規フォルダ）
```

---

## 1. できること

| 工程 | 内容 |
|---|---|
| ① 取得 | YouTubeのタイトル・文字起こし（字幕）を自動取得（字幕API → yt-dlp → 手元ファイル の順にフォールバック） |
| ② 設計 | 文字起こしを台本AI（またはAPIキー不要の `stub`）が **6本×8スライド** の構造に変換 |
| ③ スライド | Pillowで図解スライドを描画（型：title / list / boxes / compare / table3 / flow / note / summary / closing） |
| ④ 音声 | edge-tts（**無料・日本語**）でナレーション生成。スライド内の全項目を必ず読み上げる方式 |
| ⑤ 動画 | ffmpegで1スライド=1セグメント（ゆっくりズーム）→ 連結して1本のMP4に |
| ⑥ 検証 | 無音スライドの自動検出＋**ナレーション網羅チェック**を実行し、`report.txt` に記録 |

---

## 2. セットアップ

### 2-1. Python
Python 3.9 以上（tkinter 同梱の公式インストーラ推奨）
- Windows: https://www.python.org/downloads/windows/ （インストール時に **Add python.exe to PATH** にチェック）
- macOS: https://www.python.org/downloads/macos/

### 2-2. ffmpeg（必須）
- Windows: `winget install Gyan.FFmpeg` を実行 → 新しいコマンドプロンプトで `ffmpeg -version`
- macOS: `brew install ffmpeg`
- Linux: `sudo apt-get install -y ffmpeg python3-tk`

### 2-3. ライブラリ
```bash
python -m pip install -r requirements.txt
```
Windows は `run_windows.bat`、macOS は `run_mac.command` をダブルクリックすれば、初回に自動で入ります。

### 2-4. APIキー（任意）
APIキーが **無くても動きます**（`stub` がテンプレート骨格＋文字起こしから台本を組み立てます）。
品質を上げたい場合は `config.example.json` を `config.json` にコピーして設定します。

```json
{
  "llm_provider": "gemini",
  "llm_api_key": "ここにAPIキー",
  "llm_model": "gemini-2.0-flash"
}
```
OpenAI互換なら `llm_provider: "openai"` と `llm_base_url` を指定（OpenAI / OpenRouter / Ollama など）。
キーは `config.json`・`.env`・環境変数のどこかに置けます。**コードには絶対に書きません。**

---

## 3. 使い方

### GUI（かんたん）
`run_windows.bat` / `run_mac.command` をダブルクリック、または
```bash
python app.py --gui
```
URLを貼り、必要なら音声・APIキーを入れて「動画を作成する（6本）」を押すだけです。

### CLI
```bash
python app.py --url "https://www.youtube.com/watch?v=XXXXXXXXXXX"
python app.py --url "https://youtu.be/XXXXXXXXXXX" --out "/Users/kenji/Downloads" --voice ja-JP-KeitaNeural
python app.py --url "https://www.youtube.com/watch?v=XXXXXXXXXXX" --episodes 0      # 序章だけ試作
python app.py --url "https://www.youtube.com/watch?v=XXXXXXXXXXX" --transcript-file my_notes.txt
```

主なオプション

| オプション | 説明 |
|---|---|
| `--out` | 出力先の親フォルダ（既定 `~/Downloads`）。ここに日時_タイトルのフォルダを**毎回新規作成** |
| `--voice` | 日本語音声（既定 `ja-JP-NanamiNeural`） |
| `--rate` | 話速（既定 `+8%`） |
| `--episodes` | 一部の話だけ作る（例 `0 1`）。既定は全6本 |
| `--transcript-file` | 字幕が取得できない動画のときの文字起こしテキスト |
| `--images-dir` | 手元の絵素材を使うフォルダ（`1_1.png`＝第1話スライド1、`0_2.png`＝序章スライド2 …） |
| `--provider` | `stub` / `openai` / `gemini` |

---

## 4. 出力フォルダの中身

```
~/Downloads/20261003_143012_元動画のタイトル/
├─ EP0_序章.mp4            ← 納品物（6本）
├─ EP1_第1話.mp4
├─ EP2_第2話.mp4
├─ EP3_第3話.mp4
├─ EP4_第4話.mp4
├─ EP5_第5話.mp4
├─ report.txt              ← 実行レポート（尺・音量・文字数・無音チェック結果）
├─ report.json             ← 同内容のJSON（自動処理向け）
├─ script.json             ← 台本（6本×8スライドの構造データ）
├─ slideshow.md            ← 一覧（見出し＋読み上げ原稿）
├─ transcript.txt          ← 元動画の文字起こし
└─ EP1/ … EP5/             ← 各話の中間素材（slide01.png / nar01.mp3 / seg01.mp4 / contact_sheet.png）
```

`contact_sheet.png` は各話8スライドを一覧にした画像です。サムネイル選定やチェックに使えます。

---

## 5. テンプレート（型の決まりごと）

`template/series_template.json` が唯一の正です。編集すれば全話の構成を差し替えられます。

- **6本構成**：no=0 序章（見たくなる導入）／no=1〜4 理論／no=5 総括
- **各8スライド**の型の順番：`title → list → boxes or flow → compare → table3 → note → summary → closing`
- **映像仕様**：1280×720 / 30fps / h264 + aac、右上にバッジ、**下部の説明バーは描かない**、スライドはゆっくりズーム
- **ナレーション**：スライド内の全項目を読み上げる（`narration_for()` が構造から機械生成するため漏れません）
- **検証**：`lint_coverage()`（網羅チェック）＋ 無音検出（既定 -50dB 以下を無音と判定し、自動で音声を作り直す）

スライドの型を増やしたい場合は `yt6video/slides.py` に描画関数を追加し、`RENDERERS` に登録します。

---

## 6. トラブルシューティング

| 症状 | 対処 |
|---|---|
| `ffmpeg not found` | ffmpegを入れてPATHを通す（上記2-2）。入れた後はウィンドウを開き直す |
| 文字起こしが取れない | 字幕なし動画です。元動画の内容をテキストにして `--transcript-file` に指定 |
| 音声が無い／変 | ネットワーク制限で edge-tts が失敗した可能性。`report.txt` の音量欄（-50dB以下は無音）を確認 |
| 日本語が豆腐（□）になる | 日本語フォントが見つかっていません。`report.json` の `font` を確認し、Noto Sans CJK / メイリオ / ヒラギノを入れる |
| 文字起こしの内容が薄い | `--provider` にAPIキーを設定すると構成が大幅に良くなります |
| 画風を自分のイラストにしたい | `--images-dir` に `<話番号>_<スライド番号>.png` を置く |

---

## 7. クレジットの考え方

- スライド描画・ffmpeg合成・テンプレート処理＝**0クレジット**（すべてPC内で完結）
- 音声＝edge-tts（Microsoftの無料音声。APIキー不要）
- 台本AIのみ、使う場合はご自身のAPIキー分の従量課金

つまり **APIキーを使わない `stub` 運用なら完全無料**で6本を書き出せます。

---

## 8. クラウド環境（Claude Code on the web など）で動かす

GUIは使えないので CLI で実行します。セットアップはスクリプト1本です。

```bash
cd yt6video
./setup_cloud.sh          # 日本語フォント・ffmpeg・ライブラリ（オフライン音声込み）を導入
.venv/bin/python app.py --url "https://www.youtube.com/watch?v=XXXX" --out ./output
```

- **音声**：既定の `--tts auto` は edge-tts を試し、接続できなければ自動で **オフライン音声（pyopenjtalk）** に切り替えます。
  `--tts openjtalk` で最初からオフライン、`--tts edge` で edge-tts 固定（失敗時はエラー）。どちらを使ったかは `report.txt` の「音声」欄に出ます。
- **YouTube**：`www.youtube.com` をネットワーク設定で許可すると**タイトルは取得できます**が、
  **字幕は YouTube 側がクラウドのサーバーをロボット扱いして拒否**します（確認画面へ転送）。
  クラウドでは `--transcript-file 文字起こし.txt` を付けて実行してください。
- **edge-tts**：`speech.platform.bing.com` を許可しても、Microsoft 側がクラウドからの接続を 403 で拒否します。
  `--tts auto`（既定）なら自動でオフライン音声になります。
