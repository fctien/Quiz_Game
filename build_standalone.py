"""
產生不需要後端的單機版 standalone.html(題庫直接嵌入網頁,可直接用瀏覽器開啟或放到任何靜態網站)。
注意:單機版沒有「即時新聞」分類,而且答案就在網頁原始碼裡。
用法: python build_standalone.py
"""
import json
from pathlib import Path
from app import BANK, CATEGORIES

html = (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")
cats = [{"key": k, "name": v["name"],
         "count": len(BANK[k]) if k in BANK else sum(len(b) for b in BANK.values())}
        for k, v in CATEGORIES.items() if k != "news"]
inject = ("<script>window.EMBEDDED_BANK = " + json.dumps(BANK, ensure_ascii=False) +
          ";\nwindow.EMBEDDED_CATS = " + json.dumps(cats, ensure_ascii=False) + ";</script>\n")
out = html.replace("<script>", inject + "<script>", 1)
Path("standalone.html").write_text(out, encoding="utf-8")
print("已產生 standalone.html")
