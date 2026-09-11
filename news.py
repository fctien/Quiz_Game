"""
即時新聞題目產生器

兩種模式:
1. 有設定 ANTHROPIC_API_KEY  → 抓今日新聞標題,請 Claude 出選擇題(較有趣)
2. 沒有 API key              → 「猜版面」:給一則今日真實標題,猜它屬於哪個版面
結果快取 CACHE_MINUTES 分鐘,避免每局都重抓。
"""
import json
import os
import random
import time
import xml.etree.ElementTree as ET

import requests

CACHE_MINUTES = 60
MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-5")

# Google News 各版面 RSS(繁體中文、台灣版)
FEEDS = {
    "國際": "https://news.google.com/rss/headlines/section/topic/WORLD?hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    "台灣": "https://news.google.com/rss/headlines/section/topic/NATION?hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    "財經": "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    "科技": "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    "體育": "https://news.google.com/rss/headlines/section/topic/SPORTS?hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    "娛樂": "https://news.google.com/rss/headlines/section/topic/ENTERTAINMENT?hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
}

_cache = {"time": 0, "questions": []}


def fetch_headlines(per_feed=8):
    """回傳 [{'section':..., 'title':..., 'link':...}, ...]"""
    items = []
    for section, url in FEEDS.items():
        try:
            r = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            root = ET.fromstring(r.content)
            for it in root.iter("item"):
                title = (it.findtext("title") or "").strip()
                link = (it.findtext("link") or "").strip()
                # Google News 標題格式為「標題 - 媒體名稱」,把媒體名稱拆掉
                if " - " in title:
                    title = title.rsplit(" - ", 1)[0]
                if title:
                    items.append({"section": section, "title": title, "link": link})
                if sum(1 for x in items if x["section"] == section) >= per_feed:
                    break
        except Exception as e:  # 單一來源失敗不影響其他來源
            print(f"[news] {section} 抓取失敗: {e}")
    return items


# ---------------------------------------------------------------- 模式 2:猜版面
def section_questions(items, n=10):
    sections = list(FEEDS)
    random.shuffle(items)
    qs = []
    for i, it in enumerate(items[:n]):
        others = random.sample([s for s in sections if s != it["section"]], 3)
        opts = others + [it["section"]]
        random.shuffle(opts)
        qs.append({
            "id": f"news-sec-{i}",
            "region": "即時新聞",
            "category": "新聞",
            "difficulty": 1,
            "type": "choice",
            "question": f"今日新聞標題:\n「{it['title']}」\n這則新聞出現在哪個版面?",
            "options": opts,
            "answer": opts.index(it["section"]),
            "explanation": f"這則新聞刊登在「{it['section']}」版。",
            "fun_fact": "點下方連結可以閱讀全文。",
            "source": it["link"],
        })
    return qs


# ---------------------------------------------------------------- 模式 1:Claude 出題
PROMPT = """你是益智問答節目的出題者。以下是今天的新聞標題(每行一則,前面是編號):

{headlines}

請從中挑選 {n} 則適合出題的新聞,各出一題四選一選擇題,用繁體中文。規則:
- 題目只能根據標題本身的資訊出題,不可以加入標題沒有的細節或數字
- 避免政治立場用詞,以陳述事實的方式出題
- 錯誤選項要合理、有迷惑性
- explanation 用一句話說明答案;fun_fact 補一個相關的背景知識(若不確定就留空字串)

只輸出 JSON 陣列,不要其他文字,格式:
[{{"headline_id": 編號, "question": "...", "options": ["A","B","C","D"], "answer": 正確選項索引0-3, "explanation": "...", "fun_fact": "..."}}]
"""


def claude_questions(items, n=10):
    import anthropic  # pip install anthropic
    client = anthropic.Anthropic()
    items = items[:40]
    headlines = "\n".join(f"{i}. [{it['section']}] {it['title']}" for i, it in enumerate(items))
    msg = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        messages=[{"role": "user", "content": PROMPT.format(headlines=headlines, n=n)}],
    )
    text = msg.content[0].text.strip()
    text = text[text.find("["): text.rfind("]") + 1]
    raw = json.loads(text)
    qs = []
    for i, q in enumerate(raw):
        src = items[q.get("headline_id", 0)] if 0 <= q.get("headline_id", -1) < len(items) else {}
        if len(q.get("options", [])) != 4 or not 0 <= q.get("answer", -1) < 4:
            continue  # 格式不對的題目丟掉
        qs.append({
            "id": f"news-ai-{i}",
            "region": "即時新聞",
            "category": src.get("section", "新聞"),
            "difficulty": 2,
            "type": "choice",
            "question": q["question"],
            "options": q["options"],
            "answer": q["answer"],
            "explanation": q.get("explanation", ""),
            "fun_fact": q.get("fun_fact", ""),
            "source": src.get("link", ""),
            "ai_generated": True,
        })
    return qs


def get_news_questions(n=10):
    if time.time() - _cache["time"] < CACHE_MINUTES * 60 and _cache["questions"]:
        return list(_cache["questions"])
    items = fetch_headlines()
    if not items:
        return []
    qs = []
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            qs = claude_questions(items, n)
        except Exception as e:
            print(f"[news] Claude 出題失敗,改用猜版面模式: {e}")
    if not qs:
        qs = section_questions(items, n)
    _cache.update(time=time.time(), questions=qs)
    return list(qs)
