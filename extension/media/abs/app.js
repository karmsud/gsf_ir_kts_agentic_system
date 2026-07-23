/* ABS Waterfall — WebView front-end SPA.
   Talks to the extension via postMessage; the extension forwards commands to the
   Python backend (dispatcher) and bridges LLM calls to GitHub Copilot. */
(function () {
  "use strict";
  const vscode = acquireVsCodeApi();

  // ── Message bus (correlated request/response) ─────────────────
  let seq = 0;
  const pending = new Map();
  const progressHandlers = new Map();

  function dispatch(command, params, onProgress, timeoutMs) {
    const id = "ui" + ++seq;
    if (onProgress) progressHandlers.set(id, onProgress);
    return new Promise((resolve) => {
      let timer;
      const finish = (result) => {
        if (timer) clearTimeout(timer);
        pending.delete(id);
        progressHandlers.delete(id);
        resolve(result);
      };
      pending.set(id, finish);
      const ms = timeoutMs !== undefined ? timeoutMs : 60000;
      if (ms > 0) {
        timer = setTimeout(() => {
          finish({ ok: false, error: "timeout", command });
        }, ms);
      }
      vscode.postMessage({ type: "command", id, command, params: params || {} });
    });
  }
  function callExtension(type, payload) {
    const id = "ext" + ++seq;
    return new Promise((resolve) => {
      pending.set(id, resolve);
      vscode.postMessage({ type, id, ...(payload || {}) });
    });
  }

  window.addEventListener("message", (e) => {
    const msg = e.data || {};
    if (msg.type === "result" && pending.has(msg.id)) {
      pending.get(msg.id)(msg.result);
      pending.delete(msg.id);
      progressHandlers.delete(msg.id);
    } else if (msg.type === "extResult" && pending.has(msg.id)) {
      pending.get(msg.id)(msg.result);
      pending.delete(msg.id);
    } else if (msg.type === "progress" && progressHandlers.has(msg.id)) {
      progressHandlers.get(msg.id)(msg.event);
    } else if (msg.type === "toast") {
      toast(msg.message);
    } else if (msg.type === "init") {
      state.dealsRoot = msg.dealsRoot;
      boot();
    }
  });

  // ── State ─────────────────────────────────────────────────────
  const state = { deals: [], dealId: null, tab: "overview", status: null };

  const TABS = [
    ["overview", "◎", "Overview"],
    ["portfolio", "⊞", "Portfolio"],
    ["ingest", "⤓", "Ingest"],
    ["definitions", "¶", "Definitions"],
    ["seps", "⊞", "Artifacts (SEPs)"],
    ["governing", "§", "Governing Doc"],
    ["model", "{ }", "Payment Model"],
    ["qa", "✶", "Q&A & Explain"],
    ["reports", "▤", "Reports"],
    ["governance", "⚡", "Governance"],
    ["agents", "⚙", "Agents"],
    ["ops", "◎", "Ops Center"],
    ["scenarios", "∿", "Scenarios"],
    ["lifecycle", "⏱", "Lifecycle"],
    ["tax", "¥", "Tax"],
    ["jobs", "⟳", "Jobs"],
    ["lineage", "◈", "Lineage"],
    ["setup_preview", "✦", "Setup Preview"],
  ];

  // ── Helpers ───────────────────────────────────────────────────
  const $ = (sel, root) => (root || document).querySelector(sel);
  function el(tag, attrs, kids) {
    const n = document.createElement(tag);
    if (attrs) for (const k in attrs) {
      if (k === "class") n.className = attrs[k];
      else if (k === "html") n.innerHTML = attrs[k];
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), attrs[k]);
      else n.setAttribute(k, attrs[k]);
    }
    (kids || []).forEach((c) => n.appendChild(typeof c === "string" ? document.createTextNode(c) : c));
    return n;
  }
  function badge(status) {
    return el("span", { class: "badge " + status }, [status.replace("_", " ")]);
  }
  function toast(message) {
    const t = el("div", { class: "toast" }, [message]);
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 2600);
  }
  function esc(s) { const d = document.createElement("div"); d.textContent = s == null ? "" : String(s); return d.innerHTML; }

  // ── Source drawer (citation jump-to-source) ───────────────────
  async function showSource(ci) {
    const params = { deal_id: state.dealId };
    if (ci && ci.chunk_id) params.chunk_id = ci.chunk_id;
    else if (ci && ci.section_id) params.section_id = ci.section_id;
    else { toast((ci && ci.citation) || "No linked source"); return; }
    openDrawer(el("div", null, [el("span", { class: "spinner" }), " Loading source…"]));
    const res = await dispatch("source.get", params);
    if (!res || !res.ok) { openDrawer(el("div", { class: "muted" }, ["Source not found."])); return; }
    renderSource(res.data, ci && ci.citation);
  }
  function openDrawer(contentNode) {
    closeDrawer();
    const scrim = el("div", { class: "drawer-scrim", id: "drawerScrim", onclick: closeDrawer });
    const drawer = el("div", { class: "drawer", id: "drawer" });
    const head = el("div", { class: "drawer-head" }, [
      el("div", { class: "t" }, ["Source"]),
      el("div", { class: "x", onclick: closeDrawer }, ["\u00d7"]),
    ]);
    const body = el("div", { class: "drawer-body", id: "drawerBody" }, [contentNode]);
    drawer.appendChild(head); drawer.appendChild(body);
    document.body.appendChild(scrim); document.body.appendChild(drawer);
  }
  function closeDrawer() {
    ["drawer", "drawerScrim"].forEach((id) => { const n = document.getElementById(id); if (n) n.remove(); });
  }
  function renderSource(d, citation) {
    const body = document.getElementById("drawerBody");
    if (!body) return;
    body.innerHTML = "";
    const title = (d.doc_title || "Document") + (d.section_path ? " — " + d.section_path : "");
    body.appendChild(el("div", { class: "t", style: "font-weight:650;font-size:14px" }, [title]));
    const meta = el("div", { style: "margin-top:8px" });
    if (d.page_start) meta.appendChild(el("span", { class: "page-badge" }, ["Page " + d.page_start + (d.page_end && d.page_end !== d.page_start ? "–" + d.page_end : "")]));
    body.appendChild(meta);
    if (d.source_path) {
      body.appendChild(el("div", { class: "row", style: "margin-top:12px" }, [
        el("button", { class: "btn small", onclick: () => callExtension("openFile", { path: d.source_path }) }, ["Open PDF"]),
      ]));
    }
    body.appendChild(el("div", { class: "src-text" }, [d.text || "(no text)"]));
  }

  // ── Boot ──────────────────────────────────────────────────────
  async function boot() {
    const res = await dispatch("deal.list", {}, undefined, 15000);
    state.deals = (res && res.ok && res.data) || [];
    if (state.deals.length && !state.dealId) state.dealId = state.deals[0].deal_id;
    if (state.dealId) await refreshStatus();
    render();
  }
  async function refreshStatus() {
    const res = await dispatch("deal.status", { deal_id: state.dealId }, undefined, 15000);
    state.status = res && res.ok ? res.data : null;
  }

  // ── Render shell ──────────────────────────────────────────────
  function render() {
    const app = $("#app");
    app.innerHTML = "";
    app.appendChild(renderNav());
    const main = el("div", { class: "main" });
    main.appendChild(renderTopbar());
    const content = el("div", { class: "content", id: "content" });
    main.appendChild(content);
    app.appendChild(main);
    renderTab(content);
  }

  function renderNav() {
    const nav = el("div", { class: "nav" });
    nav.appendChild(el("div", { class: "brand" }, [
      el("div", { class: "logo" }, ["A"]),
      el("div", { class: "title" }, ["ABS Waterfall"]),
    ]));

    const switcher = el("div", { class: "deal-switcher" });
    if (state.deals.length) {
      const sel = el("select", {
        onchange: async (e) => { state.dealId = e.target.value; await refreshStatus(); render(); },
      });
      state.deals.forEach((d) => {
        const o = el("option", { value: d.deal_id }, [d.deal_id]);
        if (d.deal_id === state.dealId) o.selected = true;
        sel.appendChild(o);
      });
      switcher.appendChild(sel);
    } else {
      switcher.appendChild(el("span", { class: "muted" }, ["No deals yet"]));
    }
    nav.appendChild(switcher);
    nav.appendChild(el("button", { class: "btn small ghost", style: "margin:0 4px 8px;", onclick: newDeal }, ["+ New Deal"]));

    nav.appendChild(el("div", { class: "nav-section" }, ["Workspaces"]));
    TABS.forEach(([id, ico, label]) => {
      nav.appendChild(el("div", {
        class: "nav-item" + (state.tab === id ? " active" : ""),
        onclick: () => { state.tab = id; render(); },
      }, [el("span", { class: "ico" }, [ico]), el("span", null, [label])]));
    });

    nav.appendChild(el("div", { class: "nav-section" }, ["Agents"]));
    nav.appendChild(el("div", { class: "nav-item", onclick: () => callExtension("openLogs") },
      [el("span", { class: "ico" }, ["≡"]), el("span", null, ["Open Logs"])]));
    nav.appendChild(el("div", { class: "nav-item", onclick: () => askCopilot("Summarize this deal\u2019s structure and key risks.") },
      [el("span", { class: "ico" }, ["✶"]), el("span", null, ["Ask Copilot"])]));
    // Quick pre-made prompts for common questions
    const QUICK = [
      ["Fees summary", "List all fees in this deal with their formulas and payment frequency."],
      ["Waterfall order", "Explain the priority of payments waterfall step by step."],
      ["Certificates", "List all certificate classes with CUSIP, balance and rate."],
      ["Explain last run", "Explain the latest monthly distribution results for every class."],
    ];
    nav.appendChild(el("div", { class: "nav-section" }, ["Quick Ask"]));
    QUICK.forEach(([label, prompt]) =>
      nav.appendChild(el("div", { class: "nav-item", onclick: () => askCopilot(prompt) },
        [el("span", { class: "ico" }, ["↵"]), el("span", null, [label])]))
    );
    return nav;
  }

  function renderTopbar() {
    const tab = TABS.find((t) => t[0] === state.tab);
    const bar = el("div", { class: "topbar" });
    bar.appendChild(el("div", null, [
      el("h1", null, [tab ? tab[2] : "ABS Waterfall"]),
      el("div", { class: "sub" }, [state.dealId ? "Deal: " + state.dealId : "Create or select a deal to begin"]),
    ]));
    bar.appendChild(el("div", { class: "assurance" }, [
      el("span", { class: "chip" }, ["Traceable"]), el("span", { class: "chip" }, ["Explainable"]),
      el("span", { class: "chip" }, ["Audited"]),
    ]));
    return bar;
  }

  // ── Tab dispatch ──────────────────────────────────────────────
  function renderTab(c) {
    if (!state.dealId && !["overview", "portfolio", "ops", "jobs"].includes(state.tab)) return renderNoDeal(c);
    ({
      overview: renderOverview, portfolio: renderPortfolio,
      ingest: renderIngest, definitions: renderDefinitions,
      seps: renderSEPs, governing: renderGoverning, model: renderModel,
      qa: renderQA, reports: renderReports,
      governance: renderGovernanceTab, agents: renderAgentDock, ops: renderOpsCenter,
      scenarios: renderScenarios, lifecycle: renderLifecycle,
      tax: renderTax, jobs: renderJobs, lineage: renderLineage, setup_preview: renderSetupPreview,
    }[state.tab] || renderOverview)(c);
  }
  function renderNoDeal(c) {
    c.appendChild(el("div", { class: "empty" }, ["Create a deal from the sidebar to begin."]));
  }

  async function newDeal() {
    const id = await callExtension("promptDealId");
    if (!id) return;
    const res = await dispatch("deal.create", { deal_id: id });
    if (res && res.ok) { state.dealId = id; await boot(); toast("Deal created"); }
    else toast("Could not create deal");
  }

  // ── Portfolio dashboard ────────────────────────────────────
  async function renderPortfolio(c) {
    const card = el("div", { class: "card" });
    card.appendChild(el("h3", null, ["All Deals"]));
    card.appendChild(el("span", { class: "spinner" }));
    c.appendChild(card);
    const res = await dispatch("deal.portfolio", {});
    card.innerHTML = "";
    card.appendChild(el("h3", null, ["All Deals"]));
    if (!res || !res.ok) { card.appendChild(el("div", { class: "muted" }, ["Error loading portfolio."])); return; }
    const { deals, totals } = res.data;
    // Totals banner
    const tileWrap = el("div", { class: "tiles" });
    [["Deals", totals.deals], ["Documents", totals.documents], ["Definitions", totals.definitions],
     ["Pending Artifacts", totals.pending_artifacts], ["Open Exceptions", totals.open_exceptions],
     ["Models", totals.models], ["Monthly Runs", totals.runs]].forEach(([l, v]) =>
      tileWrap.appendChild(el("div", { class: "tile" }, [el("div", { class: "label" }, [l]), el("div", { class: "value" }, [String(v)])]))
    );
    card.appendChild(tileWrap);
    card.appendChild(el("h3", { style: "margin-top:18px" }, ["Deal Breakdown"]));
    deals.forEach((d) => {
      const row = el("div", { class: "list-item", onclick: () => { state.dealId = d.deal_id; state.tab = "overview"; render(); } });
      row.appendChild(el("div", null, [
        el("b", null, [d.deal_id]),
        el("div", { class: "meta" }, [
          d.documents + " docs | ",
          d.definitions + " defs | ",
          d.pending_artifacts + " pending | ",
          d.open_exceptions + " exceptions",
        ]),
      ]));
      const ms = d.model_status;
      if (ms) row.appendChild(badge(ms));
      card.appendChild(row);
    });
    if (!deals.length) card.appendChild(el("div", { class: "empty" }, ["No deals yet."]));
    }
  function renderOverview(c) {
    if (!state.dealId) return renderNoDeal(c);
    const s = state.status || {};
    const sep = s.sep_artifacts || { total: 0, by_status: {} };
    const tiles = el("div", { class: "tiles" });
    [["Documents", s.documents || 0], ["Definitions", s.definitions || 0],
     ["SEP Artifacts", sep.total || 0], ["Approved", (sep.by_status || {}).approved || 0],
     ["Model", s.payment_model && s.payment_model.exists ? "v" + s.payment_model.version : "—"],
     ["Monthly Runs", s.monthly_runs || 0]].forEach(([l, v]) => {
      tiles.appendChild(el("div", { class: "tile" }, [
        el("div", { class: "label" }, [l]), el("div", { class: "value" }, [String(v)]),
      ]));
    });
    c.appendChild(el("div", { class: "card" }, [el("h3", null, ["Deal Health"]), tiles]));

    const steps = el("div", { class: "card" });
    steps.appendChild(el("h3", null, ["Workflow"]));
    [["1", "Ingest governing document", "ingest"], ["2", "Review definitions", "definitions"],
     ["3", "Extract & approve artifacts", "seps"], ["4", "Build governing doc", "governing"],
     ["5", "Generate & audit model", "model"], ["6", "Run monthly report", "reports"]].forEach(([n, label, tab]) => {
      steps.appendChild(el("div", { class: "list-item", onclick: () => { state.tab = tab; render(); } }, [
        el("div", null, [el("b", null, [n + ". "]), label]), el("span", { class: "cite" }, ["Open →"]),
      ]));
    });
    c.appendChild(steps);
  }

  // ── Ingest (animated pipeline) ────────────────────────────────
  const PIPELINE = [["extract", "Extract"], ["sections", "Sections"], ["store", "Store"], ["embed", "Vectorize"]];
  function renderIngest(c) {
    const card = el("div", { class: "card" });
    card.appendChild(el("h3", null, ["Ingest Governing Document"]));
    card.appendChild(el("div", { class: "muted", style: "margin-bottom:12px" },
      ["Select the PSA / Indenture PDF. The pipeline extracts TOC-aware sections, page-cited chunks, and the definition graph."]));
    const pick = el("button", { class: "btn", onclick: () => doIngest(card) }, ["Select PDF & Ingest"]);
    card.appendChild(el("div", { class: "row" }, [pick]));
    const pipe = el("div", { class: "pipeline", id: "pipe" });
    PIPELINE.forEach(([id, name]) => pipe.appendChild(el("div", { class: "stage", id: "st-" + id }, [
      el("div", { class: "dot" }, ["○"]), el("div", { class: "name" }, [name]),
    ])));
    card.appendChild(pipe);
    card.appendChild(el("div", { class: "counter-grid", id: "counters" }));
    card.appendChild(el("div", { class: "def-progress", id: "def-progress", style: "display:none" }));
    c.appendChild(card);
  }
  async function doIngest(card) {
    const path = await callExtension("pickPdf");
    if (!path) return;
    PIPELINE.forEach(([id]) => { $("#st-" + id).className = "stage"; });
    const onProgress = (ev) => {
      // Map index-service events onto the "embed" pipeline stage.
      const uiStage = (ev.stage === "index" || ev.stage === "embed") ? "embed" : ev.stage;
      const node = $("#st-" + uiStage);
      if (!node) return;
      if (ev.stage === "embed" && ev.status === "in-progress") {
        node.className = "stage active";
        const lbl = node.querySelector(".name");
        if (lbl) lbl.textContent = "Vectorize " + ev.pct + "%";
      } else if (ev.stage === "index" && ev.status === "done") {
        node.className = "stage done";
        const lbl = node.querySelector(".name");
        if (lbl) lbl.textContent = "Vectorize";
      } else {
        node.className = "stage " + (ev.status === "done" ? "done" : "active");
      }
      if (ev.status === "done" && ev.stage === "store") showCounters(ev);
    };
    // No timeout: ingestion auto-runs dense embedding/indexing of every chunk,
    // which can exceed the 60s default for large documents. A premature timeout
    // would skip the chained definitions.build below and leave the deal empty.
    const res = await dispatch("ingest.document", { deal_id: state.dealId, pdf_path: path, doc_type: "PSA" }, onProgress, 0);
    if (res && res.ok) {
      showCounters(res.data);
      toast("Ingested " + res.data.sections + " sections, " + res.data.chunks + " chunks");
      // Auto-build the definition graph — no timeout, LLM resolution can take minutes.
      toast("Building definition graph\u2026 (check ABS Waterfall output channel)");
      const onDefProgress = (ev) => {
        const dp = $("#def-progress");
        if (ev.stage === "extract" && ev.status === "done") {
          if (dp) {
            dp.style.display = "";
            dp.className = "def-progress";
            dp.innerHTML = `<div class="dp-label"><span class="spinner" style="display:inline-block;vertical-align:middle;margin-right:6px"></span>Building definition graph&hellip;</div><div class="dp-term">${ev.terms || 0} terms extracted &mdash; resolving&hellip;</div><div class="dp-bar-track"><div class="dp-bar-fill" id="dp-fill" style="width:0%"></div></div>`;
          }
        }
        if (ev.stage === "resolve" && ev.status === "in-progress") {
          const pct = ev.total ? Math.round(ev.resolved * 100 / ev.total) : 0;
          if (dp) {
            const fill = $("#dp-fill");
            const lbl = dp.querySelector(".dp-label");
            const term = dp.querySelector(".dp-term");
            if (fill) fill.style.width = pct + "%";
            if (lbl) lbl.innerHTML = `<span class="spinner" style="display:inline-block;vertical-align:middle;margin-right:6px"></span>Resolving definitions: <span class="dp-counts">${ev.resolved}/${ev.total}</span> <span class="muted">(${pct}%)</span>`;
            if (term && ev.term) term.textContent = ev.term;
          }
        }
        if (ev.stage === "resolve" && ev.status === "done") {
          if (dp) {
            dp.className = "def-progress done";
            dp.innerHTML = `<div class="dp-label">&#x2713; ${ev.resolved || 0} definitions resolved</div>`;
          }
          toast("Resolved " + (ev.resolved || 0) + " definitions \u2713");
        }
      };
      await dispatch("definitions.build", { deal_id: state.dealId, doc_id: res.data.doc_id, resolve: true }, onDefProgress, 0);
      await refreshStatus();
    } else { toast("Ingestion failed: " + (res && res.error)); }
  }
  function showCounters(d) {
    const g = $("#counters"); if (!g) return; g.innerHTML = "";
    [["Pages", d.pages], ["Sections", d.sections], ["Chunks", d.chunks], ["Status", "Ready"]].forEach(([l, v]) => {
      g.appendChild(el("div", { class: "counter" }, [el("div", { class: "n" }, [String(v)]), el("div", { class: "l" }, [l])]));
    });
  }

  // ── Definitions (N-level tree) ────────────────────────────────
  async function renderDefinitions(c) {
    const card = el("div", { class: "card" });
    card.appendChild(el("h3", null, ["Defined Terms"]));
    card.appendChild(el("div", { class: "muted", style: "margin-bottom:10px" },
      ["Click a capitalized term to expand its nested definition tree. Toggle “Resolved” for the plain-English version."]));
    const host = el("div", { id: "defs" }, [el("span", { class: "spinner" })]);
    card.appendChild(host);
    c.appendChild(card);
    const res = await dispatch("definitions.top_level", { deal_id: state.dealId });
    host.innerHTML = "";
    const defs = (res && res.ok && res.data) || [];
    if (!defs.length) { host.appendChild(el("div", { class: "empty" }, ["No definitions yet. Ingest a document first."])); return; }
    defs.forEach((d) => host.appendChild(defNode(d)));
  }
  function defNode(d) {
    const node = el("div", { class: "def-node" });
    const body = el("div", { class: "def-body", style: "display:none" });
    let expanded = false, loaded = false;
    const head = el("div", { class: "def-head", onclick: async () => {
      expanded = !expanded; body.style.display = expanded ? "block" : "none";
      if (expanded && !loaded) { loaded = true; await fillDefBody(body, d.term_id); }
    }}, [el("span", { class: "def-term" }, [d.term_name]),
        el("span", { class: "cite" }, [d.page ? "p." + d.page : "—"]),
        badge(d.status || "draft")]);
    node.appendChild(head); node.appendChild(body);
    return node;
  }
  async function fillDefBody(body, termId) {
    body.appendChild(el("span", { class: "spinner" }));
    const res = await dispatch("definitions.tree", { deal_id: state.dealId, term_id: termId });
    body.innerHTML = "";
    if (!res || !res.ok) { body.appendChild(el("div", { class: "muted" }, ["Could not load."])); return; }
    renderTreeInto(body, res.data, 0);
  }
  function renderTreeInto(host, node, depth) {
    const raw = el("div", null, [node.raw_definition || "(no text)"]);
    host.appendChild(raw);
    if (node.resolved_definition) {
      const r = el("div", { class: "resolved" });
      let shown = false;
      const toggle = el("span", { class: "chip-term", onclick: () => { shown = !shown; r.style.display = shown ? "block" : "none"; } }, ["Toggle Resolved"]);
      r.appendChild(el("div", null, [node.resolved_definition]));
      r.style.display = "none";
      host.appendChild(toggle); host.appendChild(r);
    }
    if (node.children && node.children.length) {
      const kids = el("div", { class: "def-children" });
      node.children.forEach((ch) => {
        const sub = el("div", { class: "def-node" });
        const subBody = el("div", { class: "def-body" });
        sub.appendChild(el("div", { class: "def-head" }, [
          el("span", { class: "def-term" }, [ch.term_name || "?"]),
          ch.page ? el("span", { class: "cite" }, ["p." + ch.page]) : el("span", {}, []),
        ]));
        renderTreeInto(subBody, ch, depth + 1);
        sub.appendChild(subBody); kids.appendChild(sub);
      });
      host.appendChild(kids);
    }
  }

  // ── SEPs (approval cards) ─────────────────────────────────────
  const SEP_NAMES = [["fees", "Fees"], ["certificates", "Certificates"], ["accounts", "Accounts"],
    ["waterfall_rules", "Waterfall"], ["reporting", "Reporting"], ["term_functions", "Term Functions"]];
  async function renderSEPs(c) {
    const bar = el("div", { class: "card" });
    bar.appendChild(el("h3", null, ["Search & Extraction Profiles"]));
    bar.appendChild(el("div", { class: "row" }, [
      el("button", { class: "btn", onclick: () => runSEP(null) }, ["Run All SEPs"]),
      ...SEP_NAMES.map(([id, label]) => el("button", { class: "btn ghost small", onclick: () => runSEP(id) }, [label])),
    ]));
    c.appendChild(bar);
    const host = el("div", { id: "sepHost" });
    c.appendChild(host);
    await loadSEPs(host);
  }
  async function loadSEPs(host) {
    host.innerHTML = '<span class="spinner"></span>';
    const res = await dispatch("sep.list", { deal_id: state.dealId });
    host.innerHTML = "";
    const arts = (res && res.ok && res.data) || [];
    if (!arts.length) { host.appendChild(el("div", { class: "empty" }, ["No artifacts yet. Run a SEP above."])); return; }
    const groups = {};
    arts.forEach((a) => { (groups[a.sep_name] = groups[a.sep_name] || []).push(a); });
    Object.keys(groups).forEach((sep) => {
      const card = el("div", { class: "card" });
      card.appendChild(el("h3", null, [labelFor(sep) + " · " + groups[sep].length]));
      groups[sep].forEach((a) => card.appendChild(sepCard(a)));
      host.appendChild(card);
    });
  }
  function labelFor(sep) { const f = SEP_NAMES.find((x) => x[0] === sep); return f ? f[1] : sep; }
  function sepCard(a) {
    let val = {};
    try { val = JSON.parse(a.value); } catch (e) {}
    const summary = Object.keys(val).filter((k) => k !== "citation").slice(0, 4)
      .map((k) => `<span class="kv"><b>${esc(k)}:</b> ${esc(val[k])}</span>`).join(" · ");
    const item = el("div", { class: "list-item" });
    item.appendChild(el("div", { style: "flex:1" }, [
      el("div", { html: summary || esc(a.field_path) }),
      el("div", { class: "meta" }, [a.citation ? el("span", { class: "cite", onclick: () => callExtension("revealCitation", { citation: a.citation }) }, [a.citation]) : el("span", {}, []), " ", badge(a.status)]),
    ]));
    const actions = el("div", { class: "row" });
    if (a.status === "pending_review") {
      actions.appendChild(el("button", { class: "btn success small", onclick: async (e) => {
        await dispatch("sep.approve", { deal_id: state.dealId, artifact_id: a.artifact_id, actor: "user" });
        toast("Approved"); animateApprove(item);
      }}, ["Approve"]));
      actions.appendChild(el("button", { class: "btn danger small", onclick: async () => {
        await dispatch("sep.reject", { deal_id: state.dealId, artifact_id: a.artifact_id, actor: "user", rationale: "rejected via UI" });
        toast("Rejected"); render();
      }}, ["Reject"]));
    }
    item.appendChild(actions);
    return item;
  }
  function animateApprove(item) {
    item.style.transition = "transform .25s, background .25s";
    item.style.background = "color-mix(in srgb, var(--abs-green) 16%, transparent)";
    item.style.transform = "scale(0.99)";
    setTimeout(() => render(), 350);
  }
  async function runSEP(name) {
    toast(name ? "Running " + labelFor(name) : "Running all SEPs…");
    const cmd = name ? "sep.run" : "sep.run_all";
    const params = name ? { deal_id: state.dealId, sep_name: name } : { deal_id: state.dealId };
    const res = await dispatch(cmd, params);
    if (res && res.ok) { toast("Extraction complete"); await refreshStatus(); render(); }
    else toast("SEP failed: " + (res && res.error));
  }

  // ── Governing doc ─────────────────────────────────────────────
  async function renderGoverning(c) {
    const card = el("div", { class: "card" });
    card.appendChild(el("h3", null, ["Governing Document"]));
    card.appendChild(el("div", { class: "row" }, [el("button", { class: "btn", onclick: async () => {
      toast("Generating governing document…");
      const res = await dispatch("governing.generate", { deal_id: state.dealId });
      if (res && res.ok) { toast("Generated " + res.data.clauses + " clauses"); render(); } else toast("Failed");
    }}, ["Generate"])]));
    c.appendChild(card);
    const res = await dispatch("governing.list", { deal_id: state.dealId });
    const clauses = (res && res.ok && res.data) || [];
    clauses.forEach((cl) => {
      const card2 = el("div", { class: "card" });
      card2.appendChild(el("div", { class: "kv" }, [el("b", null, ["Verbatim: "]), (cl.verbatim || "").slice(0, 240)]));
      card2.appendChild(el("div", { class: "kv", style: "margin-top:6px" }, [el("b", null, ["Plain English: "]), cl.plain_english || ""]));
      if (cl.math_formula) card2.appendChild(el("pre", { class: "code" }, [cl.math_formula]));
      card2.appendChild(el("div", { class: "meta" }, [cl.citation ? el("span", { class: "cite" }, [cl.citation]) : el("span", {}, []), " ", badge(cl.status || "draft")]));
      c.appendChild(card2);
    });
  }

  // ── Payment model ─────────────────────────────────────────────
  async function renderModel(c) {
    const card = el("div", { class: "card" });
    card.appendChild(el("h3", null, ["Python Payment Model"]));
    card.appendChild(el("div", { class: "row" }, [
      el("button", { class: "btn", onclick: async () => { toast("Generating model…");
        const r = await dispatch("model.generate", { deal_id: state.dealId });
        toast(r && r.ok ? "Model generated" : "Failed"); render(); } }, ["Generate Model"]),
      el("button", { class: "btn ghost", onclick: async () => { toast("Auditing…");
        const r = await dispatch("model.audit", { deal_id: state.dealId });
        toast(r && r.ok ? "Audit: " + r.data.verdict : "Audit failed"); render(); } }, ["Run Auditor"]),
      el("button", { class: "btn ghost", onclick: async () => {
        toast("Generating model spec…");
        const r = await dispatch("model.spec", { deal_id: state.dealId });
        toast(r && r.ok ? "Spec ready" : "Failed");
      }}, ["Model Spec (Review)"]),      el("button", { class: "btn ghost", onclick: async () => {
        toast("Running cashflow model…");
        const r = await dispatch("model.run", {
          deal_id: state.dealId,
          monthly_inputs: [{ interest_collections: 0, principal_collections: 0, realized_losses: 0 }],
          run_date: new Date().toISOString().slice(0, 10),
        });
        toast(r && r.ok ? "Run complete — " + Object.keys((r.data || {}).results || {}).length + " classes" : "Run failed");
        if (r && r.ok) render();
      }}, ["Run Monthly"]),    ]));
    c.appendChild(card);
  }

  // ── Q&A & Explainability ──────────────────────────────────────
  function renderQA(c) {
    const card = el("div", { class: "card" });
    card.appendChild(el("h3", null, ["Ask a question"]));
    const input = el("textarea", { rows: "2", placeholder: "e.g. What is paid first on each Distribution Date?" });
    card.appendChild(input);
    card.appendChild(el("div", { class: "row", style: "margin-top:10px" }, [
      el("button", { class: "btn", onclick: () => doAsk(input.value, card) }, ["Ask"]),
      el("button", { class: "btn ghost", onclick: () => doExplain(input.value, card) }, ["Explain (Traceback)"]),
    ]));
    c.appendChild(card);
    c.appendChild(el("div", { id: "answer" }));
  }
  async function doAsk(q, card) {
    if (!q.trim()) return;
    const host = $("#answer"); host.innerHTML = '<div class="answer"><span class="spinner"></span> Thinking…</div>';
    const res = await dispatch("qa.ask", { deal_id: state.dealId, question: q });
    host.innerHTML = "";
    if (!res || !res.ok) { host.appendChild(el("div", { class: "answer" }, ["Error: " + (res && res.error)])); return; }
    const a = el("div", { class: "answer" }, [res.data.answer]);
    const cites = el("div", { class: "citations" });
    (res.data.citations || []).forEach((ci) => cites.appendChild(el("span", { class: "cite", onclick: () => showSource(ci) }, [ci.citation || "source"])));
    a.appendChild(cites);
    host.appendChild(a);
  }
  async function doExplain(q, card) {
    if (!q.trim()) return;
    const host = $("#answer"); host.innerHTML = '<div class="answer"><span class="spinner"></span> Tracing…</div>';
    const res = await dispatch("qa.explain", { deal_id: state.dealId, target: q });
    host.innerHTML = "";
    if (!res || !res.ok) { host.appendChild(el("div", { class: "answer" }, ["Error: " + (res && res.error)])); return; }
    const a = el("div", { class: "answer" });
    a.appendChild(el("div", { class: "ladder-step" }, [res.data.answer]));
    const cites = el("div", { class: "citations" });
    (res.data.citations || []).forEach((ci) => cites.appendChild(el("span", { class: "cite" }, [ci])));
    a.appendChild(cites);
    host.appendChild(a);
  }
  // ── Operations Center (Layer B.9: daily cross-deal queue) ────
  async function renderOpsCenter(c) {
    const card = el("div", { class: "card" });
    card.appendChild(el("h3", null, ["Operations Command Center"]));
    card.appendChild(el("div", { class: "muted", style: "margin-bottom:10px" },
      ["Cross-deal daily work queue: pending reviews, AI exceptions, model approvals, and unresolved items."]));
    card.appendChild(el("span", { class: "spinner" }));
    c.appendChild(card);
    const res = await dispatch("command_center.queue", {});
    card.innerHTML = "";
    card.appendChild(el("h3", null, ["Operations Command Center"]));
    if (!res || !res.ok) { card.appendChild(el("div", { class: "muted" }, ["Error loading queue."])); return; }
    const { items, total, by_type } = res.data;
    // Summary chips
    const chips = el("div", { class: "assurance", style: "margin-bottom:14px" });
    Object.entries(by_type || {}).forEach(([t, n]) =>
      chips.appendChild(el("span", { class: "badge pending" }, [t.replace("_", " ") + ": " + n]))
    );
    card.appendChild(chips);
    if (!items || !items.length) { card.appendChild(el("div", { class: "empty" }, ["All clear — no pending items."])); return; }
    items.forEach((item) => {
      const row = el("div", { class: "list-item", onclick: () => {
        state.dealId = item.deal_id; state.tab = "seps"; render();
      }});
      row.appendChild(el("div", null, [
        el("b", null, [item.action || item.type]),
        el("div", { class: "meta" }, ["Deal: " + item.deal_id + (item.sep_name ? " | " + item.sep_name : "") + (item.root_cause ? " | " + item.root_cause : "")]),
      ]));
      row.appendChild(badge(item.priority || "medium"));
      card.appendChild(row);
    });
  }

  function askCopilot(prompt) { callExtension("askCopilot", { deal_id: state.dealId, prompt }); }

  // ── Governance tab (exceptions, costs, RBAC) ──────────────────
  async function renderGovernanceTab(c) {
    const card = el("div", { class: "card" });
    card.appendChild(el("h3", null, ["Governance & Controls"]));
    // Cost summary
    const costSection = el("div", { style: "margin-bottom:14px" });
    costSection.appendChild(el("div", { class: "kv" }, [el("b", null, ["AI Cost: "]), el("span", { class: "spinner" })]));
    card.appendChild(costSection);
    c.appendChild(card);
    const [costRes, exceptRes] = await Promise.all([
      dispatch("governance.cost", { deal_id: state.dealId }),
      dispatch("governance.corrections", { deal_id: state.dealId }),
    ]);
    costSection.innerHTML = "";
    if (costRes && costRes.ok) {
      const d = costRes.data;
      costSection.appendChild(el("div", { class: "kv" }, [
        el("b", null, ["AI Tokens: "]),
        d.total_tokens + " total (" + d.calls + " calls)",
      ]));
    }
    // Exceptions / corrections
    const excCard = el("div", { class: "card" });
    excCard.appendChild(el("h3", null, ["AI Correction Events (Learning Loop)"]));
    excCard.appendChild(el("div", { class: "row", style: "margin-bottom:10px" }, [
      el("button", { class: "btn ghost small", onclick: async () => {
        const ot = prompt("Object type (e.g. sep_artifact):", "sep_artifact");
        const oid = prompt("Artifact id:", "");
        const rc = prompt("Root cause:", "");
        if (rc) {
          await dispatch("governance.log_correction", { deal_id: state.dealId, object_type: ot || "", object_id: oid || "", root_cause: rc, severity: "medium", actor: "user" });
          toast("Correction logged"); renderGovernanceTab(c);
        }
      }}, ["+ Log Correction"]),
    ]));
    const events = (exceptRes && exceptRes.ok) ? exceptRes.data : [];
    if (!events.length) {
      excCard.appendChild(el("div", { class: "empty" }, ["No correction events yet."]));
    } else {
      events.slice(0, 20).forEach((e) => {
        const row = el("div", { class: "list-item" });
        row.appendChild(el("div", null, [
          el("b", null, [e.lifecycle_stage || e.object_type || "event"]),
          el("div", { class: "meta" }, [e.root_cause || "" + " · " + e.ts.slice(0, 16)]),
        ]));
        row.appendChild(badge(e.severity || "medium"));
        excCard.appendChild(row);
      });
    }
    c.appendChild(excCard);

    // Selective regeneration
    const regenCard = el("div", { class: "card" });
    regenCard.appendChild(el("h3", null, ["Selective Regeneration"]));
    regenCard.appendChild(el("div", { class: "muted", style: "margin-bottom:10px" },
      ["Re-run only the impacted artifact family when something changes."]));
    const targets = [["sep:fees", "Fees SEP"], ["sep:certificates", "Certificates SEP"],
      ["sep:waterfall_rules", "Waterfall Rules SEP"], ["definitions", "Definitions"],
      ["governing", "Governing Doc"], ["model", "Payment Model"]];
    const regenRow = el("div", { class: "row", style: "flex-wrap:wrap;gap:8px" });
    targets.forEach(([t, label]) => regenRow.appendChild(el("button", { class: "btn ghost small",
      onclick: async () => {
        toast("Regenerating " + label + "…");
        const res = await dispatch("regenerate", { deal_id: state.dealId, target: t, reason: "user requested", actor: "user" });
        toast(res && res.ok ? label + " regenerated" : "Failed: " + (res && res.error));
        if (res && res.ok) await refreshStatus();
      }}, [label])));
    regenCard.appendChild(regenRow);
    c.appendChild(regenCard);
  }

  // ── Agent dock (run dormant agents) ──────────────────────────
  async function renderAgentDock(c) {
    const card = el("div", { class: "card" });
    card.appendChild(el("h3", null, ["Agent Ecosystem"]));
    card.appendChild(el("div", { class: "muted", style: "margin-bottom:14px" },
      ["Run any of the 13 AI agents against this deal. Agents materialise artifacts from the structured store."]));
    const host = el("div", { id: "agentHost" }, [el("span", { class: "spinner" })]);
    card.appendChild(host);
    c.appendChild(card);
    const res = await dispatch("agent.list", {});
    host.innerHTML = "";
    const agents = (res && res.ok && res.data) || [];
    const grid = el("div", { style: "display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:10px" });
    agents.forEach((a) => {
      const aCard = el("div", { class: "card", style: "margin:0" });
      aCard.appendChild(el("div", { class: "def-term" }, [a.label]));
      aCard.appendChild(el("div", { class: "meta", style: "margin:4px 0 10px" }, [a.name]));
      aCard.appendChild(el("button", { class: "btn small", onclick: async () => {
        toast("Running " + a.label + "…");
        const r = await dispatch("agent.run", { deal_id: state.dealId, agent_name: a.name });
        toast(r && r.ok ? a.label + " complete" : "Error: " + (r && r.error));
      }}, ["Run"]));
      grid.appendChild(aCard);
    });
    host.appendChild(grid);
  }

  // ── Reports ───────────────────────────────────────────────────
  function renderReports(c) {
    const card = el("div", { class: "card" });
    card.appendChild(el("h3", null, ["Monthly Distribution Statement"]));
    card.appendChild(el("div", { class: "muted", style: "margin-bottom:10px" }, ["Run the cashflow model against monthly inputs and generate the investor distribution statement PDF."]));
    // CSV upload for monthly inputs
    const csvInput = el("input", { type: "file", accept: ".csv", style: "display:none", id: "csvInput" });
    card.appendChild(csvInput);
    card.appendChild(el("div", { class: "row" }, [
      el("button", { class: "btn ghost small", onclick: () => csvInput.click() }, ["Upload Monthly CSV"]),
      el("button", { class: "btn small", onclick: async () => {
        const path = await callExtension("pickCsv");
        if (!path) { toast("No CSV selected"); return; }
        toast("Checking readiness…");
        const ready = await dispatch("model.readiness", { csv_path: path });
        if (ready && ready.ok && !ready.data.ready) {
          toast("⚠ Readiness issues: " + ready.data.errors + " error(s)"); return;
        }
        toast("Running cashflow model…");
        const run = await dispatch("model.run", { deal_id: state.dealId, csv_path: path, run_date: new Date().toISOString().slice(0, 10) });
        if (!run || !run.ok) { toast("Run failed: " + (run && run.error)); return; }
        toast("Generating statement…");
        const rep = await dispatch("report.generate", { deal_id: state.dealId, deal_name: state.dealId });
        if (rep && rep.ok) { toast("Report ready"); if (rep.data.pdf_path) callExtension("openFile", { path: rep.data.pdf_path }); }
      }}, ["Run From CSV"]),
      el("button", { class: "btn", onclick: async () => {
        toast("Generating report from latest run…");
        const res = await dispatch("report.generate", { deal_id: state.dealId, deal_name: state.dealId });
        if (res && res.ok) { toast("Report ready"); if (res.data.pdf_path) callExtension("openFile", { path: res.data.pdf_path }); }
        else toast("Report failed: " + (res && res.error));
      }}, ["Generate Statement"]),
    ]));
    c.appendChild(card);

    // Export row: Excel + Evidence Package + Setup files
    const exportCard = el("div", { class: "card" });
    exportCard.appendChild(el("h3", null, ["Exports & Evidence"]));
    exportCard.appendChild(el("div", { class: "muted", style: "margin-bottom:10px" }, ["Generate Excel review model, evidence package, and deal setup load files."]));
    exportCard.appendChild(el("div", { class: "row" }, [
      el("button", { class: "btn ghost", onclick: async () => {
        toast("Generating Excel workbook…");
        const r = await dispatch("excel.generate", { deal_id: state.dealId });
        toast(r && r.ok ? "Excel ready" : "Failed"); if (r && r.ok) callExtension("openFile", { path: r.data.path });
      }}, ["Excel Review Model"]),
      el("button", { class: "btn ghost", onclick: async () => {
        toast("Generating evidence package…");
        const r = await dispatch("evidence.generate", { deal_id: state.dealId });
        toast(r && r.ok ? "Evidence package ready (" + r.data.artifacts_approved + " approved)" : "Failed");
        if (r && r.ok) callExtension("openFile", { path: r.data.json_path });
      }}, ["Evidence Package"]),
      el("button", { class: "btn ghost", onclick: async () => {
        toast("Generating setup files…");
        const r = await dispatch("setup.generate", { deal_id: state.dealId });
        toast(r && r.ok ? "Setup files ready (" + Object.keys(r.data.files).length + " files)" : "Failed: " + (r && r.error));
      }}, ["Deal Setup Files"]),
      el("button", { class: "btn ghost", onclick: async () => {
        toast("Detecting document conflicts…");
        const r = await dispatch("hierarchy.detect", { deal_id: state.dealId });
        const n = (r && r.ok && r.data) ? r.data.length : 0;
        toast(n ? n + " conflict(s) found — check Governance tab" : "No conflicts detected");
      }}, ["Check Doc Conflicts"]),
    ]));
    c.appendChild(exportCard);
  }

  // ── Scenarios (CPR/CDR builder + projection results) ─────────
  async function renderScenarios(c) {
    const hdr = el("div", { class: "card" });
    hdr.appendChild(el("h3", null, ["Scenarios & Projections"]));
    hdr.appendChild(el("div", { class: "muted", style: "margin-bottom:10px" },
      ["Run multi-scenario cashflow projections (base + stress) using the CPR/CDR assumption library. Save a baseline and detect drift."]));
    hdr.appendChild(el("div", { class: "row" }, [
      el("button", { class: "btn", onclick: async () => {
        toast("Seeding default assumptions (base, stress_high_cdr, stress_high_prepay)…");
        await dispatch("assumptions.seed", { deal_id: state.dealId });
        toast("Running 12-month projections…");
        const res = await dispatch("projection.run", { deal_id: state.dealId, months: 12 });
        toast(res && res.ok ? "Projections complete (" + res.data.total + " scenarios)" : "Failed: " + (res && res.error));
        renderScenarios(c);
      }}, ["Run All Scenarios"]),
      el("button", { class: "btn ghost", onclick: async () => {
        const r = await dispatch("projection.baseline.save", { deal_id: state.dealId });
        toast(r && r.ok ? "Baseline saved (base scenario)" : "No base projection to save");
      }}, ["Save Baseline"]),
      el("button", { class: "btn ghost", onclick: async () => {
        const r = await dispatch("projection.baseline.compare", { deal_id: state.dealId });
        if (!r || !r.ok) { toast("Cannot compare"); return; }
        toast(r.data.has_drift ? r.data.diffs.length + " drift(s) found vs baseline" : "No drift vs baseline ✓");
      }}, ["Compare vs Baseline"]),
    ]));
    c.appendChild(hdr);
    const res = await dispatch("projection.results", { deal_id: state.dealId });
    const results = (res && res.ok && res.data) ? res.data : [];
    if (!results.length) { c.appendChild(el("div", { class: "empty" }, ["No projections yet. Click 'Run All Scenarios'."])); return; }
    results.forEach((r) => {
      const card = el("div", { class: "card" });
      const sc = r.agent_name || "";
      card.appendChild(el("h3", null, [sc.replace("projection:", "")]));
      const parsed = r.result_parsed || {};
      const months = parsed.months_summary || parsed.months || [];
      if (months.length) {
        const tbl = el("div", { style: "overflow-x:auto" });
        const table = el("table", { style: "width:100%;border-collapse:collapse;font-size:11px" });
        const thead = el("tr");
        ["Month","Available","Remaining","Distributions"].forEach((h) => {
          const th = el("th", { style: "text-align:left;padding:4px;border-bottom:1px solid var(--abs-hairline)" }, [h]);
          thead.appendChild(th);
        });
        table.appendChild(thead);
        months.slice(0, 12).forEach((m) => {
          const tr = el("tr");
          [m.month, (m.available_funds||0).toFixed(2), (m.remaining_funds||0).toFixed(2), (m.distributions||[]).length + " steps"].forEach((v) => {
            const td = el("td", { style: "padding:3px 6px;border-bottom:1px solid var(--abs-hairline)" }, [String(v)]);
            tr.appendChild(td);
          });
          table.appendChild(tr);
        });
        tbl.appendChild(table);
        card.appendChild(tbl);
      }
      c.appendChild(card);
    });
  }

  // ── Lifecycle Monitor ─────────────────────────────────────────
  async function renderLifecycle(c) {
    const card = el("div", { class: "card" });
    card.appendChild(el("h3", null, ["Lifecycle Monitor"]));
    card.appendChild(el("div", { class: "muted", style: "margin-bottom:10px" }, ["Trigger status, key dates, stepdowns, and clean-up call proximity."]));
    card.appendChild(el("div", { class: "row" }, [
      el("button", { class: "btn", onclick: async () => {
        toast("Running Lifecycle Monitor…");
        const r = await dispatch("agent.run", { deal_id: state.dealId, agent_name: "lifecycle", task: {} });
        toast(r && r.ok ? "Lifecycle check complete" : "Failed");
        renderLifecycle(c);
      }}, ["Run Lifecycle Check"]),
    ]));
    c.appendChild(card);
    const res = await dispatch("agent.results", { deal_id: state.dealId, agent_name: "lifecycle" });
    const results = (res && res.ok && res.data) || [];
    if (!results.length) { c.appendChild(el("div", { class: "empty" }, ["No lifecycle results yet."])); return; }
    const latest = results[0];
    const parsed = latest.result_parsed || {};
    const statusCard = el("div", { class: "card" });
    statusCard.appendChild(el("h3", null, ["Latest Run — " + (latest.created_at || "").slice(0, 16)]));
    // Render trigger states if present
    const triggers = parsed.trigger_states || parsed.triggers || {};
    if (Object.keys(triggers).length) {
      statusCard.appendChild(el("div", { class: "kv" }, [el("b", null, ["Trigger States:"]), " " + Object.entries(triggers).map(([k,v]) => k + "=" + v).join(", ")]));
    }
    const rawStr = JSON.stringify(parsed, null, 2).slice(0, 1200);
    statusCard.appendChild(el("pre", { class: "code" }, [rawStr]));
    c.appendChild(statusCard);
  }

  // ── Tax outputs ───────────────────────────────────────────────
  async function renderTax(c) {
    const card = el("div", { class: "card" });
    card.appendChild(el("h3", null, ["Tax Processing (OID / NPV / 8-K Support)"]));
    card.appendChild(el("div", { class: "muted", style: "margin-bottom:10px" }, ["Generate OID, NPV per class, and 8-K/10-K tax support outputs from projections."]));
    card.appendChild(el("div", { class: "row" }, [
      el("button", { class: "btn", onclick: async () => {
        toast("Generating tax outputs…");
        const r = await dispatch("tax.generate", { deal_id: state.dealId, scenario_name: "base", discount_rate: 0.05 });
        toast(r && r.ok ? "Tax outputs generated" : "Failed: " + (r && r.error));
        renderTax(c);
      }}, ["Generate Tax Outputs"]),
    ]));
    c.appendChild(card);
    const res = await dispatch("tax.results", { deal_id: state.dealId });
    if (!res || !res.ok || !res.data || !res.data.result_parsed) {
      c.appendChild(el("div", { class: "empty" }, ["No tax outputs yet. Run projections first, then click 'Generate Tax Outputs'."])); return;
    }
    const d = res.data.result_parsed;
    const npvCard = el("div", { class: "card" });
    npvCard.appendChild(el("h3", null, ["NPV by Class"]));
    (d.npv_outputs || []).forEach((n) => {
      npvCard.appendChild(el("div", { class: "kv" }, [
        el("b", null, [n.class_name + " (" + (n.cusip || "—") + "): "]),
        "NPV = $" + (n.npv || 0).toLocaleString() + " @ " + ((n.discount_rate || 0) * 100).toFixed(2) + "%"
      ]));
    });
    c.appendChild(npvCard);
    const oidCard = el("div", { class: "card" });
    oidCard.appendChild(el("h3", null, ["OID Summary"]));
    (d.oid_outputs || []).forEach((o) => {
      oidCard.appendChild(el("div", { class: "kv" }, [el("b", null, [o.class_name + ": "]), "OID = $" + (o.oid_amount || 0).toFixed(2)]));
    });
    c.appendChild(oidCard);
  }

  // ── Job queue panel ───────────────────────────────────────────
  async function renderJobs(c) {
    const card = el("div", { class: "card" });
    card.appendChild(el("h3", null, ["Job Queue"]));
    card.appendChild(el("div", { class: "muted", style: "margin-bottom:10px" }, ["Status of async jobs (long-running extractions, projections, etc.)."]));
    const host = el("div", { id: "jobHost" }, [el("span", { class: "spinner" })]);
    card.appendChild(host);
    c.appendChild(card);
    const res = await dispatch("jobs.list", state.dealId ? { deal_id: state.dealId } : {});
    host.innerHTML = "";
    const jobs = (res && res.ok && res.data) || [];
    if (!jobs.length) { host.appendChild(el("div", { class: "empty" }, ["No jobs."])); return; }
    jobs.slice(0, 30).forEach((j) => {
      const row = el("div", { class: "list-item" });
      row.appendChild(el("div", null, [
        el("b", null, [j.command]), el("div", { class: "meta" }, [j.queued_at ? j.queued_at.slice(0, 16) : ""]),
      ]));
      row.appendChild(badge(j.status || "queued"));
      host.appendChild(row);
    });
  }

  // ── Visual Lineage Graph (FRD Screen 8) ───────────────────────
  async function renderLineage(c) {
    const card = el("div", { class: "card" });
    card.appendChild(el("h3", null, ["Lineage & Evidence"]));
    card.appendChild(el("div", { class: "muted", style: "margin-bottom:10px" },
      ["Source → Extraction → Artifact → Model → Run — visual trace chain."]));
    c.appendChild(card);
    const [artRes, docRes, auditRes, runRes] = await Promise.all([
      dispatch("sep.list", { deal_id: state.dealId }),
      dispatch("deal.status", { deal_id: state.dealId }),
      dispatch("audit.list", { deal_id: state.dealId, limit: 50 }),
      dispatch("run.details", { deal_id: state.dealId }),
    ]);
    // Lineage chain as vertical flow
    const chainCard = el("div", { class: "card" });
    chainCard.appendChild(el("h3", null, ["Lineage Chain"]));
    const status = docRes && docRes.ok ? docRes.data : {};
    const steps = [
      ["📄", "Source Documents", status.documents + " document(s) ingested"],
      ["✂", "Sections + Chunks", "TOC-aware extraction with page citations"],
      ["⊞", "SEP Artifacts", (artRes && artRes.ok ? artRes.data.length : 0) + " artifacts extracted"],
      ["§", "Governing Doc", "Verbatim ↔ interpreted ↔ formula clauses"],
      ["{ }", "Payment Model", status.payment_model && status.payment_model.exists ? "v" + status.payment_model.version + " (" + status.payment_model.validation_status + ")" : "Not yet generated"],
      ["▤", "Monthly Runs", status.monthly_runs + " run(s)"],
    ];
    steps.forEach(([ico, title, desc]) => {
      const row = el("div", { class: "list-item" });
      row.appendChild(el("span", { style: "font-size:18px;margin-right:10px" }, [ico]));
      row.appendChild(el("div", null, [el("b", null, [title]), el("div", { class: "meta" }, [desc])]));
      chainCard.appendChild(row);
    });
    c.appendChild(chainCard);
    // Audit trail
    const auditCard = el("div", { class: "card" });
    auditCard.appendChild(el("h3", null, ["Material Audit Log"]));
    const auditEntries = (auditRes && auditRes.ok && auditRes.data) || [];
    if (!auditEntries.length) {
      auditCard.appendChild(el("div", { class: "muted" }, ["No audit entries yet."]));
    } else {
      auditEntries.slice(0, 20).forEach((e) => {
        const row = el("div", { class: "list-item" });
        row.appendChild(el("div", null, [
          el("b", null, [e.action || ""]),
          el("div", { class: "meta" }, [(e.ts || "").slice(0, 16) + " · " + (e.actor || "") + " · " + (e.object_type || "")]),
        ]));
        auditCard.appendChild(row);
      });
    }
    c.appendChild(auditCard);
    // Run details waterfall trace
    const details = (runRes && runRes.ok && runRes.data) || [];
    if (details.length) {
      const runCard = el("div", { class: "card" });
      runCard.appendChild(el("h3", null, ["Latest Run — Waterfall Trace"]));
      details.forEach((d) => {
        const txt = `${d.step_name || d.class_name}: interest=${ (d.interest||0).toFixed(2)} principal=${ (d.principal||0).toFixed(2)} ending=${ (d.ending_bal||0).toFixed(2)}`;
        runCard.appendChild(el("div", { class: "kv" }, [el("b", null, [d.class_name + " "]), txt]));
      });
      c.appendChild(runCard);
    }
  }

  // ── Setup Output Preview (FRD Screen 9) ──────────────────────
  async function renderSetupPreview(c) {
    const card = el("div", { class: "card" });
    card.appendChild(el("h3", null, ["Setup Output Preview"]));
    card.appendChild(el("div", { class: "muted", style: "margin-bottom:10px" },
      ["Review each generated setup file before approval and export. FRD Screen 9."]));
    card.appendChild(el("div", { class: "row" }, [
      el("button", { class: "btn", onclick: async () => {
        toast("Generating setup files…");
        const r = await dispatch("setup.generate", { deal_id: state.dealId });
        toast(r && r.ok ? "Setup files ready" : "Failed: " + (r && r.error));
        renderSetupPreview(c);
      }}, ["Generate Setup Files"]),
    ]));
    c.appendChild(card);
    // Try to read the manifest to list generated files
    const res = await dispatch("setup.generate", { deal_id: state.dealId });
    if (!res || !res.ok) { c.appendChild(el("div", { class: "empty" }, ["No setup files yet. Click 'Generate Setup Files'."])); return; }
    const files = res.data.files || {};
    const issues = res.data.validation_issues || [];
    if (issues.length) {
      const issCard = el("div", { class: "card" });
      issCard.appendChild(el("h3", null, ["Validation Issues"]));
      issues.forEach((iss) => {
        issCard.appendChild(el("div", { class: "list-item" }, [
          el("div", null, [el("b", null, [iss.field || ""]), " — " + (iss.message || "")]),
          badge(iss.severity || "warning"),
        ]));
      });
      c.appendChild(issCard);
    }
    Object.entries(files).forEach(([name, path]) => {
      if (name === "manifest") return;
      const fileCard = el("div", { class: "card" });
      fileCard.appendChild(el("div", { class: "row" }, [
        el("b", null, [name.replace("_", " ").replace("csv", "").toUpperCase()]),
        el("button", { class: "btn ghost small", onclick: () => callExtension("openFile", { path }) }, ["Open File"]),
      ]));
      c.appendChild(fileCard);
    });
  }

  // Kick things off once the extension sends init.
  vscode.postMessage({ type: "ready" });
})();
