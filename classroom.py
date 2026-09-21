"""
課堂模式:班級、分組名單、累積積分

- 班級:用「班級代碼」識別(例如 程式設計-115-1),第一次建立時會產生一組管理碼,
  之後要開房存分、或查看累積積分,都要有這組管理碼。
- 分組名單:老師上傳 CSV(學號,姓名,組別),存在班級裡,下次開房自動帶出。
  學生加入時只要輸入學號,系統自動帶出姓名與組別。
- 累積積分:每場結束由老師按「存入班級積分」,分數累加到該班級,可匯出 CSV 當期末加分依據。
"""
import csv
import io
import json
import os
import re
import secrets
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).parent / "leaderboard.db"
ADMIN_LOG = Path(__file__).parent / "班級管理碼.txt"   # 管理碼備份,忘記時可以來這裡翻


def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init():
    with conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS classes (
            code TEXT PRIMARY KEY,
            admin_code TEXT NOT NULL,
            roster TEXT NOT NULL DEFAULT '[]',
            created REAL NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS class_points (
            class_code TEXT NOT NULL,
            student_id TEXT NOT NULL,
            name TEXT NOT NULL,
            team TEXT NOT NULL DEFAULT '',
            points INTEGER NOT NULL DEFAULT 0,
            correct INTEGER NOT NULL DEFAULT 0,
            answered INTEGER NOT NULL DEFAULT 0,
            games INTEGER NOT NULL DEFAULT 0,
            bonus REAL NOT NULL DEFAULT 0,
            updated REAL NOT NULL,
            PRIMARY KEY (class_code, student_id))""")
        cols = [r[1] for r in c.execute("PRAGMA table_info(class_points)")]
        if "bonus" not in cols:              # 舊資料庫升級
            c.execute("ALTER TABLE class_points ADD COLUMN bonus REAL NOT NULL DEFAULT 0")
        c.execute("""CREATE TABLE IF NOT EXISTS class_games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_code TEXT NOT NULL,
            topic TEXT NOT NULL,
            players INTEGER NOT NULL,
            questions INTEGER NOT NULL,
            played REAL NOT NULL)""")


def clean_code(s):
    """班級代碼:中英數與 - _ ,最多 30 字"""
    return re.sub(r"[^\w一-鿿\-]", "", str(s or ""))[:30]


def clean_id(s):
    return re.sub(r"[^\w\-]", "", str(s or ""))[:20]


def clean_admin(s):
    """老師自訂的管理碼:只留英數,轉大寫,最多 12 字。太短(或空的)就當作沒設"""
    return re.sub(r"[^A-Za-z0-9]", "", str(s or "")).upper()[:12]


def master_code():
    """萬用鑰匙:設在環境變數 MASTER_CODE,任何班級都能用它通過驗證。
    至少 6 碼才算數,免得不小心設成空字串就整個門戶洞開。"""
    m = str(os.environ.get("MASTER_CODE", "")).strip().upper()
    return m if len(m) >= 6 else ""


def _log_admin(code, admin):
    """管理碼在畫面上只顯示一次,忘了很麻煩,所以同時在資料庫旁邊留一份純文字備份"""
    try:
        with open(ADMIN_LOG, "a", encoding="utf-8") as f:
            f.write("%s\t%s\t%s\n" % (time.strftime("%Y-%m-%d %H:%M"), code, admin))
    except Exception:
        pass        # 雲端的檔案系統可能是唯讀的,寫不進去就算了,不能害開班失敗


def get(code):
    with conn() as c:
        r = c.execute("SELECT * FROM classes WHERE code = ?", (code,)).fetchone()
    return dict(r) if r else None


def create(code, admin=None):
    """建立班級,回傳管理碼。admin 留空就隨機產生六碼,填了就用老師自己取的"""
    admin = clean_admin(admin)
    if len(admin) < 3:
        admin = secrets.token_hex(3).upper()      # 例如 A3F9C1
    with conn() as c:
        c.execute("INSERT INTO classes(code, admin_code, roster, created) VALUES (?,?,'[]',?)",
                  (code, admin, time.time()))
    _log_admin(code, admin)
    return admin


def check(code, admin_code):
    cls = get(code)
    if not cls:
        return False
    given = str(admin_code or "").upper().strip()
    try:    # 老師把管理碼打成中文時,compare_digest 會丟例外,不能讓伺服器噴 500
        m = master_code()
        if m and secrets.compare_digest(m.encode("utf-8"), given.encode("utf-8")):
            return True                 # 萬用鑰匙:忘記管理碼時的備用入口
        return secrets.compare_digest(cls["admin_code"].encode("utf-8"),
                                      given.encode("utf-8"))
    except Exception:
        return False


def recover(master):
    """忘記管理碼:用萬用鑰匙把所有班級的管理碼查出來。鑰匙沒設或不對都回 None"""
    m = master_code()
    if not m:
        return None
    try:
        if not secrets.compare_digest(m.encode("utf-8"),
                                      str(master or "").upper().strip().encode("utf-8")):
            return None
    except Exception:
        return None
    with conn() as c:
        return [{"code": r["code"], "admin_code": r["admin_code"], "created": r["created"]}
                for r in c.execute("SELECT code, admin_code, created FROM classes ORDER BY created DESC")]


# ---------------------------------------------------------------- 分組名單
def parse_roster(text):
    """
    解析 CSV / TSV 名單。欄位順序:學號, 姓名, 組別(組別可留空)
    有標題列(含「學號」或「id」)會自動略過。
    回傳 [{"sid": ..., "name": ..., "team": ...}, ...]
    """
    text = text.replace("﻿", "")
    delim = "\t" if text.count("\t") > text.count(",") else ","
    rows, seen = [], set()
    for i, row in enumerate(csv.reader(io.StringIO(text), delimiter=delim)):
        cells = [c.strip() for c in row if c is not None]
        if not cells or not any(cells):
            continue
        if i == 0 and any(k in cells[0] for k in ("學號", "id", "ID", "座號")):
            continue
        sid = clean_id(cells[0])
        if not sid or sid in seen:
            continue
        seen.add(sid)
        rows.append({"sid": sid,
                     "name": (cells[1][:12] if len(cells) > 1 and cells[1] else sid),
                     "team": (cells[2][:10] if len(cells) > 2 else "")})
    return rows


def set_roster(code, rows):
    with conn() as c:
        c.execute("UPDATE classes SET roster = ? WHERE code = ?",
                  (json.dumps(rows, ensure_ascii=False), code))


def get_roster(code):
    cls = get(code)
    return json.loads(cls["roster"]) if cls else []


def teams_of(roster):
    """名單裡出現過的組別,保持原順序"""
    out = []
    for r in roster:
        if r["team"] and r["team"] not in out:
            out.append(r["team"])
    return out


# ---------------------------------------------------------------- 累積積分
def save_game(code, topic, results, questions):
    """results: [{"sid","name","team","points","correct","answered"}, ...]"""
    now = time.time()
    with conn() as c:
        for r in results:
            c.execute("""INSERT INTO class_points(class_code, student_id, name, team, points, correct, answered, games, bonus, updated)
                         VALUES (?,?,?,?,?,?,?,1,?,?)
                         ON CONFLICT(class_code, student_id) DO UPDATE SET
                           name = excluded.name,
                           team = CASE WHEN excluded.team != '' THEN excluded.team ELSE class_points.team END,
                           points = class_points.points + excluded.points,
                           correct = class_points.correct + excluded.correct,
                           answered = class_points.answered + excluded.answered,
                           games = class_points.games + 1,
                           bonus = class_points.bonus + excluded.bonus,
                           updated = excluded.updated""",
                      (code, r["sid"], r["name"], r.get("team", ""), int(r["points"]),
                       int(r["correct"]), int(r["answered"]), float(r.get("bonus", 0)), now))
        c.execute("INSERT INTO class_games(class_code, topic, players, questions, played) VALUES (?,?,?,?,?)",
                  (code, topic, len(results), questions, now))


def summary(code):
    with conn() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT student_id, name, team, points, correct, answered, games, bonus, updated "
            "FROM class_points WHERE class_code = ? ORDER BY bonus DESC, points DESC, name ASC", (code,))]
        games = [dict(r) for r in c.execute(
            "SELECT topic, players, questions, played FROM class_games WHERE class_code = ? "
            "ORDER BY played DESC LIMIT 20", (code,))]
    teams = {}
    for r in rows:
        t = teams.setdefault(r["team"] or "未分組", {"team": r["team"] or "未分組", "points": 0, "members": 0, "bonus": 0})
        t["points"] += r["points"]
        t["bonus"] = round(t["bonus"] + r["bonus"], 2)
        t["members"] += 1
    for t in teams.values():
        t["avg"] = round(t["points"] / max(1, t["members"]))
    return {"students": rows,
            "teams": sorted(teams.values(), key=lambda t: -t["avg"]),
            "games": games}


def export_csv(code):
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["學號", "姓名", "組別", "課堂加分", "累積積分", "答對題數", "作答題數", "參加場次"])
    for r in summary(code)["students"]:
        w.writerow([r["student_id"], r["name"], r["team"], r["bonus"], r["points"],
                    r["correct"], r["answered"], r["games"]])
    return "﻿" + out.getvalue()          # 加 BOM,Excel 開啟才不會亂碼


def reset(code):
    with conn() as c:
        c.execute("DELETE FROM class_points WHERE class_code = ?", (code,))
        c.execute("DELETE FROM class_games WHERE class_code = ?", (code,))
