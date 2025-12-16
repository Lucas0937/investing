#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests
from bs4 import BeautifulSoup

from playwright.sync_api import sync_playwright


TZ = ZoneInfo("Asia/Taipei")
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SOURCES_PATH = os.path.join(ROOT, "scripts", "sources.json")

OUT_CURRENT_DIR = os.path.join(ROOT, "docs", "data", "current")
OUT_CHANGES_DIR = os.path.join(ROOT, "docs", "data", "changes")
OUT_SNAP_DIR = os.path.join(ROOT, "docs", "data", "snapshots")


def ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)


def _html_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(" ", strip=True)


def extract_date_from_text(text: str) -> Optional[str]:
    # 支援：YYYY/MM/DD 或 YYYY-MM-DD
    m = re.search(r"(資料日期|日期|Data\s*Date)\s*[:：]?\s*(\d{4}[/-]\d{2}[/-]\d{2})", text, re.IGNORECASE)
    if m:
        return m.group(2).replace("-", "/")
    return None


def pick_holdings_table(dfs: List[pd.DataFrame]) -> pd.DataFrame:
    # 用關鍵欄位挑「持股明細」：包含「代號/名稱/比重/股數」等其一，再以列數最大為主
    keyword_sets = [
        ["代號", "名稱", "比重"],
        ["股票代號", "股票名稱", "比重"],
        ["Ticker", "Name", "Weight"],
        ["代碼", "名稱", "權重"],
    ]

    def score(df: pd.DataFrame) -> int:
        cols = " ".join([str(c) for c in df.columns])
        s = 0
        for ks in keyword_sets:
            hit = sum(1 for k in ks if k in cols)
            s = max(s, hit)
        # rows/cols also matter
        return s * 100000 + df.shape[0] * 100 + df.shape[1]

    return max(dfs, key=score)


def normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    df = df.dropna(axis=1, how="all")
    df = df.where(pd.notnull(df), None)
    return df


def render_html_playwright(url: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(user_agent=UA, locale="zh-TW", timezone_id="Asia/Taipei")
        page = context.new_page()
        page.goto(url, wait_until="load", timeout=90000)
        # give the site time to render tables
        page.wait_for_timeout(6000)
        html = page.content()
        context.close()
        browser.close()
    return html


def fetch_csv(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
    r.raise_for_status()
    return r.text


def fetch_holdings_from_source(cfg: Dict[str, Any]) -> Tuple[Optional[str], List[str], List[Dict[str, Any]]]:
    typ = cfg.get("type", "playwright_html")
    url = cfg["url"]

    if typ == "playwright_html":
        html = render_html_playwright(url)
        text = _html_text(html)
        data_date = extract_date_from_text(text)
        dfs = pd.read_html(html)
        df = normalize_df(pick_holdings_table(dfs))
    elif typ == "html":
        r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
        r.raise_for_status()
        html = r.text
        text = _html_text(html)
        data_date = extract_date_from_text(text)
        dfs = pd.read_html(html)
        df = normalize_df(pick_holdings_table(dfs))
    elif typ == "csv":
        csv_text = fetch_csv(url)
        from io import StringIO
        df = pd.read_csv(StringIO(csv_text))
        df = normalize_df(df)
        data_date = None
    else:
        raise ValueError(f"Unknown source type: {typ}")

    rows = df.to_dict(orient="records")
    return data_date, list(df.columns), rows


def detect_columns(columns: List[str]) -> Dict[str, Optional[str]]:
    # 對齊用 key：優先代號，其次名稱
    code_cols = ["股票代號", "證券代號", "代號", "代碼", "Ticker", "Symbol"]
    name_cols = ["股票名稱", "證券名稱", "名稱", "Name", "Security"]
    weight_cols = ["比重(%)", "比重", "權重(%)", "權重", "Weight", "持股權重"]
    shares_cols = ["股數", "持有股數", "持股股數", "Shares", "Units", "數量"]

    def pick(cands):
        for c in cands:
            if c in columns:
                return c
        # fuzzy contains
        for c in columns:
            for k in cands:
                if k.lower().replace("(%)","") in c.lower():
                    return c
        return None

    return {
        "code": pick(code_cols),
        "name": pick(name_cols),
        "weight": pick(weight_cols),
        "shares": pick(shares_cols),
    }


def to_float(x) -> Optional[float]:
    if x is None:
        return None
    s = str(x).strip().replace(",", "")
    if s == "":
        return None
    # remove % sign
    s = s.replace("%", "")
    try:
        return float(s)
    except Exception:
        return None


def to_int(x) -> Optional[int]:
    if x is None:
        return None
    s = str(x).strip().replace(",", "")
    if s == "":
        return None
    try:
        return int(float(s))
    except Exception:
        return None


def build_map(rows: List[Dict[str, Any]], cols: Dict[str, Optional[str]]) -> Dict[str, Dict[str, Any]]:
    m = {}
    for r in rows:
        key = None
        if cols["code"] and r.get(cols["code"]) not in (None, ""):
            key = str(r.get(cols["code"])).strip()
        elif cols["name"] and r.get(cols["name"]) not in (None, ""):
            key = str(r.get(cols["name"])).strip()
        else:
            continue

        item = {
            "key": key,
            "code": str(r.get(cols["code"])).strip() if cols["code"] and r.get(cols["code"]) is not None else None,
            "name": str(r.get(cols["name"])).strip() if cols["name"] and r.get(cols["name"]) is not None else None,
            "weight": to_float(r.get(cols["weight"])) if cols["weight"] else None,
            "shares": to_int(r.get(cols["shares"])) if cols["shares"] else None,
        }
        m[key] = item
    return m


def compute_changes(prev_payload: Dict[str, Any], curr_payload: Dict[str, Any]) -> Dict[str, Any]:
    prev_rows = prev_payload.get("rows", [])
    curr_rows = curr_payload.get("rows", [])

    prev_cols = detect_columns(prev_payload.get("columns", []))
    curr_cols = detect_columns(curr_payload.get("columns", []))

    prev_map = build_map(prev_rows, prev_cols)
    curr_map = build_map(curr_rows, curr_cols)

    all_keys = sorted(set(prev_map.keys()) | set(curr_map.keys()))

    out_rows = []
    summary = {"added": 0, "removed": 0, "changed": 0, "unchanged": 0}

    for k in all_keys:
        p = prev_map.get(k)
        c = curr_map.get(k)

        status = None
        if p is None and c is not None:
            status = "新增"
            summary["added"] += 1
        elif p is not None and c is None:
            status = "移除"
            summary["removed"] += 1
        else:
            # both exist
            dw = None
            ds = None
            if p.get("weight") is not None or c.get("weight") is not None:
                dw = (c.get("weight") or 0.0) - (p.get("weight") or 0.0)
            if p.get("shares") is not None or c.get("shares") is not None:
                ds = (c.get("shares") or 0) - (p.get("shares") or 0)

            # decide changed/unchanged
            if (dw is not None and abs(dw) > 1e-9) or (ds is not None and ds != 0):
                status = "變動"
                summary["changed"] += 1
            else:
                status = "不變"
                summary["unchanged"] += 1

        out_rows.append({
            "狀態": status,
            "代號": (c or p).get("code"),
            "名稱": (c or p).get("name"),
            "權重_今日(%)": (c or {}).get("weight"),
            "權重_前日(%)": (p or {}).get("weight"),
            "權重差(%)": (
                ((c or {}).get("weight") or 0.0) - ((p or {}).get("weight") or 0.0)
                if ((c or {}).get("weight") is not None or (p or {}).get("weight") is not None)
                else None
            ),
            "股數_今日": (c or {}).get("shares"),
            "股數_前日": (p or {}).get("shares"),
            "股數差": (
                ((c or {}).get("shares") or 0) - ((p or {}).get("shares") or 0)
                if ((c or {}).get("shares") is not None or (p or {}).get("shares") is not None)
                else None
            )
        })

    # Nice ordering: 新增/移除/變動/不變
    order = {"新增": 0, "移除": 1, "變動": 2, "不變": 3}
    out_rows.sort(key=lambda r: (order.get(r["狀態"], 9), str(r.get("代號") or ""), str(r.get("名稱") or "")))

    return {
        "base_date": curr_payload.get("snapshot_date"),
        "compare_date": prev_payload.get("snapshot_date"),
        "summary": summary,
        "columns": ["狀態", "代號", "名稱", "權重_今日(%)", "權重_前日(%)", "權重差(%)", "股數_今日", "股數_前日", "股數差"],
        "rows": out_rows
    }


def list_snapshots(code: str) -> List[str]:
    d = os.path.join(OUT_SNAP_DIR, code)
    if not os.path.isdir(d):
        return []
    files = [f for f in os.listdir(d) if f.endswith(".json")]
    # filenames are YYYY-MM-DD.json
    files.sort()
    return [os.path.join(d, f) for f in files]


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, payload: Dict[str, Any]) -> None:
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def main():
    ensure_dir(OUT_CURRENT_DIR)
    ensure_dir(OUT_CHANGES_DIR)
    ensure_dir(OUT_SNAP_DIR)

    with open(SOURCES_PATH, "r", encoding="utf-8") as f:
        sources = json.load(f)

    idx = {"codes": sorted(list(sources.keys())), "generated_at": datetime.now(TZ).isoformat()}

    for code, cfg in sources.items():
        data_date, columns, rows = fetch_holdings_from_source(cfg)

        snapshot_date = None
        if data_date:
            # normalize YYYY/MM/DD -> YYYY-MM-DD
            snapshot_date = data_date.replace("/", "-")
        else:
            snapshot_date = datetime.now(TZ).date().isoformat()

        curr_payload = {
            "code": code,
            "source_url": cfg["url"],
            "data_date": data_date,
            "snapshot_date": snapshot_date,
            "scraped_at": datetime.now(TZ).isoformat(),
            "columns": columns,
            "rows": rows
        }

        # write current
        save_json(os.path.join(OUT_CURRENT_DIR, f"{code}.json"), curr_payload)

        # write snapshot (keeps history)
        snap_path = os.path.join(OUT_SNAP_DIR, code, f"{snapshot_date}.json")
        if not os.path.exists(snap_path):
            save_json(snap_path, curr_payload)
        else:
            # overwrite if same day re-run
            save_json(snap_path, curr_payload)

        # compute changes from previous snapshot (if exists)
        snaps = list_snapshots(code)
        if len(snaps) >= 2:
            prev = load_json(snaps[-2])
            curr = load_json(snaps[-1])
            changes = compute_changes(prev, curr)
            save_json(os.path.join(OUT_CHANGES_DIR, f"{code}.json"), changes)
        else:
            save_json(os.path.join(OUT_CHANGES_DIR, f"{code}.json"), {
                "base_date": snapshot_date,
                "compare_date": None,
                "summary": {"added": 0, "removed": 0, "changed": 0, "unchanged": 0},
                "columns": ["提示"],
                "rows": [{"提示": "尚無變動資料（需要至少兩天快照）"}]
            })

    # write index
    save_json(os.path.join(OUT_CURRENT_DIR, "index.json"), idx)


if __name__ == "__main__":
    main()
