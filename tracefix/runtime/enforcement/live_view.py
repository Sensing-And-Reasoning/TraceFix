"""Real-time HTML visualization for Runtime A (SSE-driven).

Generates a self-contained HTML page that:
  1. Fetches IR topology from /api/ir
  2. Connects to /api/events via EventSource for live updates
  3. Renders D3 force-directed graph with animated node states
  4. Shows per-agent state transitions in real time
  5. Plays beam animations for send/receive/acquire/release operations

Key difference from tracefix.runtime.monitoring: events are step-oriented (state transitions
with guards and effects) rather than tool-call-oriented.
"""

from __future__ import annotations

import json


def render_live_html(ir: dict, title: str = "") -> str:
    """Generate HTML page with SSE client for real-time visualization."""
    page_title = title or "Runtime A Live"

    # Pre-compute topology data for the graph
    agents_ir = ir.get("agents", [])
    resources_ir = ir.get("resources", [])
    channels_ir = ir.get("channels", [])
    states_ir = ir.get("states", [])

    # Build states lookup for IR format (list of state dicts)
    states_dict: dict[str, dict] = {}
    if isinstance(states_ir, list):
        for s in states_ir:
            states_dict[s["id"]] = s
    elif isinstance(states_ir, dict):
        states_dict = states_ir

    nodes = []
    for agent in agents_ir:
        nodes.append({"id": agent["id"], "type": "agent", "status": "idle", "steps": 0})
    for res in resources_ir:
        nodes.append({
            "id": res["id"], "type": "resource",
            "rtype": res.get("type", "Lock"),
            "initial": res.get("initial_value", res.get("config", {}).get("initial")),
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
    for state_id, state_def in states_dict.items():
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

    # Fallback: if no resource-agent links from states, connect all agents
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
            "status": "idle", "steps": 0,
        })

    resources_data = []
    for res in resources_ir:
        contenders = sorted(resource_users.get(res["id"], set()))
        resources_data.append({
            "id": res["id"], "type": res.get("type", "Lock"),
            "initial": res.get("initial_value", res.get("config", {}).get("initial")),
            "contenders": contenders,
        })

    graph_data = json.dumps({
        "nodes": nodes,
        "links": links,
        "channels": channels_data,
        "agents": agents_data,
        "resources": resources_data,
        "resource_users": {k: sorted(v) for k, v in resource_users.items()},
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
.app { display:flex; height:100vh; }
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
.status-active { background:var(--accent); animation: pulse-busy 1s ease-in-out infinite; }
.status-done { background:var(--green); }
.status-error { background:var(--red); }
.agent-name { font-weight:600; flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.agent-state { color:var(--text2); font-size:10px; flex-shrink:0; font-family:"SF Mono",Menlo,monospace; }
.agent-steps { color:var(--text2); font-size:11px; flex-shrink:0; }

.channel-list { overflow-y:auto; padding:0 8px 4px; }
.channel-item { padding:6px 10px; margin-bottom:3px; border-radius:6px;
                background:var(--bg3); border:1px solid var(--border); font-size:11px; }
.channel-name { font-weight:600; color:var(--accent); }
.channel-route { font-size:10px; color:var(--text2); margin-top:1px; }

.summary-box { padding:10px 14px; border-top:1px solid var(--border); flex-shrink:0; margin-top:auto; }
.summary-row { display:flex; justify-content:space-between; font-size:12px; padding:2px 0; }
.summary-row .val { font-weight:600; color:var(--accent); }

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
.trace-step { color:var(--text2); flex-shrink:0; width:28px; }
.trace-body { flex:1; overflow:hidden; }
.trace-transition { font-weight:600; color:var(--text); }
.trace-ops { color:var(--text2); font-size:10px; overflow:hidden;
             text-overflow:ellipsis; white-space:nowrap; max-width:220px; }
.trace-tools { font-size:10px; color:var(--purple); margin-top:1px; }
.trace-elapsed { color:var(--text2); flex-shrink:0; font-size:10px; }

/* Op-specific colors */
.op-send { color:var(--green); }
.op-recv { color:var(--accent); }
.op-acquire { color:var(--orange); }
.op-release { color:var(--text2); }
.op-done { color:var(--green); }

/* Simulation progress panel */
.sim-progress-list { overflow-y:auto; max-height:150px; padding:0 8px 4px; }
.sim-progress-item { padding:5px 10px; margin-bottom:3px; border-radius:5px;
                     background:var(--bg3); border:1px solid var(--border); font-size:11px; }
.sim-progress-bar { height:3px; background:var(--border); border-radius:2px; margin-top:4px; }
.sim-progress-fill { height:100%; border-radius:2px; transition:width 0.4s ease; }

/* Violations panel */
.vio-list { overflow-y:auto; max-height:110px; padding:0 8px 4px; }
.vio-item { padding:5px 10px; margin-bottom:3px; border-radius:5px; background:var(--bg3);
            border:1px solid rgba(248,81,73,0.45); font-size:11px; }
.vio-title { color:var(--red); font-weight:600; }
.vio-detail { color:var(--text2); font-size:10px; margin-top:2px;
              overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }

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
    <div class="panel-header" id="simPanelHdr" style="display:none">Simulation</div>
    <div class="sim-progress-list" id="simProgressList" style="display:none"></div>
    <div class="panel-header" id="vioPanelHdr" style="display:none;color:var(--red)">Violations <span id="vioCount" style="font-weight:700">0</span></div>
    <div class="vio-list" id="vioList" style="display:none"></div>
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
      <span>State Transitions</span>
      <span id="traceCount" style="color:var(--text2);font-size:11px;font-weight:400">0 steps</span>
    </div>
    <div class="trace-filter" id="traceFilter"></div>
    <div class="trace-scroll" id="traceScroll"></div>
  </div>

</div>

<script src="https://d3js.org/d3.v7.min.js"></script>
<script>
// ========== INITIAL TOPOLOGY DATA ==========
const TOPO = __GRAPH_DATA__;
let runStartTime = null;
let traceItems = [];
let activeFilter = "all";
let totalSteps = 0;

// Agent state tracking
const agentState = {};
TOPO.agents.forEach(a => {
  agentState[a.id] = { status: "idle", steps: 0, currentState: a.initial_state || "?", duration: 0 };
});

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
      <span class="agent-name">${a.id}</span>
      <span class="agent-state" data-agent-state="${a.id}">${a.initial_state || ""}</span>
      <span class="agent-steps" data-steps="${a.id}">0</span>`;
    div.addEventListener("click", () => {
      activeFilter = a.id;
      updateFilterButtons();
      filterTraceItems();
    });
    agentElements[a.id] = div;
    list.appendChild(div);
  });
})();

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

// Track lock holders
const lockHolders = {};
function updateLockHolder(lockId, agentId, action) {
  if (action === "acquire") {
    lockHolders[lockId] = agentId;
  } else if (action === "release") {
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

// ========== LEFT PANEL: CHANNELS ==========
(function buildChannelList() {
  const list = document.getElementById("channelList");
  TOPO.channels.forEach(ch => {
    const div = document.createElement("div");
    div.className = "channel-item";
    div.innerHTML = `
      <div class="channel-name">${ch.id}</div>
      <div class="channel-route">${ch.from.join(", ")} &rarr; ${ch.to.join(", ")}</div>`;
    list.appendChild(div);
  });
})();

// ========== LEFT PANEL: SUMMARY ==========
function updateSummary() {
  const box = document.getElementById("summaryBox");
  const elapsed = runStartTime ? ((Date.now() / 1000 - runStartTime).toFixed(1)) : "0.0";
  const doneCount = Object.values(agentState).filter(s => s.status === "done").length;
  box.innerHTML = `
    <div class="summary-row"><span>Elapsed</span><span class="val">${elapsed}s</span></div>
    <div class="summary-row"><span>Steps</span><span class="val">${totalSteps}</span></div>
    <div class="summary-row"><span>Agents</span><span class="val">${doneCount}/${TOPO.agents.length} done</span></div>
    <div class="summary-row"><span>Channels</span><span class="val">${TOPO.channels.length}</span></div>
    <div class="summary-row"><span>Resources</span><span class="val">${TOPO.resources.length}</span></div>`;
}
updateSummary();

// ========== FILTER BUTTONS ==========
function buildFilterButtons() {
  const bar = document.getElementById("traceFilter");
  bar.innerHTML = "";
  const allBtn = document.createElement("span");
  allBtn.className = "filter-btn active";
  allBtn.textContent = "All";
  allBtn.dataset.filter = "all";
  allBtn.onclick = () => { activeFilter = "all"; updateFilterButtons(); filterTraceItems(); };
  bar.appendChild(allBtn);

  TOPO.agents.forEach(a => {
    const btn = document.createElement("span");
    btn.className = "filter-btn";
    btn.textContent = a.id;
    btn.dataset.filter = a.id;
    btn.onclick = () => { activeFilter = a.id; updateFilterButtons(); filterTraceItems(); };
    bar.appendChild(btn);
  });
}
buildFilterButtons();

function updateFilterButtons() {
  document.querySelectorAll(".filter-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.filter === activeFilter);
  });
  Object.entries(agentElements).forEach(([id, el]) => {
    el.classList.toggle("selected", activeFilter === id);
  });
}

function filterTraceItems() {
  const container = document.getElementById("traceScroll");
  const items = container.querySelectorAll(".trace-item");
  items.forEach(el => {
    if (activeFilter === "all" || el.dataset.agent === activeFilter) {
      el.style.display = "";
    } else {
      el.style.display = "none";
    }
  });
}

// ========== TRACE HELPERS ==========
function opIcon(op) {
  if (op.startsWith("send(")) return "\u2191";
  if (op.startsWith("recv(")) return "\u2193";
  if (op.startsWith("acquire(")) return "\uD83D\uDD12";
  if (op.startsWith("release(")) return "\uD83D\uDD13";
  if (op.startsWith("dec(")) return "\u2212";
  if (op.startsWith("inc(")) return "+";
  if (op.startsWith("inc_local(")) return "\u21BB";
  return "\u25CF";
}

function opClass(op) {
  if (op.startsWith("send(")) return "op-send";
  if (op.startsWith("recv(")) return "op-recv";
  if (op.startsWith("acquire(") || op.startsWith("dec(")) return "op-acquire";
  if (op.startsWith("release(") || op.startsWith("inc(")) return "op-release";
  return "";
}

function appendTraceItem(step, agentId, fromState, toState, guards, effects, toolCalls, elapsed) {
  const container = document.getElementById("traceScroll");
  const div = document.createElement("div");
  div.className = "trace-item";
  div.dataset.agent = agentId;
  if (activeFilter !== "all" && activeFilter !== agentId) {
    div.style.display = "none";
  }

  const allOps = [...guards, ...effects];
  const opsHtml = allOps.map(op =>
    `<span class="${opClass(op)}">${opIcon(op)} ${op}</span>`
  ).join(" ");

  const toolsHtml = toolCalls && toolCalls.length > 0
    ? `<div class="trace-tools">\uD83E\uDD16 ${toolCalls.map(t => t.name || t.tool || "?").join(", ")}</div>`
    : "";

  div.innerHTML = `
    <span class="trace-agent">${agentId}</span>
    <span class="trace-step">#${step}</span>
    <div class="trace-body">
      <span class="trace-transition">${fromState} \u2192 ${toState}</span>
      ${opsHtml ? `<div class="trace-ops">${opsHtml}</div>` : ""}
      ${toolsHtml}
    </div>
    <span class="trace-elapsed">${elapsed.toFixed(2)}s</span>`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;

  traceItems.push({ agentId, step });
  document.getElementById("traceCount").textContent = traceItems.length + " steps";
}

// ========== AGENT STATUS UPDATE ==========
function updateAgentStatus(agentId, status) {
  if (!agentState[agentId]) return;
  agentState[agentId].status = status;

  const dot = document.querySelector(`[data-status-dot="${agentId}"]`);
  if (dot) {
    dot.className = `agent-status status-${status}`;
  }

  const node = graphNodeMap[agentId];
  if (node) {
    const circle = node.select("circle");
    if (status === "active") {
      circle.style("stroke", "var(--accent)").classed("pulse", true);
    } else if (status === "done") {
      circle.style("stroke", "var(--green)").classed("pulse", false);
    } else if (status === "error") {
      circle.style("stroke", "var(--red)").classed("pulse", false);
    } else {
      circle.style("stroke", "var(--text2)").classed("pulse", false);
    }
  }
}

function updateAgentState(agentId, state) {
  const el = document.querySelector(`[data-agent-state="${agentId}"]`);
  if (el) el.textContent = state;

  const node = graphNodeMap[agentId];
  if (node) {
    node.select(".node-sub").text(state);
  }
}

function updateAgentSteps(agentId, steps) {
  const el = document.querySelector(`[data-steps="${agentId}"]`);
  if (el) el.textContent = steps;
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
const beamLayer = g.append("g");

const link = linkLayer.selectAll(".link")
  .data(TOPO.links).join("path")
  .attr("class", d => d.type === "channel" ? "link-channel" : "link-resource")
  .attr("data-source", d => typeof d.source === "object" ? d.source.id : d.source)
  .attr("data-target", d => typeof d.target === "object" ? d.target.id : d.target)
  .attr("marker-end", d => d.type === "channel" ? "url(#arrowCh)" : null);

// Highlight resource link
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
  .text(d => {
    const a = TOPO.agents.find(a => a.id === d.id);
    return a ? a.initial_state : "";
  });

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

// Parse guard/effect strings and trigger beams
function parseOps(agentId, ops, isGuard) {
  ops.forEach(op => {
    // send(channel, label)
    let m = op.match(/^send\((\w+),/);
    if (m) {
      const ch = findChannelRoute(m[1]);
      if (ch) {
        ch.to.forEach(toAgent => playBeam(agentId, toAgent, "var(--green)"));
      }
      return;
    }
    // recv(channel, label)
    m = op.match(/^recv\((\w+),/);
    if (m) {
      const ch = findChannelRoute(m[1]);
      if (ch) {
        ch.from.forEach(fromAgent => playBeam(fromAgent, agentId, "var(--accent)"));
      }
      return;
    }
    // acquire(resource)
    m = op.match(/^acquire\((\w+)\)/);
    if (m) {
      playBeam(agentId, m[1], "var(--orange)");
      flashResourceLink(agentId, m[1]);
      updateLockHolder(m[1], agentId, "acquire");
      return;
    }
    // release(resource)
    m = op.match(/^release\((\w+)\)/);
    if (m) {
      playBeam(m[1], agentId, "var(--text2)");
      clearResourceLink(agentId, m[1]);
      updateLockHolder(m[1], agentId, "release");
      return;
    }
    // dec(resource) — counter acquire
    m = op.match(/^dec\((\w+)\)/);
    if (m) {
      playBeam(agentId, m[1], "var(--orange)");
      flashResourceLink(agentId, m[1], 800);
      return;
    }
    // inc(resource) — counter release
    m = op.match(/^inc\((\w+)\)/);
    if (m) {
      playBeam(m[1], agentId, "var(--text2)");
      flashResourceLink(agentId, m[1], 800);
      return;
    }
  });
}

// ========== SSE EVENT HANDLING ==========
const evtSource = new EventSource("/api/events");

evtSource.addEventListener("run.start", (e) => {
  const data = JSON.parse(e.data);
  runStartTime = data._ts;
  setInterval(updateSummary, 1000);
});

evtSource.addEventListener("step", (e) => {
  const data = JSON.parse(e.data);
  const { step, agent_id, from_state, to_state, guards, effects, tool_calls, timestamp } = data;

  totalSteps = step;

  // Update agent state
  if (agentState[agent_id]) {
    agentState[agent_id].steps++;
    agentState[agent_id].currentState = to_state;
    updateAgentSteps(agent_id, agentState[agent_id].steps);
    updateAgentState(agent_id, to_state);
    updateAgentStatus(agent_id, "active");
    // Brief pulse then back to idle
    setTimeout(() => {
      if (agentState[agent_id].status === "active") {
        updateAgentStatus(agent_id, "idle");
      }
    }, 500);
  }

  // Append trace
  appendTraceItem(step, agent_id, from_state, to_state, guards || [], effects || [], tool_calls || [], timestamp || 0);

  // Trigger beam animations from guards and effects
  parseOps(agent_id, guards || [], true);
  parseOps(agent_id, effects || [], false);

  updateSummary();
});

evtSource.addEventListener("agent.done", (e) => {
  const data = JSON.parse(e.data);
  updateAgentStatus(data.agent_id, "done");
  if (data.final_state) {
    updateAgentState(data.agent_id, data.final_state);
  }
  updateSummary();
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
    badge.textContent = data.error && data.error.includes("Timeout") ? "TIMEOUT" : "FAILED";
    badge.className = "badge badge-fail";
  }

  const meta = document.getElementById("headerMeta");
  meta.textContent = (data.duration || 0).toFixed(1) + "s | " + (data.steps || 0) + " steps";

  // Mark any remaining agents
  if (data.final_states) {
    Object.entries(data.final_states).forEach(([aid, state]) => {
      updateAgentStatus(aid, "done");
      updateAgentState(aid, state);
    });
  }

  updateSummary();
});

evtSource.addEventListener("sim.update", (e) => {
  const data = JSON.parse(e.data);
  updateSimPanel(data.progress || {}, data.violations || []);
});

function updateSimPanel(progress, violations) {
  const hdr = document.getElementById("simPanelHdr");
  const listEl = document.getElementById("simProgressList");
  const vioHdr = document.getElementById("vioPanelHdr");
  const vioEl = document.getElementById("vioList");

  hdr.style.display = "";
  listEl.style.display = "";
  listEl.innerHTML = "";

  let allComplete = false;

  for (const [category, value] of Object.entries(progress)) {
    if (category === "all_complete") { allComplete = value; continue; }

    const div = document.createElement("div");
    div.className = "sim-progress-item";

    if (typeof value === "object" && value !== null && !Array.isArray(value)) {
      const items = Object.values(value);
      const done = items.filter(v => v === true).length;
      const total = items.length;
      const pct = total > 0 ? Math.round(done / total * 100) : 0;
      const finished = done === total && total > 0;
      div.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span style="color:${finished ? 'var(--green)' : 'var(--text)'}">${category}</span>
          <span style="color:${finished ? 'var(--green)' : 'var(--orange)'};font-weight:600">${done}/${total}</span>
        </div>
        <div class="sim-progress-bar">
          <div class="sim-progress-fill" style="width:${pct}%;background:${finished ? 'var(--green)' : 'var(--accent)'}"></div>
        </div>`;
    } else {
      const isDone = value === true;
      div.innerHTML = `<span style="color:${isDone ? 'var(--green)' : 'var(--text2)'}">
        ${isDone ? "✓" : "○"} ${category}: ${value}</span>`;
    }
    listEl.appendChild(div);
  }

  if (allComplete) {
    hdr.style.color = "var(--green)";
    hdr.innerHTML = "Simulation <span style='font-size:10px'>\u2713 COMPLETE</span>";
  } else {
    hdr.style.color = "";
    hdr.textContent = "Simulation";
  }

  if (violations && violations.length > 0) {
    vioHdr.style.display = "";
    vioEl.style.display = "";
    document.getElementById("vioCount").textContent = violations.length;
    vioEl.innerHTML = "";
    violations.slice(-8).forEach(v => {
      const div = document.createElement("div");
      div.className = "vio-item";
      div.innerHTML = `
        <div class="vio-title">[${v.type || "?"}] ${v.agent || ""}${v.tool ? " / " + v.tool : ""}</div>
        <div class="vio-detail" title="${v.message || ""}">${v.message || ""}</div>`;
      vioEl.appendChild(div);
    });
  }
}

evtSource.onerror = () => {
  evtSource.close();
};
</script>
</body>
</html>"""
