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
        <button class="tab active" data-view="occupations">职业清单</button>
        <button class="tab" data-view="visas">签证列表</button>
        <button class="tab" data-view="summary">汇总</button>
        <button class="tab" data-view="sources">来源</button>
      </nav>
    </div>
  </header>

  <main>
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
        ["职业清单", uniqueValues(DATA.occupations, "list_code").length],
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
      renderFilters();
      renderTable();
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

    renderMetrics();
    renderFilters();
    renderTable();
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
