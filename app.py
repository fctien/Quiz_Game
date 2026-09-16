"""
脈衝 PULSE — Flask 後端
執行:  python app.py   然後用手機(同一個 Wi-Fi)開 http://<電腦IP>:5000

分數完全由伺服器計算(含作答秒數),前端送不了假分數,排行榜才可信。
"""
import json
import random
import secrets
import time
from datetime import date
from pathlib import Path
from urllib.parse import quote

from flask import Flask, Response, jsonify, request, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix

import classroom
import leaderboard
import multiplayer
import news

BASE = Path(__file__).parent
QDIR = BASE / "questions"

app = Flask(__name__, static_folder="static")
# 靜態檔不快取:改了樣式或題庫,重新整理就會看到新的
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
# 部署到 Render 等雲端平台時,前面會有一層反向代理;
# 這行讓 Flask 讀得到真正的網址與 https,QR code 才不會產生錯的連結。
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# ---------------------------------------------------------------- 遊戲規則
LIVES = 3
TIME_LIMIT = {"choice": 15, "order": 25}   # 秒
GRACE = 1.5                                 # 網路延遲容忍秒數
GAME_TTL = 60 * 60                          # 一局最長保留 1 小時

TOPICS = {
    "python":  {"name": "Python",   "seal": "蟒"},
    "pytorch": {"name": "Deep Learning", "seal": "深"},
    "geo":     {"name": "地理",     "seal": "輿"},
    "history": {"name": "歷史",     "seal": "史"},
    "human":   {"name": "人文",     "seal": "文"},
    "tech":    {"name": "科技",     "seal": "科"},
    "star":    {"name": "娛樂",     "seal": "星"},
    "fun":     {"name": "趣聞",     "seal": "奇"},
    "tt":      {"name": "桌球",     "seal": "桌"},
    "news":    {"name": "即時新聞", "seal": "聞"},
    "mix":     {"name": "綜合挑戰", "seal": "雜"},
}
CATEGORIES = TOPICS            # 舊名稱,保留相容
# 題庫檔案 -> 這個檔的題目屬於哪個地區(顯示在題目上,也可以當篩選條件)
FILES = {"taiwan": "台灣", "china": "中國", "world": "世界", "poetry": "古典詩詞",
         "stars": "娛樂", "fun": "趣聞", "tech": "科技", "python": "Python", "pytorch": "Deep Learning",
         "pingpong": "桌球"}
REGIONS = ["台灣", "中國", "世界"]   # 地理、歷史、人文可再依地區篩選


def load_all():
    """把各檔題庫讀進來,依 topic 分組(地區則放在每題的 region 欄位)"""
    bank = {k: [] for k in TOPICS if k not in ("news", "mix")}
    for f, region in FILES.items():
        with open(QDIR / f"{f}.json", encoding="utf-8") as fp:
            for q in json.load(fp):
                q.setdefault("region", region)
                bank[q["topic"]].append(q)
    return bank


BANK = load_all()


def active(q):
    """題目可設 expires(YYYY-MM-DD),過了這天自動下架,例如會被打破的世界紀錄"""
    return not q.get("expires") or q["expires"] >= date.today().isoformat()


def active_bank(topic, region=None, unit=None):
    qs = [q for q in BANK[topic] if active(q)]
    if region:
        qs = [q for q in qs if q.get("region") == region]
    if unit:                                   # 課程週次(Python 題庫用)
        qs = [q for q in qs if q.get("unit") == unit]
    return qs


def units_of(topic):
    """回傳這個主題的單元清單(依題庫出現順序),例如 Python 的 W1~W16 週次"""
    out, seen = [], set()
    for q in BANK.get(topic, []):
        u = q.get("unit")
        if u and u not in seen:
            seen.add(u)
            out.append({"key": u, "name": q.get("unit_name", u),
                        "count": len(active_bank(topic, None, u))})
    return out


# 進行中的遊戲 session_id -> 狀態
# (教學雛形用記憶體保存;多台主機或多個 worker 時請改用 Redis)
GAMES = {}


def new_game(cat, qs):
    return {"cat": cat, "questions": qs, "i": 0, "created": time.time(),
            "shown_at": None, "extra": 0,
            "lives": LIVES, "score": 0, "streak": 0, "best": 0,
            "right": 0, "answered": 0, "skipped": 0,
            "powers": {"fifty": True, "skip": True, "time": True},
            "over": False, "submitted": False}


def cleanup():
    now = time.time()
    for sid in [s for s, g in GAMES.items() if now - g["created"] > GAME_TTL]:
        GAMES.pop(sid, None)


def public_view(q):
    """送到前端的題目:不含答案"""
    return {k: v for k, v in q.items()
            if k not in ("answer", "explanation", "fun_fact", "source", "expires")}


# 一份考卷的難度比例:25% 簡單、50% 中等、25% 較難
DIFF_MIX = {1: 0.25, 2: 0.50, 3: 0.25}


def by_ratio(pool, n):
    """依 DIFF_MIX 的比例抽 n 題;某一級題目不夠時,缺的份額由其他級補上。"""
    buckets = {d: [q for q in pool if q.get("difficulty", 2) == d] for d in DIFF_MIX}
    for b in buckets.values():
        random.shuffle(b)
    # 最大餘數法:先取整數部分,剩下的名額給小數最大的那一級
    raw = {d: n * r for d, r in DIFF_MIX.items()}
    want = {d: int(v) for d, v in raw.items()}
    order = list(raw)
    random.shuffle(order)                      # 餘數相同時隨機分配,長期平均才會貼近 25/50/25
    for d in sorted(order, key=lambda d: raw[d] - want[d], reverse=True):
        if sum(want.values()) >= n:
            break
        want[d] += 1
    chosen = []
    for d in (1, 2, 3):
        chosen += buckets[d][:want[d]]
    # 有哪一級題目不夠,就從剩下的題目補滿
    if len(chosen) < n:
        taken = {id(q) for q in chosen}
        rest = [q for q in pool if id(q) not in taken]
        random.shuffle(rest)
        chosen += rest[:n - len(chosen)]
    chosen.sort(key=lambda q: q.get("difficulty", 2))   # 由易到難
    return chosen


def pick_questions(cat, n, region=None, unit=None, only_choice=False):
    if cat == "news":
        pool = news.get_news_questions()
    elif cat == "mix":
        pool = [q for k in BANK for q in active_bank(k, region)]
    else:
        pool = active_bank(cat, region, unit)
    if only_choice:
        pool = [q for q in pool if q.get("type") == "choice"]
    return by_ratio(list(pool), n)


def multiplier(streak):
    return 2 if streak >= 5 else 1.5 if streak >= 3 else 1


def state(g):
    """回傳給前端的遊戲狀態"""
    return {k: g[k] for k in ("i", "lives", "score", "streak", "best",
                              "right", "answered", "over", "powers")}


def get_game(body):
    g = GAMES.get(body.get("session"))
    if not g:
        return None, (jsonify(error="這局遊戲已過期,請回首頁重新開始"), 404)
    return g, None


def advance(g):
    g["i"] += 1
    g["shown_at"] = None
    g["extra"] = 0
    if g["lives"] <= 0 or g["i"] >= len(g["questions"]):
        g["over"] = True


# ---------------------------------------------------------------- 頁面與題目 API
@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/host")
def host_page():
    return send_from_directory(app.static_folder, "host.html")


@app.get("/play")
def play_page():
    return send_from_directory(app.static_folder, "play.html")


@app.get("/manifest.json")
def manifest():
    return send_from_directory(app.static_folder, "manifest.json")


@app.get("/sw.js")
def service_worker():
    # Service Worker 必須放在根目錄,才能控制整個網站
    return send_from_directory(app.static_folder, "sw.js", mimetype="application/javascript")


@app.get("/class")
def class_page():
    return send_from_directory(app.static_folder, "class.html")


@app.get("/api/categories")
def categories():
    region = request.args.get("region") or None
    out = []
    for k, v in TOPICS.items():
        if k == "mix":
            count = sum(len(active_bank(b, region)) for b in BANK)
        elif k == "news":
            count = None
        else:
            count = len(active_bank(k, region))
        out.append({"key": k, "name": v["name"], "seal": v["seal"], "count": count})
    return jsonify(out)


@app.get("/api/units")
def units():
    """某個主題的單元(週次)清單"""
    topic = request.args.get("topic", "")
    if topic not in BANK:
        return jsonify([])
    return jsonify(units_of(topic))


@app.post("/api/start")
def start():
    cleanup()
    body = request.get_json(silent=True) or {}
    cat = body.get("category", "mix")
    if cat not in TOPICS:
        return jsonify(error="沒有這個主題"), 400
    region = body.get("region") or None
    if region and region not in REGIONS:
        return jsonify(error="沒有這個地區"), 400
    unit = body.get("unit") or None
    qs = pick_questions(cat, 10, region, unit)
    if not qs:
        return jsonify(error="目前抓不到新聞,請稍後再試或先玩其他分類"), 503
    sid = secrets.token_urlsafe(12)
    GAMES[sid] = new_game(cat, qs)
    return jsonify(session=sid, total=len(qs), lives=LIVES, time_limit=TIME_LIMIT,
                   unit_name=(qs[0].get("unit_name", "") if unit else ""),
                   questions=[public_view(q) for q in qs])


@app.post("/api/show")
def show():
    """前端把題目顯示出來時呼叫,伺服器從這一刻開始計時"""
    body = request.get_json(silent=True) or {}
    g, err = get_game(body)
    if err:
        return err
    if int(body.get("index", -1)) != g["i"] or g["over"]:
        return jsonify(error="題號不符"), 409
    if g["shown_at"] is None:            # 重複呼叫不會重設計時
        g["shown_at"] = time.time()
    return jsonify(ok=True)


@app.post("/api/answer")
def answer():
    body = request.get_json(silent=True) or {}
    g, err = get_game(body)
    if err:
        return err
    i = int(body.get("index", -1))
    if g["over"] or i != g["i"] or g["shown_at"] is None:
        return jsonify(error="題號不符"), 409
    q = g["questions"][i]
    limit = TIME_LIMIT.get(q["type"], 15) + g["extra"]
    elapsed = time.time() - g["shown_at"]
    given = body.get("answer")
    timed_out = given is None or elapsed > limit + GRACE
    correct = (not timed_out) and check(q, given)

    gained = 0
    g["answered"] += 1
    if correct:
        g["streak"] += 1
        g["right"] += 1
        g["best"] = max(g["best"], g["streak"])
        sec_left = max(0, limit - elapsed)
        gained = round((100 * q.get("difficulty", 1) + round(sec_left) * 5) * multiplier(g["streak"]))
        g["score"] += gained
    else:
        g["streak"] = 0
        g["lives"] -= 1
    advance(g)
    return jsonify(correct=correct, timed_out=timed_out, gained=gained,
                   answer=q["answer"], explanation=q.get("explanation", ""),
                   fun_fact=q.get("fun_fact", ""), source=q.get("source", ""),
                   state=state(g))


def check(q, given):
    if q["type"] == "order":
        return isinstance(given, list) and list(given) == list(q["answer"])
    return given == q["answer"]


@app.post("/api/power")
def power():
    """道具:fifty(刪去兩個)、skip(跳過)、time(加時 10 秒),每局各一次"""
    body = request.get_json(silent=True) or {}
    g, err = get_game(body)
    if err:
        return err
    kind = body.get("type")
    if g["over"] or int(body.get("index", -1)) != g["i"]:
        return jsonify(error="題號不符"), 409
    if not g["powers"].get(kind):
        return jsonify(error="這個道具已經用過了"), 400
    q = g["questions"][g["i"]]
    g["powers"][kind] = False
    out = {}
    if kind == "fifty":
        if q["type"] != "choice" or len(q["options"]) < 4:
            g["powers"][kind] = True
            return jsonify(error="這題不能用刪去法"), 400
        wrong = [k for k in range(len(q["options"])) if k != q["answer"]]
        out["remove"] = random.sample(wrong, 2)
    elif kind == "time":
        g["extra"] += 10
    elif kind == "skip":
        g["skipped"] += 1
        advance(g)
    return jsonify(out | {"state": state(g)})


@app.post("/api/finish")
def finish():
    """放棄這局(沒有要上榜)"""
    body = request.get_json(silent=True) or {}
    g = GAMES.get(body.get("session"))
    if g and (g["submitted"] or not g["over"]):
        GAMES.pop(body.get("session"), None)
    return jsonify(ok=True)


# ---------------------------------------------------------------- 排行榜 API
@app.post("/api/submit")
def submit():
    body = request.get_json(silent=True) or {}
    g, err = get_game(body)
    if err:
        return err
    if not g["over"]:
        return jsonify(error="這局還沒結束"), 400
    if g["submitted"]:
        return jsonify(error="這局已經上榜過了"), 400
    name = leaderboard.clean_name(body.get("name", ""))
    if not name:
        return jsonify(error="請輸入 1 到 12 個字的暱稱"), 400
    g["submitted"] = True
    row_id = leaderboard.add_score(name=name, category=g["cat"], score=g["score"],
                                   right=g["right"], answered=g["answered"], best_streak=g["best"])
    GAMES.pop(body.get("session"), None)
    return jsonify(id=row_id,
                   rank_week=leaderboard.rank_of(row_id, g["cat"], "week"),
                   rank_all=leaderboard.rank_of(row_id, g["cat"], "all"))


@app.get("/api/leaderboard")
def get_leaderboard():
    cat = request.args.get("category", "all")
    period = request.args.get("period", "week")
    if cat != "all" and cat not in TOPICS:
        return jsonify(error="沒有這個分類"), 400
    if period not in ("week", "all"):
        return jsonify(error="period 只能是 week 或 all"), 400
    return jsonify(leaderboard.top(cat, period, limit=20))


multiplayer.init(app, pick_questions, leaderboard.clean_name, TOPICS)

@app.post("/api/class/summary")
def class_summary():
    b = request.get_json(silent=True) or {}
    code = classroom.clean_code(b.get("code", ""))
    if not classroom.get(code):
        return jsonify(error="找不到這個班級代碼"), 404
    if not classroom.check(code, b.get("admin", "")):
        return jsonify(error="管理碼不對"), 403
    out = classroom.summary(code)
    out["roster"] = classroom.get_roster(code)
    return jsonify(out)


@app.get("/api/class/export")
def class_export():
    code = classroom.clean_code(request.args.get("code", ""))
    if not classroom.check(code, request.args.get("admin", "")):
        return jsonify(error="管理碼不對"), 403
    csv_text = classroom.export_csv(code)
    # 檔名含中文,要用 RFC 5987 的 filename* 編碼,HTTP 標頭只能放 ASCII
    quoted = quote(f"{code}-積分.csv")
    return Response(csv_text, mimetype="text/csv",
                    headers={"Content-Disposition":
                             f"attachment; filename=class-points.csv; filename*=UTF-8''{quoted}"})


@app.post("/api/class/reset")
def class_reset():
    b = request.get_json(silent=True) or {}
    code = classroom.clean_code(b.get("code", ""))
    if not classroom.check(code, b.get("admin", "")):
        return jsonify(error="管理碼不對"), 403
    classroom.reset(code)
    return jsonify(ok=True)


if __name__ == "__main__":
    leaderboard.init()
    classroom.init()
    # host=0.0.0.0 讓同網段的手機也能連進來
    # threaded=True:多人模式每位玩家會保持一條即時連線
    app.run(host="0.0.0.0", port=5000, debug=True, threaded=True)
else:
    leaderboard.init()      # 用 gunicorn 啟動時
    classroom.init()
