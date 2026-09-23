# 脈衝 PULSE — 專案規範

課堂搶答遊戲。老師開一間考坊，學生用手機掃 QR 進場搶答；也有不需後端的單機版。

## 目錄
```
app.py               Flask 主程式：主題/單元、題庫載入、單人練習 API
multiplayer.py       多人考坊：房間、SSE 推播、加入/踢人/清單/中斷/換題
classroom.py         班級代碼與累積成績
leaderboard.py       排行榜   news.py 即時新聞主題
questions/*.json     題庫（一個檔一個來源，見下）
static/              index(單人) host(主持台) play(學生) class join qrcard
build_standalone.py  產生 standalone.html（完整版）與 docs/index.html（公開版）
docs/                GitHub Pages 目錄 + 兩份列印用小抄
```

## 題庫規則
- 每題：`id / topic / unit / unit_name / category / difficulty(1-3) / type / question /
  options / answer(索引) / explanation / fun_fact`，`region` 由 `FILES` 依檔名帶入。
- `topic` 見 `app.py` 的 `TOPICS`；`unit` 是單元：Python/DL/VBA 用**週次**（W1、L0、V1…），
  地理/歷史/人文用**地區代碼**（見 `REGION_ORDER`），課程主題用 `UNIT_ORDER` 裡定好的代碼。
- 課程主題（`ai`、`emba`）的單元順序寫在 `app.py` 的 `UNIT_ORDER`，中文名稱對照在 `UNIT_NAMES`。
  單元清單是由題目長出來的，題庫還沒補的單元不會出現；補進來就會自動照 `UNIT_ORDER` 排好。
- 題庫還是空的主題，主題格子會顯示「準備中」且點不下去，不必為了佔位塞假題目。
- 地區按鈕的順序固定由 `REGION_ORDER` 決定，不受題庫檔順序影響；
  單機版由 `build_standalone.py` 做同樣排序。
- 題數少於一場最低題數（5 題）的單元不會出現在單元清單上。
- 出題品質門檻：難度約 25%/50%/25%、正解索引 0–3 平均分散、
  「最長的選項就是答案」低於 30%、誘答要同類型同層級、繁體中文與台灣慣用譯名、
  不用會過期的數字（人口、排名、現任者）。
- **出題與查核要分開**：寫完的題目一定要由另一個獨立的查核流程逐題比對權威來源，
  再把發現的問題逐條修掉。

## 開發慣例
- Python 3，不引入付費服務；Render 免費方案（0.1 CPU / 512 MB）是效能基準線。
- 改完一定要跑過 `scratchpad` 裡的回歸測試（多人、60 人壓測、中斷換題、清名單、
  重複加入、殭屍連線、固定入口、自動公布），以及各單元的判分一致性測試。
- 改題庫或前端後要重跑 `python build_standalone.py`。
- 版本字樣同時出現在 `static/*.html`、`DEPLOY-Render.md`、`docs/*.html`，要一起改。
- **公開版（docs/）不可含 Python、Deep Learning、VBA 題庫**，見 `build_standalone.py` 的 `PRIVATE`。
- repo 是公開的：課程代碼、管理碼、任何密碼都不可以寫進檔案。
- **改完一定要把檔案同步回使用者的電腦**（`mcp__remote-devices__device_commit_files`
  寫到 `C:\Users\User\Desktop\Tien Research\益智問答開發\quiz_game`）。
  在雲端工作區 commit **不會**讓使用者的電腦有任何改變，他跑 `推上GitHub.bat`
  也推不出東西。順序永遠是：雲端改好 → 測試 → 同步檔案到他的電腦 → 他自己跑 .bat。
- 同步完要確認檔案真的到位，再告訴他可以推了。確認方式用 `md5sum` 兩邊對拉，
  **不要用 `git status`**（見下一條）。
- **不要從掛載層對他的 repo 下任何 git 指令**（`fetch`、`add`、`commit`、`gc`
  **以及 `status`** 都不行）。`git status` 會去寫 `.git/index.lock` 來刷新 index——
  它不是唯讀指令。那一層預設不允許刪檔，git 清不掉自己的 lock，就會留下
  `.git/index.lock`，之後他在 Windows 上跑 `推上GitHub.bat` 會靜靜失敗
  （`git add` 失敗 → .bat 判定「沒有新的變更需要提交」→ 什麼都沒推）。
  真正安全的只有不碰 index 的 `git log`、`git ls-tree`、`git rev-list`。
- 萬一還是留下了 lock：用 `device_request_delete_permission` 要到刪檔權限，
  `rm -f .git/index.lock`，再確認 `.git/*.lock` 已經清空。
- 推上 GitHub 由使用者自己執行 `推上GitHub.bat`。

## 每次工作結束前
把本次過程追加到 `DEVLOG.md`（只追加、不改寫），欄位固定：
需求／做法／產出／驗證／問題與修正／待辦。失敗的嘗試也要寫，並說明原因。
