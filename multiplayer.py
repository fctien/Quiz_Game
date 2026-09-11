"""
多人同場搶答（類似 Kahoot)

流程：主持人開房 → 玩家用手機輸入房號加入 → 主持人開始 → 每題同時作答、計時
     → 公布答案與分布、即時排名 → 最後一題分數加倍 → 放榜（狀元、榜眼、探花)

即時推播使用 Server-Sent Events(SSE):純 Flask 就能做，不需要安裝 WebSocket 套件。
每次房間狀態改變，伺服器把「這位使用者該看到的畫面資料」整包推給他，
斷線重連時也能直接拿到最新狀態。
"""
import json
import random
import secrets
import socket
import threading
import time

from flask import Blueprint, Response, jsonify, request

bp = Blueprint("mp", __name__)

MAX_PLAYERS = 100
ROOM_TTL = 3 * 60 * 60        # 房間最長保留 3 小時
GRACE = 1.0                   # 網路延遲容忍秒數
COUNTS = (5, 10, 15, 20)
TIMES = (10, 15, 20, 30)

rooms = {}                    # 房號 -> Room
rooms_lock = threading.Lock()

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
    def __init__(self, code, category, count, limit):
        self.code = code
        self.host_token = secrets.token_urlsafe(16)
        self.category = category
        self.count = count
        self.limit = limit
        self.created = self.touched = time.time()
        self.cond = threading.Condition()
        self.version = 0
        self.players = {}         # pid -> dict
        self.closed = False
        self.new_round()

    def new_round(self):
        pool = [q for q in pick_questions(self.category, 200) if q["type"] == "choice"]
        qs = pool[:self.count]
        qs.sort(key=lambda q: q.get("difficulty", 2))
        self.questions = qs
        self.state = "lobby"      # lobby → question → reveal → … → final
        self.qi = -1
        self.deadline = 0
        self.q_started = 0
        self.answers = {}         # pid -> (choice, elapsed)
        self.reveal = None
        self.prev_rank = {}
        self.round_id = 0
        for p in self.players.values():
            p.update(score=0, streak=0, right=0, last=None)

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
        self.deadline = self.q_started + self.limit
        self.round_id += 1
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
        if elapsed > self.limit + GRACE:
            return False
        self.answers[pid] = (choice, elapsed)
        online = [k for k, p in self.players.items() if p["online"]]
        if all(k in self.answers for k in online):
            self.do_reveal()
        else:
            self.bump()
        return True

    def ranking(self):
        return sorted(self.players.items(), key=lambda kv: (-kv[1]["score"], kv[1]["joined"]))

    def do_reveal(self):
        q = self.questions[self.qi]
        dist = [0] * len(q["options"])
        fastest = None
        mult = 2 if self.is_double() else 1
        for pid, p in self.players.items():
            choice, elapsed = self.answers.get(pid, (None, None))
            if choice is not None and 0 <= choice < len(dist):
                dist[choice] += 1
            if choice == q["answer"]:
                p["streak"] += 1
                p["right"] += 1
                frac = max(0.0, (self.limit - elapsed) / self.limit)
                bonus = 100 * min(p["streak"] - 1, 5)
                gained = round((500 + 500 * frac + bonus) * mult)
                p["score"] += gained
                p["last"] = {"correct": True, "gained": gained, "bonus": bonus * mult,
                             "choice": choice, "secs": round(elapsed, 1)}
                if fastest is None or elapsed < fastest[1]:
                    fastest = (p["name"], elapsed)
            else:
                p["streak"] = 0
                p["last"] = {"correct": False, "gained": 0, "bonus": 0,
                             "choice": choice, "secs": None if elapsed is None else round(elapsed, 1)}
        ranks = {pid: i + 1 for i, (pid, _) in enumerate(self.ranking())}
        for pid, p in self.players.items():
            p["rank"] = ranks[pid]
            p["move"] = self.prev_rank.get(pid, ranks[pid]) - ranks[pid]   # 正數 = 名次上升
        self.prev_rank = ranks
        self.reveal = {"answer": q["answer"], "dist": dist,
                       "explanation": q.get("explanation", ""), "fun_fact": q.get("fun_fact", ""),
                       "fastest": {"name": fastest[0], "secs": round(fastest[1], 1)} if fastest else None,
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
                 "online": p["online"], "right": p["right"]} for _, p in self.ranking()]
        return rows[:n] if n else rows

    def view(self, pid):
        v = {"code": self.code, "state": "closed" if self.closed else self.state,
             "category": categories.get(self.category, {}).get("name", self.category),
             "players": len(self.players), "limit": self.limit, "total": len(self.questions)}
        if self.state in ("question", "reveal"):
            v["q"] = self.public_question()
            v["remaining"] = max(0.0, round(self.deadline - time.time(), 2))
            v["answered"] = len(self.answers)
        if self.state == "reveal":
            v["reveal"] = self.reveal
            v["last_q"] = self.qi == len(self.questions) - 1
        if pid == "host":
            v["role"] = "host"
            v["roster"] = self.board()
            if self.state == "reveal":
                v["top"] = self.board(5)
            if self.state == "final":
                v["final"] = self.board()
        else:
            p = self.players[pid]
            v.update(role="player", name=p["name"], score=p["score"], streak=p["streak"])
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
    raise RuntimeError("房間太多了")


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


def lan_ip():
    """找出這台電腦在區網的 IP，讓手機掃 QR code 就能連進來"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def err(msg, code=400):
    return jsonify(error=msg), code


# ================================================================ 主持人 API
@bp.post("/api/mp/create")
def create():
    b = _body()
    cat = b.get("category", "mix")
    if cat not in categories:
        return err("沒有這個分類")
    count = int(b.get("count", 10))
    limit = int(b.get("time", 20))
    if count not in COUNTS or limit not in TIMES:
        return err("題數或秒數不在可選範圍內")
    with rooms_lock:
        _cleanup()
        code = _new_code()
        r = Room(code, cat, count, limit)
        if not r.questions:
            return err("這個分類目前沒有可用的題目", 503)
        rooms[code] = r
    # 加入連結：主持人若用 localhost 開，改用區網 IP，手機才連得到
    host = request.host
    if host.split(":")[0] in ("127.0.0.1", "localhost"):
        port = host.split(":")[1] if ":" in host else "80"
        host = f"{lan_ip()}:{port}"
    return jsonify(code=code, token=r.host_token, join_url=f"{request.scheme}://{host}/play?code={code}",
                   total=len(r.questions))


@bp.post("/api/mp/start")
def start():
    b = _body()
    with rooms_lock:
        r = _host_room(b)
        if not r:
            return err("房間不存在或你不是主持人", 403)
        if r.state != "lobby":
            return err("遊戲已經開始了")
        if not r.players:
            return err("還沒有玩家加入")
        r.start_question()
    return jsonify(ok=True)


@bp.post("/api/mp/reveal")
def reveal():
    with rooms_lock:
        r = _host_room(_body())
        if not r:
            return err("房間不存在或你不是主持人", 403)
        if r.state == "question":
            r.do_reveal()
    return jsonify(ok=True)


@bp.post("/api/mp/next")
def next_q():
    with rooms_lock:
        r = _host_room(_body())
        if not r:
            return err("房間不存在或你不是主持人", 403)
        if r.state == "reveal":
            r.start_question()
    return jsonify(ok=True)


@bp.post("/api/mp/again")
def again():
    with rooms_lock:
        r = _host_room(_body())
        if not r:
            return err("房間不存在或你不是主持人", 403)
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
@bp.get("/api/mp/info")
def info():
    r = rooms.get(request.args.get("code", ""))
    if not r or r.closed:
        return jsonify(exists=False)
    return jsonify(exists=True, state=r.state, players=len(r.players),
                   category=categories.get(r.category, {}).get("name", r.category))


@bp.post("/api/mp/join")
def join():
    b = _body()
    with rooms_lock:
        r = rooms.get(str(b.get("code", "")))
        if not r or r.closed:
            return err("找不到這個房號，請再確認一次", 404)
        # 斷線重連：帶著原本的 pid + token 就回到原位
        rr, pid = _player(b)
        if pid:
            return jsonify(pid=pid, token=r.players[pid]["token"], name=r.players[pid]["name"])
        name = clean_name(b.get("name", ""))
        if not name:
            return err("請輸入 1 到 12 個字的暱稱")
        if any(p["name"] == name for p in r.players.values()):
            return err("這個暱稱已經有人用了，換一個吧")
        if len(r.players) >= MAX_PLAYERS:
            return err("房間已滿")
        pid = secrets.token_hex(4)
        r.players[pid] = {"name": name, "token": secrets.token_urlsafe(12), "score": 0, "streak": 0,
                          "right": 0, "last": None, "online": False, "conns": 0, "joined": time.time()}
        r.bump()
    return jsonify(pid=pid, token=r.players[pid]["token"], name=name)


@bp.post("/api/mp/answer")
def answer():
    b = _body()
    with rooms_lock:
        r, pid = _player(b)
        if not pid:
            return err("請重新加入房間", 403)
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
        return err("房間不存在", 404)
    if pid == "host":
        if not secrets.compare_digest(token, r.host_token):
            return err("你不是主持人", 403)
    elif pid not in r.players or not secrets.compare_digest(token, r.players[pid]["token"]):
        return err("請重新加入房間", 403)

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
