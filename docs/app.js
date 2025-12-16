async function fetchJSON(path){
  const res = await fetch(path, { cache: "no-store" });
  if(!res.ok) throw new Error(`Failed: ${res.status} ${path}`);
  return await res.json();
}

function renderTable(table, columns, rows){
  const thead = table.querySelector("thead");
  const tbody = table.querySelector("tbody");
  thead.innerHTML = "";
  tbody.innerHTML = "";

  const trh = document.createElement("tr");
  for(const col of columns){
    const th = document.createElement("th");
    th.textContent = col;
    trh.appendChild(th);
  }
  thead.appendChild(trh);

  for(const r of rows){
    const tr = document.createElement("tr");
    for(const col of columns){
      const td = document.createElement("td");
      const v = (r[col] === null || r[col] === undefined) ? "" : String(r[col]);
      td.textContent = v;
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
}

function setTabs(active){
  document.querySelectorAll(".tab").forEach(b => {
    b.classList.toggle("active", b.dataset.tab === active);
  });
  document.getElementById("panel-holdings").classList.toggle("hidden", active !== "holdings");
  document.getElementById("panel-changes").classList.toggle("hidden", active !== "changes");
}

function renderChips(summary){
  const el = document.getElementById("changeChips");
  el.innerHTML = "";
  const items = [
    ["新增", summary.added ?? 0],
    ["移除", summary.removed ?? 0],
    ["變動", summary.changed ?? 0],
    ["不變", summary.unchanged ?? 0],
  ];
  for(const [k, v] of items){
    const s = document.createElement("span");
    s.className = "chip";
    s.textContent = `${k}: ${v}`;
    el.appendChild(s);
  }
}

async function loadETF(code){
  const current = await fetchJSON(`./data/current/${code}.json`);
  const changes = await fetchJSON(`./data/changes/${code}.json`);

  document.getElementById("dataDate").textContent = current.data_date || "-";
  document.getElementById("scrapedAt").textContent = current.scraped_at || "-";
  document.getElementById("rowCount").textContent = (current.rows || []).length;

  const compareInfo = (changes && changes.base_date && changes.compare_date)
    ? `${changes.compare_date} → ${changes.base_date}`
    : "（缺少前一日快照）";
  document.getElementById("compareInfo").textContent = compareInfo;

  renderTable(document.getElementById("holdingsTable"), current.columns || [], current.rows || []);

  if(changes && changes.rows){
    renderChips(changes.summary || {});
    renderTable(document.getElementById("changesTable"), changes.columns || [], changes.rows || []);
  }else{
    renderChips({added:0, removed:0, changed:0, unchanged:0});
    renderTable(document.getElementById("changesTable"), ["提示"], [{提示:"尚無變動資料（需要至少兩天快照）"}]);
  }
}

async function init(){
  const idx = await fetchJSON("./data/current/index.json");
  const select = document.getElementById("etfSelect");
  select.innerHTML = "";
  for(const code of idx.codes){
    const opt = document.createElement("option");
    opt.value = code;
    opt.textContent = code;
    select.appendChild(opt);
  }

  const defaultCode = localStorage.getItem("last_etf") || idx.codes[0];
  select.value = defaultCode;
  await loadETF(select.value);

  select.addEventListener("change", async () => {
    localStorage.setItem("last_etf", select.value);
    await loadETF(select.value);
  });

  document.getElementById("reloadBtn").addEventListener("click", async () => {
    await loadETF(select.value);
  });

  document.querySelectorAll(".tab").forEach(b => {
    b.addEventListener("click", () => setTabs(b.dataset.tab));
  });
}

init().catch(err => {
  console.error(err);
  alert("載入失敗：可能是 GitHub Pages 尚未部署完成，或 data 檔還沒產生。\n\n" + err.message);
});
