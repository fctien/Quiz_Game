# -*- coding: utf-8 -*-
"""課程題庫門禁的回歸測試。

重點不是「有沒有回 403」,而是「學生到底還撈不撈得到題目」。
所以測試裡有一支真的會去撈的 scrape(),改之前它撈得到,改之後應該撈不到。
"""
import json, os, pathlib, subprocess, sys, time, urllib.error, urllib.request, http.cookiejar

ROOT = pathlib.Path(__file__).resolve().parent.parent
HERE = str(ROOT)
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 5099
BASE = f"http://127.0.0.1:{PORT}"
CODE = "TEST-UNLOCK-9137"

ok = fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1;  print(f"  [ok]   {name}")
    else:    fail += 1; print(f"  [FAIL] {name}  {extra}")

def client():
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

def call(op, method, path, data=None):
    req = urllib.request.Request(BASE + path, method=method)
    body = None
    if data is not None:
        body = json.dumps(data).encode(); req.add_header("Content-Type", "application/json")
    try:
        with op.open(req, body, timeout=20) as r:
            return r.status, json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        try:    return e.code, json.loads(e.read().decode() or "null")
        except Exception: return e.code, None
    except Exception:
        return 0, None

def boot(env_extra):
    env = dict(os.environ); env.pop("RENDER", None); env.pop("TEACH_CODE", None)
    env.update(env_extra); env["PORT"] = str(PORT)
    p = subprocess.Popen([sys.executable,
                          str(ROOT / "tests" / "_serve.py"),
                          str(PORT)], cwd=HERE, env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    op = client()
    for _ in range(80):
        s, _d = call(op, "GET", "/api/health")
        if s == 200: return p
        time.sleep(0.5)
    p.kill(); raise SystemExit("伺服器起不來")

def scrape(op, topic, rounds=6):
    """模擬學生寫的撈題腳本:開局拿題 → 送答案換正解。回傳 (題幹數, 拿到答案數)"""
    stems, answers = set(), 0
    for _ in range(rounds):
        s, d = call(op, "POST", "/api/start", {"category": topic})
        if s != 200 or not d: break
        sid = d["session"]
        for i, q in enumerate(d["questions"]):
            stems.add(q["question"])
            call(op, "POST", "/api/show", {"session": sid, "index": i})
            s2, r = call(op, "POST", "/api/answer",
                         {"session": sid, "index": i, "answer": 0})
            if s2 == 200 and r and isinstance(r.get("answer"), (int, list)): answers += 1
    return len(stems), answers


# ============ 情境 1:雲端 + 有設 TEACH_CODE(正式上線的樣子) ============
print("\n情境 1　雲端 + 有設 TEACH_CODE")
srv = boot({"RENDER": "true", "TEACH_CODE": CODE})
try:
    stu = client()                                   # 學生:沒有解鎖

    s, cats = call(stu, "GET", "/api/categories")
    keys = [c["key"] for c in cats]
    check("課程主題不出現在主題清單", not any(k in keys for k in
          ("python", "pytorch", "ai", "vba", "emba")), keys)
    check("通識主題照常出現", "geo" in keys and "human" in keys, keys)
    check("每個主題都帶 group", all("group" in c for c in cats))

    s, _ = call(stu, "GET", "/api/units?topic=ai")
    check("課程主題的單元清單被清空", _ == [], _)

    s, d = call(stu, "POST", "/api/start", {"category": "ai"})
    check("單人練習拿課程題目 → 403", s == 403, f"得到 {s}")

    s, d = call(stu, "POST", "/api/mp/create", {"category": "ai", "count": 10, "time": 20})
    check("自己開課程考坊 → 403", s == 403, f"得到 {s}")

    got, ans = scrape(stu, "ai")
    check("撈題腳本一題都撈不到", got == 0 and ans == 0, f"題幹 {got} 答案 {ans}")

    s, d = call(stu, "POST", "/api/start", {"category": "geo"})
    check("通識題目學生照樣玩得到", s == 200, f"得到 {s}")

    # --- 老師解鎖 ---
    teach = client()
    s, d = call(teach, "POST", "/api/gate", {"code": "猜錯的密碼"})
    check("密碼錯 → 403", s == 403, f"得到 {s}")
    s, d = call(teach, "POST", "/api/gate", {"code": CODE})
    check("密碼對 → 解鎖成功", s == 200 and d.get("unlocked"), d)

    s, cats = call(teach, "GET", "/api/categories")
    keys = [c["key"] for c in cats]
    check("解鎖後課程主題出現", all(k in keys for k in
          ("python", "pytorch", "ai", "vba", "emba")), keys)
    s, u = call(teach, "GET", "/api/units?topic=ai")
    check("解鎖後看得到 AI 導論的 17 個單元", len(u) == 17, len(u))
    s, d = call(teach, "POST", "/api/mp/create",
                {"category": "ai", "count": 10, "time": 20})
    check("解鎖後開得了課程考坊", s == 200 and d.get("code"), d)
    room, htok = (d.get("code"), d.get("token")) if s == 200 else (None, None)

    # --- 學生進老師開的房:應該正常,而且一次只看得到一題 ---
    if room:
        s, j = call(stu, "POST", "/api/mp/join", {"code": room, "name": "小明"})
        check("學生進得了老師開的考坊", s == 200, j)
        pid, ptok = (j.get("pid"), j.get("token")) if s == 200 else (None, None)
        sv, sd = call(teach, "POST", "/api/mp/start", {"code": room, "token": htok})
        check("老師開始遊戲", sv == 200, sd)
        time.sleep(0.3)
        s, v = call(stu, "GET", f"/api/mp/view?code={room}&pid={pid}&token={ptok}")
        check("學生看得到當前題目", s == 200 and v.get("q"), v)
        if s == 200 and v.get("q"):
            q = v["q"]
            check("題目不帶 id", "id" not in q, list(q))
            check("題目不帶 answer", "answer" not in q, list(q))
            check("題目不帶 explanation", "explanation" not in q, list(q))
            check("一次只發一題", isinstance(q.get("question"), str))
            check("reveal 還沒出現(題目進行中不給答案)", "reveal" not in v)

    # --- 解鎖是綁 cookie,不是綁整台伺服器 ---
    stu2 = client()
    s, d = call(stu2, "POST", "/api/start", {"category": "ai"})
    check("另一個沒解鎖的人還是 403", s == 403, f"得到 {s}")
finally:
    srv.kill(); srv.wait()

# ============ 情境 2:雲端但忘了設 TEACH_CODE(fail-safe) ============
print("\n情境 2　雲端但忘了設 TEACH_CODE")
srv = boot({"RENDER": "true"})
try:
    op = client()
    s, cats = call(op, "GET", "/api/categories")
    keys = [c["key"] for c in cats]
    check("課程主題整批關閉", not any(k in keys for k in ("python", "ai", "emba")), keys)
    s, d = call(op, "POST", "/api/start", {"category": "ai"})
    check("拿不到課程題目", s == 403, f"得到 {s}")
    s, d = call(op, "POST", "/api/gate", {"code": CODE})
    check("而且解不開(寧可你發現課程不見,也不要以為鎖好其實沒鎖)", s == 403, f"得到 {s}")
    s, d = call(op, "POST", "/api/start", {"category": "geo"})
    check("通識照常", s == 200, f"得到 {s}")
finally:
    srv.kill(); srv.wait()

# ============ 情境 3:本機、零設定(原本的使用習慣不能被改壞) ============
print("\n情境 3　本機、沒設 TEACH_CODE")
srv = boot({})
try:
    op = client()
    s, cats = call(op, "GET", "/api/categories")
    keys = [c["key"] for c in cats]
    check("14 個主題全部都在", len(cats) == 14, len(cats))
    s, d = call(op, "POST", "/api/start", {"category": "ai"})
    check("課程題目直接玩得到,不用解鎖", s == 200, f"得到 {s}")
    s, d = call(op, "POST", "/api/mp/create", {"category": "pytorch", "count": 10, "time": 20})
    check("課程考坊直接開得了", s == 200, d)
finally:
    srv.kill(); srv.wait()

print(f"\n通過 {ok}　失敗 {fail}")
sys.exit(1 if fail else 0)
