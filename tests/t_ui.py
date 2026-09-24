# -*- coding: utf-8 -*-
"""主持台與單人練習頁的畫面驗證：分頁、上鎖、解鎖。"""
import os, pathlib, subprocess, sys, time
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 5097; BASE = f"http://127.0.0.1:{PORT}"
CODE = "TEST-UNLOCK-9137"
ok = fail = 0
def check(n, c, extra=""):
    global ok, fail
    if c: ok += 1; print(f"  [ok]   {n}")
    else: fail += 1; print(f"  [FAIL] {n}  {extra}")

env = dict(os.environ); env["RENDER"] = "true"; env["TEACH_CODE"] = CODE
srv = subprocess.Popen([sys.executable, str(ROOT / "tests" / "_serve.py"), str(PORT)], env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(6)
errs = []
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=os.environ.get("CHROME") or None)
        pg = b.new_page()
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)

        # ---------- 主持台：未解鎖 ----------
        pg.goto(f"{BASE}/host"); pg.wait_for_selector("#grp button", timeout=20000)
        tabs = [t.inner_text().strip() for t in pg.query_selector_all("#grp button")]
        check("主持台有四個分頁", len(tabs) == 4, tabs)
        check("課程那一頁標著需解鎖", any("需解鎖" in t for t in tabs), tabs)
        check("預設停在通識", pg.query_selector('#grp button[data-g="known"]')
              .get_attribute("aria-pressed") == "true")
        names = [c.inner_text().replace("\n", " ") for c in pg.query_selector_all(".cat")]
        check("通識頁只有四個主題", len(names) == 4, names)
        check("通識頁看不到課程主題",
              not any(k in " ".join(names) for k in ("Python", "Deep Learning", "AI 導論", "VBA", "EMBA")), names)

        pg.click('#grp button[data-g="light"]'); pg.wait_for_timeout(500)
        names = [c.inner_text().replace("\n", " ") for c in pg.query_selector_all(".cat")]
        check("輕鬆頁有三個主題", len(names) == 3, names)

        pg.click('#grp button[data-g="course"]'); pg.wait_for_timeout(400)
        check("按課程頁會跳出解鎖卡", pg.is_visible("#lockbox"))
        check("解鎖碼欄位是密碼欄（投影時不會露出來）",
              pg.get_attribute("#tcode", "type") == "password")
        check("解鎖卡出現時主題格藏起來", not pg.is_visible("#cats"))

        pg.fill("#tcode", "錯的密碼"); pg.click("#tgo"); pg.wait_for_timeout(800)
        check("密碼錯會顯示錯誤訊息", pg.is_visible("#terr"), pg.inner_text("#terr") if pg.query_selector("#terr") else "")

        pg.fill("#tcode", CODE); pg.click("#tgo")
        pg.wait_for_selector('.cat', timeout=15000); pg.wait_for_timeout(600)
        names = [c.inner_text().replace("\n", " ") for c in pg.query_selector_all(".cat")]
        check("解鎖後課程頁出現五個主題", len(names) == 5, names)
        check("五個課程主題都在", all(k in " ".join(names)
              for k in ("Python", "Deep Learning", "AI 導論", "VBA", "EMBA")), names)
        tabs = [t.inner_text().strip() for t in pg.query_selector_all("#grp button")]
        check("解鎖後分頁不再標需解鎖", not any("需解鎖" in t for t in tabs), tabs)

        # 選一個課程主題，單元清單要出得來
        pg.click('.cat[data-k="ai"]'); pg.wait_for_timeout(1200)
        units = pg.query_selector_all("#units button")
        check("AI 導論的單元清單載入（17 單元 + 不分單元）", len(units) == 18, len(units))

        # 重新整理：cookie 還在，應該仍是解鎖狀態
        pg.reload(); pg.wait_for_selector("#grp button", timeout=20000); pg.wait_for_timeout(500)
        tabs = [t.inner_text().strip() for t in pg.query_selector_all("#grp button")]
        check("重新整理後還是解鎖的", not any("需解鎖" in t for t in tabs), tabs)

        # ---------- 單人練習頁 ----------
        st = b.new_page()                                  # 新分頁沒有解鎖 cookie? 同一個 context 會有
        st.goto(f"{BASE}/"); st.wait_for_selector("#grp button", timeout=20000)
        check("單人頁也有分頁", len(st.query_selector_all("#grp button")) >= 3)

        # 另一個瀏覽器情境：完全沒解鎖過的人
        c2 = b.new_context(); p2 = c2.new_page()
        p2.goto(f"{BASE}/"); p2.wait_for_selector("#grp button", timeout=20000); p2.wait_for_timeout(400)
        t2 = [t.inner_text().strip() for t in p2.query_selector_all("#grp button")]
        check("沒解鎖的人在單人頁看不到課程分頁", "課程" not in t2, t2)

        b.close()
finally:
    srv.kill(); srv.wait()

# 密碼打錯那一次本來就會收到 403，那是預期中的，不算錯誤
skip = ("favicon", "manifest", "403 (forbidden)", "403 (FORBIDDEN)".lower())
real = [e for e in errs if not any(k in e.lower() for k in skip)]
check("沒有 JS 錯誤", not real, real[:3])
print(f"\n通過 {ok}　失敗 {fail}")
sys.exit(1 if fail else 0)
