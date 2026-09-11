"""
排行榜:SQLite 儲存(單一檔案 leaderboard.db,不用另外架資料庫)

- 本週榜:依 ISO 週(週一到週日)分開
- 總榜:全部時間
- 同分時,較早達成的排前面
"""
import re
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "leaderboard.db"
TW = timezone(timedelta(hours=8))           # 以台灣時間切週

# 不雅字詞可自行擴充
BLOCKED = ["幹你", "操你", "fuck", "shit"]


def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init():
    with conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            score INTEGER NOT NULL,
            correct INTEGER NOT NULL,
            answered INTEGER NOT NULL,
            best_streak INTEGER NOT NULL,
            week TEXT NOT NULL,
            created REAL NOT NULL)""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_rank ON scores(category, week, score DESC)")


def week_key(ts=None):
    d = datetime.fromtimestamp(ts or time.time(), TW)
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def clean_name(name):
    name = re.sub(r"[\x00-\x1f<>&\"']", "", str(name)).strip()
    name = re.sub(r"\s+", " ", name)[:12]
    if any(b in name.lower() for b in BLOCKED):
        return ""
    return name


def add_score(name, category, score, right, answered, best_streak):
    now = time.time()
    with conn() as c:
        cur = c.execute(
            "INSERT INTO scores(name, category, score, correct, answered, best_streak, week, created) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (name, category, score, right, answered, best_streak, week_key(now), now))
        return cur.lastrowid


def _where(category, period):
    cond, args = [], []
    if category != "all":
        cond.append("category = ?"); args.append(category)
    if period == "week":
        cond.append("week = ?"); args.append(week_key())
    return (" WHERE " + " AND ".join(cond)) if cond else "", args


def top(category="all", period="week", limit=20):
    where, args = _where(category, period)
    with conn() as c:
        rows = c.execute(
            f"SELECT id, name, category, score, correct, answered, best_streak, created "
            f"FROM scores{where} ORDER BY score DESC, created ASC LIMIT ?", args + [limit]).fetchall()
    return [dict(r) for r in rows]


def rank_of(row_id, category, period):
    """某筆成績在「該分類」的名次(1 起算)"""
    with conn() as c:
        me = c.execute("SELECT score, created, week FROM scores WHERE id = ?", (row_id,)).fetchone()
        if not me:
            return None
        where, args = _where(category, period)
        where = where + (" AND " if where else " WHERE ") + "(score > ? OR (score = ? AND created < ?))"
        n = c.execute(f"SELECT COUNT(*) FROM scores{where}",
                      args + [me["score"], me["score"], me["created"]]).fetchone()[0]
    return n + 1
