# -*- coding: utf-8 -*-
"""パイプライン本体: YouTube URL → 6本のコンテンツ動画

入力 : YouTube動画URL
出力 : <出力先>/<YYYYMMDD_HHMMSS>_<タイトル>/EP0..EP5.mp4（毎回 新規フォルダ）
"""
import asyncio
import datetime as _dt
import json
import os
import re
import shutil
import subprocess
import sys

from . import slides as SL
from . import llm as LLM

DEF_TPL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "template", "series_template.json")


def log_default(msg):
    print(msg, flush=True)


def load_json(p, default=None):
    if p and os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def load_config(path=None, base=None):
    cfg = {}
    for p in [os.path.join(base or ".", ".env"), os.path.join(base or ".", "config.json"),
              path, os.path.expanduser("~/.yt6video.json")]:
        if not p or not os.path.exists(p):
            continue
        if p.endswith(".json"):
            cfg.update(load_json(p, {}) or {})
        else:
            for line in open(p, encoding="utf-8"):
                m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$", line)
                if m:
                    cfg[m.group(1).lower()] = m.group(2).strip().strip('"').strip("'")
    for k, v in {"llm_provider": "LLM_PROVIDER", "llm_api_key": "LLM_API_KEY",
                 "llm_base_url": "LLM_BASE_URL", "llm_model": "LLM_MODEL",
                 "voice": "TTS_VOICE", "fps": "FPS"}.items():
        if os.environ.get(v):
            cfg[k] = os.environ[v]
    cfg.setdefault("llm_provider", "stub")
    cfg.setdefault("voice", "ja-JP-NanamiNeural")
    cfg.setdefault("rate", "+8%")
    cfg.setdefault("fps", 30)
    cfg.setdefault("max_silence_db", -50.0)
    cfg.setdefault("out_root", os.path.join(os.path.expanduser("~"), "Downloads"))
    cfg.setdefault("template", DEF_TPL)
    return cfg


def slug(s, n=48):
    s = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", str(s or "")).strip(" ._")
    s = re.sub(r"\s+", "_", s)
    return (s[:n] or "youtube")


def vid_of(url):
    m = (re.search(r"[?&]v=([\w-]{6,})", url) or re.search(r"youtu\.be/([\w-]{6,})", url)
         or re.search(r"/shorts/([\w-]{6,})", url) or re.search(r"/live/([\w-]{6,})", url)
         or re.search(r"/embed/([\w-]{6,})", url))
    if not m:
        raise ValueError("YouTubeのURLから動画IDを取得できません: %s" % url)
    return m.group(1)


# ------------------------- 入力: タイトルと文字起こし -------------------------
def fetch_title(url, log=log_default):
    vid = vid_of(url)
    try:
        import urllib.request
        u = "https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=%s&format=json" % vid
        with urllib.request.urlopen(u, timeout=20) as r:
            return json.loads(r.read().decode("utf-8")).get("title") or vid
    except Exception as e:
        log("[input] タイトル取得をスキップ(%s)" % type(e).__name__)
    return vid


def fetch_transcript(url, log=log_default, fallback_file=None):
    vid = vid_of(url)
    # 1) youtube-transcript-api
    try:
        from youtube_transcript_api import YouTubeTranscriptApi as YTA
        try:
            fetched = YTA().fetch(vid, languages=["ja", "en"])
            raw = fetched.to_raw_data() if hasattr(fetched, "to_raw_data") else fetched
        except TypeError:
            raw = YTA.get_transcript(vid, languages=["ja", "en"])
        except AttributeError:
            raw = YTA().get_transcript(vid, languages=["ja", "en"])
        txt = " ".join(x.get("text", "") for x in raw).strip()
        if len(txt) > 60:
            log("[input] 文字起こし取得: youtube-transcript-api (%d文字)" % len(txt))
            return txt, "youtube-transcript-api"
    except Exception as e:
        log("[input] 字幕API失敗(%s)" % type(e).__name__)
    # 2) yt-dlp 字幕
    try:
        import yt_dlp
        tmp = os.path.join(os.path.expanduser("~"), ".yt6video_subs")
        shutil.rmtree(tmp, ignore_errors=True)
        os.makedirs(tmp, exist_ok=True)
        opts = {"skip_download": True, "writeautomaticsub": True, "writesubtitles": True,
                "subtitleslangs": ["ja", "ja-orig", "en"], "subtitlesformat": "vtt",
                "outtmpl": os.path.join(tmp, "%(id)s.%(ext)s"), "quiet": True, "no_warnings": True}
        with yt_dlp.YoutubeDL(opts) as y:
            y.download([url])
        for f in sorted(os.listdir(tmp)):
            if f.endswith(".vtt"):
                txt = parse_vtt(os.path.join(tmp, f))
                if len(txt) > 60:
                    log("[input] 文字起こし取得: yt-dlp字幕 (%d文字)" % len(txt))
                    return txt, "yt-dlp"
    except Exception as e:
        log("[input] yt-dlp字幕失敗(%s)" % type(e).__name__)
    # 3) 手元のテキスト
    if fallback_file and os.path.exists(fallback_file):
        txt = open(fallback_file, encoding="utf-8").read().strip()
        log("[input] 文字起こし取得: 手元のファイル %s (%d文字)" % (fallback_file, len(txt)))
        return txt, "file:%s" % os.path.basename(fallback_file)
    raise RuntimeError(
        "文字起こしを取得できませんでした。字幕が無効な動画か、ネットワーク制限の可能性があります。"
        "「文字起こしファイル」欄に対象動画のテキスト(.txt/.md/.vtt)を指定して再実行してください。")


def parse_vtt(path):
    out = []
    for line in open(path, encoding="utf-8", errors="ignore"):
        line = line.strip()
        if not line or "-->" in line or line.upper().startswith(("WEBVTT", "KIND:", "LANGUAGE:", "NOTE")):
            continue
        line = re.sub(r"<[^>]+>", "", line)
        if line and (not out or out[-1] != line):
            out.append(line)
    return re.sub(r"\s+", " ", " ".join(out)).strip()


# ------------------------- 台本の正規化とナレーション -------------------------
VALID_TYPES = set(SL.RENDERERS.keys())


def normalize(data, template):
    eps = {e["no"]: e for e in template["episodes"]}
    out = []
    for i, e in enumerate(data.get("episodes", [])):
        tgt = eps.get(e.get("no", i))
        if tgt is None:
            continue
        sl = list(e.get("slides") or [])
        fixed = []
        for k, tpl in enumerate(tgt["slides"]):
            s = dict(sl[k]) if k < len(sl) and isinstance(sl[k], dict) else {}
            if s.get("type") not in VALID_TYPES:
                s["type"] = tpl["type"]
            if not s.get("header"):
                s["header"] = tpl["header"]
            for f in ("items", "cols", "rows", "steps", "lines", "left", "right"):
                if tpl.get(f) and not s.get(f):
                    s[f] = tpl[f]
            for f in ("sub", "left_title", "right_title"):
                if tpl.get(f) and not s.get(f):
                    s[f] = tpl[f]
            fixed.append(s)
        out.append({"no": tgt["no"], "badge": tgt["badge"],
                    "accent": e.get("accent") or tgt["accent"], "slides": fixed})
    if not out:
        raise RuntimeError("台本の生成に失敗しました（episodes が空）")
    return {"folder_title": data.get("folder_title") or "youtube", "episodes": out}


def _join(items):
    parts = []
    for x in items:
        x = str(x).strip().strip("。")
        if x:
            parts.append(x)
    return "。".join(parts) + "。"


def narration_for(sp):
    """スライド内の全項目を必ず読み上げる（前回発生した『項目の読み上げ漏れ』を構造的に防ぐ）"""
    t = sp.get("type", "title")
    h = str(sp.get("header", "")).strip()
    if t == "title":
        return _join([h, sp.get("sub", "")])
    if t == "list":
        return _join([h] + ["%dつめ、%s" % (i + 1, x) for i, x in enumerate(sp.get("items", []))])
    if t == "boxes":
        return _join([h] + ["%s。%s" % (c.get("t", ""), c.get("d", "")) for c in sp.get("cols", [])])
    if t == "compare":
        return _join([h, sp.get("left_title", ""), "、".join(str(x) for x in sp.get("left", [])),
                      sp.get("right_title", ""), "、".join(str(x) for x in sp.get("right", []))])
    if t == "table3":
        return _join([h] + ["%sなら、%s" % (r.get("q", ""), r.get("a", "")) for r in sp.get("rows", [])])
    if t == "flow":
        return _join([h, "、".join(str(x) for x in sp.get("steps", [])) + "。この順番で回します"])
    if t in ("note", "summary", "closing"):
        return _join([h] + list(sp.get("lines", [])))
    return _join([h])


def lint_coverage(spec):
    """ナレーションが全項目を網羅しているかを機械検証する"""
    problems = []
    for ep in spec["episodes"]:
        for i, sp in enumerate(ep["slides"], 1):
            nar = re.sub(r"\s+", "", narration_for(sp))
            items = []
            t = sp.get("type")
            if t == "list":
                items = sp.get("items", [])
            elif t == "boxes":
                items = [c.get("t", "") for c in sp.get("cols", [])] + [c.get("d", "") for c in sp.get("cols", [])]
            elif t == "compare":
                items = list(sp.get("left", [])) + list(sp.get("right", []))
            elif t == "table3":
                items = [r.get("q", "") for r in sp.get("rows", [])] + [r.get("a", "") for r in sp.get("rows", [])]
            elif t == "flow":
                items = sp.get("steps", [])
            elif t in ("note", "summary", "closing"):
                items = sp.get("lines", [])
            for it in items:
                key = re.sub(r"\s+", "", str(it))[:8]
                if key and key not in nar:
                    problems.append("第%s話 スライド%d: 「%s」の読み上げが無い" % (ep["badge"], i, it))
    return problems


# ------------------------- 音声合成と検証 -------------------------
def dur(path):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "json", path], capture_output=True, text=True)
        return float(json.loads(r.stdout)["format"]["duration"])
    except Exception:
        return 0.0


def mean_volume(path, ss=None, t=None):
    cmd = ["ffmpeg", "-hide_banner"]
    if ss is not None:
        cmd += ["-ss", "%.3f" % ss]
    if t is not None:
        cmd += ["-t", "%.3f" % t]
    cmd += ["-i", path, "-vn", "-af", "volumedetect", "-f", "null", "-"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    for l in r.stderr.splitlines():
        if "mean_volume" in l:
            try:
                return float(l.split("mean_volume:")[1].replace("dB", "").strip())
            except Exception:
                return None
    return None


async def _tts_save(text, out, voice, rate):
    import edge_tts
    await edge_tts.Communicate(text, voice, rate=rate).save(out)


def tts(text, out, voice, rate, log=log_default, retries=3):
    last = None
    for k in range(retries):
        try:
            asyncio.run(_tts_save(text, out, voice, rate))
            if os.path.exists(out) and os.path.getsize(out) > 1200 and dur(out) > 0.4:
                return out
            last = "生成結果が空"
        except Exception as e:
            last = "%s: %s" % (type(e).__name__, e)
        log("[tts] 再試行 %d/%d (%s)" % (k + 1, retries, last))
    raise RuntimeError("音声合成に失敗: %s" % last)


def run_ff(args):
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg失敗: %s" % " ".join(args[-4:]) + "\n" + r.stderr.strip()[-500:])
    return True


# ------------------------- 6本のビルド -------------------------
def build_episode(ep, workdir, cfg, log=log_default):
    no = ep["no"]
    epdir = os.path.join(workdir, "EP%d" % no)
    os.makedirs(epdir, exist_ok=True)
    W, H, fps = cfg["width"], cfg["height"], int(cfg["fps"])
    segs, notes = [], []
    for i, sp in enumerate(ep["slides"]):
        slot = i + 1
        png = os.path.join(epdir, "slide%02d.png" % slot)
        SL.render(sp, png, ep["badge"], ep["accent"], cfg.get("images_dir"), no, slot)
        nar = narration_for(sp)
        mp3 = os.path.join(epdir, "nar%02d.mp3" % slot)
        tts(nar, mp3, cfg["voice"], cfg.get("rate", "+8%"), log)
        nd = dur(mp3)
        D = max(nd + 0.8, 3.2)
        pre = os.path.join(epdir, "pre%02d.mp4" % slot)
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-t", "%.2f" % D,
                            "-i", png, "-vf",
                            "scale=%d:%d,zoompan=z='min(zoom+0.0005,1.08)':x='iw/2-(iw/zoom/2)':"
                            "y='ih/2-(ih/zoom/2)':d=1:s=%dx%d:fps=%d,setsar=1"
                            % (W + 120, H + 68, W, H, fps),
                            "-c:v", "libx264", "-crf", "18", "-preset", "veryfast", pre],
                           capture_output=True, text=True)
        if r.returncode != 0 or dur(pre) < 1:
            run_ff(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-t", "%.2f" % D, "-i", png,
                    "-vf", "scale=%d:%d,setsar=1,fps=%d" % (W, H, fps),
                    "-c:v", "libx264", "-crf", "18", "-preset", "veryfast", pre])
        seg = os.path.join(epdir, "seg%02d.mp4" % slot)
        run_ff(["ffmpeg", "-y", "-loglevel", "error", "-i", pre, "-i", mp3,
                "-filter_complex", "[1:a]apad[a]", "-map", "0:v", "-map", "[a]",
                "-c:v", "libx264", "-crf", "20", "-preset", "veryfast", "-c:a", "aac",
                "-b:a", "192k", "-ar", "44100", "-ac", "2", "-t", "%.3f" % D, seg])
        mv = mean_volume(seg)
        if mv is None or mv <= cfg["max_silence_db"]:
            log("[check] 無音を検知 EP%d スライド%d → 音声を作り直します" % (no, slot))
            tts(nar, mp3, cfg["voice"], cfg.get("rate", "+8%"), log)
            run_ff(["ffmpeg", "-y", "-loglevel", "error", "-i", pre, "-i", mp3,
                    "-filter_complex", "[1:a]apad[a]", "-map", "0:v", "-map", "[a]",
                    "-c:v", "libx264", "-crf", "20", "-preset", "veryfast", "-c:a", "aac",
                    "-b:a", "192k", "-ar", "44100", "-ac", "2", "-t", "%.3f" % D, seg])
            mv = mean_volume(seg)
        notes.append({"episode": no, "slot": slot, "type": sp.get("type"), "header": sp.get("header"),
                      "sec": round(dur(seg), 2), "vol_db": mv, "chars": len(nar)})
        segs.append(seg)
        log("  EP%d スライド%d/%d %s (%.1fs, %.1fdB)"
            % (no, slot, len(ep["slides"]), sp.get("header", "")[:24], dur(seg), mv or 0))
    lst = os.path.join(epdir, "list.txt")
    with open(lst, "w", encoding="utf-8") as f:
        f.write("".join("file '%s'\n" % s.replace("'", "'\\''") for s in segs))
    final = os.path.join(workdir, "EP%d_%s.mp4" % (no, slug(ep["badge"], 16)))
    run_ff(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst,
            "-c:v", "libx264", "-crf", "20", "-preset", "medium", "-c:a", "aac", "-b:a", "192k",
            "-ar", "44100", "-ac", "2", "-movflags", "+faststart", final])
    # 最終検証: 連結後のMP4を スライド位置ごとに実測
    cur, silent = 0.0, []
    for i, s in enumerate(segs, 1):
        d = dur(s)
        v = mean_volume(final, cur + 0.15, max(d - 0.3, 0.5))
        if v is None or v <= cfg["max_silence_db"]:
            silent.append(i)
        cur += d
    sheet = sheet_of(final, epdir, len(segs))
    log("[check] EP%d 完成 %s (%.1fs) 無音スライド=%s"
        % (no, os.path.basename(final), dur(final), silent or "なし"))
    return {"episode": no, "file": final, "duration": round(dur(final), 2),
            "size": os.path.getsize(final), "silent_slides": silent,
            "sheet": sheet, "slides": notes}


def sheet_of(video, epdir, n, W=1280, H=720):
    """各スライドから代表フレームを抜いて 2xN のコンタクトシートを作る"""
    from PIL import Image
    fr = []
    for i in range(1, n + 1):
        p = os.path.join(epdir, "fr%02d.png" % i)
        seg = os.path.join(epdir, "seg%02d.mp4" % i)
        if not os.path.exists(seg):
            continue
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "1.5", "-i", seg,
                        "-frames:v", "1", p], capture_output=True)
        if os.path.exists(p):
            fr.append(p)
    if not fr:
        return None
    tw, th = 640, 360
    rows = (len(fr) + 1) // 2
    img = Image.new("RGB", (tw * 2, th * rows), (255, 255, 255))
    for i, p in enumerate(fr):
        img.paste(Image.open(p).convert("RGB").resize((tw, th), Image.LANCZOS),
                  ((i % 2) * tw, (i // 2) * th))
    out = os.path.join(epdir, "contact_sheet.png")
    img.save(out)
    return out


def run(url, out_root=None, cfg=None, log=log_default, episodes=None, fallback_transcript=None):
    cfg = dict(cfg or load_config())
    cfg.setdefault("width", 1280)
    cfg.setdefault("height", 720)
    out_root = os.path.abspath(os.path.expanduser(out_root or cfg["out_root"]))
    tpl = load_json(cfg["template"]) or load_json(DEF_TPL)
    if not tpl:
        raise RuntimeError("テンプレートが見つかりません: %s" % cfg["template"])

    title = fetch_title(url, log)
    transcript, src = fetch_transcript(url, log, fallback_file=fallback_transcript or cfg.get("transcript_file"))
    data = LLM.call_llm(cfg, transcript, title, tpl, log)
    spec = normalize(data, tpl)
    problems = lint_coverage(spec)

    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = os.path.join(out_root, "%s_%s" % (stamp, slug(data.get("folder_title") or title)))
    os.makedirs(folder, exist_ok=True)
    log("[out] 出力フォルダ: %s" % folder)

    # 台本と検証前レポートを保存
    with open(os.path.join(folder, "script.json"), "w", encoding="utf-8") as f:
        json.dump({"url": url, "title": title, "transcript_source": src, "spec": spec,
                   "coverage_problems": problems}, f, ensure_ascii=False, indent=2)
    with open(os.path.join(folder, "transcript.txt"), "w", encoding="utf-8") as f:
        f.write(transcript)
    with open(os.path.join(folder, "slideshow.md"), "w", encoding="utf-8") as f:
        for ep in spec["episodes"]:
            f.write("## %s\n\n" % ep["badge"])
            for i, sp in enumerate(ep["slides"], 1):
                f.write("%d. [%s] %s\n   - ナレ: %s\n" % (i, sp.get("type"), sp.get("header"), narration_for(sp)))
            f.write("\n")

    results, only = [], None
    if episodes:
        only = set(int(x) for x in str(episodes).replace(",", " ").split())
    for ep in spec["episodes"]:
        if only and ep["no"] not in only:
            continue
        results.append(build_episode(ep, folder, cfg, log))

    rep = {"url": url, "title": title, "folder": folder, "transcript_source": src,
           "font": SL.font_report(), "voice": cfg["voice"], "resolution": "%dx%d" % (cfg["width"], cfg["height"]),
           "caption_bar": False, "badge": True,
           "coverage_problems": problems, "episodes": results,
           "silent_total": sum(len(r["silent_slides"]) for r in results)}
    with open(os.path.join(folder, "report.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    with open(os.path.join(folder, "report.txt"), "w", encoding="utf-8") as f:
        f.write("YouTube → 6本のコンテンツ動画  実行レポート\n")
        f.write("元動画 : %s\nタイトル: %s\n文字起こし: %s\n音声: %s\n" % (url, title, src, cfg["voice"]))
        f.write("出力: %s\n\n" % folder)
        f.write("[ナレーション網羅チェック] %s\n" % ("問題なし（全項目を読み上げ）" if not problems else "\n".join(problems)))
        for r in results:
            f.write("\nEP%d  %s  尺=%.1f秒  無音スライド=%s\n" % (r["episode"], os.path.basename(r["file"]),
                                                              r["duration"], r["silent_slides"] or "なし"))
            for s in r["slides"]:
                f.write("   スライド%2d %-9s %-28s %5.1fs %6.1fdB %3d文字\n"
                        % (s["slot"], s["type"], (s["header"] or "")[:28], s["sec"], s["vol_db"] or 0, s["chars"]))
        f.write("\n合計 無音スライド数: %d\n" % rep["silent_total"])
    log("[done] %d本を出力しました → %s" % (len(results), folder))
    if rep["silent_total"]:
        log("[warn] 無音スライドが残っています。report.txt を確認してください。")
    return rep
