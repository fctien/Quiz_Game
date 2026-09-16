"""
多人同場搶答（類似 Kahoot)

流程：主持人開考場 → 玩家用手機輸入房號加入 → 主持人開始 → 每題同時作答、計時
     → 公布答案與分布、即時排名 → 最後一題分數加倍 → 放榜（滿格、高峰、躍升)

即時推播使用 Server-Sent Events(SSE):純 Flask 就能做，不需要安裝 WebSocket 套件。
每次房間狀態改變，伺服器把「這位使用者該看到的畫面資料」整包推給他，
斷線重連時也能直接拿到最新狀態。
"""
import csv
import io
import json
import random
import secrets
import socket
import threading
import time

from urllib.parse import quote

from flask import Blueprint, Response, jsonify, request

import classroom

bp = Blueprint("mp", __name__)

MAX_PLAYERS = 100
ROOM_TTL = 3 * 60 * 60        # 房間最長保留 3 小時
GRACE = 1.0                   # 網路延遲容忍秒數
COUNTS = (5, 10, 15, 20)
TIMES = (0, 10, 15, 20, 30)      # 0 = 手動,由主持人按鈕控制每題的開始與結束
MANUAL_WINDOW = 30               # 手動模式的速度分以 30 秒為基準
BONUS = 0.5                      # 每題最快答對的人,課堂加分

rooms = {}                    # 房號 -> Room
rooms_lock = threading.Lock()

MAX_TEAMS = 8

# 由 app.py 注入
pick_questions = None
clean_name = None
categories = {}


def init(app, pick, clean, cats):
    global pick_questions, clean_name, categories
    pick_questions, clean_name, categories = pick, clean, cats
    app.register_blueprint(bp)


# ================================================================ 房間
class Room:
    def __init__(self, code, category, count, limit, region=None, mode="solo",
                 teams=None, class_code="", roster=None, unit=None, unit_name=""):
        self.code = code
        self.host_token = secrets.token_urlsafe(16)
        self.category = category
        self.region = region
        self.unit = unit                      # 課程週次,例如 W5
        self.unit_name = unit_name
        self.count = count
        self.limit = limit
        self.mode = mode                      # solo(個人賽) / team(分組賽)
        self.teams = list(teams or [])
        self.class_code = class_code          # 課堂累積積分用
        self.roster = list(roster or [])      # [{"sid","name","team"}]
        self.saved = False
        self.created = self.touched = time.time()
        self.cond = threading.Condition()
        self.version = 0
        self.players = {}         # pid -> dict
        self.closed = False
        self.new_round()

    def roster_of(self, sid):
        return next((r for r in self.roster if r["sid"] == sid), None)

    def new_round(self):
        # 依 25% 簡單 / 50% 中等 / 25% 較難的比例抽題,由易到難排好
        self.questions = pick_questions(self.category, self.count, self.region,
                                        self.unit, only_choice=True)
        self.state = "lobby"      # lobby → question → reveal → … → final
        self.qi = -1
        self.deadline = 0
        self.q_started = 0
        self.answers = {}         # pid -> (choice, elapsed)
        self.reveal = None
        self.prev_rank = {}
        self.round_id = 0
        self.saved = False
        for p in self.players.values():
            p.update(score=0, streak=0, right=0, bonus=0.0, last=None, rank=None, move=0)

    # ---------- 狀態改變時通知所有連線 ----------
    def bump(self):
        with self.cond:
            self.version += 1
            self.touched = time.time()
            self.cond.notify_all()

    # ---------- 流程 ----------
    def is_double(self, i=None):
        i = self.qi if i is None else i
        return i == len(self.questions) - 1 and len(self.questions) > 1

    def start_question(self):
        self.qi += 1
        if self.qi >= len(self.questions):
            return self.finish()
        self.state = "question"
        self.answers = {}
        self.reveal = None
        self.q_started = time.time()
        self.deadline = (self.q_started + self.limit) if self.limit else 0
        self.round_id += 1
        if self.limit:                       # 限時模式:時間到自動公布
            rid = self.round_id
            t = threading.Timer(self.limit + GRACE, self._timeout, args=(rid,))
            t.daemon = True
            t.start()
        self.bump()

    def _timeout(self, rid):
        with rooms_lock:
            if self.round_id == rid and self.state == "question":
                self.do_reveal()

    def answer(self, pid, choice):
        if self.state != "question" or pid in self.answers:
            return False
        elapsed = time.time() - self.q_started
        if self.limit and elapsed > self.limit + GRACE:
            return False
        self.answers[pid] = (choice, elapsed)
        online = [k for k, p in self.players.items() if p["online"]]
        if self.limit and all(k in self.answers for k in online):   # 手動模式一律等主持人結束
            self.do_reveal()
        else:
            self.bump()
        return True

    def ranking(self):
        return sorted(self.players.items(), key=lambda kv: (-kv[1]["score"], kv[1]["joined"]))

    def team_board(self):
        """隊伍排名:以隊員平均分計算,人數不同也公平"""
        if self.mode != "team":
            return []
        rows = {t: {"team": t, "total": 0, "members": 0, "right": 0} for t in self.teams}
        for p in self.players.values():
            t = rows.get(p.get("team"))
            if t:
                t["total"] += p["score"]
                t["members"] += 1
                t["right"] += p["right"]
        for t in rows.values():
            t["avg"] = round(t["total"] / t["members"]) if t["members"] else 0
        return sorted(rows.values(), key=lambda t: (-t["avg"], t["team"]))

    def do_reveal(self):
        q = self.questions[self.qi]
        dist = [0] * len(q["options"])
        fastest = fastest_pid = None
        mult = 2 if self.is_double() else 1
        window = self.limit or MANUAL_WINDOW
        for pid, p in self.players.items():
            choice, elapsed = self.answers.get(pid, (None, None))
            if choice is not None and 0 <= choice < len(dist):
                dist[choice] += 1
            if choice == q["answer"]:
                p["streak"] += 1
                p["right"] += 1
                frac = max(0.0, (window - elapsed) / window)
                bonus = 100 * min(p["streak"] - 1, 5)
                gained = round((500 + 500 * frac + bonus) * mult)
                p["score"] += gained
                p["last"] = {"correct": True, "gained": gained, "bonus": bonus * mult,
                             "choice": choice, "secs": round(elapsed, 1)}
                if fastest is None or elapsed < fastest[1]:
                    fastest = (p["name"], elapsed)
                    fastest_pid = pid
            else:
                p["streak"] = 0
                p["last"] = {"correct": False, "gained": 0, "bonus": 0,
                             "choice": choice, "secs": None if elapsed is None else round(elapsed, 1)}
        if fastest_pid:                       # 最快答對的人得到課堂加分
            self.players[fastest_pid]["bonus"] = round(self.players[fastest_pid]["bonus"] + BONUS, 2)
            self.players[fastest_pid]["last"]["bonus_point"] = BONUS
        ranks = {pid: i + 1 for i, (pid, _) in enumerate(self.ranking())}
        for pid, p in self.players.items():
            p["rank"] = ranks[pid]
            p["move"] = self.prev_rank.get(pid, ranks[pid]) - ranks[pid]   # 正數 = 名次上升
        self.prev_rank = ranks
        self.reveal = {"answer": q["answer"], "dist": dist,
                       "explanation": q.get("explanation", ""), "fun_fact": q.get("fun_fact", ""),
                       "fastest": {"name": fastest[0], "secs": round(fastest[1], 1),
                                   "bonus": BONUS} if fastest else None,
                       "answered": len(self.answers)}
        self.state = "reveal"
        self.bump()

    def finish(self):
        self.state = "final"
        self.bump()

    # ---------- 各角色看到的畫面資料 ----------
    def public_question(self):
        q = self.questions[self.qi]
        return {"index": self.qi, "total": len(self.questions), "question": q["question"],
                "options": q["options"], "category": q.get("category", ""),
                "region": q.get("region", ""), "difficulty": q.get("difficulty", 1),
                "double": self.is_double()}

    def board(self, n=None):
        rows = [{"name": p["name"], "score": p["score"], "move": p.get("move", 0),
                 "online": p["online"], "right": p["right"], "team": p.get("team", ""),
                 "sid": p.get("sid", ""), "bonus": p.get("bonus", 0)} for _, p in self.ranking()]
        return rows[:n] if n else rows

    def view(self, pid):
        v = {"code": self.code, "state": "closed" if self.closed else self.state,
             "topic": self.category,
             "category": categories.get(self.category, {}).get("name", self.category),
             "region": self.region or "", "unit": self.unit or "", "unit_name": self.unit_name,
             "mode": self.mode, "teams": self.teams,
             "class_code": self.class_code, "has_roster": bool(self.roster),
             "players": len(self.players), "limit": self.limit, "total": len(self.questions)}
        if self.state in ("question", "reveal"):
            v["q"] = self.public_question()
            v["remaining"] = max(0.0, round(self.deadline - time.time(), 2)) if self.limit else None
            v["elapsed"] = round(time.time() - self.q_started, 1)
            v["manual"] = not self.limit
            v["answered"] = len(self.answers)
        if self.state == "reveal":
            v["reveal"] = self.reveal
            v["last_q"] = self.qi == len(self.questions) - 1
        if self.mode == "team" and self.state in ("lobby", "reveal", "final"):
            v["team_board"] = self.team_board()
        if pid == "host":
            v["role"] = "host"
            v["roster"] = self.board()
            if self.roster:
                here = {p["sid"] for p in self.players.values() if p.get("sid")}
                v["missing"] = [r["name"] for r in self.roster if r["sid"] not in here]
                v["roster_size"] = len(self.roster)
            if self.state == "reveal":
                v["top"] = self.board(5)
            if self.state == "final":
                v["final"] = self.board()
                v["saved"] = self.saved
        else:
            p = self.players[pid]
            v.update(role="player", name=p["name"], score=p["score"], streak=p["streak"],
                     team=p.get("team", ""), sid=p.get("sid", ""), bonus=p.get("bonus", 0))
            if self.state == "question":
                a = self.answers.get(pid)
                v["my_answer"] = None if a is None else a[0]
            if self.state == "reveal":
                v["result"] = p["last"]
                v["rank"] = p.get("rank")
                v["move"] = p.get("move", 0)
            if self.state == "final":
                rank = next(i + 1 for i, (k, _) in enumerate(self.ranking()) if k == pid)
                v["rank"] = rank
                v["podium"] = self.board(3)
                v["right"] = p["right"]
        return v


# ================================================================ 工具
def _new_code():
    for _ in range(1000):
        code = f"{random.randint(0, 9999):04d}"
        if code not in rooms:
            return code
    raise RuntimeError("考場太多了")


def _cleanup():
    now = time.time()
    for code in [c for c, r in rooms.items() if now - r.touched > ROOM_TTL]:
        r = rooms.pop(code)
        r.closed = True
        r.bump()


def _body():
    return request.get_json(silent=True) or {}


def _host_room(b):
    r = rooms.get(str(b.get("code", "")))
    if not r or r.closed or not secrets.compare_digest(str(b.get("token", "")), r.host_token):
        return None
    return r


def _player(b):
    r = rooms.get(str(b.get("code", "")))
    if not r or r.closed:
        return None, None
    pid = str(b.get("pid", ""))
    p = r.players.get(pid)
    if not p or not secrets.compare_digest(str(b.get("token", "")), p["token"]):
        return r, None
    return r, pid


def _private(ip):
    return (ip.startswith("192.168.") or ip.startswith("10.")
            or (ip.startswith("172.") and ip.split(".")[1].isdigit() and 16 <= int(ip.split(".")[1]) <= 31))


def lan_ip():
    """這台電腦對外的主要區網 IP"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def lan_ips():
    """
    列出這台電腦所有可能的區網 IP。
    筆電常同時有 Wi-Fi、有線網路、VPN 等多張網卡，自動挑的那個不一定是手機連得到的，
    所以主持台會把全部列出來讓老師切換。
    """
    ips = []
    main = lan_ip()
    if _private(main):
        ips.append(main)
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if _private(ip) and ip not in ips:
                ips.append(ip)
    except OSError:
        pass
    return ips or [main]


def err(msg, code=400):
    return jsonify(error=msg), code


# ================================================================ 主持人 API
@bp.post("/api/mp/create")
def create():
    b = _body()
    cat = b.get("category", "mix")
    if cat not in categories:
        return err("沒有這個主題")
    count, limit = int(b.get("count", 10)), int(b.get("time", 20))
    if count not in COUNTS or limit not in TIMES:
        return err("題數或秒數不在可選範圍內")
    region = b.get("region") or None
    unit = b.get("unit") or None
    unit_name = str(b.get("unit_name", ""))[:40]
    mode = "team" if b.get("mode") == "team" else "solo"

    # ---- 班級(選填):有填才會累積積分 ----
    class_code = classroom.clean_code(b.get("class_code", ""))
    admin_code = None
    roster = []
    if class_code:
        cls = classroom.get(class_code)
        if cls:
            if not classroom.check(class_code, b.get("admin_code", "")):
                return err("這個班級已經存在,請輸入管理碼", 403)
            roster = classroom.get_roster(class_code)
        else:
            admin_code = classroom.create(class_code)          # 新班級,產生管理碼
    # ---- 分組名單(選填):上傳後覆蓋班級名單 ----
    if b.get("roster_text"):
        roster = classroom.parse_roster(b["roster_text"])
        if not roster:
            return err("名單讀不到資料,請確認格式為:學號,姓名,組別")
        if class_code:
            classroom.set_roster(class_code, roster)
    # ---- 隊伍 ----
    teams = []
    if mode == "team":
        teams = classroom.teams_of(roster)
        if not teams:
            n = max(2, min(MAX_TEAMS, int(b.get("team_count", 4))))
            teams = [f"第{'一二三四五六七八'[i]}組" for i in range(n)]

    with rooms_lock:
        _cleanup()
        code = _new_code()
        r = Room(code, cat, count, limit, region, mode, teams, class_code, roster, unit, unit_name)
        if not r.questions:
            return err("這個主題目前沒有可用的題目", 503)
        rooms[code] = r
    # 加入連結:自己的電腦要換成區網 IP,手機才連得到;部署在雲端時直接用網域
    host = request.host
    hostname = host.split(":")[0]
    port = host.split(":")[1] if ":" in host else ("443" if request.scheme == "https" else "80")
    local = hostname in ("127.0.0.1", "localhost") or _private(hostname)
    if hostname in ("127.0.0.1", "localhost"):
        host = f"{lan_ip()}:{port}"
    urls = [f"{request.scheme}://{host}/play?code={code}"]
    if local:                                  # 只有區網模式才需要列出其他網卡
        for ip in lan_ips():
            u = f"{request.scheme}://{ip}:{port}/play?code={code}"
            if u not in urls:
                urls.append(u)
    return jsonify(code=code, token=r.host_token, join_url=urls[0], join_urls=urls,
                   total=len(r.questions), teams=teams, roster_size=len(roster),
                   class_code=class_code, admin_code=admin_code)


@bp.post("/api/mp/roster")
def upload_roster():
    """開考場之後再上傳/更換分組名單"""
    b = _body()
    with rooms_lock:
        r = _host_room(b)
        if not r:
            return err("考場不存在或你不是主持人", 403)
        if r.state != "lobby":
            return err("遊戲已經開始,不能換名單")
        rows = classroom.parse_roster(b.get("roster_text", ""))
        if not rows:
            return err("名單讀不到資料,請確認格式為:學號,姓名,組別")
        r.roster = rows
        if r.class_code:
            classroom.set_roster(r.class_code, rows)
        if r.mode == "team":
            teams = classroom.teams_of(rows)
            if teams:
                r.teams = teams
                for p in r.players.values():                  # 已加入的人依名單重新歸隊
                    m = r.roster_of(p.get("sid", ""))
                    if m and m["team"]:
                        p["team"] = m["team"]
        r.bump()
    return jsonify(ok=True, teams=r.teams, roster_size=len(rows))


@bp.get("/api/mp/export")
def export_game():
    """匯出這一場的成績 CSV(不必存到班級也能下載)"""
    r = rooms.get(request.args.get("code", ""))
    if not r or not secrets.compare_digest(request.args.get("token", ""), r.host_token):
        return err("考場不存在或你不是主持人", 403)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["名次", "學號", "姓名", "組別", "分數", "答對題數", "總題數", "課堂加分"])
    for i, (_, p) in enumerate(r.ranking(), 1):
        w.writerow([i, p.get("sid", ""), p["name"], p.get("team", ""), p["score"],
                    p["right"], len(r.questions), p.get("bonus", 0)])
    name = f"{r.class_code or 'PULSE'}-{time.strftime('%m%d')}-成績.csv"
    return Response("\ufeff" + out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition":
                             f"attachment; filename=quiz-scores.csv; filename*=UTF-8''{quote(name)}"})


@bp.post("/api/mp/save_class")
def save_class():
    """把這一場的成績存進班級累積積分"""
    b = _body()
    with rooms_lock:
        r = _host_room(b)
        if not r:
            return err("考場不存在或你不是主持人", 403)
        if not r.class_code:
            return err("這場沒有設定班級代碼")
        if r.state != "final":
            return err("等放榜後才能存入")
        if r.saved:
            return err("這場已經存過了")
        results = [{"sid": p.get("sid") or p["name"], "name": p["name"], "team": p.get("team", ""),
                    "points": p["score"], "correct": p["right"], "answered": len(r.questions),
                    "bonus": p.get("bonus", 0)}
                   for p in r.players.values()]
        topic = r.category + (f"・{r.unit_name}" if r.unit_name else "")
        classroom.save_game(r.class_code, topic, results, len(r.questions))
        r.saved = True
        r.bump()
    return jsonify(ok=True, saved=len(results))


@bp.post("/api/mp/start")
def start():
    b = _body()
    with rooms_lock:
        r = _host_room(b)
        if not r:
            return err("考場不存在或你不是主持人", 403)
        if r.state != "lobby":
            return err("遊戲已經開始了")
        if not r.players:
            return err("還沒有玩家加入")
        if r.mode == "team":
            no_team = [p["name"] for p in r.players.values() if not p.get("team")]
            if no_team:
                return err("還有人沒選隊:" + "、".join(no_team[:5]))
        r.start_question()
    return jsonify(ok=True)


@bp.post("/api/mp/reveal")
def reveal():
    with rooms_lock:
        r = _host_room(_body())
        if not r:
            return err("考場不存在或你不是主持人", 403)
        if r.state == "question":
            r.do_reveal()
    return jsonify(ok=True)


@bp.post("/api/mp/next")
def next_q():
    with rooms_lock:
        r = _host_room(_body())
        if not r:
            return err("考場不存在或你不是主持人", 403)
        if r.state == "reveal":
            r.start_question()
    return jsonify(ok=True)


@bp.post("/api/mp/again")
def again():
    with rooms_lock:
        r = _host_room(_body())
        if not r:
            return err("考場不存在或你不是主持人", 403)
        r.new_round()
        r.bump()
    return jsonify(ok=True)


@bp.post("/api/mp/close")
def close():
    with rooms_lock:
        r = _host_room(_body())
        if r:
            r.closed = True
            rooms.pop(r.code, None)
            r.bump()
    return jsonify(ok=True)


# ================================================================ 玩家 API
@bp.get("/api/health")
def health():
    """手機開這個網址如果看得到 ok,就表示連得到老師的電腦"""
    return jsonify(ok=True, ips=lan_ips(), rooms=len(rooms), time=time.strftime("%H:%M:%S"))


@bp.get("/api/mp/info")
def info():
    r = rooms.get(request.args.get("code", ""))
    if not r or r.closed:
        return jsonify(exists=False)
    return jsonify(exists=True, state=r.state, players=len(r.players), mode=r.mode,
                   teams=r.teams, has_roster=bool(r.roster), needs_sid=bool(r.roster or r.class_code),
                   category=categories.get(r.category, {}).get("name", r.category))


@bp.post("/api/mp/join")
def join():
    b = _body()
    with rooms_lock:
        r = rooms.get(str(b.get("code", "")))
        if not r or r.closed:
            return err("找不到這個房號,請再確認一次", 404)
        # 斷線重連:帶著原本的 pid + token 就回到原位
        _, pid = _player(b)
        if pid:
            p = r.players[pid]
            return jsonify(pid=pid, token=p["token"], name=p["name"], team=p.get("team", ""))
        sid = classroom.clean_id(b.get("sid", ""))
        name = clean_name(b.get("name", ""))
        team = str(b.get("team", ""))[:10]
        if r.roster:                                   # 有名單:認學號,姓名與組別自動帶出
            if not sid:
                return err("請輸入學號")
            m = r.roster_of(sid)
            if not m:
                return err("名單上沒有這個學號,請確認或洽老師", 403)
            name, team = m["name"], m["team"] or team
        elif r.class_code and not sid:                 # 課堂但沒名單:至少要學號才對得上人
            return err("請輸入學號")
        if not name:
            return err("請輸入 1 到 12 個字的姓名或暱稱")
        if any(p["name"] == name for p in r.players.values()):
            return err("這個名字已經有人用了,請加上學號後兩碼")
        if sid and any(p.get("sid") == sid for p in r.players.values()):
            return err("這個學號已經加入了,如果是斷線請重新整理原本的頁面")
        if len(r.players) >= MAX_PLAYERS:
            return err("考場已滿")
        if r.mode == "team" and team not in r.teams:
            team = ""                                   # 之後在選隊畫面挑
        pid = secrets.token_hex(4)
        r.players[pid] = {"name": name, "sid": sid, "team": team, "token": secrets.token_urlsafe(12),
                          "score": 0, "streak": 0, "right": 0, "bonus": 0.0, "last": None,
                          "online": False, "conns": 0, "joined": time.time()}
        r.bump()
    return jsonify(pid=pid, token=r.players[pid]["token"], name=name, team=r.players[pid]["team"])


@bp.post("/api/mp/team")
def choose_team():
    """分組賽:玩家自己選隊(名單已指定組別的話不能改)"""
    b = _body()
    with rooms_lock:
        r, pid = _player(b)
        if not pid:
            return err("請重新加入考場", 403)
        if r.mode != "team":
            return err("這場不是分組賽")
        if r.state != "lobby":
            return err("遊戲已經開始,不能換隊")
        if r.roster_of(r.players[pid].get("sid", "")) and r.roster_of(r.players[pid]["sid"])["team"]:
            return err("你的組別由名單決定")
        team = str(b.get("team", ""))
        if team not in r.teams:
            return err("沒有這一隊")
        r.players[pid]["team"] = team
        r.bump()
    return jsonify(ok=True, team=team)


@bp.post("/api/mp/answer")
def answer():
    b = _body()
    with rooms_lock:
        r, pid = _player(b)
        if not pid:
            return err("請重新加入考場", 403)
        choice = b.get("choice")
        if not isinstance(choice, int):
            return err("答案格式錯誤")
        if int(b.get("index", -1)) != r.qi:
            return err("這題已經結束了", 409)
        ok = r.answer(pid, choice)
    return jsonify(ok=ok)


# ================================================================ 即時推播
@bp.get("/api/mp/stream")
def stream():
    code = request.args.get("code", "")
    pid = request.args.get("pid", "")
    token = request.args.get("token", "")
    r = rooms.get(code)
    if not r:
        return err("考場不存在", 404)
    if pid == "host":
        if not secrets.compare_digest(token, r.host_token):
            return err("你不是主持人", 403)
    elif pid not in r.players or not secrets.compare_digest(token, r.players[pid]["token"]):
        return err("請重新加入考場", 403)

    def gen():
        last = -1
        if pid != "host":
            p = r.players[pid]
            p["conns"] += 1                 # 同一人可能重新整理，連線數歸零才算離線
            p["online"] = True
            r.bump()
        try:
            while True:
                with r.cond:
                    if r.version == last:
                        r.cond.wait(timeout=15)
                    changed = r.version != last
                    last = r.version
                if not changed:
                    yield ": ping\n\n"          # 心跳，避免連線被中間設備切斷
                    continue
                with rooms_lock:
                    data = r.view(pid)
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                if r.closed:
                    return
        finally:
            if pid != "host" and pid in r.players:
                p = r.players[pid]
                p["conns"] = max(0, p["conns"] - 1)
                p["online"] = p["conns"] > 0
                r.bump()

    return Response(gen(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
