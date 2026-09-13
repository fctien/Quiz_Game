# 部署到 Render（備援方案）

學生用自己的行動網路就能玩，不必和老師在同一個 Wi-Fi，也不受校園網路的裝置隔離影響。
Render 免費方案就夠用，不需要信用卡。

## 一、一次性設定（建議上課前幾天做）

1. **把程式放上 GitHub**（Render 從 repo 部署）
   ```bash
   cd quiz_game
   git init                     # 若解壓縮的是含 git 紀錄的版本就跳過
   git add -A
   git commit -m "金榜問答"
   git branch -M main
   git remote add origin https://github.com/<你的帳號>/jinbang-quiz.git
   git push -u origin main
   ```
   儲存庫設為 **Private 也可以**，Render 連得到。

2. **在 Render 建立服務**
   - 到 <https://render.com> 用 GitHub 帳號登入
   - **New → Blueprint** → 選這個 repo → Render 會讀取 `render.yaml` 自動設定 → **Apply**
   - 等 2～5 分鐘，狀態變成 **Live**
   - 拿到網址，例如 `https://jinbang-quiz.onrender.com`

   （若不用 Blueprint，也可以 New → Web Service 手動填：
   Build `pip install -r requirements.txt gunicorn`、
   Start `gunicorn -w 1 --threads 100 --timeout 0 -b 0.0.0.0:$PORT app:app`）

3. **測試**：手機用行動網路開 `https://<你的網址>/api/health`，看到 `ok: true` 就成功。

## 二、上課當天

1. 老師開 `https://<你的網址>/host`，照平常的方式開房。
2. QR code 會自動變成雲端網址，學生用 4G 或任何 Wi-Fi 都能加入。
3. **重要：下課前先按「匯出本場成績 CSV」再關閉**（原因見下）。

## 三、免費方案要注意的事

| 事項 | 說明 | 對策 |
|---|---|---|
| **閒置會休眠** | 15 分鐘沒人用就停機，下次開啟要等 30～60 秒 | 上課前 5 分鐘先開一次網頁把它叫醒 |
| **資料不會永久保存** | 重新部署或休眠重啟後，`leaderboard.db`（班級積分）可能被清空 | 每堂課結束**立刻匯出 CSV**；班級積分只當輔助 |
| **同時連線數** | 免費方案資源有限，約 40～50 人的班級可行，但反應會比區網慢一點 | 人多時改用區網模式，或升級付費方案 |
| **要保留班級積分** | 需要永久儲存 | 升級付費方案並掛一顆 Disk（掛載到程式資料夾），或改用外部資料庫 |

## 四、兩種方案怎麼選

| | 區網（老師電腦） | Render（雲端） |
|---|---|---|
| 學生用什麼上網 | 必須同一個 Wi-Fi | 4G 或任何網路都行 |
| 速度 | 最快 | 稍慢（約多 0.1～0.3 秒） |
| 會被校園網路擋 | 有可能 | 不會 |
| 成績保存 | 存在你電腦上，穩 | 要當場匯出 |
| 手機可安裝成 App | Android 不行（非 HTTPS） | 可以（Render 是 HTTPS） |

**建議**：主要用區網，Render 當備援。兩邊都先設好，上課當天哪個通就用哪個。
