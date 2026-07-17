#!/usr/bin/env python3
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "processed" / "australia_migration.db"
PREVIEW_DIR = ROOT / "preview"
PREVIEW_PATH = PREVIEW_DIR / "index.html"


def rows(conn, query):
    conn.row_factory = sqlite3.Row
    return [dict(row) for row in conn.execute(query)]


def build_payload():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    try:
        data = {
            "sources": rows(conn, "SELECT * FROM sources ORDER BY id"),
            "categories": rows(conn, "SELECT * FROM visa_categories ORDER BY sort_order"),
            "visas": rows(
                conn,
                """
                SELECT
                    v.id,
                    c.name AS category,
                    v.name,
                    v.status,
                    v.official_url,
                    COALESCE(GROUP_CONCAT(s.subclass, ', '), '') AS subclasses
                FROM visas v
                JOIN visa_categories c ON c.id = v.category_id
                LEFT JOIN visa_subclasses s ON s.visa_id = v.id
                GROUP BY v.id
                ORDER BY c.sort_order, v.id
                """,
            ),
            "occupations": rows(
                conn,
                """
                SELECT
                    id,
                    visa_subclass,
                    visa_name,
                    visa_stream,
                    list_code,
                    list_name,
                    anzsco_version,
                    occupation_title,
                    anzsco_code,
                    assessing_authority,
                    assessing_authority_expanded,
                    applicable_circumstance_code,
                    applicable_circumstance_text,
                    source_id,
                    source_table,
                    source_row
                FROM occupation_records
                ORDER BY CAST(visa_subclass AS INTEGER), visa_stream, list_code, occupation_title
                """,
            ),
            "summary": rows(conn, "SELECT * FROM visa_occupation_summary"),
        }
        # Add state nominations if the table exists
        try:
            data["state_nominations"] = rows(
                conn,
                """
                SELECT
                    id,
                    state_code,
                    state_name,
                    anzsco_code,
                    occupation_title,
                    visa_subclass,
                    stream,
                    priority,
                    conditions,
                    source_url
                FROM state_nominations
                ORDER BY state_code, occupation_title
                """,
            )
        except Exception:
            data["state_nominations"] = []
        return data
    finally:
        conn.close()


HTML_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Australia Migration Database Preview</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f7f8f5;
      --surface: #ffffff;
      --ink: #172026;
      --muted: #5e6b72;
      --line: #d7ded8;
      --accent: #176b5f;
      --accent-2: #9b3d2c;
      --focus: #2d6cdf;
      --soft: #eef4f1;
      --warn-soft: #f7eee8;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 14px;
      line-height: 1.45;
    }

    header {
      position: sticky;
      top: 0;
      z-index: 10;
      background: rgba(247, 248, 245, 0.96);
      border-bottom: 1px solid var(--line);
      backdrop-filter: blur(12px);
    }

    .topbar {
      max-width: 1480px;
      margin: 0 auto;
      padding: 16px 20px 12px;
      display: grid;
      gap: 12px;
    }

    .title-row {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 16px;
      flex-wrap: wrap;
    }

    h1 {
      margin: 0;
      font-size: 20px;
      font-weight: 720;
      letter-spacing: 0;
    }

    .meta {
      color: var(--muted);
      font-size: 13px;
    }

    .tabs {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }

    .tab {
      border: 1px solid var(--line);
      background: var(--surface);
      color: var(--ink);
      min-height: 34px;
      padding: 0 12px;
      border-radius: 8px;
      cursor: pointer;
      font: inherit;
    }

    .tab.active {
      border-color: var(--accent);
      background: var(--accent);
      color: #ffffff;
    }

    main {
      max-width: 1480px;
      margin: 0 auto;
      padding: 18px 20px 28px;
    }

    .metrics {
      display: grid;
      grid-template-columns: repeat(5, minmax(120px, 1fr));
      gap: 10px;
      margin-bottom: 14px;
    }

    .metric {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px 12px;
      min-height: 68px;
    }

    .metric b {
      display: block;
      font-size: 22px;
      line-height: 1.15;
    }

    .metric span {
      color: var(--muted);
      font-size: 12px;
    }

    .filters {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      display: grid;
      gap: 10px;
      margin-bottom: 12px;
    }

    .filter-grid {
      display: grid;
      grid-template-columns: repeat(6, minmax(140px, 1fr));
      gap: 10px;
    }

    label,
    .filter-field {
      display: grid;
      gap: 5px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 640;
    }

    .filter-label {
      color: var(--muted);
      font-size: 12px;
      font-weight: 640;
    }

    input, select {
      width: 100%;
      min-height: 36px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #ffffff;
      color: var(--ink);
      padding: 7px 9px;
      font: inherit;
    }

    .multi-filter {
      position: relative;
    }

    .multi-filter summary {
      min-height: 36px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #ffffff;
      color: var(--ink);
      padding: 8px 30px 8px 9px;
      cursor: pointer;
      list-style: none;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-weight: 400;
    }

    .multi-filter summary::-webkit-details-marker {
      display: none;
    }

    .multi-filter summary::after {
      content: "▾";
      position: absolute;
      right: 10px;
      top: 8px;
      color: var(--muted);
      font-size: 12px;
    }

    .multi-filter[open] summary {
      border-color: var(--accent);
    }

    .multi-panel {
      position: absolute;
      top: calc(100% + 4px);
      left: 0;
      right: 0;
      z-index: 20;
      max-height: 260px;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--surface);
      box-shadow: 0 14px 32px rgba(23, 32, 38, 0.16);
      padding: 6px;
    }

    .multi-actions {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
      padding: 4px 4px 8px;
      color: var(--muted);
      font-size: 11px;
      font-weight: 500;
    }

    .mini-command {
      min-height: 26px;
      border: 1px solid var(--line);
      border-radius: 5px;
      background: #ffffff;
      color: var(--ink);
      padding: 0 8px;
      cursor: pointer;
      font: inherit;
      font-size: 12px;
    }

    .check-row {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 6px 7px;
      border-radius: 6px;
      color: var(--ink);
      font-size: 13px;
      font-weight: 400;
      cursor: pointer;
    }

    .check-row:hover {
      background: var(--soft);
    }

    .check-row input {
      width: 16px;
      min-height: 16px;
      padding: 0;
      accent-color: var(--accent);
      flex: 0 0 auto;
    }

    .check-row span {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    input:focus, select:focus, button:focus {
      outline: 2px solid var(--focus);
      outline-offset: 1px;
    }

    .actions {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
    }

    .button-row {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }

    button.command {
      min-height: 36px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #ffffff;
      color: var(--ink);
      padding: 0 12px;
      cursor: pointer;
      font: inherit;
    }

    button.command.primary {
      border-color: var(--accent);
      background: var(--accent);
      color: #ffffff;
    }

    .table-shell {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }

    .table-meta {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      color: var(--muted);
      flex-wrap: wrap;
    }

    .table-wrap {
      overflow: auto;
      max-height: calc(100vh - 310px);
    }

    table {
      width: 100%;
      border-collapse: collapse;
      min-width: 980px;
    }

    th, td {
      padding: 9px 10px;
      border-bottom: 1px solid #e7ece8;
      text-align: left;
      vertical-align: top;
      white-space: nowrap;
    }

    td.wrap {
      white-space: normal;
      min-width: 220px;
      max-width: 460px;
    }

    th {
      position: sticky;
      top: 0;
      z-index: 2;
      background: #eef4f1;
      color: #243137;
      font-size: 12px;
      font-weight: 760;
      cursor: pointer;
      user-select: none;
    }

    tr:hover td {
      background: #fbfcfa;
    }

    .pill {
      display: inline-flex;
      align-items: center;
      min-height: 22px;
      border-radius: 999px;
      padding: 2px 8px;
      background: var(--soft);
      color: #184d45;
      border: 1px solid #cce0d9;
      font-size: 12px;
      font-weight: 680;
    }

    .pill.warn {
      background: var(--warn-soft);
      color: var(--accent-2);
      border-color: #e6cfc4;
    }

    a {
      color: #195d8b;
      text-decoration: none;
    }

    a:hover {
      text-decoration: underline;
    }

    .hidden {
      display: none !important;
    }

    .guide-box {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 20px 24px;
      margin-bottom: 16px;
    }

    .guide-box h2 {
      margin: 0 0 16px;
      font-size: 16px;
      font-weight: 700;
    }

    .guide-steps {
      display: grid;
      gap: 14px;
    }

    .step {
      display: flex;
      gap: 14px;
      align-items: flex-start;
    }

    .step-num {
      flex: 0 0 28px;
      height: 28px;
      background: var(--accent);
      color: #fff;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 13px;
      font-weight: 700;
    }

    .step-content b {
      display: block;
      margin-bottom: 4px;
    }

    .step-content p {
      margin: 0;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
    }

    .lookup-box {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 20px 24px;
    }

    .lookup-box h2 {
      margin: 0 0 14px;
      font-size: 16px;
      font-weight: 700;
    }

    .lookup-input-row {
      display: flex;
      gap: 10px;
      margin-bottom: 16px;
    }

    .lookup-input-row input {
      flex: 1;
    }

    .result-card {
      background: var(--bg);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px 20px;
      margin-bottom: 12px;
    }

    .result-card h3 {
      margin: 0 0 4px;
      font-size: 15px;
      font-weight: 700;
    }

    .result-card .anzsco-badge {
      display: inline-block;
      background: var(--accent);
      color: #fff;
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 12px;
      font-weight: 600;
      margin-left: 8px;
    }

    .result-section {
      margin-top: 14px;
    }

    .result-section h4 {
      margin: 0 0 8px;
      font-size: 13px;
      font-weight: 700;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }

    .visa-paths {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
      gap: 8px;
    }

    .visa-path-item {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px 12px;
    }

    .visa-path-item .subclass {
      font-weight: 700;
      color: var(--accent);
    }

    .visa-path-item .list-name {
      font-size: 12px;
      color: var(--muted);
    }

    .state-chips {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }

    .state-chip {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      background: var(--soft);
      border: 1px solid #cce0d9;
      border-radius: 6px;
      padding: 6px 10px;
      font-size: 13px;
    }

    .state-chip .state-label {
      font-weight: 600;
    }

    .state-chip .visa-label {
      font-size: 11px;
      color: var(--muted);
    }

    .assessor-info {
      font-size: 13px;
      color: var(--ink);
    }

    .no-results {
      color: var(--muted);
      font-size: 14px;
      padding: 12px 0;
    }

    .empty {
      padding: 28px;
      text-align: center;
      color: var(--muted);
    }

    @media (max-width: 1100px) {
      .metrics { grid-template-columns: repeat(2, minmax(120px, 1fr)); }
      .filter-grid { grid-template-columns: repeat(2, minmax(140px, 1fr)); }
    }

    @media (max-width: 640px) {
      .topbar, main { padding-left: 12px; padding-right: 12px; }
      .metrics { grid-template-columns: 1fr; }
      .filter-grid { grid-template-columns: 1fr; }
      .table-wrap { max-height: none; }
      th, td { padding: 8px; }
    }
  </style>
</head>
<body>
  <header>
    <div class="topbar">
      <div class="title-row">
        <h1>Australia Migration Database</h1>
        <div class="meta" id="sourceMeta"></div>
      </div>
      <nav class="tabs" aria-label="views">
        <button class="tab active" data-view="lookup">职业查询</button>
        <button class="tab" data-view="occupations">联邦职业清单</button>
        <button class="tab" data-view="state_nominations">州提名</button>
        <button class="tab" data-view="visas">签证列表</button>
        <button class="tab" data-view="summary">汇总</button>
        <button class="tab" data-view="sources">来源</button>
      </nav>
    </div>
  </header>

  <main>
    <!-- Lookup view (default) -->
    <section id="lookupView">
      <div class="guide-box">
        <h2>澳洲技术移民签证逻辑</h2>
        <div class="guide-steps">
          <div class="step">
            <div class="step-num">1</div>
            <div class="step-content">
              <b>确认职业在清单上</b>
              <p>联邦政府维护多份职业清单（MLTSSL、STSOL、CSOL、ROL），你的职业必须在对应清单上才能申请对应签证。</p>
            </div>
          </div>
          <div class="step">
            <div class="step-num">2</div>
            <div class="step-content">
              <b>完成职业评估</b>
              <p>每个职业有指定的评估机构（如 Engineers Australia、ACS、VETASSESS 等），需要通过评估证明你的学历和工作经验符合要求。</p>
            </div>
          </div>
          <div class="step">
            <div class="step-num">3</div>
            <div class="step-content">
              <b>选择签证通道</b>
              <p><b>189</b> 独立技术移民（无需州担保，凑分制）<br>
                 <b>190</b> 州担保（需要州/领地提名，+5分）<br>
                 <b>491</b> 偏远地区州担保（+15分，需在偏远地区生活工作）<br>
                 <b>482</b> 雇主担保工作签<br>
                 <b>186</b> 雇主担保永居<br>
                 <b>494</b> 偏远地区雇主担保</p>
            </div>
          </div>
          <div class="step">
            <div class="step-num">4</div>
            <div class="step-content">
              <b>州提名（190/491）</b>
              <p>如果走州担保路线，需要确认目标州是否在提名你的职业。每个州有自己的优先清单和额外要求。</p>
            </div>
          </div>
        </div>
      </div>

      <div class="lookup-box">
        <h2>输入你的职业，查看完整路径</h2>
        <div class="lookup-input-row">
          <input type="text" id="lookupInput" placeholder="输入职业名称或 ANZSCO 代码，如 software engineer 或 261313" autocomplete="off">
          <button class="command primary" id="lookupBtn">查询</button>
        </div>
        <div id="lookupResults"></div>
      </div>
    </section>

    <!-- Data browser views (hidden by default) -->
    <section id="dataView" class="hidden">
      <section class="metrics" id="metrics"></section>

      <section class="filters">
        <div class="filter-grid" id="filterGrid"></div>
        <div class="actions">
          <div class="meta" id="resultLabel"></div>
          <div class="button-row">
            <button class="command" id="resetBtn">重置筛选</button>
            <button class="command primary" id="exportBtn">导出当前结果</button>
          </div>
        </div>
      </section>

      <section class="table-shell">
        <div class="table-meta">
          <div id="tableTitle"></div>
          <label style="display:flex; align-items:center; gap:8px; grid-auto-flow:column;">
            每页
            <select id="pageSize" style="width:88px;">
              <option value="50">50</option>
              <option value="100" selected>100</option>
              <option value="250">250</option>
              <option value="100000">全部</option>
            </select>
          </label>
        </div>
        <div class="table-wrap" id="tableWrap"></div>
        <div class="table-meta">
          <div id="pageLabel"></div>
          <div class="button-row">
            <button class="command" id="prevBtn">上一页</button>
            <button class="command" id="nextBtn">下一页</button>
          </div>
        </div>
      </section>
    </section>
  </main>

  <script id="db-data" type="application/json">__DATA_JSON__</script>
  <script>
    const DATA = JSON.parse(document.getElementById("db-data").textContent);

    const views = {
      occupations: {
        title: "职业清单记录",
        rows: DATA.occupations,
        searchable: ["occupation_title", "anzsco_code", "visa_subclass", "visa_name", "visa_stream", "assessing_authority", "applicable_circumstance_text"],
        filters: [
          { key: "q", type: "search", label: "搜索" },
          { key: "visa_subclass", label: "Subclass" },
          { key: "list_code", label: "职业清单" },
          { key: "visa_stream", label: "Stream" },
          { key: "anzsco_version", label: "ANZSCO" },
          { key: "source_id", label: "来源" }
        ],
        columns: [
          ["visa_subclass", "Subclass"],
          ["visa_stream", "Stream"],
          ["list_code", "清单"],
          ["occupation_title", "职业", "wrap"],
          ["anzsco_code", "ANZSCO"],
          ["assessing_authority", "评估机构"],
          ["applicable_circumstance_code", "条件"],
          ["source_id", "来源"]
        ]
      },
      visas: {
        title: "签证列表",
        rows: DATA.visas,
        searchable: ["name", "category", "subclasses", "status"],
        filters: [
          { key: "q", type: "search", label: "搜索" },
          { key: "category", label: "类型" },
          { key: "status", label: "状态" },
          { key: "subclasses", label: "Subclass" }
        ],
        columns: [
          ["category", "类型"],
          ["name", "签证", "wrap"],
          ["subclasses", "Subclass"],
          ["status", "状态"],
          ["official_url", "官方链接", "link"]
        ]
      },
      summary: {
        title: "职业清单汇总",
        rows: DATA.summary,
        searchable: ["visa_subclass", "visa_name", "visa_stream", "list_code", "list_name"],
        filters: [
          { key: "q", type: "search", label: "搜索" },
          { key: "visa_subclass", label: "Subclass" },
          { key: "list_code", label: "职业清单" }
        ],
        columns: [
          ["visa_subclass", "Subclass"],
          ["visa_name", "签证", "wrap"],
          ["visa_stream", "Stream"],
          ["list_code", "清单"],
          ["occupation_count", "记录数"]
        ]
      },
      sources: {
        title: "官方来源",
        rows: DATA.sources,
        searchable: ["id", "title", "publisher", "source_type", "register_id", "official_url"],
        filters: [
          { key: "q", type: "search", label: "搜索" },
          { key: "source_type", label: "来源类型" },
          { key: "publisher", label: "发布方" }
        ],
        columns: [
          ["id", "ID"],
          ["title", "标题", "wrap"],
          ["source_type", "类型"],
          ["register_id", "Register ID"],
          ["effective_from", "生效日"],
          ["official_url", "官方链接", "link"]
        ]
      },
      state_nominations: {
        title: "州/领地职业提名清单",
        rows: DATA.state_nominations || [],
        searchable: ["occupation_title", "anzsco_code", "state_name", "visa_subclass", "priority", "conditions"],
        filters: [
          { key: "q", type: "search", label: "搜索" },
          { key: "state_name", label: "州/领地" },
          { key: "visa_subclass", label: "签证" },
          { key: "priority", label: "优先级" }
        ],
        columns: [
          ["state_name", "州/领地"],
          ["anzsco_code", "ANZSCO"],
          ["occupation_title", "职业", "wrap"],
          ["visa_subclass", "签证"],
          ["priority", "优先级"],
          ["conditions", "备注", "wrap"],
          ["source_url", "来源", "link"]
        ]
      }
    };

    const state = {
      view: "occupations",
      filters: {},
      sortKey: null,
      sortDir: "asc",
      page: 1,
      pageSize: 100
    };

    const el = (id) => document.getElementById(id);
    const value = (row, key) => row[key] == null ? "" : String(row[key]);

    function uniqueValues(rows, key) {
      const set = new Set();
      rows.forEach(row => {
        if (key === "subclasses") {
          value(row, key).split(",").map(x => x.trim()).filter(Boolean).forEach(x => set.add(x));
        } else {
          const v = value(row, key).trim();
          if (v) set.add(v);
        }
      });
      return Array.from(set).sort((a, b) => {
        const na = Number(a), nb = Number(b);
        if (!Number.isNaN(na) && !Number.isNaN(nb)) return na - nb;
        return a.localeCompare(b);
      });
    }

    function renderMetrics() {
      const metrics = [
        ["签证条目", DATA.visas.length],
        ["Subclass", uniqueValues(DATA.visas, "subclasses").length],
        ["职业记录", DATA.occupations.length],
        ["州提名", (DATA.state_nominations || []).length],
        ["官方来源", DATA.sources.length]
      ];
      el("metrics").innerHTML = metrics.map(([label, count]) => (
        `<div class="metric"><b>${count.toLocaleString()}</b><span>${label}</span></div>`
      )).join("");
      const retrieved = DATA.sources.map(s => s.retrieved_at).filter(Boolean).sort().pop();
      el("sourceMeta").textContent = retrieved ? `Snapshot ${retrieved.replace("T", " ")}` : "";
    }

    function renderFilters() {
      const config = views[state.view];
      el("filterGrid").innerHTML = config.filters.map(filter => {
        if (filter.type === "search") {
          const current = state.filters[filter.key] || "";
          return `<label>${filter.label}<input data-filter="${filter.key}" value="${escapeAttr(current)}" placeholder="关键词、代码、签证名"></label>`;
        }
        const current = selectedValues(filter.key);
        const options = uniqueValues(config.rows, filter.key).map(v => {
          const checked = current.includes(v) ? " checked" : "";
          return `<label class="check-row"><input type="checkbox" data-filter="${filter.key}" value="${escapeAttr(v)}"${checked}><span title="${escapeAttr(v)}">${escapeHtml(v)}</span></label>`;
        }).join("");
        return `<div class="filter-field"><div class="filter-label">${escapeHtml(filter.label)}</div><details class="multi-filter" data-filter-box="${filter.key}"><summary>${escapeHtml(filterSummary(current))}</summary><div class="multi-panel"><div class="multi-actions"><button type="button" class="mini-command" data-clear-filter="${filter.key}">清空</button><span>可多选</span></div>${options}</div></details></div>`;
      }).join("");

      document.querySelectorAll("[data-filter]").forEach(input => {
        const eventName = input.type === "checkbox" ? "change" : "input";
        input.addEventListener(eventName, () => {
          if (input.type === "checkbox") {
            syncMultiFilter(input.dataset.filter);
            updateMultiSummary(input.dataset.filter);
          } else {
            state.filters[input.dataset.filter] = input.value;
          }
          state.page = 1;
          renderTable();
        });
      });
      document.querySelectorAll("[data-clear-filter]").forEach(button => {
        button.addEventListener("click", (event) => {
          event.preventDefault();
          event.stopPropagation();
          const key = button.dataset.clearFilter;
          document.querySelectorAll(`input[type="checkbox"][data-filter="${key}"]`).forEach(input => {
            input.checked = false;
          });
          delete state.filters[key];
          updateMultiSummary(key);
          state.page = 1;
          renderTable();
        });
      });
      document.querySelectorAll(".multi-filter").forEach(box => {
        box.addEventListener("toggle", () => {
          if (box.open) closeMultiFilters(box);
        });
      });
    }

    function filteredRows() {
      const config = views[state.view];
      let rows = config.rows.slice();
      for (const filter of config.filters) {
        const picked = state.filters[filter.key];
        if (filter.key === "q") {
          if (!picked) continue;
          const needle = picked.toLowerCase();
          rows = rows.filter(row => config.searchable.some(key => value(row, key).toLowerCase().includes(needle)));
        } else if (filter.key === "subclasses") {
          const selected = selectedValues(filter.key);
          if (!selected.length) continue;
          rows = rows.filter(row => {
            const rowValues = value(row, filter.key).split(",").map(x => x.trim());
            return selected.some(item => rowValues.includes(item));
          });
        } else {
          const selected = selectedValues(filter.key);
          if (!selected.length) continue;
          rows = rows.filter(row => selected.includes(value(row, filter.key)));
        }
      }
      if (state.sortKey) {
        rows.sort((a, b) => compareValues(value(a, state.sortKey), value(b, state.sortKey)) * (state.sortDir === "asc" ? 1 : -1));
      }
      return rows;
    }

    function selectedValues(key) {
      const picked = state.filters[key];
      if (!picked) return [];
      return Array.isArray(picked) ? picked : [picked];
    }

    function syncMultiFilter(key) {
      const values = Array.from(document.querySelectorAll(`input[type="checkbox"][data-filter="${key}"]:checked`)).map(input => input.value);
      if (values.length) state.filters[key] = values;
      else delete state.filters[key];
    }

    function filterSummary(values) {
      if (!values.length) return "全部";
      if (values.length <= 2) return values.join(", ");
      return `${values.slice(0, 2).join(", ")} +${values.length - 2}`;
    }

    function updateMultiSummary(key) {
      const box = document.querySelector(`[data-filter-box="${key}"]`);
      if (!box) return;
      const summary = box.querySelector("summary");
      summary.textContent = filterSummary(selectedValues(key));
    }

    function closeMultiFilters(except = null) {
      document.querySelectorAll(".multi-filter[open]").forEach(box => {
        if (box !== except) box.open = false;
      });
    }

    function compareValues(a, b) {
      const na = Number(a), nb = Number(b);
      if (a !== "" && b !== "" && !Number.isNaN(na) && !Number.isNaN(nb)) return na - nb;
      return a.localeCompare(b);
    }

    function renderCell(row, col) {
      const [key, label, mode] = col;
      const raw = value(row, key);
      if (mode === "link" && raw) {
        return `<a href="${escapeAttr(raw)}" target="_blank" rel="noopener">打开</a>`;
      }
      if (key === "status") {
        return `<span class="pill ${raw === "repealed" ? "warn" : ""}">${escapeHtml(raw || "-")}</span>`;
      }
      if (["list_code", "visa_subclass", "anzsco_code"].includes(key) && raw) {
        return `<span class="pill">${escapeHtml(raw)}</span>`;
      }
      return escapeHtml(raw || "-");
    }

    function renderTable() {
      const config = views[state.view];
      const rows = filteredRows();
      const totalPages = Math.max(1, Math.ceil(rows.length / state.pageSize));
      if (state.page > totalPages) state.page = totalPages;
      const start = (state.page - 1) * state.pageSize;
      const pageRows = rows.slice(start, start + state.pageSize);

      el("tableTitle").textContent = config.title;
      el("resultLabel").textContent = `${rows.length.toLocaleString()} 条结果`;
      el("pageLabel").textContent = `${state.page} / ${totalPages}`;
      el("prevBtn").disabled = state.page <= 1;
      el("nextBtn").disabled = state.page >= totalPages;

      if (!pageRows.length) {
        el("tableWrap").innerHTML = `<div class="empty">没有匹配结果</div>`;
        return;
      }

      const headers = config.columns.map(([key, label]) => {
        const mark = state.sortKey === key ? (state.sortDir === "asc" ? " ↑" : " ↓") : "";
        return `<th data-sort="${key}">${escapeHtml(label + mark)}</th>`;
      }).join("");
      const body = pageRows.map(row => {
        const cells = config.columns.map(col => {
          const mode = col[2];
          return `<td class="${mode === "wrap" ? "wrap" : ""}">${renderCell(row, col)}</td>`;
        }).join("");
        return `<tr>${cells}</tr>`;
      }).join("");
      el("tableWrap").innerHTML = `<table><thead><tr>${headers}</tr></thead><tbody>${body}</tbody></table>`;

      document.querySelectorAll("[data-sort]").forEach(th => {
        th.addEventListener("click", () => {
          const key = th.dataset.sort;
          if (state.sortKey === key) state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
          else {
            state.sortKey = key;
            state.sortDir = "asc";
          }
          renderTable();
        });
      });
    }

    function switchView(view) {
      state.view = view;
      state.filters = {};
      state.sortKey = null;
      state.sortDir = "asc";
      state.page = 1;
      document.querySelectorAll(".tab").forEach(tab => tab.classList.toggle("active", tab.dataset.view === view));

      if (view === "lookup") {
        el("lookupView").classList.remove("hidden");
        el("dataView").classList.add("hidden");
      } else {
        el("lookupView").classList.add("hidden");
        el("dataView").classList.remove("hidden");
        renderMetrics();
        renderFilters();
        renderTable();
      }
    }

    function exportCsv() {
      const config = views[state.view];
      const rows = filteredRows();
      const columns = config.columns.map(col => col[0]);
      const csvRows = [columns.join(",")].concat(rows.map(row => columns.map(key => csvEscape(value(row, key))).join(",")));
      const blob = new Blob([csvRows.join("\\n")], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${state.view}_filtered.csv`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    }

    function csvEscape(text) {
      return `"${String(text).replaceAll('"', '""')}"`;
    }

    function escapeHtml(text) {
      return String(text).replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[ch]));
    }

    function escapeAttr(text) {
      return escapeHtml(text);
    }

    document.querySelectorAll(".tab").forEach(tab => tab.addEventListener("click", () => switchView(tab.dataset.view)));
    el("resetBtn").addEventListener("click", () => {
      state.filters = {};
      state.page = 1;
      renderFilters();
      renderTable();
    });
    el("exportBtn").addEventListener("click", exportCsv);
    el("prevBtn").addEventListener("click", () => {
      if (state.page > 1) {
        state.page -= 1;
        renderTable();
      }
    });
    el("nextBtn").addEventListener("click", () => {
      state.page += 1;
      renderTable();
    });
    el("pageSize").addEventListener("change", (event) => {
      state.pageSize = Number(event.target.value);
      state.page = 1;
      renderTable();
    });
    document.addEventListener("click", (event) => {
      if (!event.target.closest(".multi-filter")) closeMultiFilters();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeMultiFilters();
    });

    // --- Lookup logic ---
    function doLookup() {
      const query = el("lookupInput").value.trim().toLowerCase();
      if (!query) {
        el("lookupResults").innerHTML = "";
        return;
      }

      // Search federal occupation records
      const matches = DATA.occupations.filter(row => {
        return row.occupation_title.toLowerCase().includes(query)
          || row.anzsco_code.includes(query);
      });

      // Group by ANZSCO code + title
      const grouped = {};
      matches.forEach(row => {
        const key = row.anzsco_code;
        if (!grouped[key]) {
          grouped[key] = {
            code: row.anzsco_code,
            title: row.occupation_title,
            visas: [],
            assessors: new Set()
          };
        }
        grouped[key].visas.push(row);
        if (row.assessing_authority) grouped[key].assessors.add(row.assessing_authority);
      });

      // Also search state nominations (including 4-digit unit group match)
      const stateNoms = (DATA.state_nominations || []).filter(row => {
        return row.occupation_title.toLowerCase().includes(query)
          || row.anzsco_code.includes(query);
      });

      // Match state nominations by code prefix for NSW 4-digit codes
      const stateByCode = {};
      stateNoms.forEach(row => {
        const key = row.anzsco_code;
        if (!stateByCode[key]) stateByCode[key] = [];
        stateByCode[key].push(row);
      });

      if (Object.keys(grouped).length === 0 && stateNoms.length === 0) {
        el("lookupResults").innerHTML = `<div class="no-results">没有找到匹配「${escapeHtml(query)}」的职业。试试英文名称或 ANZSCO 代码。</div>`;
        return;
      }

      let html = "";
      for (const [code, info] of Object.entries(grouped)) {
        // Find matching state nominations (exact 6-digit or 4-digit prefix)
        const relatedStates = (DATA.state_nominations || []).filter(sn => {
          if (sn.anzsco_code === code) return true;
          if (sn.anzsco_code.length === 4 && code.startsWith(sn.anzsco_code)) return true;
          return false;
        });

        // Visa paths - deduplicate by subclass+stream
        const visaMap = {};
        info.visas.forEach(v => {
          const vkey = v.visa_subclass + "|" + (v.visa_stream || "");
          if (!visaMap[vkey]) visaMap[vkey] = v;
        });

        html += `<div class="result-card">`;
        html += `<h3>${escapeHtml(info.title)}<span class="anzsco-badge">${escapeHtml(code)}</span></h3>`;

        // Assessing authorities
        if (info.assessors.size) {
          html += `<div class="result-section"><h4>职业评估机构</h4>`;
          html += `<div class="assessor-info">${Array.from(info.assessors).map(a => escapeHtml(a)).join(" / ")}</div>`;
          html += `</div>`;
        }

        // Visa pathways
        html += `<div class="result-section"><h4>可申请签证</h4><div class="visa-paths">`;
        for (const v of Object.values(visaMap)) {
          html += `<div class="visa-path-item">`;
          html += `<div><span class="subclass">${escapeHtml(v.visa_subclass)}</span> ${escapeHtml(v.visa_name || "")}</div>`;
          html += `<div class="list-name">${escapeHtml(v.list_code || "")}${v.visa_stream ? " · " + escapeHtml(v.visa_stream) : ""}</div>`;
          html += `</div>`;
        }
        html += `</div></div>`;

        // State nominations
        if (relatedStates.length) {
          html += `<div class="result-section"><h4>州/领地提名</h4><div class="state-chips">`;
          relatedStates.forEach(sn => {
            html += `<div class="state-chip"><span class="state-label">${escapeHtml(sn.state_name)}</span><span class="visa-label">${escapeHtml(sn.visa_subclass || "")}</span></div>`;
          });
          html += `</div></div>`;
        } else {
          html += `<div class="result-section"><h4>州/领地提名</h4><div class="no-results">暂无州提名数据（目前仅收录 NSW、QLD）</div></div>`;
        }

        html += `</div>`;
      }

      // Show state-only results (4-digit codes not matched above)
      const shownCodes = new Set(Object.keys(grouped));
      const extraStates = stateNoms.filter(sn => {
        if (shownCodes.has(sn.anzsco_code)) return false;
        for (const code of shownCodes) {
          if (code.startsWith(sn.anzsco_code)) return false;
        }
        return true;
      });

      if (extraStates.length && Object.keys(grouped).length === 0) {
        html += `<div class="result-card"><h3>州提名匹配结果</h3>`;
        html += `<div class="result-section"><div class="state-chips">`;
        extraStates.forEach(sn => {
          html += `<div class="state-chip"><span class="state-label">${escapeHtml(sn.state_name)}</span> ${escapeHtml(sn.occupation_title)} <span class="visa-label">${escapeHtml(sn.anzsco_code)} · ${escapeHtml(sn.visa_subclass || "")}</span></div>`;
        });
        html += `</div></div></div>`;
      }

      el("lookupResults").innerHTML = html;
    }

    el("lookupBtn").addEventListener("click", doLookup);
    el("lookupInput").addEventListener("keydown", (event) => {
      if (event.key === "Enter") doLookup();
    });

    // Start on lookup view - don't render data view initially
    el("lookupView").classList.remove("hidden");
    el("dataView").classList.add("hidden");
  </script>
</body>
</html>
"""


def main():
    payload = build_payload()
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    data_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    PREVIEW_PATH.write_text(HTML_TEMPLATE.replace("__DATA_JSON__", data_json), encoding="utf-8")
    print(PREVIEW_PATH)


if __name__ == "__main__":
    main()
