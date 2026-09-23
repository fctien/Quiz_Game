"""
產生不需要後端的單機版網頁(題庫直接嵌入網頁,用瀏覽器打開就能玩)。

會產生兩份:
  standalone.html    完整版,含 Python 與 Deep Learning,自己與上課用
  docs/index.html    公開版,不含 Python 與 Deep Learning(那是課程教材,不放到網路上)
                     GitHub Pages 設成「main 分支 + /docs 資料夾」就會發佈這一頁

注意:單機版沒有「即時新聞」分類,而且答案就在網頁原始碼裡。
用法: python build_standalone.py
"""
import base64
import json
import re
from pathlib import Path

from app import BANK, REGION_ORDER, REGION_TOPICS, TOPICS

HERE = Path(__file__).parent
# 公開版要藏起來的主題(課程教材)
PRIVATE = ("python", "pytorch", "vba", "ai", "emba")

html = (HERE / "static" / "index.html").read_text(encoding="utf-8")
css = (HERE / "static" / "style.css").read_text(encoding="utf-8")
html = re.sub(r'<link rel="stylesheet" href="/static/style\.css[^"]*">',
              lambda m: "<style>\n" + css + "</style>", html)


def data_uri(name):
    raw = (HERE / "static" / "icons" / name).read_bytes()
    return "data:image/png;base64," + base64.b64encode(raw).decode()


# 單機版沒有後端,/manifest.json 與 /sw.js 抓不到,圖示改成內嵌
html = html.replace('<link rel="manifest" href="/manifest.json">\n', "")
html = html.replace('href="/static/icons/icon-180.png"', f'href="{data_uri("icon-180.png")}"')
html = html.replace('href="/static/icons/favicon.png"', f'href="{data_uri("favicon.png")}"')
html = re.sub(r"if \('serviceWorker' in navigator\)[^\n]*\n", "", html)

SUB = re.compile(r'(<p class="sub">)[^<]*?(，十題定名次</p>)')


def build(hide=()):
    """hide 裡的主題會整個從這一份網頁裡拿掉:題庫、主題清單、排行榜的分類籤、首頁副標都不會出現"""
    bank = {k: v for k, v in BANK.items() if k not in hide}
    # 單機版的地區按鈕是照題庫順序長出來的,先把地理/歷史/人文按 REGION_ORDER 排好
    for k in REGION_TOPICS:
        if k in bank:
            bank[k] = sorted(bank[k], key=lambda q: REGION_ORDER.index(q["unit"])
                             if q.get("unit") in REGION_ORDER else len(REGION_ORDER))
    cats = [{"key": k, "name": v["name"], "seal": v["seal"],
             "count": len(bank[k]) if k in bank else sum(len(b) for b in bank.values())}
            for k, v in TOPICS.items() if k != "news" and k not in hide]
    inject = ("<script>window.EMBEDDED_BANK = " + json.dumps(bank, ensure_ascii=False) +
              ";\nwindow.EMBEDDED_CATS = " + json.dumps(cats, ensure_ascii=False) + ";</script>\n")
    out = html.replace("<script>", inject + "<script>", 1)
    for k in hide:                      # 排行榜的分類籤是寫死在前端的,一併拿掉
        out = out.replace(f"'{k}', ", "", 1)
    # 首頁副標列出的主題名稱也要跟著換
    names = "・".join(c["name"] for c in cats if c["key"] != "mix")
    out = SUB.sub(lambda m: m.group(1) + names + m.group(2), out, count=1)
    total = sum(len(v) for v in bank.values())
    return out, total, [c["key"] for c in cats]


full, n_full, _ = build()
(HERE / "standalone.html").write_text(full, encoding="utf-8")

share, n_share, keys = build(hide=PRIVATE)
docs = HERE / "docs"
docs.mkdir(exist_ok=True)
(docs / "index.html").write_text(share, encoding="utf-8")

print(f"standalone.html   完整版　{n_full} 題")
print(f"docs/index.html   公開版　{n_share} 題（已藏起 {'、'.join(PRIVATE)}）")
print(f"                  公開版主題:{'、'.join(keys)}")
