# ETF 全持股網站（含持股變動）｜GitHub Pages + GitHub Actions

這個專案會把 **00980A / 00981A / 00982A** 的「全持股」抓下來，並自動計算「與前一日相比的持股變動」，做成網站讓你點進去就能看。

## 資料來源（你指定的官網頁）
- 00980A：Nomura（野村）Shareholding 頁
- 00981A：ezmoney（你提供的官網頁）
- 00982A：群益投信 portfolio 頁

> 由於這三頁多半是 JS 動態渲染，本專案用 Playwright 先「像瀏覽器一樣打開頁面」，再用 pandas 抓表格，因此能拿到全持股（不是只有前十大）。

## 部署步驟
1. 在 GitHub 建一個新 repo（例如：etf-holdings）
2. 把整包專案檔案上傳到 repo（根目錄）
3. Settings → Pages
   - Source: Deploy from a branch
   - Branch: `main`
   - Folder: `/docs`
4. Actions → `Update holdings daily` → **Run workflow**（先手動跑一次）
5. 回到 Pages 的網址，打開就能看

## 每日更新時間
- 預設排程：UTC 01:30（台北 09:30）
- 你可以改 `.github/workflows/update.yml` 的 cron

## 檔案輸出（網站讀這裡）
- 最新全持股：`docs/data/current/{code}.json`
- 每日快照（留存歷史）：`docs/data/snapshots/{code}/YYYY-MM-DD.json`
- 與前一日比較的變動：`docs/data/changes/{code}.json`

## 如果某站阻擋爬蟲怎麼辦？
最穩的是改抓「PCF/投資組合檔（CSV）」：
- 到 `scripts/sources.json` 把某檔的 `type` 改為 `csv`
- `url` 換成官方 CSV 下載連結
