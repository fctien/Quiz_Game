# 金榜問答 — 益智問答遊戲

台灣・中國・世界・詩詞・明星・趣聞・即時新聞，七大分類 + 綜合挑戰，題庫 328 題（不含即時新聞）。Python(Flask)後端 + 手機友善的 HTML/JS 前端。

## 快速開始

```bash
pip install -r requirements.txt
python app.py
```

- 電腦瀏覽器開 http://127.0.0.1:5000
- 手機（和電腦同一個 Wi-Fi)開 `http://<電腦的IP>:5000`

## 兩種模式

首頁可以切換「單人闖關」和「多人對戰」。

### 多人對戰（同場即時搶答）

1. 主持人在電腦開 `http://127.0.0.1:5000/host`，選分類、題數（5／10／15／20）、每題秒數（10／15／20／30），按「開房間」
2. 畫面會顯示四位數房號和 QR code（程式會自動換成區網 IP，手機掃了就能連）；建議投影到大螢幕
3. 玩家用手機掃 QR code，或打開首頁 →「多人對戰」→ 輸入房號、暱稱加入
4. 主持人按「開始考試」，所有人同時作答；全員作答完或時間到就公布答案
5. 公布時顯示正解、每個選項幾人選、最快答對的人、目前前五名與名次升降
6. **最後一題分數加倍**，最後放榜：狀元、榜眼、探花；主持人可「再來一局」

計分：答對 500 分 + 速度分（最多 500）+ 連中加分（每連中一題 +100，最多 +500），最後一題 ×2。答案只存在伺服器，公布前手機拿不到。

技術：即時推播用 **Server-Sent Events（SSE）**，純 Flask 就能做，不必另外安裝 WebSocket 套件；玩家重新整理頁面會自動回到原本的位置。一間房最多 100 人。

## 單人玩法

- 每局 10 題，3 條命，答錯或超時扣一條
- 答得越快分數越高；連中 3 題 ×1.5、連中 5 題 ×2
- 道具（每局各一次）:刪去兩個選項、跳過此題、加時 10 秒
- 題型：選擇題、是非題、排序題（時間軸）
- 依正確率放榜：狀元、榜眼、探花、進士、秀才

## 排行榜

- 結算時輸入暱稱即可「題名上榜」，可切換**本週榜 / 總榜**與各分類
- 前三名顯示為狀元、榜眼、探花；本週榜每週一 00:00（台灣時間）重新開始
- 成績存在 `leaderboard.db`(SQLite，第一次執行自動建立，不用另外架資料庫）
- **防作弊**:分數完全由伺服器計算——伺服器記錄每題顯示與作答的時間、檢查題號順序、道具每局限用一次、一局只能上榜一次，前端送不了假分數
- 暱稱會過濾 HTML 字元與不雅字詞(`leaderboard.py` 的 `BLOCKED` 可自行擴充）
- 清空排行榜：刪除 `leaderboard.db` 後重新啟動

## 專案結構

```
app.py               Flask 後端:出題、計時、計分、道具、上榜 API(答案只存在後端)
leaderboard.py       排行榜(SQLite)
news.py              即時新聞出題(Google News RSS)
questions/*.json     題庫:taiwan / china / world / poetry
static/index.html    前端(單一檔案)
build_standalone.py  產生免後端的單機版 standalone.html
```

## 新增題目

在 `questions/*.json` 加一筆即可，重新啟動 `app.py` 生效：

```json
{
  "id": "tw-017",
  "category": "文化",
  "difficulty": 2,
  "type": "choice",
  "question": "題目文字",
  "options": ["選項A", "選項B", "選項C", "選項D"],
  "answer": 1,
  "explanation": "答案說明",
  "fun_fact": "冷知識(可留空)"
}
```

- `type: "choice"`:`answer` 是正確選項的索引（從 0 開始）
- 是非題：`options` 設為 `["對", "錯"]`,`answer` 為 0（對）或 1（錯）
- `type: "order"`:`answer` 是依正確順序排列的選項索引，例如 `[2, 0, 3, 1]`
- `difficulty`:1~3，影響得分，每局會由易到難排序

要新增分類，在 `app.py` 的 `CATEGORIES` 加一行，並在 `static/index.html` 的 `SEAL` 設定印章字。

## 即時新聞

- **未設定 API key**:抓今日新聞標題，玩「猜版面」（這則新聞在國際、財經、體育……哪一版？）
- **設定 `ANTHROPIC_API_KEY`**:由 Claude 根據當日標題出選擇題，題目標示「AI 出題」

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export CLAUDE_MODEL=claude-sonnet-4-5   # 可改成你帳號可用的模型
python app.py
```

題目快取 60 分鐘(`news.py` 的 `CACHE_MINUTES`)。AI 出的題目可能有錯，正式使用前建議抽查。

## 上線給一般大眾

- 進行中的遊戲和多人房間都存在記憶體，重啟就清空
- 請用**單一 worker、多執行緒**啟動：`gunicorn -w 1 --threads 100 app:app`（多人模式每位玩家占用一條連線，執行緒數要大於同時上線人數）
- 前面若有 Nginx，SSE 路徑 `/api/mp/stream` 要關閉緩衝（程式已送出 `X-Accel-Buffering: no`）
- 部署可用 Render、Railway、Fly.io，或學校主機
- 只想放靜態網頁：執行 `python build_standalone.py`，上傳 `standalone.html` 即可（只有單人模式，沒有新聞分類，答案在網頁原始碼裡）
