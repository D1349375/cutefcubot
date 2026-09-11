<div align="center">
  <h1>🤖 可愛逢甲搶課小幫手 (FCU Course Alert LINE Bot)</h1>
  <p>專為逢甲大學生打造的 LINE 互動式「退選即時通知機器人」</p>
  <p>只要在 LINE 說：<b>「3073這堂課有人退選就提醒我」</b>，系統自動 24 小時後台巡檢，有名額立刻推播快去搶！</p>
</div>

---

## 🌟 專案特色

* 🔒 **零資安疑慮、免學號密碼**：  
  完全透過逢甲公開之「課程檢索系統」API 查詢，**100% 不向使用者索取 NID 與密碼**，徹底杜絕個資洩漏與第三方雲端環境變數被盜風險。
* ⚡ **超輕量架構（非 Selenium）**：  
  擺脫笨重的 Chrome 瀏覽器自動化，採用純 Python 非同步查詢，記憶體僅佔用約 30MB，開機常駐無負擔。
* 💬 **自然語言互動**：  
  支援自然中文指令（如「`3073這堂課有人退選就提醒我`」、「`監控 3073`」、「`查詢 3073`」、「`我的清單`」）。
* 🚀 **智慧聚合輪詢**：  
  自動合併多人重複關注的課程，每 25 秒單次禮貌請求，避免觸發學校 WAF 防火牆封鎖，抗阻擋能力極強。
* 💸 **真正 100% 0 費用本地部署**：  
  利用家用桌機（台灣真實家用 IP）搭配官方免費的 **Cloudflare Tunnel**，不需要固定 IP、不需要路由器開 Port，免受學校 TANet 擋海外機房之苦。

---

## 📱 LINE 支援指令列表

| 功能 | 輸入範例 | 說明 |
| :--- | :--- | :--- |
| **加入退選監控** | `3073這堂課有人退選就提醒我`<br>`監控 3073`<br>`關注 3073` | 自動查證課堂資訊，並在後台啟動每 25 秒巡邏。 |
| **即時名額查詢** | `查詢 3073`<br>`查 3073` | 立即回傳該課程名稱、授課教師、時間教室與目前人數上限。 |
| **查看我的清單** | `我的清單`<br>`清單` | 列出自己目前正在監控中的所有課號與人數狀態。 |
| **取消監控** | `取消 3073`<br>`刪除 3073` | 停止對該門課程的背景巡查。 |
| **功能說明** | `說明`<br>`幫助`<br>`help` | 叫出完整的操作指引。 |

---

## 🛠️ 專案架構與檔案說明

```text
cutefcubot/
├── fcu_client.py       # 逢甲大學公開課程檢索 API 客戶端 (自動維持 Session/Token)
├── monitor.py          # 背景非同步輪詢引擎與狀態持久化 (儲存於 watchlist.json)
├── bot.py              # FastAPI LINE Webhook 伺服器與自然語言指令解析
├── test_bot.py         # 本機 E2E 整合測試腳本
├── run_bot.bat         # Windows 一鍵啟動機器人腳本
├── start_tunnel.bat    # Windows 一鍵啟動 Cloudflare Tunnel 免費穿透通道腳本
├── requirements.txt    # Python 依賴套件清單
├── .env.example        # 金鑰環境變數範本檔
└── .env                # 本地金鑰設定檔 (受 .gitignore 保護，絕不上傳 GitHub)
```

---

## 🚀 完整部署教學（以本機 / 家用桌機為例）

### 第一部分：LINE 官方帳號與金鑰申請

1. **建立 Provider 與 Channel**：
   * 前往 [LINE Developers Console](https://developers.line.biz/console/)，使用個人 LINE 帳號登入。
   * 點擊 **Create a new provider**（輸入如 `FCUBOT`）。
   * 進入 Provider 後，點選 **Create a Messaging API channel**，填妥名稱與分類完成建立。

2. **取得兩大金鑰**：
   * **Channel secret**：位於 Channel 的 **Basic settings** 分頁中。
   * **Channel access token**：位於 Channel 的 **Messaging API** 分頁最底部，點擊 **Issue（發行）** 獲取長效憑證。

3. **調整回應設定**：
   * 在 **Messaging API** 分頁中點擊 **Auto-reply messages** 旁邊的 Edit。
   * 將 **「自動回應訊息」設為【停用】**。
   * 將 **「Webhook」設為【啟用】**。

---

### 第二部分：桌機端程式部署

#### 步驟 1：下載專案
在桌機上打開 PowerShell 或 CMD：
```bash
git clone https://github.com/D1349375/cutefcubot.git
cd cutefcubot
```

#### 步驟 2：安裝 Python 套件與通道工具
```bash
pip install -r requirements.txt
winget install Cloudflare.cloudflared
```

#### 步驟 3：設定 `.env` 金鑰
將專案內的 `.env.example` 複製一份並命名為 `.env`：
```bash
copy .env.example .env
```
用記事本打開 `.env`，填入第一部分拿到的兩組金鑰：
```ini
LINE_CHANNEL_SECRET=你的Channel_Secret
LINE_CHANNEL_ACCESS_TOKEN=你的Channel_Access_Token
POLL_INTERVAL=25
PORT=8000
```

---

### 第三部分：啟動連線與巡邏

1. **啟動外網通道**：
   * 雙擊執行專案目錄下的 **`start_tunnel.bat`**。
   * 視窗內會出現一行免費分配的網址，例如：`https://random-subdomain.trycloudflare.com`。
   * 將該網址加上 `/callback`（例如：`https://random-subdomain.trycloudflare.com/callback`）。
   * 回到 LINE Developers Console 的 **Messaging API** 頁面，貼進 **Webhook URL** 欄位，點擊 **Update** 並點 **Verify**（出現 `Success` 即代表成功）。
   * 確保下方的 **Use webhook** 開關處於 **【ON】** 狀態。

2. **啟動機器人**：
   * 雙擊執行專案目錄下的 **`run_bot.bat`**。
   * 伺服器啟動，背景巡邏排程器自動開始運轉！

3. **加入好友與測試**：
   * 用手機掃描 LINE 後台的 QR Code 加入好友。
   * 在聊天室傳送：`3073這堂課有人退選就提醒我`。
   * 享受專屬於你的 24 小時選課守護神！

---

## 🔒 資安與免責聲明

1. **零個資風險**：本專案僅查詢逢甲大學公開的選課人數數據，不儲存、不經手使用者的逢甲學號或選課密碼。
2. **免責聲明**：本工具僅提供退選名額之「即時推播提醒」，實際加退選操作仍須由學生本人登入學校官方系統進行，使用者應遵守逢甲大學校園網路與選課相關規章。