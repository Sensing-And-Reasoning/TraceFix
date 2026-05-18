"""Real-time HTML visualization for Runtime B (SSE-driven).

Generates a self-contained HTML page that:
  1. Fetches IR topology from /api/ir
  2. Connects to /api/events via EventSource for live updates
  3. Renders D3 force-directed graph with animated node states
  4. Shows per-agent tool-call traces in real time
  5. Plays beam animations for send/receive operations
"""

from __future__ import annotations

import json


def render_live_html(ir: dict, title: str = "", model: str = "") -> str:
    """Generate HTML page with SSE client for real-time visualization."""
    page_title = title or "Runtime B Live"

    # Pre-compute topology data for the graph (same as visualize.py _build_data)
    agents_ir = ir.get("agents", [])
    resources_ir = ir.get("resources", [])
    channels_ir = ir.get("channels", [])
    states_ir = ir.get("states", {})

    nodes = []
    for agent in agents_ir:
        nodes.append({"id": agent["id"], "type": "agent", "status": "idle", "steps": 0})
    for res in resources_ir:
        nodes.append({
            "id": res["id"], "type": "resource",
            "rtype": res.get("type", "Lock"),
            "initial": res.get("initial_value"),
        })

    links = []
    for ch in channels_ir:
        froms = ch.get("from", [])
        tos = ch.get("to", [])
        if isinstance(froms, str):
            froms = [froms]
        if isinstance(tos, str):
            tos = [tos]
        for f in froms:
            for t in tos:
                if f != t:
                    links.append({
                        "source": f, "target": t, "type": "channel",
                        "id": ch["id"], "labels": ch.get("labels", []),
                    })

    resource_users: dict[str, set[str]] = {r["id"]: set() for r in resources_ir}
    for state_id, state_def in states_ir.items():
        agent_id = state_def.get("agent")
        if not agent_id:
            continue
        for action in state_def.get("actions", []):
            for lock_id in action.get("acquire", []):
                if lock_id in resource_users:
                    resource_users[lock_id].add(agent_id)
            for lock_id in action.get("release", []):
                if lock_id in resource_users:
                    resource_users[lock_id].add(agent_id)

    # Fallback: if no resource-agent links from states, connect all agents to all resources
    if resources_ir and not any(resource_users.values()):
        agent_ids = [a["id"] for a in agents_ir]
        for rid in resource_users:
            resource_users[rid] = set(agent_ids)

    for rid, agents_set in resource_users.items():
        for aid in sorted(agents_set):
            links.append({"source": aid, "target": rid, "type": "resource"})

    channels_data = []
    for ch in channels_ir:
        froms = ch.get("from", [])
        tos = ch.get("to", [])
        if isinstance(froms, str):
            froms = [froms]
        if isinstance(tos, str):
            tos = [tos]
        channels_data.append({
            "id": ch["id"], "from": froms, "to": tos,
            "labels": ch.get("labels", []),
        })

    agents_data = []
    for agent in agents_ir:
        agents_data.append({
            "id": agent["id"],
            "initial_state": agent.get("initial_state", ""),
            "tools": agent.get("tools", []),
            "status": "idle", "steps": 0, "duration": 0,
        })

    resources_data = []
    for res in resources_ir:
        contenders = sorted(resource_users.get(res["id"], set()))
        resources_data.append({
            "id": res["id"], "type": res.get("type", "Lock"),
            "initial": res.get("initial_value"),
            "contenders": contenders,
        })

    # Cost pricing config for live cost tracking
    cost_config = None
    if model:
        from tracefix.runtime.monitoring.cost import get_prices
        prices = get_prices(model)
        if prices:
            cost_config = {"model": model, "input": prices[0], "output": prices[1]}

    graph_data = json.dumps({
        "nodes": nodes,
        "links": links,
        "channels": channels_data,
        "agents": agents_data,
        "resources": resources_data,
        "resource_users": {k: sorted(v) for k, v in resource_users.items()},
        "cost_config": cost_config,
    })

    return _HTML_TEMPLATE.replace("__PAGE_TITLE__", page_title).replace("__GRAPH_DATA__", graph_data)


_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>__PAGE_TITLE__</title>
<style>
:root {
  --bg: #0d1117; --bg2: #161b22; --bg3: #21262d; --border: #30363d;
  --text: #c9d1d9; --text2: #8b949e; --accent: #58a6ff; --green: #3fb950;
  --red: #f85149; --orange: #d29922; --purple: #bc8cff;
}
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
       background:var(--bg); color:var(--text); overflow:hidden; }

/* Layout */
.app { display:flex; flex-direction:column; height:100vh; }
.top-sim-bar { background:var(--bg2); border-bottom:1px solid var(--border);
               padding:0; flex-shrink:0; }
.top-sim-bar.hidden { display:none; }
.main-row { display:flex; flex:1; min-height:0; }
.left-panel { width:260px; background:var(--bg2); border-right:1px solid var(--border);
              display:flex; flex-direction:column; flex-shrink:0; }
.center { flex:1; position:relative; }
.right-panel { width:380px; background:var(--bg2); border-left:1px solid var(--border);
               display:flex; flex-direction:column; flex-shrink:0; }

/* Header */
.header { height:40px; background:var(--bg3); border-bottom:1px solid var(--border);
          display:flex; align-items:center; padding:0 14px; font-size:13px; font-weight:600; gap:8px; }
.header .title { color:var(--text); }
.header .badge { font-size:11px; padding:2px 8px; border-radius:10px; }
.badge-running { background:var(--accent); color:var(--bg); }
.badge-success { background:var(--green); color:var(--bg); }
.badge-fail { background:var(--red); color:#fff; }
.header .meta { margin-left:auto; font-size:11px; color:var(--text2); font-weight:400; }

/* Left panel */
.panel-header { padding:10px 14px 6px; font-size:11px; text-transform:uppercase;
                color:var(--text2); letter-spacing:0.8px; font-weight:600; }
.agent-list { overflow-y:auto; padding:0 8px 4px; }
.agent-item { padding:7px 10px; margin-bottom:3px; border-radius:6px;
              background:var(--bg3); border:1px solid var(--border); cursor:pointer;
              display:flex; align-items:center; gap:8px;
              transition:border-color 0.15s; font-size:12px; }
.agent-item:hover { border-color:var(--accent); }
.agent-item.selected { border-color:var(--accent); background:rgba(88,166,255,0.08); }
.agent-status { width:8px; height:8px; border-radius:50%; flex-shrink:0; transition: background 0.3s; }
.status-idle { background:var(--text2); }
.status-busy { background:var(--accent); animation: pulse-busy 1s ease-in-out infinite; }
.status-completed { background:var(--green); }
.status-error { background:var(--red); }
.status-timeout { background:var(--orange); }
.agent-name { font-weight:600; flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.agent-steps { color:var(--text2); font-size:11px; flex-shrink:0; }

.channel-list { overflow-y:auto; padding:0 8px 4px; }
.channel-item { padding:6px 10px; margin-bottom:3px; border-radius:6px;
                background:var(--bg3); border:1px solid var(--border); font-size:11px;
                cursor:pointer; transition:border-color 0.15s; }
.channel-item:hover { border-color:var(--accent); }
.channel-item.selected { border-color:var(--accent); background:rgba(88,166,255,0.08); }
.channel-name { font-weight:600; color:var(--accent); display:flex; justify-content:space-between; }
.channel-route { font-size:10px; color:var(--text2); margin-top:1px; }
.ch-count { color:var(--text2); font-weight:400; font-size:10px; }

.summary-box { padding:10px 14px; border-top:1px solid var(--border); flex-shrink:0; }
.summary-row { display:flex; justify-content:space-between; font-size:12px; padding:2px 0; }
.summary-row .val { font-weight:600; color:var(--accent); }

/* Sim panel (top bar) */
.sim-panel { padding:8px 14px; display:flex; align-items:flex-start; gap:16px; flex-wrap:wrap; }
.sim-title { font-size:11px; text-transform:uppercase; color:var(--text2);
             letter-spacing:0.8px; font-weight:600; flex-shrink:0; padding-top:2px; }
.sim-section { display:flex; align-items:center; gap:6px; flex-shrink:0; }
.sim-section-title { font-size:10px; text-transform:uppercase; color:var(--text2);
                     letter-spacing:0.5px; font-weight:600; flex-shrink:0; }
.sim-items { display:flex; flex-wrap:wrap; gap:4px; }
.sim-item { font-size:11px; padding:2px 6px; border-radius:3px;
           border:1px solid var(--border); background:var(--bg); font-family:monospace;
           transition: color 0.3s, border-color 0.3s; }
.sim-item.done { color:var(--green); border-color:rgba(63,185,80,0.3); }
.sim-item.pending { color:var(--text2); }
.sim-status { font-size:12px; font-weight:600; flex-shrink:0; padding-top:1px; }
.sim-status.complete { color:var(--green); }
.sim-status.incomplete { color:var(--orange); }
.sim-violations { display:flex; flex-wrap:wrap; gap:4px; }
.sim-violation { font-size:11px; padding:3px 8px; border-radius:4px;
                background:rgba(248,81,73,0.08); border:1px solid rgba(248,81,73,0.2);
                color:var(--red); font-family:monospace; animation: trace-appear 0.3s ease-out; }
.sim-violation .viol-detail { color:var(--text2); font-size:10px; }
.protocol-violation { font-size:11px; padding:3px 8px; border-radius:4px;
                background:rgba(248,81,73,0.08); border:1px solid rgba(248,81,73,0.2);
                color:var(--red); font-family:monospace; animation: trace-appear 0.3s ease-out; }
.protocol-violation .viol-detail { color:var(--text2); font-size:10px; }
.agent-state { font-family:"SF Mono",Menlo,monospace; font-size:10px; color:var(--text2);
               overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.trace-state { opacity:0.7; font-style:italic; }
.trace-state .trace-body { color:var(--text2); }

/* Right panel: trace */
.trace-header { padding:10px 14px; border-bottom:1px solid var(--border); font-size:13px; font-weight:600;
                display:flex; align-items:center; gap:8px; }
.trace-filter { display:flex; gap:4px; padding:6px 8px; border-bottom:1px solid var(--border); flex-wrap:wrap; }
.filter-btn { font-size:10px; padding:2px 8px; border-radius:10px; cursor:pointer;
              border:1px solid var(--border); background:var(--bg3); color:var(--text2);
              transition:all 0.15s; }
.filter-btn.active { border-color:var(--accent); color:var(--accent); background:rgba(88,166,255,0.1); }
.trace-scroll { flex:1; overflow-y:auto; padding:4px 0; }
.trace-item { display:flex; align-items:flex-start; padding:5px 8px; margin-bottom:2px;
              border-radius:4px; background:var(--bg); font-size:11px;
              font-family:"SF Mono",Menlo,monospace; gap:6px; line-height:1.4;
              animation: trace-appear 0.3s ease-out; }
.trace-agent { color:var(--purple); flex-shrink:0; width:80px; overflow:hidden;
               text-overflow:ellipsis; white-space:nowrap; font-weight:600; }
.trace-round { color:var(--text2); flex-shrink:0; width:28px; }
.trace-body { flex:1; overflow:hidden; }
.trace-tool { font-weight:600; }
.trace-args { color:var(--text2); font-size:10px; overflow:hidden;
              text-overflow:ellipsis; white-space:nowrap; max-width:180px; }
.trace-result { font-size:10px; margin-top:1px; }
.trace-elapsed { color:var(--text2); flex-shrink:0; font-size:10px; }

/* Tool-specific colors */
.tool-acquire-acquired { color:var(--green); }
.tool-acquire-busy { color:var(--orange); }
.tool-acquire-already { color:var(--accent); }
.tool-release { color:var(--text2); }
.tool-send { color:var(--green); }
.tool-receive-ok { color:var(--accent); }
.tool-receive-timeout { color:var(--orange); }
.tool-done { color:var(--green); }
.tool-domain { color:var(--purple); }
.tool-error { color:var(--red); }

/* SVG graph */
svg { width:100%; height:100%; }
.link-channel { stroke:var(--accent); stroke-width:1.5; fill:none; opacity:0.6; }
.link-resource { stroke:var(--red); stroke-width:1; fill:none; opacity:0.25; stroke-dasharray:4,3;
                 transition: opacity 0.3s, stroke-width 0.3s; }
.link-resource.active { opacity:0.8; stroke-width:2.5; stroke:var(--orange);
                        filter:drop-shadow(0 0 3px var(--orange)); }
.node-agent { fill:transparent; stroke-width:2; cursor:pointer; transition: stroke 0.3s; }
.node-agent:hover { stroke-width:3; filter:brightness(1.3); }
.node-agent.pulse { animation: node-pulse 1s ease-in-out infinite; }
.node-resource { fill:transparent; stroke:var(--red); stroke-width:1.5; cursor:pointer; rx:4; }
.node-resource:hover { stroke-width:2.5; stroke:var(--orange); }
.node-label { font-size:11px; fill:var(--text); text-anchor:middle; pointer-events:none; }
.node-sub { font-size:9px; fill:var(--text2); text-anchor:middle; pointer-events:none; }
.node-icon { fill:var(--text); pointer-events:none; }
.link-arrow { fill:var(--accent); opacity:0.6; }

/* Zoom controls */
.zoom-bar { position:absolute; bottom:12px; left:50%; transform:translateX(-50%);
            background:var(--bg3); border:1px solid var(--border); border-radius:6px;
            display:flex; align-items:center; padding:4px 10px; gap:8px; font-size:12px; }
.zoom-bar button { background:none; border:1px solid var(--border); color:var(--text);
                   width:26px; height:26px; border-radius:4px; cursor:pointer; font-size:14px; }
.zoom-bar button:hover { background:var(--border); }
.zoom-bar .zoom-level { color:var(--text2); min-width:40px; text-align:center; }

/* Animations */
@keyframes pulse-busy {
  0%, 100% { opacity:1; }
  50% { opacity:0.4; }
}
@keyframes node-pulse {
  0%, 100% { stroke-opacity:1; filter:drop-shadow(0 0 4px var(--accent)); }
  50% { stroke-opacity:0.4; filter:drop-shadow(0 0 8px var(--accent)); }
}
@keyframes trace-appear {
  from { opacity:0; transform:translateY(-4px); }
  to { opacity:1; transform:translateY(0); }
}

/* Beam animation */
.beam-particle { fill:var(--green); }
@keyframes beam-fade {
  0% { opacity:0.9; }
  100% { opacity:0; }
}
</style>
</head>
<body>
<div class="app">

  <!-- Top: Sim Checks Bar -->
  <div class="top-sim-bar hidden" id="simBar">
    <div id="simPanel"></div>
  </div>

  <!-- Main Row -->
  <div class="main-row">

    <!-- Left Panel -->
    <div class="left-panel">
      <div class="header" id="headerBar">
        <span class="title">__PAGE_TITLE__</span>
        <span class="badge badge-running" id="statusBadge">RUNNING</span>
        <span class="meta" id="headerMeta">0.0s</span>
      </div>
      <div class="panel-header">Agents</div>
      <div class="agent-list" id="agentList"></div>
      <div class="panel-header">Resources</div>
      <div class="channel-list" id="resourceList"></div>
      <div class="panel-header">Channels</div>
      <div class="channel-list" id="channelList"></div>
      <div class="summary-box" id="summaryBox"></div>
    </div>

    <!-- Center: Graph -->
    <div class="center" id="graphContainer">
      <div class="zoom-bar">
        <button id="zoomOut">&minus;</button>
        <span class="zoom-level" id="zoomLevel">100%</span>
        <button id="zoomIn">+</button>
        <button id="zoomReset" style="font-size:11px;width:auto;padding:0 8px;">Reset</button>
      </div>
    </div>

    <!-- Right Panel: Live Trace -->
    <div class="right-panel">
      <div class="trace-header">
        <span>Live Trace</span>
        <span id="traceCount" style="color:var(--text2);font-size:11px;font-weight:400">0 events</span>
      </div>
      <div class="trace-filter" id="traceFilter"></div>
      <div class="trace-scroll" id="traceScroll"></div>
    </div>

  </div>
</div>

<script src="https://d3js.org/d3.v7.min.js"></script>
<script>
// ========== INITIAL TOPOLOGY DATA ==========
const TOPO = __GRAPH_DATA__;
let runStartTime = null;
let traceItems = [];
let activeFilter = "all";
let activeChannelFilter = null;  // channel id or null

// Agent state tracking
const agentState = {};
TOPO.agents.forEach(a => {
  agentState[a.id] = { status: "idle", steps: 0, duration: 0, error: null };
});

// Token / cost tracking
const tokenState = { totalIn: 0, totalOut: 0 };
const agentTokens = {};
TOPO.agents.forEach(a => { agentTokens[a.id] = { in: 0, out: 0 }; });
const COST_CFG = TOPO.cost_config || null;  // {model, input, output} per 1M tokens or null

function calcCost(inTok, outTok) {
  if (!COST_CFG) return null;
  return (inTok * COST_CFG.input + outTok * COST_CFG.output) / 1e6;
}
function fmtCost(c) {
  if (c === null) return "";
  if (c < 0.001) return ` (~$${c.toFixed(5)})`;
  return ` (~$${c.toFixed(4)})`;
}

// ========== LEFT PANEL: AGENTS ==========
const agentElements = {};
(function buildAgentList() {
  const list = document.getElementById("agentList");
  TOPO.agents.forEach(a => {
    const div = document.createElement("div");
    div.className = "agent-item";
    div.dataset.agentId = a.id;
    div.innerHTML = `
      <span class="agent-status status-idle" data-status-dot="${a.id}"></span>
      <span class="agent-name">${a.id}<span class="agent-state" data-agent-state="${a.id}"></span></span>
      <span class="agent-steps" data-steps="${a.id}">0</span>`;
    div.addEventListener("click", () => {
      activeFilter = a.id;
      activeChannelFilter = null;
      Object.values(channelElements).forEach(el => el.classList.remove("selected"));
      updateFilterButtons();
      filterTraceItems();
    });
    agentElements[a.id] = div;
    list.appendChild(div);
  });
})();

// ========== LEFT PANEL: CHANNELS ==========
// ========== LEFT PANEL: RESOURCES ==========
const resourceElements = {};
(function buildResourceList() {
  const list = document.getElementById("resourceList");
  TOPO.resources.forEach(r => {
    const div = document.createElement("div");
    div.className = "channel-item";
    div.dataset.resourceId = r.id;
    const typeIcon = r.type === "Lock" ? "\uD83D\uDD12" : "\uD83D\uDD22";
    const initStr = r.initial !== null && r.initial !== undefined ? ` = ${r.initial}` : "";
    div.innerHTML = `
      <div class="channel-name">${typeIcon} ${r.id}</div>
      <div class="channel-route">${r.type}${initStr} | <span data-lock-holder="${r.id}" style="color:var(--text2)">free</span></div>`;
    resourceElements[r.id] = div;
    list.appendChild(div);
  });
})();

// Track lock holders for display
const lockHolders = {};
function updateLockHolder(lockId, agentId, action) {
  if (action === "acquired") {
    lockHolders[lockId] = agentId;
  } else if (action === "released") {
    if (lockHolders[lockId] === agentId) delete lockHolders[lockId];
  }
  const el = document.querySelector(`[data-lock-holder="${lockId}"]`);
  if (el) {
    if (lockHolders[lockId]) {
      el.textContent = lockHolders[lockId];
      el.style.color = "var(--orange)";
    } else {
      el.textContent = "free";
      el.style.color = "var(--text2)";
    }
  }
}

const channelElements = {};
const channelMsgCounts = {};
(function buildChannelList() {
  const list = document.getElementById("channelList");
  TOPO.channels.forEach(ch => {
    channelMsgCounts[ch.id] = 0;
    const div = document.createElement("div");
    div.className = "channel-item";
    div.dataset.channelId = ch.id;
    div.innerHTML = `
      <div class="channel-name"><span>${ch.id}</span><span class="ch-count" data-ch-count="${ch.id}">0 msgs</span></div>
      <div class="channel-route">${ch.from.join(", ")} &rarr; ${ch.to.join(", ")}</div>`;
    div.addEventListener("click", () => selectChannel(ch.id));
    channelElements[ch.id] = div;
    list.appendChild(div);
  });
})();

function selectChannel(chId) {
  // Toggle: click same channel deselects
  if (activeChannelFilter === chId) {
    activeChannelFilter = null;
  } else {
    activeChannelFilter = chId;
    activeFilter = "all";  // clear agent filter
    updateFilterButtons();
  }
  // Update channel item highlights
  Object.entries(channelElements).forEach(([id, el]) => {
    el.classList.toggle("selected", activeChannelFilter === id);
  });
  // Also deselect agent items
  if (activeChannelFilter) {
    Object.values(agentElements).forEach(el => el.classList.remove("selected"));
  }
  filterTraceItems();
}

function updateChannelCount(chId) {
  const el = document.querySelector(`[data-ch-count="${chId}"]`);
  if (el) el.textContent = channelMsgCounts[chId] + " msgs";
}

// ========== LEFT PANEL: SUMMARY ==========
function updateSummary() {
  const box = document.getElementById("summaryBox");
  const elapsed = runStartTime ? ((Date.now() / 1000 - runStartTime).toFixed(1)) : "0.0";
  const cost = calcCost(tokenState.totalIn, tokenState.totalOut);
  const tokenRow = (tokenState.totalIn || tokenState.totalOut)
    ? `<div class="summary-row"><span>Tokens in/out</span><span class="val">${tokenState.totalIn.toLocaleString()} / ${tokenState.totalOut.toLocaleString()}</span></div>
       <div class="summary-row"><span>Est. cost</span><span class="val">${cost !== null ? "~$" + cost.toFixed(4) : "N/A"}</span></div>`
    : "";
  box.innerHTML = `
    <div class="summary-row"><span>Elapsed</span><span class="val">${elapsed}s</span></div>
    <div class="summary-row"><span>Agents</span><span class="val">${TOPO.agents.length}</span></div>
    <div class="summary-row"><span>Channels</span><span class="val">${TOPO.channels.length}</span></div>
    <div class="summary-row"><span>Resources</span><span class="val">${TOPO.resources.length}</span></div>
    ${tokenRow}`;
}
updateSummary();

// ========== TOP BAR: SIMULATION CHECKS ==========
const simViolations = [];

function renderSimPanel(progress) {
  if (!progress) return;
  const bar = document.getElementById("simBar");
  const panel = document.getElementById("simPanel");
  bar.classList.remove("hidden");  // show once data arrives
  panel.className = "sim-panel";

  function renderItems(obj) {
    return Object.entries(obj).map(([k, v]) =>
      `<span class="sim-item ${v ? 'done' : 'pending'}">${v ? '\u2713' : '\u2022'} ${k}</span>`
    ).join("");
  }

  let html = '<span class="sim-title">Sim Checks</span>';

  // Render all progress sections generically
  const skipKeys = ["all_complete"];
  Object.entries(progress).forEach(([section, val]) => {
    if (skipKeys.includes(section)) return;
    if (typeof val === "object" && val !== null) {
      const label = section.replace(/_/g, " ");
      html += `<div class="sim-section"><span class="sim-section-title">${label}</span><div class="sim-items">${renderItems(val)}</div></div>`;
    }
  });

  if (progress.all_complete) {
    html += '<span class="sim-status complete">\u2705 COMPLETE</span>';
  } else {
    html += '<span class="sim-status incomplete">\u23F3 INCOMPLETE</span>';
  }

  if (simViolations.length > 0) {
    html += `<span class="sim-section-title" style="color:var(--red)">Violations (${simViolations.length})</span>`;
    html += '<div class="sim-violations">';
    simViolations.forEach(v => {
      html += `<span class="sim-violation">\u26A0 ${v.agent}/${v.tool}: ${v.type} <span class="viol-detail">${v.message}</span></span>`;
    });
    html += '</div>';
  }

  panel.innerHTML = html;
}

// ========== PROTOCOL STATE TRACKING ==========
const protocolState = {};   // agent_id → current state name
const protocolViolations = [];

function updateAgentStateLabel(agentId) {
  const el = document.querySelector(`[data-agent-state="${agentId}"]`);
  if (el && protocolState[agentId]) {
    el.textContent = " @ " + protocolState[agentId];
  }
  // Update graph node sub-label to include state
  const node = graphNodeMap[agentId];
  if (node) {
    const steps = agentState[agentId] ? agentState[agentId].steps : 0;
    const stateStr = protocolState[agentId] ? " \u00b7 " + protocolState[agentId] : "";
    node.select(".node-sub").text(steps + " calls" + stateStr);
  }
}

function appendStateTransitionTrace(agentId, fromState, toState, trigger) {
  const container = document.getElementById("traceScroll");
  const div = document.createElement("div");
  div.className = "trace-item trace-state";
  div.dataset.agent = agentId;
  if (activeChannelFilter) {
    div.style.display = "none";
  } else if (activeFilter !== "all" && activeFilter !== agentId) {
    div.style.display = "none";
  }
  div.innerHTML = `
    <span class="trace-agent">${agentId}</span>
    <span class="trace-round" style="color:var(--text2)">\u2192</span>
    <span style="flex-shrink:0;color:var(--purple)">\u25C6</span>
    <div class="trace-body">
      <span style="color:var(--text2)">${fromState || "?"} \u2192 ${toState}</span>
      <div class="trace-args">${trigger}</div>
    </div>`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

function renderProtocolPanel() {
  if (protocolViolations.length === 0) return;
  const bar = document.getElementById("simBar");
  bar.classList.remove("hidden");
  // Append protocol violations section to existing sim panel or create new
  let panel = document.getElementById("protocolPanel");
  if (!panel) {
    panel = document.createElement("div");
    panel.id = "protocolPanel";
    panel.className = "sim-panel";
    panel.style.borderTop = "1px solid var(--border)";
    bar.appendChild(panel);
  }
  let html = `<span class="sim-title" style="color:var(--red)">Protocol Violations (${protocolViolations.length})</span>`;
  html += '<div class="sim-violations">';
  protocolViolations.forEach(v => {
    const argsStr = Object.entries(v.args || {}).map(([k,val]) => val).join(", ");
    html += `<span class="protocol-violation">\u26A0 ${v.agent_id} @ ${v.current_state}: unexpected ${v.operation}(${argsStr})</span>`;
  });
  html += '</div>';
  panel.innerHTML = html;
}

function flashAgentNodeRed(agentId) {
  const node = graphNodeMap[agentId];
  if (!node) return;
  const circle = node.select("circle");
  circle.style("stroke", "var(--red)");
  setTimeout(() => {
    // Restore to current status color
    const status = agentState[agentId] ? agentState[agentId].status : "idle";
    if (status === "busy") circle.style("stroke", "var(--accent)");
    else if (status === "completed") circle.style("stroke", "var(--green)");
    else circle.style("stroke", "var(--text2)");
  }, 1500);
}

// ========== FILTER BUTTONS ==========
function buildFilterButtons() {
  const bar = document.getElementById("traceFilter");
  bar.innerHTML = "";
  const allBtn = document.createElement("span");
  allBtn.className = "filter-btn active";
  allBtn.textContent = "All";
  allBtn.dataset.filter = "all";
  allBtn.onclick = () => { activeFilter = "all"; activeChannelFilter = null; Object.values(channelElements).forEach(el => el.classList.remove("selected")); updateFilterButtons(); filterTraceItems(); };
  bar.appendChild(allBtn);

  TOPO.agents.forEach(a => {
    const btn = document.createElement("span");
    btn.className = "filter-btn";
    btn.textContent = a.id;
    btn.dataset.filter = a.id;
    btn.onclick = () => { activeFilter = a.id; activeChannelFilter = null; Object.values(channelElements).forEach(el => el.classList.remove("selected")); updateFilterButtons(); filterTraceItems(); };
    bar.appendChild(btn);
  });
}
buildFilterButtons();

function updateFilterButtons() {
  document.querySelectorAll(".filter-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.filter === activeFilter);
  });
  // Also highlight agent item in left panel
  Object.entries(agentElements).forEach(([id, el]) => {
    el.classList.toggle("selected", activeFilter === id);
  });
}

function filterTraceItems() {
  const container = document.getElementById("traceScroll");
  const items = container.querySelectorAll(".trace-item");
  items.forEach(el => {
    let show = true;
    if (activeChannelFilter) {
      show = el.dataset.channel === activeChannelFilter;
    } else if (activeFilter !== "all") {
      show = el.dataset.agent === activeFilter;
    }
    el.style.display = show ? "" : "none";
  });
}

// ========== TRACE HELPERS ==========
function toolClass(toolName, result) {
  const status = result.status || "";
  if (toolName === "acquire_lock") {
    if (status === "acquired") return "tool-acquire-acquired";
    if (status === "busy") return "tool-acquire-busy";
    if (status === "already_held") return "tool-acquire-already";
  }
  if (toolName === "release_lock") return "tool-release";
  if (toolName === "send_message") return "tool-send";
  if (toolName === "receive_message") {
    return status === "received" ? "tool-receive-ok" : "tool-receive-timeout";
  }
  if (toolName === "signal_done") return "tool-done";
  if (status === "error") return "tool-error";
  return "tool-domain";
}

function toolIcon(toolName, result) {
  const status = result.status || "";
  if (toolName === "acquire_lock") {
    if (status === "acquired") return "\u2713";
    if (status === "busy") return "\u23F3";
    return "\uD83D\uDD17";
  }
  if (toolName === "release_lock") return "\uD83D\uDD13";
  if (toolName === "send_message") return "\u2191";
  if (toolName === "receive_message") return status === "received" ? "\u2193" : "\u23F0";
  if (toolName === "signal_done") return "\u2714";
  return "\u25CF";
}

function formatArgs(toolName, args) {
  if (toolName === "acquire_lock" || toolName === "release_lock") return args.lock_id || "";
  if (toolName === "send_message") return (args.channel_id || "") + ' label="' + (args.label || "") + '"';
  if (toolName === "receive_message") return args.channel_id || "";
  if (toolName === "signal_done") return "";
  const s = JSON.stringify(args);
  return s.length > 50 ? s.slice(0, 47) + "..." : s;
}

function formatResult(toolName, result) {
  const status = result.status || "?";
  if (toolName === "acquire_lock") return status;
  if (toolName === "release_lock") return "released";
  if (toolName === "send_message") return "sent";
  if (toolName === "receive_message") {
    if (status === "received") return 'label="' + (result.label || "") + '"';
    return "timeout";
  }
  if (toolName === "signal_done") return "done";
  if (status === "ok") return "ok";
  if (status === "error") return result.message || "error";
  return status;
}

function appendTraceItem(agentId, round, toolName, args, result, elapsed) {
  const container = document.getElementById("traceScroll");
  const cls = toolClass(toolName, result);
  const icon = toolIcon(toolName, result);
  const argsStr = formatArgs(toolName, args);
  const resultStr = formatResult(toolName, result);

  const div = document.createElement("div");
  div.className = "trace-item";
  div.dataset.agent = agentId;
  // Tag channel for send/receive operations
  if ((toolName === "send_message" || toolName === "receive_message") && args.channel_id) {
    div.dataset.channel = args.channel_id;
  }
  // Visibility
  if (activeChannelFilter) {
    if (div.dataset.channel !== activeChannelFilter) div.style.display = "none";
  } else if (activeFilter !== "all" && activeFilter !== agentId) {
    div.style.display = "none";
  }
  div.innerHTML = `
    <span class="trace-agent">${agentId}</span>
    <span class="trace-round">R${String(round).padStart(2, '0')}</span>
    <span class="${cls}" style="flex-shrink:0">${icon}</span>
    <div class="trace-body">
      <span class="trace-tool ${cls}">${toolName}</span>
      ${argsStr ? `<div class="trace-args">${argsStr}</div>` : ""}
      <div class="trace-result ${cls}">&rarr; ${resultStr}</div>
    </div>
    <span class="trace-elapsed">${elapsed.toFixed(1)}s</span>`;
  container.appendChild(div);

  // Auto-scroll
  container.scrollTop = container.scrollHeight;

  traceItems.push({ agentId, toolName });
  document.getElementById("traceCount").textContent = traceItems.length + " events";
}

// ========== AGENT STATUS UPDATE ==========
function updateAgentStatus(agentId, status) {
  if (!agentState[agentId]) return;
  agentState[agentId].status = status;

  // Update left panel dot
  const dot = document.querySelector(`[data-status-dot="${agentId}"]`);
  if (dot) {
    dot.className = `agent-status status-${status}`;
  }

  // Update graph node
  const node = graphNodeMap[agentId];
  if (node) {
    const circle = node.select("circle");
    if (status === "busy") {
      circle.style("stroke", "var(--accent)").classed("pulse", true);
    } else if (status === "completed") {
      circle.style("stroke", "var(--green)").classed("pulse", false);
    } else if (status === "error" || status === "timeout") {
      circle.style("stroke", "var(--red)").classed("pulse", false);
    } else {
      circle.style("stroke", "var(--text2)").classed("pulse", false);
    }
  }
}

function updateAgentSteps(agentId, steps) {
  const el = document.querySelector(`[data-steps="${agentId}"]`);
  if (el) el.textContent = steps;

  // Update graph sub-label
  const node = graphNodeMap[agentId];
  if (node) {
    node.select(".node-sub").text(steps + " calls");
  }
}

// ========== D3 GRAPH ==========
const graphNodeMap = {};
const container = document.getElementById("graphContainer");
const W = container.clientWidth || 800;
const H = container.clientHeight || 600;

const svg = d3.select("#graphContainer").insert("svg", ".zoom-bar")
  .attr("width", W).attr("height", H);
const g = svg.append("g");

// Zoom
const zoom = d3.zoom().scaleExtent([0.3, 3]).on("zoom", (e) => {
  g.attr("transform", e.transform);
  document.getElementById("zoomLevel").textContent = Math.round(e.transform.k * 100) + "%";
});
svg.call(zoom);
document.getElementById("zoomIn").onclick = () => svg.transition().call(zoom.scaleBy, 1.3);
document.getElementById("zoomOut").onclick = () => svg.transition().call(zoom.scaleBy, 0.77);
document.getElementById("zoomReset").onclick = () => svg.transition().call(zoom.transform, d3.zoomIdentity);

// Arrow marker
g.append("defs").append("marker")
  .attr("id", "arrowCh").attr("viewBox", "0 -4 8 8")
  .attr("refX", 8).attr("refY", 0)
  .attr("markerWidth", 6).attr("markerHeight", 6)
  .attr("orient", "auto")
  .append("path").attr("d", "M0,-3L8,0L0,3").attr("class", "link-arrow");

const nodes = TOPO.nodes.map(d => ({...d}));
const agentR = 28;
const resSize = 20;

// Assign curvature to parallel channel links
const pairBuckets = {};
TOPO.links.filter(l => l.type === "channel").forEach(l => {
  const key = [l.source, l.target].sort().join("||");
  if (!pairBuckets[key]) pairBuckets[key] = [];
  pairBuckets[key].push(l);
});
Object.values(pairBuckets).forEach(group => {
  const n = group.length;
  group.forEach((l, i) => { l.curve = n === 1 ? 0 : (i - (n - 1) / 2) * 60; });
});

const simulation = d3.forceSimulation(nodes)
  .force("link", d3.forceLink(TOPO.links).id(d => d.id).distance(d =>
    d.type === "resource" ? 100 : 180))
  .force("charge", d3.forceManyBody().strength(d => d.type === "resource" ? -200 : -500))
  .force("center", d3.forceCenter(W / 2, H / 2))
  .force("collision", d3.forceCollide().radius(d => d.type === "agent" ? agentR + 20 : resSize + 15));

const linkLayer = g.append("g");
const nodeLayer = g.append("g");
const beamLayer = g.append("g");  // Layer for beam animations

const link = linkLayer.selectAll(".link")
  .data(TOPO.links).join("path")
  .attr("class", d => d.type === "channel" ? "link-channel" : "link-resource")
  .attr("data-source", d => typeof d.source === "object" ? d.source.id : d.source)
  .attr("data-target", d => typeof d.target === "object" ? d.target.id : d.target)
  .attr("marker-end", d => d.type === "channel" ? "url(#arrowCh)" : null);

// Highlight resource link between agent and lock
function flashResourceLink(agentId, lockId, durationMs) {
  link.filter(d => {
    const src = typeof d.source === "object" ? d.source.id : d.source;
    const tgt = typeof d.target === "object" ? d.target.id : d.target;
    return d.type === "resource" &&
      ((src === agentId && tgt === lockId) || (src === lockId && tgt === agentId));
  }).classed("active", true);

  if (durationMs) {
    setTimeout(() => {
      link.filter(d => {
        const src = typeof d.source === "object" ? d.source.id : d.source;
        const tgt = typeof d.target === "object" ? d.target.id : d.target;
        return d.type === "resource" &&
          ((src === agentId && tgt === lockId) || (src === lockId && tgt === agentId));
      }).classed("active", false);
    }, durationMs);
  }
}

function clearResourceLink(agentId, lockId) {
  link.filter(d => {
    const src = typeof d.source === "object" ? d.source.id : d.source;
    const tgt = typeof d.target === "object" ? d.target.id : d.target;
    return d.type === "resource" &&
      ((src === agentId && tgt === lockId) || (src === lockId && tgt === agentId));
  }).classed("active", false);
}

// Agent nodes
const agentNodes = nodeLayer.selectAll(".agent-g")
  .data(nodes.filter(n => n.type === "agent")).join("g")
  .attr("class", "agent-g").style("cursor", "pointer");

agentNodes.append("circle")
  .attr("class", "node-agent").attr("r", agentR)
  .style("stroke", "var(--text2)");

agentNodes.append("text")
  .attr("class", "node-icon")
  .attr("text-anchor", "middle").attr("dominant-baseline", "central")
  .attr("font-size", "18px")
  .text("\uD83D\uDC64");

agentNodes.append("text")
  .attr("class", "node-label").attr("dy", agentR + 14).text(d => d.id);

agentNodes.append("text")
  .attr("class", "node-sub").attr("dy", agentR + 26)
  .text("0 calls");

// Store node selections by id
agentNodes.each(function(d) { graphNodeMap[d.id] = d3.select(this); });

// Resource nodes
const resNodes = nodeLayer.selectAll(".res-g")
  .data(nodes.filter(n => n.type === "resource")).join("g")
  .attr("class", "res-g").style("cursor", "pointer");

resNodes.append("rect")
  .attr("class", "node-resource")
  .attr("x", -resSize).attr("y", -resSize)
  .attr("width", resSize * 2).attr("height", resSize * 2)
  .attr("rx", 4);

resNodes.append("text")
  .attr("class", "node-icon")
  .attr("text-anchor", "middle").attr("dominant-baseline", "central")
  .attr("font-size", "14px")
  .text(d => d.rtype === "Lock" ? "\uD83D\uDD12" : "\uD83D\uDD22");

resNodes.append("text")
  .attr("class", "node-label").attr("dy", resSize + 14).text(d => d.id);

resNodes.append("text")
  .attr("class", "node-sub").attr("dy", resSize + 26)
  .text(d => d.rtype + (d.initial !== null && d.initial !== undefined ? " = " + d.initial : ""));

resNodes.each(function(d) { graphNodeMap[d.id] = d3.select(this); });

// Drag
const drag = d3.drag()
  .on("start", (e, d) => { if (!e.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
  .on("drag", (e, d) => { d.fx = e.x; d.fy = e.y; })
  .on("end", (e, d) => { if (!e.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; });
agentNodes.call(drag);
resNodes.call(drag);

// Path computation
function getNodeR(d) {
  const n = nodes.find(x => x.id === (typeof d === "string" ? d : d.id));
  return n && n.type === "resource" ? resSize + 2 : agentR + 2;
}

function computePath(d) {
  const sx = d.source.x, sy = d.source.y;
  const tx = d.target.x, ty = d.target.y;
  const dx = tx - sx, dy = ty - sy;
  const dist = Math.sqrt(dx * dx + dy * dy) || 1;
  const curve = d.curve || 0;
  const nx = -dy / dist, ny = dx / dist;
  const cx = (sx + tx) / 2 + nx * curve;
  const cy = (sy + ty) / 2 + ny * curve;

  const rS = getNodeR(d.source);
  const rT = getNodeR(d.target) + (d.type === "channel" ? 8 : 0);

  const dSC = Math.sqrt((cx - sx) ** 2 + (cy - sy) ** 2) || 1;
  const sX = sx + (cx - sx) / dSC * rS, sY = sy + (cy - sy) / dSC * rS;

  const dTC = Math.sqrt((cx - tx) ** 2 + (cy - ty) ** 2) || 1;
  const eX = tx + (cx - tx) / dTC * rT, eY = ty + (cy - ty) / dTC * rT;

  return `M${sX},${sY} Q${cx},${cy} ${eX},${eY}`;
}

simulation.on("tick", () => {
  link.attr("d", computePath);
  agentNodes.attr("transform", d => `translate(${d.x},${d.y})`);
  resNodes.attr("transform", d => `translate(${d.x},${d.y})`);
});

// ========== BEAM ANIMATION ==========
function findNodePos(nodeId) {
  const n = nodes.find(x => x.id === nodeId);
  return n ? { x: n.x, y: n.y } : null;
}

function playBeam(fromId, toId, color) {
  const from = findNodePos(fromId);
  const to = findNodePos(toId);
  if (!from || !to) return;

  const particle = beamLayer.append("circle")
    .attr("class", "beam-particle")
    .attr("r", 5)
    .attr("cx", from.x).attr("cy", from.y)
    .style("fill", color || "var(--green)")
    .style("filter", `drop-shadow(0 0 4px ${color || "var(--green)"})`)
    .style("opacity", 0.9);

  particle.transition()
    .duration(800)
    .attr("cx", to.x).attr("cy", to.y)
    .transition()
    .duration(400)
    .style("opacity", 0)
    .remove();
}

// Find channel route for beam animation
function findChannelRoute(channelId) {
  return TOPO.channels.find(ch => ch.id === channelId);
}

// ========== SSE EVENT HANDLING ==========
const evtSource = new EventSource("/api/events");

evtSource.addEventListener("run.start", (e) => {
  const data = JSON.parse(e.data);
  runStartTime = data._ts;
  // Start elapsed timer
  setInterval(updateSummary, 1000);
});

evtSource.addEventListener("agent.llm_start", (e) => {
  const data = JSON.parse(e.data);
  updateAgentStatus(data.agent_id, "busy");
});

evtSource.addEventListener("agent.llm_end", (e) => {
  const { agent_id, input_tokens, output_tokens } = JSON.parse(e.data);
  if (agentTokens[agent_id]) {
    agentTokens[agent_id].in += input_tokens || 0;
    agentTokens[agent_id].out += output_tokens || 0;
  }
  tokenState.totalIn += input_tokens || 0;
  tokenState.totalOut += output_tokens || 0;
  updateSummary();
});

evtSource.addEventListener("agent.tool_call", (e) => {
  const data = JSON.parse(e.data);
  const { agent_id, round, tool_name, arguments: args, result, elapsed } = data;

  // Update step count
  if (agentState[agent_id]) {
    agentState[agent_id].steps++;
    updateAgentSteps(agent_id, agentState[agent_id].steps);
  }

  // Back to idle after tool call (will pulse again on next llm_start)
  updateAgentStatus(agent_id, "idle");

  // Append trace
  appendTraceItem(agent_id, round, tool_name, args || {}, result || {}, elapsed || 0);

  // Update channel message counts
  if ((tool_name === "send_message" || tool_name === "receive_message") && args && args.channel_id) {
    if (channelMsgCounts[args.channel_id] !== undefined) {
      channelMsgCounts[args.channel_id]++;
      updateChannelCount(args.channel_id);
    }
  }

  // Beam animation for send/receive
  if (tool_name === "send_message" && args) {
    const ch = findChannelRoute(args.channel_id);
    if (ch) {
      ch.to.forEach(toAgent => {
        playBeam(agent_id, toAgent, "var(--green)");
      });
    }
  }
  if (tool_name === "receive_message" && result && result.status === "received" && args) {
    const ch = findChannelRoute(args.channel_id);
    if (ch) {
      ch.from.forEach(fromAgent => {
        playBeam(fromAgent, agent_id, "var(--accent)");
      });
    }
  }

  // Lock beam + link highlight + holder tracking
  if (tool_name === "acquire_lock" && args) {
    if (result && result.status === "acquired") {
      playBeam(agent_id, args.lock_id, "var(--orange)");
      flashResourceLink(agent_id, args.lock_id);  // stays active until release
      updateLockHolder(args.lock_id, agent_id, "acquired");
    } else {
      // busy/already_held — brief flash
      flashResourceLink(agent_id, args.lock_id, 800);
    }
  }
  if (tool_name === "release_lock" && args) {
    playBeam(args.lock_id, agent_id, "var(--text2)");
    clearResourceLink(agent_id, args.lock_id);
    updateLockHolder(args.lock_id, agent_id, "released");
  }
});

// chat.send: agent broadcasts to group chat (tracefix.runtime.baselines.shared_chat)
evtSource.addEventListener("chat.send", (e) => {
  const { agent_id, channel_id } = JSON.parse(e.data);
  if (channelMsgCounts[channel_id] !== undefined) {
    channelMsgCounts[channel_id]++;
    updateChannelCount(channel_id);
  }
  // Beam from agent toward "group_chat" hub node
  playBeam(agent_id, "group_chat", "var(--green)");
});

// chat.receive: agent reads message(s) from group chat (tracefix.runtime.baselines.shared_chat)
evtSource.addEventListener("chat.receive", (e) => {
  const { agent_id, from_agent, channel_id } = JSON.parse(e.data);
  // Beam from "group_chat" hub to receiving agent
  playBeam("group_chat", agent_id, "var(--accent)");
});

evtSource.addEventListener("sim.update", (e) => {
  const data = JSON.parse(e.data);
  if (data.latest_violation) {
    // Avoid duplicates by checking last entry
    const lv = data.latest_violation;
    const last = simViolations[simViolations.length - 1];
    if (!last || last.type !== lv.type || last.agent !== lv.agent || last.tool !== lv.tool || last.message !== lv.message) {
      simViolations.push(lv);
    }
  }
  renderSimPanel(data.progress);
});

evtSource.addEventListener("state.transition", (e) => {
  const data = JSON.parse(e.data);
  protocolState[data.agent_id] = data.to_state;
  updateAgentStateLabel(data.agent_id);
  appendStateTransitionTrace(data.agent_id, data.from_state, data.to_state, data.trigger);
});

evtSource.addEventListener("state.violation", (e) => {
  const data = JSON.parse(e.data);
  protocolViolations.push(data);
  renderProtocolPanel();
  flashAgentNodeRed(data.agent_id);
});

evtSource.addEventListener("agent.done", (e) => {
  const data = JSON.parse(e.data);
  const status = data.status || "completed";
  updateAgentStatus(data.agent_id, status);

  if (agentState[data.agent_id]) {
    agentState[data.agent_id].duration = data.duration || 0;
    agentState[data.agent_id].error = data.error || null;
  }
});

evtSource.addEventListener("run.done", (e) => {
  const data = JSON.parse(e.data);
  evtSource.close();

  // Update header
  const badge = document.getElementById("statusBadge");
  if (data.success) {
    badge.textContent = "SUCCESS";
    badge.className = "badge badge-success";
  } else {
    badge.textContent = "FAILED";
    badge.className = "badge badge-fail";
  }

  const meta = document.getElementById("headerMeta");
  meta.textContent = (data.duration || 0).toFixed(1) + "s";

  // Final sim state from run.done
  if (data.sim) {
    // Replace accumulated violations with final authoritative list
    simViolations.length = 0;
    if (data.sim.violations) {
      data.sim.violations.forEach(v => simViolations.push(v));
    }
    renderSimPanel(data.sim.progress);
  }

  // Final protocol state from run.done
  if (data.protocol) {
    protocolViolations.length = 0;
    if (data.protocol.violations) {
      data.protocol.violations.forEach(v => {
        protocolViolations.push({
          agent_id: v.agent, current_state: v.state,
          operation: v.operation, args: v.args,
        });
      });
    }
    if (data.protocol.final_states) {
      Object.entries(data.protocol.final_states).forEach(([aid, st]) => {
        protocolState[aid] = st;
        updateAgentStateLabel(aid);
      });
    }
    renderProtocolPanel();
  }

  // Final summary update
  updateSummary();
});

evtSource.onerror = () => {
  // Connection closed — run is done
  evtSource.close();
};
</script>
</body>
</html>"""
