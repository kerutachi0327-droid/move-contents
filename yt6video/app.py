#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""yt6video — YouTube動画URLから 6本のコンテンツ動画を作るアプリ

使い方:
  GUI  : python app.py            （または app.py --gui）
  CLI  : python app.py --url "https://www.youtube.com/watch?v=XXXX" [--out ~/Downloads]
出力先の直下に「YYYYMMDD_HHMMSS_タイトル」フォルダを毎回新規作成し、そこへ出力します。
"""
import argparse
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from yt6video import core  # noqa: E402


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="YouTube動画URL → 6本のコンテンツ動画")
    ap.add_argument("--url", help="YouTube動画のURL")
    ap.add_argument("--out", help="出力先の親フォルダ（既定: ~/Downloads）")
    ap.add_argument("--config", help="config.json / .env のパス")
    ap.add_argument("--template", help="テンプレートJSONのパス（既定: template/series_template.json）")
    ap.add_argument("--voice", help="音声（例 ja-JP-NanamiNeural / ja-JP-KeitaNeural / ja-JP-NanamiNeural-Female）")
    ap.add_argument("--tts", choices=["auto", "edge", "openjtalk"],
                    help="音声エンジン（既定 auto: edge-tts、使えなければオフラインの pyopenjtalk）")
    ap.add_argument("--rate", help="話速（例 +8%%）")
    ap.add_argument("--fps", type=int, help="フレームレート（既定 30）")
    ap.add_argument("--episodes", help="一部だけ作る（例 0 1 5 / 既定は全6本）")
    ap.add_argument("--transcript-file", help="字幕が取れない場合に使う文字起こしテキスト(.txt/.md/.vtt)")
    ap.add_argument("--images-dir", help="差し替え用の絵素材フォルダ（<話番号>_<スライド番号>.png）")
    ap.add_argument("--provider", help="stub / openai / gemini")
    ap.add_argument("--gui", action="store_true", help="GUIを起動")
    return ap.parse_args(argv)


def build_cfg(a):
    cfg = core.load_config(a.config, base=os.path.dirname(os.path.abspath(__file__)))
    if a.template:
        cfg["template"] = a.template
    if a.voice:
        cfg["voice"] = a.voice
    if a.tts:
        cfg["tts_engine"] = a.tts
    if a.rate:
        cfg["rate"] = a.rate
    if a.fps:
        cfg["fps"] = a.fps
    if a.provider:
        cfg["llm_provider"] = a.provider
    if a.transcript_file:
        cfg["transcript_file"] = a.transcript_file
    if a.images_dir:
        cfg["images_dir"] = a.images_dir
    if a.out:
        cfg["out_root"] = a.out
    return cfg


def cli(a):
    cfg = build_cfg(a)
    rep = core.run(a.url, out_root=cfg["out_root"], cfg=cfg, episodes=a.episodes)
    print("\n===== 完了 =====")
    for r in rep["episodes"]:
        print("  EP%d  %s  %.1f秒  無音スライド=%s" % (r["episode"], os.path.basename(r["file"]),
                                                  r["duration"], r["silent_slides"] or "なし"))
    print("  出力フォルダ: %s" % rep["folder"])
    print("  ナレーション網羅: %s" % ("問題なし" if not rep["coverage_problems"] else rep["coverage_problems"]))
    return 0


def gui(a):
    import threading
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    cfg = build_cfg(a)
    root = tk.Tk()
    root.title("YouTube → 6本のコンテンツ動画（テンプレート）")
    root.geometry("860x620")

    tk.Label(root, text="YouTube動画のURL", font=("", 12, "bold")).pack(anchor="w", padx=14, pady=(12, 2))
    url_v = tk.StringVar(value=a.url or "")
    tk.Entry(root, textvariable=url_v, font=("", 11)).pack(fill="x", padx=14)

    row = tk.Frame(root); row.pack(fill="x", padx=14, pady=8)
    tk.Label(row, text="出力先:").pack(side="left")
    out_v = tk.StringVar(value=cfg["out_root"])
    tk.Entry(row, textvariable=out_v).pack(side="left", fill="x", expand=True, padx=6)
    tk.Button(row, text="参照", command=lambda: out_v.set(filedialog.askdirectory() or out_v.get())).pack(side="left")

    row2 = tk.Frame(root); row2.pack(fill="x", padx=14)
    tk.Label(row2, text="音声:").pack(side="left")
    voice_v = tk.StringVar(value=cfg["voice"])
    ttk.Combobox(row2, textvariable=voice_v, width=26, values=[
        "ja-JP-NanamiNeural", "ja-JP-KeitaNeural", "ja-JP-AoiNeural", "ja-JP-DaichiNeural",
        "ja-JP-MayuNeural", "ja-JP-NaokiNeural", "ja-JP-ShioriNeural"]).pack(side="left", padx=6)
    tk.Label(row2, text="台本AI:").pack(side="left", padx=(16, 0))
    prov_v = tk.StringVar(value=cfg["llm_provider"])
    ttk.Combobox(row2, textvariable=prov_v, width=12, values=["stub", "openai", "gemini"]).pack(side="left", padx=6)
    tk.Label(row2, text="APIキー:").pack(side="left", padx=(10, 0))
    key_v = tk.StringVar(value=cfg.get("llm_api_key", ""))
    tk.Entry(row2, textvariable=key_v, width=28, show="*").pack(side="left", padx=6)

    log = tk.Text(root, height=20, font=("Consolas", 9))
    log.pack(fill="both", expand=True, padx=14, pady=10)

    def emit(m):
        log.insert("end", str(m) + "\n"); log.see("end"); root.update_idletasks()

    def start():
        if not url_v.get().strip():
            messagebox.showwarning("確認", "YouTubeのURLを入力してください。"); return
        btn.config(state="disabled"); log.delete("1.0", "end")
        c = dict(cfg); c["llm_api_key"] = key_v.get().strip(); c["llm_provider"] = prov_v.get()
        c["voice"] = voice_v.get()

        def work():
            try:
                rep = core.run(url_v.get().strip(), out_root=out_v.get().strip() or cfg["out_root"],
                               cfg=c, log=emit)
                emit("\n完了: %s" % rep["folder"])
                emit("無音スライド合計: %d" % rep["silent_total"])
                messagebox.showinfo("完了", "6本の動画を出力しました。\n%s" % rep["folder"])
            except Exception as e:
                emit("\n[エラー] %s" % e)
                emit(traceback.format_exc()[-1500:])
                messagebox.showerror("エラー", str(e))
            finally:
                btn.config(state="normal")
        threading.Thread(target=work, daemon=True).start()

    btn = tk.Button(root, text="動画を作成する（6本）", height=2, bg="#1C5AC8", fg="white",
                    font=("", 12, "bold"), command=start)
    btn.pack(fill="x", padx=14, pady=(0, 6))
    tk.Label(root, text="出力先に「日時_タイトル」フォルダを毎回新規作成して EP0〜EP5 を書き出します。").pack(pady=(0, 10))
    root.mainloop()
    return 0


def main(argv=None):
    a = parse_args(argv)
    if a.gui or not a.url:
        try:
            return gui(a)
        except Exception as e:                       # tkinter が無い環境
            if a.url:
                print("[warn] GUIを起動できません(%s)。CLIで実行します。" % type(e).__name__)
                return cli(a)
            print("GUIを利用できません(%s)。次のようにURLを指定して実行してください：" % type(e).__name__)
            print('  python app.py --url "https://www.youtube.com/watch?v=XXXX"')
            try:
                u = input("YouTubeのURLを入力（Enterで終了）: ").strip()
            except EOFError:
                return 1
            if not u:
                return 1
            a.url = u
    return cli(a)


if __name__ == "__main__":
    sys.exit(main())
