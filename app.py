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
import gate
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

# group 決定主題出現在主持台的哪一個分頁。course 那一頁要先解鎖才看得到,
# 判斷「能不能碰」一律用 gate.py,不要用 group 當安全依據 —— group 只是畫面分類。
GROUPS = [
    {"key": "course", "name": "課程"},
    {"key": "known",  "name": "通識"},
    {"key": "light",  "name": "輕鬆"},
    {"key": "extra",  "name": "特別"},
]
TOPICS = {
    "python":  {"name": "Python",   "seal": "蟒", "group": "course"},
    "pytorch": {"name": "Deep Learning", "seal": "深", "group": "course"},
    "ai":      {"name": "AI 導論",  "seal": "導", "group": "course"},
    "vba":     {"name": "VBA",      "seal": "巨", "group": "course"},
    "emba":    {"name": "EMBA",     "seal": "商", "group": "course"},
    "geo":     {"name": "地理",     "seal": "輿", "group": "known"},
    "history": {"name": "歷史",     "seal": "史", "group": "known"},
    "human":   {"name": "人文",     "seal": "文", "group": "known"},
    "tech":    {"name": "科技",     "seal": "科", "group": "known"},
    "star":    {"name": "娛樂",     "seal": "星", "group": "light"},
    "fun":     {"name": "趣聞",     "seal": "奇", "group": "light"},
    "tt":      {"name": "桌球",     "seal": "桌", "group": "light"},
    "news":    {"name": "即時新聞", "seal": "聞", "group": "extra"},
    "mix":     {"name": "綜合挑戰", "seal": "雜", "group": "extra"},
}
CATEGORIES = TOPICS            # 舊名稱,保留相容
# 題庫檔案 -> 這個檔的題目屬於哪個地區(顯示在題目上,也可以當篩選條件)
FILES = {"taiwan": "台灣", "china": "中國", "world": "世界", "poetry": "古典詩詞",
         "r_taiwan": "台灣", "r_china": "中國", "r_eastasia": "日韓・東亞",
         "r_southasia": "東南亞・南亞", "r_europe": "歐洲", "r_america": "美洲",
         "r_other": "中東・非洲・大洋洲",
         "stars": "娛樂", "fun": "趣聞", "tech": "科技", "python": "Python", "pytorch": "Deep Learning",
         "vba": "VBA", "pingpong": "桌球",
         "ai": "AI 導論", "emba": "EMBA"}
# 地理、歷史、人文的題目再依地區分成幾個單元,主持台是「先選主題,再選地區」。
# 地區直接用單元(unit)的機制,和 Python 的週次共用同一套,不必多一套東西。
REGIONS = ["台灣", "中國", "日韓・東亞", "東南亞・南亞", "歐洲", "美洲",
           "中東・非洲・大洋洲", "全球・跨區", "古典詩詞"]
# 主持台上地區按鈕的排列順序(地理、歷史、人文三個主題共用)
REGION_ORDER = ["TW", "CN", "EA", "SEA", "EU", "AM", "OTH", "GLOBAL", "POEM"]
REGION_TOPICS = ("geo", "history", "human")
COUNTS_MIN = 5                      # 一場最少 5 題,單元少於這個數就不列出來

# 課程主題的單元順序。題庫是逐週(逐科)慢慢補上來的,單元清單由題目長出來,
# 但順序要照課程的順序,不能照檔案裡碰巧的先後,所以在這裡先寫死。
# 還沒有題目的單元不會出現在畫面上,補進來就會自動照這個順序排好。
UNIT_ORDER = {
    "ai": [f"W{i}" for i in range(1, 17)] + ["MIX"],
    "emba": ["MV", "AOI", "AIINTRO", "AGENTIC", "AIWAR", "USCN", "TWNOW"],
}
# 各單元的中文名稱(題目裡也會寫,這裡是給還沒有題目時的對照與檢查用)
UNIT_NAMES = {
    "ai": {
        "W1": "W1 什麼是 AI", "W2": "W2 AI 術語地圖", "W3": "W3 AI 與神經網路簡史",
        "W4": "W4 什麼是機器學習", "W5": "W5 神經元與感知機", "W6": "W6 學習就是最佳化",
        "W7": "W7 反向傳播", "W8": "W8 什麼是深度學習", "W9": "W9 CNN 卷積原理與四種任務",
        "W10": "W10 注意力機制與 Transformer", "W11": "W11 什麼是 LLM",
        "W12": "W12 LLM 的能力邊界", "W13": "W13 什麼是 AI Agent",
        "W14": "W14 Agent 與程式開發", "W15": "W15 Physical AI",
        "W16": "W16 主權 AI 與 AI 時代的你", "MIX": "綜合題組（跨週整合）",
    },
    "emba": {
        "MV": "機器視覺檢測技術", "AOI": "AOI 案例分享", "AIINTRO": "AI 簡介",
        "AGENTIC": "Agentic AI", "AIWAR": "AI War",
        "USCN": "美中競賽", "TWNOW": "談台灣現狀與台灣病",
    },
}


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
    out = [u for u in out if u["count"] >= min(COUNTS_MIN, 5)]   # 題數太少的單元不顯示,免得一開場就湊不滿
    if topic in REGION_TOPICS:          # 地區按鈕固定照 REGION_ORDER 排,不受題庫檔順序影響
        out.sort(key=lambda d: REGION_ORDER.index(d["key"])
                 if d["key"] in REGION_ORDER else len(REGION_ORDER))
    elif topic in UNIT_ORDER:           # 課程主題照課程順序排,不照題庫檔裡碰巧的先後
        order = UNIT_ORDER[topic]
        out.sort(key=lambda d: order.index(d["key"]) if d["key"] in order else len(order))
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


@app.get("/qrcard")
def qr_card():
    """做一張可以印出來的固定入口卡"""
    return send_from_directory(app.static_folder, "qrcard.html")


@app.get("/j/<entry>")
def join_entry(entry):
    """固定入口:印出來的 QR 都指向這裡,再自動轉進目前開著的考坊"""
    return send_from_directory(app.static_folder, "join.html")


@app.get("/class")
def class_page():
    return send_from_directory(app.static_folder, "class.html")


@app.get("/api/categories")
def categories():
    region = request.args.get("region") or None
    show_course = gate.unlocked(request)
    out = []
    for k, v in TOPICS.items():
        if gate.is_course(k) and not show_course:
            continue                    # 沒解鎖,課程主題連格子都不出現
        if k == "mix":
            count = sum(len(active_bank(b, region)) for b in BANK)
        elif k == "news":
            count = None
        else:
            count = len(active_bank(k, region))
        out.append({"key": k, "name": v["name"], "seal": v["seal"],
                    "group": v.get("group", "extra"), "count": count})
    return jsonify(out)


@app.get("/api/gate")
def gate_status():
    """前端拿來決定要不要畫「解鎖課程題庫」那個按鈕"""
    return jsonify(gate.status(request))


@app.post("/api/gate")
def gate_unlock():
    """老師輸入 TEACH_CODE 解鎖課程題庫。密碼在環境變數裡,不在任何檔案裡。"""
    body = request.get_json(silent=True) or {}
    if not gate.enforced():
        return jsonify(ok=True, unlocked=True)          # 本機零設定,本來就全開
    if not gate.openable():
        return jsonify(error="這台伺服器沒有設定 TEACH_CODE,課程題庫在這裡打不開"), 403
    if gate.too_fast("unlock:" + (request.remote_addr or "?"), limit=10):
        return jsonify(error="試太多次了,等一分鐘再來"), 429
    if not gate.check_code(body.get("code")):
        return jsonify(error="密碼不對"), 403
    resp = jsonify(ok=True, unlocked=True)
    resp.set_cookie(gate.COOKIE, gate.make_token(), max_age=gate.MAX_AGE,
                    httponly=True, samesite="Lax", secure=request.is_secure)
    return resp


@app.delete("/api/gate")
def gate_lock():
    """鎖回去(換教室、借別人用的時候)"""
    resp = jsonify(ok=True, unlocked=False)
    resp.delete_cookie(gate.COOKIE, samesite="Lax")
    return resp


@app.get("/api/units")
def units():
    """某個主題的單元(週次)清單"""
    topic = request.args.get("topic", "")
    if topic not in BANK:
        return jsonify([])
    if not gate.allow(topic, request):
        return jsonify([])
    return jsonify(units_of(topic))


@app.post("/api/start")
def start():
    cleanup()
    body = request.get_json(silent=True) or {}
    cat = body.get("category", "mix")
    if cat not in TOPICS:
        return jsonify(error="沒有這個主題"), 400
    # 單人練習是「一次吐 10 題」的端點,沒擋的話跑個迴圈就能把整個題庫掃走。
    # 課程題目要先解鎖才給;學生在考坊裡玩完全不會走到這裡。
    if not gate.allow(cat, request):
        return jsonify(error="課程題庫要先解鎖"), 403
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
    # debug=False:上課用。開 debug 會多耗一倍記憶體,而且同網段的人可以透過偵錯畫面
    #             在你的電腦上執行指令。要改程式時把下面那行的 False 改成 True 就好。
    from werkzeug.serving import WSGIRequestHandler
    WSGIRequestHandler.protocol_version = "HTTP/1.1"     # 55 支手機同時連線比較穩
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
else:
    leaderboard.init()      # 用 gunicorn 啟動時
    classroom.init()
