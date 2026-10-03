# -*- coding: utf-8 -*-
"""スライド描画エンジン（テンプレート準拠）

固定仕様:
  - 1280x720 / 30fps
  - エピソードバッジ = 右上に表示
  - 画面下部の説明バー（字幕帯）は 描かない
  - 図解は必ず CONTENT_TOP..CONTENT_BOT に収める（はみ出しは例外で検知）
"""
import os
import glob

from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720
HEAD_TOP, HEAD_BOT = 12, 100
CONTENT_TOP, CONTENT_BOT = 118, 700
BG = (250, 248, 244)
INK = (26, 26, 30)
WHITE = (255, 255, 255)
DARK = (25, 26, 32)
GREY = (110, 114, 122)
YEL = (206, 152, 16)
BLU = (28, 90, 200)
RED = (178, 58, 58)
GRN = (36, 140, 100)
PUR = (124, 58, 237)

_BOLD_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "C:/Windows/Fonts/YuGothB.ttc",
    "C:/Windows/Fonts/meiryob.ttc",
    "C:/Windows/Fonts/msgothic.ttc",
    "C:/Windows/Fonts/BIZ-UDGothicB.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/System/Library/Fonts/Hiragino Sans W6.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
]
_MED_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Medium.ttc",
    "C:/Windows/Fonts/YuGothM.ttc",
    "C:/Windows/Fonts/meiryo.ttc",
    "C:/Windows/Fonts/msgothic.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/System/Library/Fonts/Hiragino Sans W3.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
]

_CACHE = {}


def _find(cands, kind):
    for p in cands:
        if os.path.exists(p):
            return p
    for pat in ("/usr/share/fonts/**/NotoSansCJK*", "/System/Library/Fonts/**/*ヒラギノ*"):
        hits = sorted(glob.glob(pat, recursive=True))
        hits = [h for h in hits if os.path.isfile(h) and (".ttc" in h or ".otf" in h)]
        if hits:
            return hits[0] if kind == "b" else hits[min(1, len(hits) - 1)]
    return None


def font(bold=True, size=32):
    key = ("b" if bold else "m", size)
    if key in _CACHE:
        return _CACHE[key]
    path = _find(_BOLD_CANDIDATES if bold else _MED_CANDIDATES, "b" if bold else "m")
    if path:
        try:
            f = ImageFont.truetype(path, size)
            _CACHE[key] = f
            return f
        except Exception:
            pass
    _CACHE[key] = ImageFont.load_default()
    return _CACHE[key]


def font_report():
    return "bold=%s / medium=%s" % (_find(_BOLD_CANDIDATES, "b"), _find(_MED_CANDIDATES, "m"))


def blend(c, w, ratio=0.85):
    return tuple(int(round(c[i] * (1 - ratio) + w[i] * ratio)) for i in range(3))


def hex2rgb(s, default=BLU):
    s = (s or "").lstrip("#")
    if len(s) == 6:
        try:
            return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
        except Exception:
            return default
    return default


def wrap(d, text, ft, maxw):
    """日本語は空白が無いので1文字ずつ折り返す。\n も尊重。"""
    lines, cur = [], ""
    for ch in str(text):
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        if d.textlength(cur + ch, font=ft) <= maxw or not cur:
            cur += ch
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


def fit(d, text, maxw, sizes, max_lines=2, bold=True):
    for s in sizes:
        ft = font(bold, s)
        ls = wrap(d, text, ft, maxw)
        if len(ls) <= max_lines:
            return ft, ls
    ft = font(bold, sizes[-1])
    return ft, wrap(d, text, ft, maxw)


def fit_h(d, text, maxw, sizes, avail_h, max_lines=3, bold=True, line_gap=8):
    """高さの予算も守ってフォントと行を決める（箱からの はみ出し・重なりを防ぐ）"""
    for s in sizes:
        ft = font(bold, s)
        ls = wrap(d, text, ft, maxw)
        if len(ls) <= max_lines and len(ls) * (ft.size + line_gap) <= avail_h:
            return ft, ls
    ft = font(bold, sizes[-1])
    ls = wrap(d, text, ft, maxw)
    keep = max(1, int(avail_h // (ft.size + line_gap)))
    return ft, ls[:max(1, min(keep, max_lines, len(ls)))]


def header(d, title, accent):
    d.rectangle([0, 0, W - 1, H - 1], outline=INK, width=12)
    d.rectangle([12, HEAD_TOP, W - 12, HEAD_BOT], fill=blend(accent, WHITE, 0.86))
    d.line([12, HEAD_BOT, W - 12, HEAD_BOT], fill=INK, width=5)
    ft, ls = fit(d, title, W - 300, [46, 40, 34, 30], max_lines=1)
    d.text((W / 2, (HEAD_TOP + HEAD_BOT) / 2), ls[0], font=ft, fill=INK, anchor="mm")


def badge(d, text):
    if not text:
        return
    bs = font(True, 26)
    bw = d.textlength(text, font=bs) + 36
    d.rounded_rectangle([W - 44 - bw, 24, W - 44, 70], radius=8, fill=(0, 0, 0, 180))
    d.text((W - 44 - bw / 2, 47), text, font=bs, fill=WHITE, anchor="mm")


# ------------------------- 各スライドタイプ -------------------------
def s_title(d, sp, accent):
    ft, ls = fit(d, sp.get("header", ""), W - 260, [80, 68, 58, 48], max_lines=2)
    top = 240
    for i, ln in enumerate(ls):
        d.text((W / 2, top + i * (ft.size + 14)), ln, font=ft, fill=INK, anchor="mm")
    y = top + len(ls) * (ft.size + 14) + 24
    d.rounded_rectangle([W / 2 - 90, y, W / 2 + 90, y + 8], radius=4, fill=accent)
    sub = sp.get("sub", "")
    if sub:
        ft2, ls2 = fit(d, sub, W - 320, [40, 34, 30], max_lines=2, bold=False)
        for i, ln in enumerate(ls2):
            d.text((W / 2, y + 70 + i * (ft2.size + 12)), ln, font=ft2, fill=GREY, anchor="mm")


def s_list(d, sp, accent):
    items = [str(x) for x in sp.get("items", [])][:5]
    n = max(len(items), 1)
    gap = 16
    hh = int((CONTENT_BOT - CONTENT_TOP - gap * (n - 1)) / n)
    hh = min(hh, 150)
    total = hh * n + gap * (n - 1)
    y = CONTENT_TOP + int((CONTENT_BOT - CONTENT_TOP - total) / 2)
    for i, t in enumerate(items):
        d.rounded_rectangle([70, y, W - 70, y + hh], radius=16, fill=WHITE, outline=accent, width=6)
        d.ellipse([96, y + hh / 2 - 34, 170, y + hh / 2 + 34], fill=accent)
        d.text((133, y + hh / 2), str(i + 1), font=font(True, 40), fill=WHITE, anchor="mm")
        ft, ls = fit_h(d, t, W - 330, [38, 34, 30, 26], hh - 26, max_lines=2)
        ty = y + hh / 2 - (len(ls) - 1) * (ft.size + 8) / 2
        for k, ln in enumerate(ls):
            d.text((206, ty + k * (ft.size + 8)), ln, font=ft, fill=INK, anchor="lm")
        y += hh + gap
    assert y - gap <= CONTENT_BOT + 1, "list overflow"


def s_boxes(d, sp, accent):
    cols = sp.get("cols", [])[:4]
    n = max(len(cols), 1)
    gap = 34
    bw = int((W - 120 - gap * (n - 1)) / n)
    bh = 330
    y0 = CONTENT_TOP + int((CONTENT_BOT - CONTENT_TOP - bh) / 2)
    for i, c in enumerate(cols):
        x = 60 + i * (bw + gap)
        d.rounded_rectangle([x, y0, x + bw, y0 + bh], radius=16, fill=WHITE, outline=accent, width=6)
        d.rectangle([x + 6, y0 + 6, x + bw - 6, y0 + 78], fill=accent)
        ft, ls = fit(d, c.get("t", ""), bw - 40, [34, 30, 26], max_lines=1)
        d.text((x + bw / 2, y0 + 42), ls[0], font=ft, fill=WHITE, anchor="mm")
        ft2, ls2 = fit_h(d, c.get("d", ""), bw - 44, [30, 26, 22, 20], bh - 124, max_lines=6, bold=False)
        ty = y0 + 110
        for ln in ls2:
            d.text((x + bw / 2, ty), ln, font=ft2, fill=INK, anchor="mm")
            ty += ft2.size + 12
    assert y0 + bh <= CONTENT_BOT, "boxes overflow"


def s_compare(d, sp, accent):
    gap = 40
    bw = int((W - 120 - gap) / 2)
    bh = 360
    y0 = CONTENT_TOP + int((CONTENT_BOT - CONTENT_TOP - bh) / 2)
    for i, (ttl, items, col) in enumerate((
            (sp.get("left_title", "A"), sp.get("left", []), GREY),
            (sp.get("right_title", "B"), sp.get("right", []), accent))):
        x = 60 + i * (bw + gap)
        d.rounded_rectangle([x, y0, x + bw, y0 + bh], radius=16, fill=WHITE, outline=col, width=6)
        d.rectangle([x + 6, y0 + 6, x + bw - 6, y0 + 82], fill=col)
        ft, ls = fit(d, ttl, bw - 40, [34, 30, 26], max_lines=1)
        d.text((x + bw / 2, y0 + 44), ls[0], font=ft, fill=WHITE, anchor="mm")
        ty = y0 + 118
        for it in [str(z) for z in items][:4]:
            ft2, ls2 = fit_h(d, "・" + it, bw - 60, [28, 24, 20], y0 + bh - 30 - ty, max_lines=3, bold=False)
            for ln in ls2:
                d.text((x + 30, ty), ln, font=ft2, fill=INK, anchor="lm")
                ty += ft2.size + 8
            ty += 12
            if ty > y0 + bh - 30:
                break
    assert y0 + bh <= CONTENT_BOT, "compare overflow"


def s_table3(d, sp, accent):
    rows = sp.get("rows", [])[:4]
    n = max(len(rows), 1)
    gap = 20
    hh = int((CONTENT_BOT - CONTENT_TOP - gap * (n - 1)) / n)
    hh = min(hh, 150)
    total = hh * n + gap * (n - 1)
    y = CONTENT_TOP + int((CONTENT_BOT - CONTENT_TOP - total) / 2)
    cols = [accent, YEL, GRN, BLU]
    for i, r in enumerate(rows):
        col = hex2rgb(r.get("color"), cols[i % 4])
        d.rounded_rectangle([52, y, W - 52, y + hh], radius=16, fill=WHITE, outline=col, width=6)
        d.ellipse([78, y + hh / 2 - 40, 158, y + hh / 2 + 40], fill=col)
        d.text((118, y + hh / 2), str(i + 1), font=font(True, 44), fill=WHITE, anchor="mm")
        ft, ls = fit_h(d, r.get("q", ""), 430, [32, 28, 24, 20], hh - 24, max_lines=2)
        qy = y + hh / 2 - (len(ls) - 1) * (ft.size + 8) / 2
        for k, ln in enumerate(ls):
            d.text((190, qy + k * (ft.size + 8)), ln, font=ft, fill=INK, anchor="lm")
        d.text((830, y + hh / 2), "→", font=font(True, 36), fill=col, anchor="mm")
        ft2, ls2 = fit_h(d, r.get("a", ""), 300, [32, 28, 24, 20], hh - 24, max_lines=2)
        ay = y + hh / 2 - (len(ls2) - 1) * (ft2.size + 8) / 2
        for k, ln in enumerate(ls2):
            d.text((W - 190, ay + k * (ft2.size + 8)), ln, font=ft2, fill=col, anchor="rm")
        y += hh + gap
    assert y - gap <= CONTENT_BOT + 1, "table3 overflow"


def s_flow(d, sp, accent):
    steps = [str(x) for x in sp.get("steps", [])][:4]
    n = max(len(steps), 1)
    gap = 46
    bw = int((W - 120 - gap * (n - 1)) / n)
    bh = 190
    y0 = CONTENT_TOP + int((CONTENT_BOT - CONTENT_TOP - bh) / 2)
    pal = [accent, GRN, YEL, RED]
    for i, t in enumerate(steps):
        x = 60 + i * (bw + gap)
        col = pal[i % 4]
        d.rounded_rectangle([x, y0, x + bw, y0 + bh], radius=16, fill=WHITE, outline=col, width=7)
        d.rectangle([x + 7, y0 + 7, x + bw - 7, y0 + 70], fill=col)
        d.text((x + bw / 2, y0 + 38), "%d" % (i + 1), font=font(True, 34), fill=WHITE, anchor="mm")
        ft, ls = fit_h(d, t, bw - 36, [32, 28, 24, 20], bh - 122, max_lines=3)
        ty = y0 + 110
        for ln in ls:
            d.text((x + bw / 2, ty), ln, font=ft, fill=INK, anchor="mm")
            ty += ft.size + 8
        if i < n - 1:
            d.text((x + bw + gap / 2, y0 + bh / 2), "→", font=font(True, 44), fill=INK, anchor="mm")
    assert y0 + bh <= CONTENT_BOT, "flow overflow"


def s_note(d, sp, accent):
    """1行=1ボックス。行ごとに高さを確保するので 文字の重なりが構造的に起きない。"""
    lines = [str(x) for x in sp.get("lines", [])][:4]
    n = max(len(lines), 1)
    gap = 14
    avail = CONTENT_BOT - CONTENT_TOP
    panel_h = avail - 40
    y_panel = CONTENT_TOP + 20
    d.rounded_rectangle([70, y_panel, W - 70, y_panel + panel_h], radius=20, fill=DARK)
    row_h = int((panel_h - 24 - gap * (n - 1)) / n)
    y = y_panel + 12
    for ln in lines:
        ft, ls, need = font(True, 44), [ln], 0
        for sz in (44, 38, 32, 27, 22, 18):
            ft = font(True, sz)
            ls = wrap(d, ln, ft, W - 240)
            need = len(ls) * (ft.size + 8)
            if need <= row_h - 12:
                break
        if need > row_h - 12:
            keep = max(1, int((row_h - 12) // (ft.size + 8)))
            ls = ls[:keep]
            need = len(ls) * (ft.size + 8)
        ty = y + (row_h - need) / 2.0
        for s in ls:
            d.text((W / 2, ty + ft.size / 2.0), s, font=ft, fill=WHITE, anchor="mm")
            ty += ft.size + 8
        y += row_h + gap
    assert y - gap <= y_panel + panel_h + 2, "note overflow"


def s_summary(d, sp, accent):
    lines = [str(x) for x in sp.get("lines", [])][:3]
    panels = len(lines)
    gap = 26
    hh = int((CONTENT_BOT - CONTENT_TOP - gap * (panels - 1)) / panels)
    hh = min(hh, 210)
    total = hh * panels + gap * (panels - 1)
    y = CONTENT_TOP + int((CONTENT_BOT - CONTENT_TOP - total) / 2)
    for i, ln in enumerate(lines):
        d.rounded_rectangle([70, y, W - 70, y + hh], radius=18, fill=WHITE,
                            outline=accent if i == 0 else GREY, width=6)
        ft, ls = fit_h(d, ln, W - 200, [40, 34, 28, 24], hh - 28, max_lines=2)
        ty = y + hh / 2 - (len(ls) - 1) * (ft.size + 10) / 2
        for k, s in enumerate(ls):
            d.text((W / 2, ty + k * (ft.size + 10)), s, font=ft,
                   fill=accent if i == 0 else INK, anchor="mm")
        y += hh + gap
    assert y - gap <= CONTENT_BOT + 1, "summary overflow"


def s_closing(d, sp, accent):
    ft, ls = fit(d, sp.get("header", ""), W - 240, [72, 62, 52, 44], max_lines=2)
    ty = 250
    for ln in ls:
        d.text((W / 2, ty), ln, font=ft, fill=INK, anchor="mm")
        ty += ft.size + 14
    ty += 20
    d.rounded_rectangle([W / 2 - 110, ty, W / 2 + 110, ty + 8], radius=4, fill=accent)
    ty += 60
    for ln in [str(x) for x in sp.get("lines", [])][:3]:
        ft2, ls2 = fit(d, ln, W - 280, [38, 32, 28], max_lines=2, bold=False)
        for s in ls2:
            d.text((W / 2, ty), s, font=ft2, fill=GREY, anchor="mm")
            ty += ft2.size + 10
        ty += 6


def s_image(d, sp, accent, img_path):
    im = Image.open(img_path).convert("RGB")
    sw, sh = im.size
    sc = max(W / sw, H / sh)
    im = im.resize((int(sw * sc), int(sh * sc)), Image.LANCZOS)
    left = (im.size[0] - W) // 2
    top = (im.size[1] - H) // 2
    im = im.crop((left, top, left + W, top + H))
    return im


RENDERERS = {
    "title": s_title, "list": s_list, "boxes": s_boxes, "compare": s_compare,
    "table3": s_table3, "flow": s_flow, "note": s_note, "summary": s_summary,
    "closing": s_closing,
}


def render(slide, out_png, badge_text="", accent_hex="#1C5AC8", images_dir=None, ep_no=1, slot=1):
    accent = hex2rgb(accent_hex)
    t = slide.get("type", "title")
    img = None
    if images_dir:
        for cand in ("%d_%d.png" % (ep_no, slot), "%d_%d.jpg" % (ep_no, slot),
                     "%d_%d.jpeg" % (ep_no, slot)):
            p = os.path.join(images_dir, cand)
            if os.path.exists(p):
                img = s_image(None, slide, accent, p)
                break
    if img is None:
        img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    if t == "image":
        d.rectangle([0, 0, W - 1, H - 1], outline=INK, width=12)
    else:
        header(d, slide.get("header", ""), accent)
        fn = RENDERERS.get(t, s_title)
        fn(d, slide, accent)
    badge(d, badge_text)
    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    img.save(out_png)
    return out_png
