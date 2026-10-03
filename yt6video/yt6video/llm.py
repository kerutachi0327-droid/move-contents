# -*- coding: utf-8 -*-
"""台本生成アダプタ

プロバイダ:
  stub   : APIキー不要。テンプレート骨格＋文字起こしから機械的に埋める（オフライン動作用）
  openai : OpenAI 互換 Chat Completions（OpenAI / Gemini OpenAI互換 / OpenRouter / Ollama 等）
  gemini : Google Gemini ネイティブ REST
APIキーは config.json / .env / 環境変数 から読み込み、コードには絶対に埋め込まない。
"""
import json
import os
import re
import urllib.request

SYSTEM = (
    "あなたは中小企業経営者向けの縦型教育コンテンツの構成作家です。"
    "与えられた入力（YouTube動画の文字起こし）から、6本×8スライドの台本をJSONで設計します。"
    "出力はJSONのみ。説明文・コードフェンスは禁止。"
)

SLOT_GUIDE = [
    "1: 課題提示（type=title。header=課題の一言, sub=補足1行）",
    "2: 原因/要素の列挙（type=list。items=3〜5個）",
    "3: 図解（type=boxes か flow。boxes は cols=[{t:見出し,d:説明}] 3〜4個 / flow は steps 3〜4個）",
    "4: 対比（type=compare。left_title,left[],right_title,right[]）",
    "5: 分岐・対応表（type=table3。rows=[{q:状況,a:打ち手}] 3個）",
    "6: 要点（type=note。lines 2〜4行）",
    "7: まとめ（type=summary。lines 2〜3行）",
    "8: 締めと次への誘導（type=closing。header=決めゼリフ, lines 1〜3行）",
]


def prompt_for(transcript, title, template):
    eps = template["episodes"]
    lines = ["# 入力YouTube動画のタイトル", title, "", "# 文字起こし（要約して構造化する）",
             transcript[:14000], "", "# 作るべき6本の役割"]
    for e in eps:
        lines.append("- no=%s badge=%s 役割=%s アクセント色=%s" % (e["no"], e["badge"], e["role"], e["accent"]))
    lines += ["", "# 各本の8スライドの型（この順番を厳守）"] + ["  " + s for s in SLOT_GUIDE]
    lines += [
        "", "# 制約",
        "- 日本語。専門用語は使わない。小学生でも理解できる表現。",
        "- 各項目は20文字以内。1スライドの情報は1メッセージ。",
        "- 事例・数字は文字起こしに無いものを創作しない。無ければ一般原則として書く。",
        "- 全6本が1つの物語としてつながる（序章→理論→統合→総括）。",
        "",
        "# 出力JSONスキーマ（この形のみ。前後に文章を書かない）",
        '{"folder_title":"...","episodes":[{"no":0,"badge":"序章","accent":"#1C5AC8",',
        ' "slides":[{"type":"title","header":"...","sub":"..."},{"type":"list","header":"...","items":["..."]},',
        ' {"type":"boxes","header":"...","cols":[{"t":"...","d":"..."}]},{"type":"compare","header":"...",',
        ' "left_title":"...","left":["..."],"right_title":"...","right":["..."]},',
        ' {"type":"table3","header":"...","rows":[{"q":"...","a":"..."}]},{"type":"note","header":"...","lines":["..."]},',
        ' {"type":"summary","header":"...","lines":["..."]},{"type":"closing","header":"...","lines":["..."]}]}]}',
    ]
    return "\n".join(lines)


def _http_json(url, payload, headers, timeout=180):
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def extract_json(text):
    if not text:
        raise ValueError("empty LLM response")
    t = text.strip()
    t = re.sub(r"^```(?:json)?", "", t).strip()
    t = re.sub(r"```$", "", t).strip()
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j <= i:
        raise ValueError("no JSON object in response")
    return json.loads(t[i:j + 1])


def call_openai(cfg, prompt):
    base = (cfg.get("llm_base_url") or "https://api.openai.com/v1").rstrip("/")
    model = cfg.get("llm_model") or "gpt-4o-mini"
    data = _http_json(base + "/chat/completions", {
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        "temperature": 0.6,
        "response_format": {"type": "json_object"},
    }, {"Content-Type": "application/json", "Authorization": "Bearer " + cfg["llm_api_key"]})
    return data["choices"][0]["message"]["content"]


def call_gemini(cfg, prompt):
    model = cfg.get("llm_model") or "gemini-2.0-flash"
    url = ("https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent?key=%s"
           % (model, cfg["llm_api_key"]))
    data = _http_json(url, {
        "system_instruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.6, "responseMimeType": "application/json"},
    }, {"Content-Type": "application/json"})
    return data["candidates"][0]["content"]["parts"][0]["text"]


def call_llm(cfg, transcript, title, template, log=print):
    if not cfg.get("llm_api_key") or cfg.get("llm_provider", "stub") == "stub":
        log("[llm] プロバイダ=stub（APIキー未設定のため、テンプレート骨格から機械生成）")
        return stub_spec(transcript, title, template)
    log("[llm] プロバイダ=%s モデル=%s で台本を生成中…" % (cfg.get("llm_provider"), cfg.get("llm_model")))
    prompt = prompt_for(transcript, title, template)
    txt = call_gemini(cfg, prompt) if cfg.get("llm_provider") == "gemini" else call_openai(cfg, prompt)
    data = extract_json(txt)
    data.setdefault("folder_title", title)
    log("[llm] 台本JSONを受領（episodes=%d）" % len(data.get("episodes", [])))
    return data


# ------------------------- stub（APIキー不要） -------------------------
def _sents(text, n=400):
    text = re.sub(r"\s+", " ", text or "")
    parts = re.split(r"(?<=[。！？!?\.])\s*", text)
    out = []
    for p in parts:
        p = p.strip(" 　")
        if 8 <= len(p) <= 60:
            out.append(p)
    return out[:n]


def stub_spec(transcript, title, template):
    """テンプレート骨格を維持しつつ、見出しの一部を文字起こしの語句で置き換える。"""
    ss = _sents(transcript)
    pick = lambda i: (ss[i % len(ss)] if ss else "")
    out = {"folder_title": title, "episodes": []}
    k = 0
    for e in template["episodes"]:
        ep = {"no": e["no"], "badge": e["badge"], "accent": e["accent"], "slides": []}
        for i, sp in enumerate(e["slides"]):
            sp = dict(sp)
            if ss and sp.get("type") in ("title",) and i == 0:
                sp["header"] = e.get("theme", sp.get("header", ""))
                sp["sub"] = pick(k); k += 1
            elif ss and sp.get("type") == "note":
                sp["lines"] = [pick(k), pick(k + 1)]; k += 2
            ep["slides"].append(sp)
        out["episodes"].append(ep)
    return out
