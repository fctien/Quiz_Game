# -*- coding: utf-8 -*-
"""單元複選（1～3 個）＋ 30 題的回歸測試。

重點三件事：
  1. 題數真的平均分給每個單元，而且每個單元各自維持 25／50／25 的難度分布
  2. 複選之後判分還是對的（一題一題答完，伺服器算的對錯要跟題庫一致）
  3. /api/mp/reconfig 也要過門禁 —— 少了這一關，學生可以先開地理考坊再換成課程主題
"""
import collections, json, os, pathlib, subprocess, sys, time
import http.cookiejar, urllib.error, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 5093
BASE = f"http://127.0.0.1:{PORT}"
CODE = "TEST-UNLOCK-9137"
ok = fail = 0


def check(n, c, extra=""):
    global ok, fail
    if c: ok += 1; print(f"  [ok]   {n}")
    else: fail += 1; print(f"  [FAIL] {n}  {extra}")


def client():
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def call(o, m, p, d=None):
    r = urllib.request.Request(BASE + p, method=m); b = None
    if d is not None:
        b = json.dumps(d).encode(); r.add_header("Content-Type", "application/json")
    try:
        with o.open(r, b, timeout=30) as x:
            return x.status, json.loads(x.read().decode() or "null")
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode() or "null")
        except Exception: return e.code, None
    except Exception:
        return 0, None


env = dict(os.environ); env["RENDER"] = "true"; env["TEACH_CODE"] = CODE
srv = subprocess.Popen([sys.executable, str(ROOT / "tests" / "_serve.py"), str(PORT)],
                       env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
op = client()
for _ in range(80):
    if call(op, "GET", "/api/health")[0] == 200: break
    time.sleep(0.5)

try:
    # ---------- 門禁：reconfig 不能繞過 ----------
    print("\n門禁")
    stu = client()
    s, d = call(stu, "POST", "/api/mp/create", {"category": "geo", "count": 10, "time": 20})
    check("學生開得了地理考坊", s == 200, s)
    room, tok = d["code"], d["token"]
    s, _ = call(stu, "POST", "/api/mp/reconfig",
                {"code": room, "token": tok, "category": "ai", "count": 10, "time": 20})
    check("學生用 reconfig 換成課程主題 → 403", s == 403, f"得到 {s}")
    s, v = call(stu, "GET", f"/api/mp/view?code={room}&pid=host&token={tok}")
    check("房間主題沒有被換掉", v.get("topic") == "geo", v.get("topic"))

    # ---------- 老師解鎖 ----------
    t = client()
    call(t, "POST", "/api/gate", {"code": CODE})

    # ---------- 題數 30 ----------
    print("\n題數與分配")
    s, d = call(t, "POST", "/api/mp/create",
                {"category": "ai", "count": 30, "time": 20, "unit": ["W1", "W2", "W3"],
                 "unit_name": "W1・W2・W3"})
    check("30 題開得起來", s == 200, d)
    check("真的出了 30 題", s == 200 and d.get("total") == 30, d.get("total") if d else None)

    # ---------- 分配：跑多次看平均 ----------
    def sample(units, n, rounds=20):
        per, diff, totals = collections.Counter(), collections.Counter(), []
        bank = json.load(open(ROOT / "questions" / "ai.json", encoding="utf-8"))
        by_q = {q["question"]: q for q in bank}
        for _ in range(rounds):
            s, d = call(t, "POST", "/api/mp/create",
                        {"category": "ai", "count": n, "time": 0, "unit": units, "unit_name": "x"})
            if s != 200: return None
            code, htok = d["code"], d["token"]
            j = call(t, "POST", "/api/mp/join", {"code": code, "name": "測"})[1]
            pid, ptok = j["pid"], j["token"]
            call(t, "POST", "/api/mp/start", {"code": code, "token": htok})
            seen = 0
            while seen < n + 2:
                v = call(t, "GET", f"/api/mp/view?code={code}&pid={pid}&token={ptok}")[1]
                if v.get("state") == "final": break
                if v.get("state") == "question" and v.get("q"):
                    q = by_q.get(v["q"]["question"])
                    if q: per[q["unit"]] += 1; diff[q.get("difficulty", 2)] += 1
                    seen += 1
                    call(t, "POST", "/api/mp/reveal", {"code": code, "token": htok})
                    call(t, "POST", "/api/mp/next", {"code": code, "token": htok})
                else:
                    call(t, "POST", "/api/mp/next", {"code": code, "token": htok})
            totals.append(seen)
            call(t, "POST", "/api/mp/close", {"code": code, "token": htok})
        return per, diff, totals

    r = sample(["W1", "W2", "W3"], 30, rounds=10)
    if r:
        per, diff, totals = r
        avg = {u: per[u] / 10 for u in ("W1", "W2", "W3")}
        tot = sum(diff.values())
        pct = {k: diff[k] / tot for k in (1, 2, 3)}
        print(f"        每單元平均 {avg}　難度 {{1:{pct[1]:.0%}, 2:{pct[2]:.0%}, 3:{pct[3]:.0%}}}")
        check("三個單元各拿到 10 題", all(abs(v - 10) < 0.01 for v in avg.values()), avg)
        check("難度接近 25／50／25",
              abs(pct[1] - .25) < .06 and abs(pct[2] - .50) < .06 and abs(pct[3] - .25) < .06, pct)
        check("每場都是 30 題", all(x == 30 for x in totals), totals)

    # ---------- 判分 ----------
    print("\n判分（複選單元時也要對）")
    bank = json.load(open(ROOT / "questions" / "ai.json", encoding="utf-8"))
    by_q = {q["question"]: q for q in bank}
    s, d = call(t, "POST", "/api/mp/create",
                {"category": "ai", "count": 30, "time": 0, "unit": ["W5", "W10", "MIX"],
                 "unit_name": "三單元"})
    code, htok = d["code"], d["token"]
    j = call(t, "POST", "/api/mp/join", {"code": code, "name": "考生"})[1]
    pid, ptok = j["pid"], j["token"]
    call(t, "POST", "/api/mp/start", {"code": code, "token": htok})
    bad = n_done = 0
    units_seen = collections.Counter()
    while n_done < 30:
        v = call(t, "GET", f"/api/mp/view?code={code}&pid={pid}&token={ptok}")[1]
        if v.get("state") == "final": break
        if v.get("state") != "question" or not v.get("q"):
            call(t, "POST", "/api/mp/next", {"code": code, "token": htok}); continue
        q = by_q[v["q"]["question"]]
        units_seen[q["unit"]] += 1
        sa, _ra = call(t, "POST", "/api/mp/answer",
                       {"code": code, "pid": pid, "token": ptok,
                        "choice": q["answer"], "index": v["q"]["index"]})
        if sa != 200: bad += 1
        call(t, "POST", "/api/mp/reveal", {"code": code, "token": htok})
        v2 = call(t, "GET", f"/api/mp/view?code={code}&pid={pid}&token={ptok}")[1]
        if v2.get("reveal", {}).get("answer") != q["answer"]: bad += 1
        if not (v2.get("result") or {}).get("correct"): bad += 1
        n_done += 1
        call(t, "POST", "/api/mp/next", {"code": code, "token": htok})
    check("30 題全部答對且伺服器判分一致", bad == 0 and n_done == 30, f"不一致 {bad} 件, 做了 {n_done} 題")
    check("三個單元都有出到，而且各 10 題",
          sorted(units_seen.values()) == [10, 10, 10], dict(units_seen))

    # ---------- 邊界 ----------
    print("\n邊界")
    s, d = call(t, "POST", "/api/mp/create",
                {"category": "ai", "count": 30, "time": 20,
                 "unit": ["W1", "W2", "W3", "W4", "W5"], "unit_name": "五個"})
    check("送超過 3 個單元也不會爆（只取前 3 個）", s == 200 and d.get("total") == 30, d)
    s, d = call(t, "POST", "/api/mp/create",
                {"category": "ai", "count": 30, "time": 20, "unit": "W1", "unit_name": "W1"})
    check("舊的寫法（單一字串）還是能用", s == 200 and d.get("total") == 30, d)
    s, d = call(t, "POST", "/api/mp/create",
                {"category": "ai", "count": 30, "time": 20, "unit": [], "unit_name": ""})
    check("不選單元 → 整個主題一起出", s == 200 and d.get("total") == 30, d)
    s, d = call(t, "POST", "/api/start", {"category": "ai", "unit": ["W1", "W2"]})
    check("單人練習也收得了複選", s == 200 and len(d.get("questions", [])) == 10, s)
    check("單人練習的 unit_name 會把兩個單元串起來",
          s == 200 and "・" in (d.get("unit_name") or ""), d.get("unit_name") if d else None)
finally:
    srv.kill(); srv.wait()

print(f"\n通過 {ok}　失敗 {fail}")
sys.exit(1 if fail else 0)
