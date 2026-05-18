"""Topology → self-contained HTML visualization (swarm-ide style dark theme).

Two entry points:
  save_html(topology, ...)   — static topology-only visualization (viz command)
  save_run_html(ir, result, ...) — execution trace visualization (run command)
"""

from __future__ import annotations

import html as _html
import json
from pathlib import Path
from typing import TYPE_CHECKING

from tracefix.runtime.enforcement.topology import Topology, StateMachine

if TYPE_CHECKING:
    from tracefix.runtime.enforcement.engine import RunResult


def _escape(text: str) -> str:
    return _html.escape(text, quote=True)


def _build_graph_data(topology: Topology) -> str:
    """Build the JS data object embedding all topology info."""
    t = topology

    # Nodes: agents (circle) + resources (rect)
    nodes = []
    for agent in t.agents:
        sm = next(s for s in t.state_machines if s.agent_id == agent.id)
        nodes.append({
            "id": agent.id, "type": "agent", "states": len(sm.states),
            "decisions": len(sm.decision_points),
        })
    for res in t.resources:
        nodes.append({
            "id": res.id, "type": "resource", "rtype": res.type,
            "initial": res.initial_value,
        })

    # Links: channels (agent→agent) + resource usage (agent↔resource)
    links = []
    for ch in t.channels:
        from_agents = ch.from_agents
        to_agents = ch.to_agents
        for f in from_agents:
            for to in to_agents:
                if f != to:
                    links.append({
                        "source": f, "target": to, "type": "channel",
                        "id": ch.id, "labels": ch.labels,
                    })

    # Resource → agent links (from resource_usage which tracks ALL agents)
    for rid, agents_set in t.analysis.resource_usage.items():
        for aid in sorted(agents_set):
            links.append({"source": aid, "target": rid, "type": "resource"})

    # channels panel data (including operations)
    channels_data = []
    for ch in t.channels:
        ops = t.channel_operations.get(ch.id, [])
        ops_data = [
            {"dir": op.direction, "agent": op.agent, "state": op.state,
             "target": op.target, "label": op.label}
            for op in ops
        ]
        channels_data.append({
            "id": ch.id,
            "from": ch.from_agents,
            "to": ch.to_agents,
            "labels": ch.labels,
            "operations": ops_data,
        })

    # agent detail data
    agents_data = []
    for agent in t.agents:
        sm = next(s for s in t.state_machines if s.agent_id == agent.id)
        states_info = []
        for sid in sm.states:
            tags = []
            if sid == sm.initial_state:
                tags.append("initial")
            if sid in sm.terminal_states:
                tags.append("terminal")
            if sid in sm.decision_points:
                tags.append("decision")
            states_info.append({"id": sid, "tags": tags})
        agents_data.append({
            "id": agent.id,
            "tools": agent.tools,
            "initial_state": agent.initial_state,
            "state_count": len(sm.states),
            "decision_count": len(sm.decision_points),
            "terminal_count": len(sm.terminal_states),
            "states": states_info,
        })

    # resources data
    resources_data = []
    for res in t.resources:
        resources_data.append({
            "id": res.id, "type": res.type, "initial": res.initial_value,
        })

    summary = {
        "agents": t.analysis.agent_count,
        "channels": t.analysis.channel_count,
        "resources": t.analysis.resource_count,
        "states": t.analysis.state_count,
        "decisions": t.analysis.decision_point_count,
    }

    data = {
        "nodes": nodes, "links": links,
        "channels": channels_data, "agents": agents_data,
        "resources": resources_data, "summary": summary,
        "contention": {k: sorted(v) for k, v in t.analysis.resource_contention.items()},
    }
    return json.dumps(data)


def render_html(topology: Topology, title: str = "") -> str:
    """Generate a self-contained HTML page visualizing the topology (swarm-ide style)."""
    page_title = _escape(title) if title else "Topology Visualization"
    graph_data = _build_graph_data(topology)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{page_title}</title>
<style>
:root {{
  --bg: #0d1117; --bg2: #161b22; --bg3: #21262d; --border: #30363d;
  --text: #c9d1d9; --text2: #8b949e; --accent: #58a6ff; --green: #3fb950;
  --red: #f85149; --orange: #d29922; --purple: #bc8cff;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
       background:var(--bg); color:var(--text); overflow:hidden; }}

/* --- Layout: left channel panel | center graph | right detail panel --- */
.app {{ display:flex; height:100vh; }}
.left-panel {{ width:260px; background:var(--bg2); border-right:1px solid var(--border);
               display:flex; flex-direction:column; flex-shrink:0; }}
.center {{ flex:1; position:relative; }}
.right-panel {{ width:320px; background:var(--bg2); border-left:1px solid var(--border);
                overflow-y:auto; flex-shrink:0; }}

/* --- Header bar --- */
.header {{ height:40px; background:var(--bg3); border-bottom:1px solid var(--border);
           display:flex; align-items:center; padding:0 14px; font-size:13px; font-weight:600; }}
.header .title {{ color:var(--text); }}
.header .badge {{ margin-left:auto; background:var(--accent); color:var(--bg);
                  font-size:11px; padding:2px 8px; border-radius:10px; }}

/* --- Left panel: channels + summary --- */
.panel-header {{ padding:10px 14px 6px; font-size:11px; text-transform:uppercase;
                 color:var(--text2); letter-spacing:0.8px; font-weight:600; }}
.channel-list {{ flex:1; overflow-y:auto; padding:0 8px 8px; }}
.channel-item {{ padding:8px 10px; margin-bottom:4px; border-radius:6px;
                 background:var(--bg3); border:1px solid var(--border); cursor:pointer;
                 transition:border-color 0.15s; }}
.channel-item:hover {{ border-color:var(--accent); }}
.channel-item.selected {{ border-color:var(--accent); background:rgba(88,166,255,0.08); }}
.channel-name {{ font-size:12px; font-weight:600; color:var(--accent); }}
.channel-route {{ font-size:11px; color:var(--text2); margin-top:2px; }}
.channel-labels {{ font-size:10px; color:var(--text2); margin-top:3px; }}
.channel-labels span {{ background:var(--bg); padding:1px 6px; border-radius:3px;
                        margin-right:4px; border:1px solid var(--border); }}
.summary-box {{ padding:10px 14px; border-top:1px solid var(--border); }}
.summary-row {{ display:flex; justify-content:space-between; font-size:12px; padding:2px 0; }}
.summary-row .val {{ font-weight:600; color:var(--accent); }}

/* --- Right panel: agent/resource detail --- */
.detail-placeholder {{ padding:40px 20px; text-align:center; color:var(--text2); font-size:13px; }}
.detail-header {{ padding:14px; border-bottom:1px solid var(--border); }}
.detail-header .name {{ font-size:16px; font-weight:700; }}
.detail-header .type-badge {{ font-size:11px; padding:2px 8px; border-radius:4px;
                              margin-left:8px; vertical-align:middle; }}
.type-agent {{ background:rgba(88,166,255,0.15); color:var(--accent); }}
.type-lock {{ background:rgba(248,81,73,0.15); color:var(--red); }}
.type-counter {{ background:rgba(210,153,34,0.15); color:var(--orange); }}
.detail-section {{ padding:12px 14px; border-bottom:1px solid var(--border); }}
.detail-section h4 {{ font-size:11px; text-transform:uppercase; color:var(--text2);
                      margin-bottom:8px; letter-spacing:0.5px; }}
.detail-stat {{ display:flex; justify-content:space-between; font-size:12px; padding:2px 0; }}
.detail-stat .val {{ color:var(--accent); font-weight:600; }}
.state-item {{ font-size:12px; font-family:"SF Mono",Menlo,monospace; padding:3px 6px;
               margin-bottom:2px; border-radius:4px; background:var(--bg); }}
.state-item .tag {{ font-size:9px; padding:1px 5px; border-radius:3px; margin-left:6px;
                    font-family:sans-serif; }}
.tag-initial {{ background:var(--accent); color:var(--bg); }}
.tag-terminal {{ background:var(--red); color:#fff; }}
.tag-decision {{ background:var(--orange); color:var(--bg); }}
.contention-agents {{ font-size:11px; color:var(--text2); padding:2px 6px; }}

/* --- SVG graph --- */
svg {{ width:100%; height:100%; }}
.link-channel {{ stroke:var(--accent); stroke-width:1.5; fill:none; opacity:0.6; }}
.link-resource {{ stroke:var(--green); stroke-width:1; fill:none; opacity:0.4;
                  stroke-dasharray:4,3; }}
.node-agent {{ fill:transparent; stroke:var(--green); stroke-width:2; cursor:pointer; }}
.node-agent:hover {{ stroke-width:3; stroke:var(--accent); }}
.node-agent.selected {{ stroke:var(--accent); stroke-width:3; filter:drop-shadow(0 0 6px rgba(88,166,255,0.5)); }}
.node-resource {{ fill:transparent; stroke:var(--red); stroke-width:1.5; cursor:pointer; rx:4; }}
.node-resource:hover {{ stroke-width:2.5; stroke:var(--orange); }}
.node-resource.selected {{ stroke:var(--orange); stroke-width:2.5; filter:drop-shadow(0 0 6px rgba(210,153,34,0.5)); }}
.node-label {{ font-size:11px; fill:var(--text); text-anchor:middle; pointer-events:none; }}
.node-sub {{ font-size:9px; fill:var(--text2); text-anchor:middle; pointer-events:none; }}
.node-icon {{ fill:var(--text); pointer-events:none; }}
.link-arrow {{ fill:var(--accent); opacity:0.6; }}

/* --- Channel detail: message log --- */
.op-list {{ padding:0; }}
.op-item {{ display:flex; align-items:flex-start; padding:6px 8px; margin-bottom:2px;
            border-radius:4px; background:var(--bg); font-size:12px; gap:8px; }}
.op-dir {{ flex-shrink:0; width:18px; text-align:center; font-size:14px; }}
.op-dir.send {{ color:var(--green); }}
.op-dir.recv {{ color:var(--accent); }}
.op-body {{ flex:1; }}
.op-agent {{ font-weight:600; color:var(--text); }}
.op-label {{ display:inline-block; background:var(--bg3); border:1px solid var(--border);
             padding:0 6px; border-radius:3px; font-size:11px; color:var(--orange);
             margin-left:4px; font-family:"SF Mono",Menlo,monospace; }}
.op-transition {{ font-size:10px; color:var(--text2); margin-top:2px;
                  font-family:"SF Mono",Menlo,monospace; }}
.type-channel {{ background:rgba(88,166,255,0.15); color:var(--accent); }}

/* --- Zoom controls --- */
.zoom-bar {{ position:absolute; bottom:12px; left:50%; transform:translateX(-50%);
             background:var(--bg3); border:1px solid var(--border); border-radius:6px;
             display:flex; align-items:center; padding:4px 10px; gap:8px; font-size:12px; }}
.zoom-bar button {{ background:none; border:1px solid var(--border); color:var(--text);
                    width:26px; height:26px; border-radius:4px; cursor:pointer; font-size:14px; }}
.zoom-bar button:hover {{ background:var(--border); }}
.zoom-bar .zoom-level {{ color:var(--text2); min-width:40px; text-align:center; }}
</style>
</head>
<body>
<div class="app">

  <!-- Left Panel: Channels -->
  <div class="left-panel">
    <div class="header">
      <span class="title">{page_title}</span>
    </div>
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

  <!-- Right Panel: Detail -->
  <div class="right-panel" id="detailPanel">
    <div class="detail-placeholder">Click an agent or resource to view details</div>
  </div>

</div>

<script src="https://d3js.org/d3.v7.min.js"></script>
<script>
const DATA = {graph_data};
let selectedId = null;

// ========== LEFT PANEL ==========
let selectedChannelId = null;
const channelElements = {{}};

(function buildLeftPanel() {{
  const list = document.getElementById("channelList");
  DATA.channels.forEach(ch => {{
    const div = document.createElement("div");
    div.className = "channel-item";
    div.dataset.channelId = ch.id;
    const labelsHtml = ch.labels.length
      ? ch.labels.map(l => `<span>${{l}}</span>`).join("")
      : "<span>unlabeled</span>";
    div.innerHTML = `
      <div class="channel-name">${{ch.id}}</div>
      <div class="channel-route">${{ch.from.join(", ")}} &rarr; ${{ch.to.join(", ")}}</div>
      <div class="channel-labels">${{labelsHtml}}</div>`;
    div.addEventListener("click", () => selectChannel(ch.id));
    channelElements[ch.id] = div;
    list.appendChild(div);
  }});

  const box = document.getElementById("summaryBox");
  const s = DATA.summary;
  box.innerHTML = `
    <div class="summary-row"><span>Agents</span><span class="val">${{s.agents}}</span></div>
    <div class="summary-row"><span>Channels</span><span class="val">${{s.channels}}</span></div>
    <div class="summary-row"><span>Resources</span><span class="val">${{s.resources}}</span></div>
    <div class="summary-row"><span>States</span><span class="val">${{s.states}}</span></div>
    <div class="summary-row"><span>Decision Points</span><span class="val">${{s.decisions}}</span></div>`;
}})();

function selectChannel(chId) {{
  // Clear graph node selection
  selectedId = null;
  d3.selectAll(".node-agent, .node-resource").classed("selected", false);
  // Update channel selection
  Object.values(channelElements).forEach(el => el.classList.remove("selected"));
  if (chId === selectedChannelId) {{
    selectedChannelId = null;
    document.getElementById("detailPanel").innerHTML =
      '<div class="detail-placeholder">Click an agent or resource to view details</div>';
    return;
  }}
  selectedChannelId = chId;
  if (channelElements[chId]) channelElements[chId].classList.add("selected");
  showChannelDetail(chId);
}}

function clearChannelSelection() {{
  selectedChannelId = null;
  Object.values(channelElements).forEach(el => el.classList.remove("selected"));
}}

// ========== RIGHT PANEL ==========
function showChannelDetail(chId) {{
  const panel = document.getElementById("detailPanel");
  const ch = DATA.channels.find(x => x.id === chId);
  if (!ch) return;

  const labelsHtml = ch.labels.length
    ? ch.labels.map(l => `<span class="op-label">${{l}}</span>`).join(" ")
    : '<span style="color:var(--text2)">unlabeled</span>';

  // Build operation log — group sends first, then receives
  const sends = ch.operations.filter(o => o.dir === "send");
  const recvs = ch.operations.filter(o => o.dir === "receive");

  function renderOps(ops) {{
    if (ops.length === 0) return '<div style="font-size:12px;color:var(--text2);padding:4px 8px">None</div>';
    return ops.map(op => {{
      const arrow = op.dir === "send" ? "&uarr;" : "&darr;";
      const dirClass = op.dir === "send" ? "send" : "recv";
      const labelHtml = op.label ? `<span class="op-label">${{op.label}}</span>` : "";
      return `<div class="op-item">
        <div class="op-dir ${{dirClass}}">${{arrow}}</div>
        <div class="op-body">
          <span class="op-agent">${{op.agent}}</span> ${{labelHtml}}
          <div class="op-transition">${{op.state}} &rarr; ${{op.target}}</div>
        </div>
      </div>`;
    }}).join("");
  }}

  panel.innerHTML = `
    <div class="detail-header">
      <span class="name">${{ch.id}}</span>
      <span class="type-badge type-channel">Channel</span>
    </div>
    <div class="detail-section">
      <h4>Route</h4>
      <div class="detail-stat"><span>From</span><span class="val">${{ch.from.join(", ")}}</span></div>
      <div class="detail-stat"><span>To</span><span class="val">${{ch.to.join(", ")}}</span></div>
    </div>
    <div class="detail-section">
      <h4>Labels</h4>
      <div style="padding:2px 0">${{labelsHtml}}</div>
    </div>
    <div class="detail-section">
      <h4>Send Operations (${{sends.length}})</h4>
      <div class="op-list">${{renderOps(sends)}}</div>
    </div>
    <div class="detail-section">
      <h4>Receive Operations (${{recvs.length}})</h4>
      <div class="op-list">${{renderOps(recvs)}}</div>
    </div>`;
}}

function showAgentDetail(agentId) {{
  const panel = document.getElementById("detailPanel");
  const a = DATA.agents.find(x => x.id === agentId);
  if (!a) return;

  // Which channels involve this agent
  const relatedCh = DATA.channels.filter(
    ch => ch.from.includes(agentId) || ch.to.includes(agentId));
  const chHtml = relatedCh.map(ch => {{
    const dir = ch.from.includes(agentId) ? "send" : "recv";
    return `<div class="state-item">${{dir === "send" ? "&uarr;" : "&darr;"}} ${{ch.id}}</div>`;
  }}).join("");

  // Which resources this agent uses (from contention + resource links)
  const usedRes = DATA.resources.filter(r => {{
    const cont = DATA.contention[r.id];
    if (cont && cont.includes(agentId)) return true;
    // check links
    return DATA.links.some(l => l.type === "resource" &&
      ((l.source === agentId && l.target === r.id) || (l.source === r.id && l.target === agentId)));
  }});

  const statesHtml = a.states.map(s => {{
    const tags = s.tags.map(t => `<span class="tag tag-${{t}}">${{t}}</span>`).join("");
    return `<div class="state-item">${{s.id}} ${{tags}}</div>`;
  }}).join("");

  panel.innerHTML = `
    <div class="detail-header">
      <span class="name">${{a.id}}</span>
      <span class="type-badge type-agent">Agent</span>
    </div>
    <div class="detail-section">
      <h4>Statistics</h4>
      <div class="detail-stat"><span>States</span><span class="val">${{a.state_count}}</span></div>
      <div class="detail-stat"><span>Decision Points</span><span class="val">${{a.decision_count}}</span></div>
      <div class="detail-stat"><span>Terminal States</span><span class="val">${{a.terminal_count}}</span></div>
      <div class="detail-stat"><span>Initial State</span><span class="val">${{a.initial_state}}</span></div>
    </div>
    ${{a.tools.length ? `<div class="detail-section"><h4>Tools</h4>${{a.tools.map(t => `<div class="state-item">${{t}}</div>`).join("")}}</div>` : ""}}
    <div class="detail-section">
      <h4>Channels</h4>
      ${{chHtml || '<div style="font-size:12px;color:var(--text2)">None</div>'}}
    </div>
    <div class="detail-section">
      <h4>States</h4>
      ${{statesHtml}}
    </div>`;
}}

function showResourceDetail(resId) {{
  const panel = document.getElementById("detailPanel");
  const r = DATA.resources.find(x => x.id === resId);
  if (!r) return;
  const cont = DATA.contention[resId] || [];
  const typeClass = r.type === "Lock" ? "type-lock" : "type-counter";

  panel.innerHTML = `
    <div class="detail-header">
      <span class="name">${{r.id}}</span>
      <span class="type-badge ${{typeClass}}">${{r.type}}</span>
    </div>
    <div class="detail-section">
      <h4>Configuration</h4>
      <div class="detail-stat"><span>Type</span><span class="val">${{r.type}}</span></div>
      ${{r.initial !== null ? `<div class="detail-stat"><span>Initial Value</span><span class="val">${{r.initial}}</span></div>` : ""}}
    </div>
    <div class="detail-section">
      <h4>Contending Agents${{cont.length ? " (" + cont.length + ")" : ""}}</h4>
      ${{cont.length
        ? cont.map(a => `<div class="state-item">${{a}}</div>`).join("")
        : '<div style="font-size:12px;color:var(--text2)">Single-user (no contention)</div>'}}
    </div>`;
}}

// ========== D3 GRAPH ==========
const container = document.getElementById("graphContainer");
const W = container.clientWidth || 800;
const H = container.clientHeight || 600;

const svg = d3.select("#graphContainer").insert("svg", ".zoom-bar")
  .attr("width", W).attr("height", H);

const g = svg.append("g"); // zoom group

// Zoom
const zoom = d3.zoom().scaleExtent([0.3, 3]).on("zoom", (e) => {{
  g.attr("transform", e.transform);
  document.getElementById("zoomLevel").textContent = Math.round(e.transform.k * 100) + "%";
}});
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

// Build graph nodes & links
const nodes = DATA.nodes.map(d => ({{...d}}));
const agentR = 28;
const resSize = 20; // half-side of resource rect

// Build resource-agent links from contention data
const resAgentLinks = [];
const resUsers = {{}};
Object.entries(DATA.contention).forEach(([rid, agents]) => {{
  resUsers[rid] = new Set(agents);
  agents.forEach(a => resAgentLinks.push({{source: a, target: rid, type: "resource"}}));
}});

const allLinks = [...DATA.links, ...resAgentLinks];

// Assign curvature to parallel channel links
const pairBuckets = {{}};
allLinks.filter(l => l.type === "channel").forEach(l => {{
  const key = [l.source, l.target].sort().join("||");
  if (!pairBuckets[key]) pairBuckets[key] = [];
  pairBuckets[key].push(l);
}});
Object.values(pairBuckets).forEach(group => {{
  const n = group.length;
  group.forEach((l, i) => {{ l.curve = n === 1 ? 0 : (i - (n - 1) / 2) * 60; }});
}});

const simulation = d3.forceSimulation(nodes)
  .force("link", d3.forceLink(allLinks).id(d => d.id).distance(d =>
    d.type === "resource" ? 100 : 180))
  .force("charge", d3.forceManyBody().strength(d => d.type === "resource" ? -200 : -500))
  .force("center", d3.forceCenter(W / 2, H / 2))
  .force("collision", d3.forceCollide().radius(d => d.type === "agent" ? agentR + 20 : resSize + 15));

// Layers
const linkLayer = g.append("g");
const nodeLayer = g.append("g");

// Links
const link = linkLayer.selectAll(".link")
  .data(allLinks).join("path")
  .attr("class", d => d.type === "channel" ? "link-channel" : "link-resource")
  .attr("marker-end", d => d.type === "channel" ? "url(#arrowCh)" : null);

// Agent nodes
const agentNodes = nodeLayer.selectAll(".agent-g")
  .data(nodes.filter(n => n.type === "agent")).join("g")
  .attr("class", "agent-g").style("cursor", "pointer");

agentNodes.append("circle")
  .attr("class", "node-agent").attr("r", agentR);

// Person icon (simplified SVG path)
agentNodes.append("text")
  .attr("class", "node-icon")
  .attr("text-anchor", "middle").attr("dominant-baseline", "central")
  .attr("font-size", "18px")
  .text("\U0001F464");

agentNodes.append("text")
  .attr("class", "node-label").attr("dy", agentR + 14).text(d => d.id);

agentNodes.append("text")
  .attr("class", "node-sub").attr("dy", agentR + 26)
  .text(d => d.states + " states");

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
  .text(d => d.rtype === "Lock" ? "\U0001F512" : "\U0001F522");

resNodes.append("text")
  .attr("class", "node-label").attr("dy", resSize + 14).text(d => d.id);

resNodes.append("text")
  .attr("class", "node-sub").attr("dy", resSize + 26)
  .text(d => d.rtype + (d.initial !== null ? " = " + d.initial : ""));

// Drag
const drag = d3.drag()
  .on("start", (e, d) => {{ if (!e.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; }})
  .on("drag", (e, d) => {{ d.fx = e.x; d.fy = e.y; }})
  .on("end", (e, d) => {{ if (!e.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; }});
agentNodes.call(drag);
resNodes.call(drag);

// Click to show detail
function selectNode(id, type) {{
  selectedId = id;
  clearChannelSelection();
  d3.selectAll(".node-agent, .node-resource").classed("selected", false);
  if (type === "agent") {{
    agentNodes.select("circle").classed("selected", d => d.id === id);
    showAgentDetail(id);
  }} else {{
    resNodes.select("rect").classed("selected", d => d.id === id);
    showResourceDetail(id);
  }}
}}
agentNodes.on("click", (e, d) => {{ e.stopPropagation(); selectNode(d.id, "agent"); }});
resNodes.on("click", (e, d) => {{ e.stopPropagation(); selectNode(d.id, "resource"); }});
svg.on("click", () => {{
  selectedId = null;
  clearChannelSelection();
  d3.selectAll(".node-agent, .node-resource").classed("selected", false);
  document.getElementById("detailPanel").innerHTML =
    '<div class="detail-placeholder">Click an agent or resource to view details</div>';
}});

// Path computation
function getNodeR(d) {{
  const n = nodes.find(x => x.id === (typeof d === "string" ? d : d.id));
  return n && n.type === "resource" ? resSize + 2 : agentR + 2;
}}

function computePath(d) {{
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

  return `M${{sX}},${{sY}} Q${{cx}},${{cy}} ${{eX}},${{eY}}`;
}}

simulation.on("tick", () => {{
  link.attr("d", computePath);
  agentNodes.attr("transform", d => `translate(${{d.x}},${{d.y}})`);
  resNodes.attr("transform", d => `translate(${{d.x}},${{d.y}})`);
}});

// Auto-select first agent
if (DATA.agents.length > 0) {{
  selectNode(DATA.agents[0].id, "agent");
}}
</script>
</body>
</html>"""


def save_html(topology: Topology, output_path: str | Path, title: str = "") -> Path:
    """Render topology to HTML and write to file. Returns the output path."""
    output_path = Path(output_path)
    content = render_html(topology, title=title)
    output_path.write_text(content, encoding="utf-8")
    return output_path


# ---------------------------------------------------------------------------
# Execution trace visualization (3-panel: agents+channels | graph | trace)
# ---------------------------------------------------------------------------

def _build_run_data(ir: dict, run_result: RunResult, sim=None) -> str:
    """Build JSON data embedding topology (from IR) + execution trace (from RunResult)."""
    from tracefix.runtime.enforcement.result_saver import _aggregate_agents

    agents_ir = ir.get("agents", [])
    resources_ir = ir.get("resources", [])
    channels_ir = ir.get("channels", [])

    agent_stats = _aggregate_agents(run_result)

    # --- Summary ---
    summary = {
        "success": run_result.success,
        "duration": round(run_result.duration, 1),
        "steps": run_result.steps,
        "error": run_result.error,
        "agent_count": len(agents_ir),
        "channel_count": len(channels_ir),
        "resource_count": len(resources_ir),
    }

    # --- Graph nodes ---
    nodes = []
    for agent in agents_ir:
        aid = agent["id"]
        stats = agent_stats.get(aid, {})
        nodes.append({
            "id": aid, "type": "agent",
            "steps": stats.get("steps", 0),
            "status": "completed" if aid in run_result.final_states else (
                "error" if run_result.error else "unknown"),
        })
    for res in resources_ir:
        nodes.append({
            "id": res["id"], "type": "resource",
            "rtype": res.get("type", "Lock"),
            "initial": res.get("config", {}).get("initial") if res.get("type") == "Counter" else None,
        })

    # --- Graph links ---
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

    # Resource usage links from trace
    resource_users: dict[str, set[str]] = {r["id"]: set() for r in resources_ir}
    for ev in run_result.trace:
        for g in ev.guards:
            if g.startswith("acquire("):
                rid = g[8:-1]
                if rid in resource_users:
                    resource_users[rid].add(ev.agent)
            elif g.startswith("dec("):
                rid = g[4:-1]
                if rid in resource_users:
                    resource_users[rid].add(ev.agent)
        for e in ev.effects:
            if e.startswith("release("):
                rid = e[8:-1]
                if rid in resource_users:
                    resource_users[rid].add(ev.agent)
            elif e.startswith("inc("):
                rid = e[4:-1]
                if rid in resource_users:
                    resource_users[rid].add(ev.agent)
    for rid, agents_set in resource_users.items():
        for aid in sorted(agents_set):
            links.append({"source": aid, "target": rid, "type": "resource"})

    # --- Channel panel data ---
    channels_data = []
    for ch in channels_ir:
        froms = ch.get("from", [])
        tos = ch.get("to", [])
        if isinstance(froms, str):
            froms = [froms]
        if isinstance(tos, str):
            tos = [tos]
        # Count messages from trace
        msg_count = sum(
            1 for ev in run_result.trace
            for g in ev.guards + ev.effects
            if (g.startswith("send(") or g.startswith("recv("))
            and ch["id"] in g
        )
        channels_data.append({
            "id": ch["id"], "from": froms, "to": tos,
            "labels": ch.get("labels", []), "msg_count": msg_count,
        })

    # --- Agent panel data ---
    agents_data = []
    for agent in agents_ir:
        aid = agent["id"]
        stats = agent_stats.get(aid, {})
        agents_data.append({
            "id": aid,
            "steps": stats.get("steps", 0),
            "tool_calls": stats.get("tool_calls", 0),
            "final_state": stats.get("final_state", ""),
            "status": "completed" if aid in run_result.final_states else (
                "error" if run_result.error else "unknown"),
        })

    # --- Resources data ---
    resources_data = []
    for res in resources_ir:
        contenders = sorted(resource_users.get(res["id"], set()))
        resources_data.append({
            "id": res["id"],
            "type": res.get("type", "Lock"),
            "initial": res.get("config", {}).get("initial") if res.get("type") == "Counter" else None,
            "contenders": contenders,
        })

    # --- Per-agent traces ---
    traces: dict[str, list[dict]] = {}
    for ev in run_result.trace:
        if ev.agent not in traces:
            traces[ev.agent] = []
        entry: dict = {
            "step": ev.step,
            "from": ev.from_state,
            "to": ev.to_state,
            "guards": ev.guards,
            "effects": ev.effects,
        }
        if ev.tool_calls:
            entry["tool_calls"] = ev.tool_calls
        traces[ev.agent].append(entry)

    # --- Sim data ---
    sim_data = None
    if sim is not None:
        sim_data = {
            "progress": sim.progress,
            "violations": [
                {"type": v.violation_type, "agent": v.agent,
                 "tool": v.tool, "message": v.message}
                for v in sim.violations
            ],
        }

    data: dict = {
        "summary": summary,
        "nodes": nodes,
        "links": links,
        "channels": channels_data,
        "agents": agents_data,
        "resources": resources_data,
        "traces": traces,
        "resource_users": {k: sorted(v) for k, v in resource_users.items()},
    }
    if sim_data is not None:
        data["sim"] = sim_data
    return json.dumps(data)


def render_run_html(ir: dict, run_result: RunResult, title: str = "", sim=None) -> str:
    """Generate a self-contained HTML page with IR topology + execution trace."""
    page_title = _escape(title) if title else "Runtime A Execution Trace"
    graph_data = _build_run_data(ir, run_result, sim=sim)

    status_text = "SUCCESS" if run_result.success else "FAILED"
    status_class = "badge-success" if run_result.success else "badge-fail"
    agent_count = len(ir.get("agents", []))
    duration = f"{run_result.duration:.1f}s"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{page_title}</title>
<style>
:root {{
  --bg: #0d1117; --bg2: #161b22; --bg3: #21262d; --border: #30363d;
  --text: #c9d1d9; --text2: #8b949e; --accent: #58a6ff; --green: #3fb950;
  --red: #f85149; --orange: #d29922; --purple: #bc8cff;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
       background:var(--bg); color:var(--text); overflow:hidden; }}

.app {{ display:flex; height:100vh; }}
.left-panel {{ width:260px; background:var(--bg2); border-right:1px solid var(--border);
               display:flex; flex-direction:column; flex-shrink:0; }}
.center {{ flex:1; position:relative; }}
.right-panel {{ width:380px; background:var(--bg2); border-left:1px solid var(--border);
                overflow-y:auto; flex-shrink:0; }}

.header {{ height:40px; background:var(--bg3); border-bottom:1px solid var(--border);
           display:flex; align-items:center; padding:0 14px; font-size:13px; font-weight:600; gap:8px; }}
.header .title {{ color:var(--text); }}
.header .badge {{ font-size:11px; padding:2px 8px; border-radius:10px; }}
.badge-success {{ background:var(--green); color:var(--bg); }}
.badge-fail {{ background:var(--red); color:#fff; }}
.header .meta {{ margin-left:auto; font-size:11px; color:var(--text2); font-weight:400; }}

.panel-header {{ padding:10px 14px 6px; font-size:11px; text-transform:uppercase;
                 color:var(--text2); letter-spacing:0.8px; font-weight:600; }}
.agent-list {{ overflow-y:auto; padding:0 8px 4px; }}
.agent-item {{ padding:7px 10px; margin-bottom:3px; border-radius:6px;
               background:var(--bg3); border:1px solid var(--border); cursor:pointer;
               display:flex; align-items:center; gap:8px;
               transition:border-color 0.15s; font-size:12px; }}
.agent-item:hover {{ border-color:var(--accent); }}
.agent-item.selected {{ border-color:var(--accent); background:rgba(88,166,255,0.08); }}
.agent-status {{ width:8px; height:8px; border-radius:50%; flex-shrink:0; }}
.status-completed {{ background:var(--green); }}
.status-error {{ background:var(--red); }}
.status-unknown {{ background:var(--text2); }}
.agent-name {{ font-weight:600; flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
.agent-steps {{ color:var(--text2); font-size:11px; flex-shrink:0; }}

.channel-list {{ overflow-y:auto; padding:0 8px 4px; }}
.channel-item {{ padding:6px 10px; margin-bottom:3px; border-radius:6px;
                 background:var(--bg3); border:1px solid var(--border); cursor:pointer;
                 transition:border-color 0.15s; }}
.channel-item:hover {{ border-color:var(--accent); }}
.channel-item.selected {{ border-color:var(--accent); background:rgba(88,166,255,0.08); }}
.channel-name {{ font-size:11px; font-weight:600; color:var(--accent); display:flex; justify-content:space-between; }}
.channel-route {{ font-size:10px; color:var(--text2); margin-top:1px; }}
.ch-count {{ color:var(--text2); font-weight:400; font-size:10px; }}

.summary-box {{ padding:10px 14px; border-top:1px solid var(--border); flex-shrink:0; }}
.summary-row {{ display:flex; justify-content:space-between; font-size:12px; padding:2px 0; }}
.summary-row .val {{ font-weight:600; color:var(--accent); }}

.sim-panel {{ padding:10px 14px; border-top:1px solid var(--border); overflow-y:auto; }}
.sim-section {{ margin-bottom:8px; }}
.sim-section-title {{ font-size:10px; text-transform:uppercase; color:var(--text2);
                      letter-spacing:0.5px; margin-bottom:4px; font-weight:600; }}
.sim-items {{ display:flex; flex-wrap:wrap; gap:4px; }}
.sim-item {{ font-size:11px; padding:2px 6px; border-radius:3px;
            border:1px solid var(--border); background:var(--bg); font-family:monospace; }}
.sim-item.done {{ color:var(--green); border-color:rgba(63,185,80,0.3); }}
.sim-item.pending {{ color:var(--text2); }}
.sim-complete {{ font-size:12px; font-weight:600; color:var(--green); margin-top:6px; }}
.sim-incomplete {{ font-size:12px; font-weight:600; color:var(--orange); margin-top:6px; }}
.sim-violation {{ font-size:11px; padding:4px 6px; margin-bottom:3px; border-radius:4px;
                 background:rgba(248,81,73,0.08); border:1px solid rgba(248,81,73,0.2);
                 color:var(--red); font-family:monospace; }}

.detail-placeholder {{ padding:40px 20px; text-align:center; color:var(--text2); font-size:13px; }}
.detail-header {{ padding:14px; border-bottom:1px solid var(--border); }}
.detail-header .name {{ font-size:16px; font-weight:700; }}
.detail-header .type-badge {{ font-size:11px; padding:2px 8px; border-radius:4px;
                              margin-left:8px; vertical-align:middle; }}
.type-agent {{ background:rgba(88,166,255,0.15); color:var(--accent); }}
.type-lock {{ background:rgba(248,81,73,0.15); color:var(--red); }}
.type-counter {{ background:rgba(210,153,34,0.15); color:var(--orange); }}
.type-channel {{ background:rgba(88,166,255,0.15); color:var(--accent); }}
.detail-section {{ padding:12px 14px; border-bottom:1px solid var(--border); }}
.detail-section h4 {{ font-size:11px; text-transform:uppercase; color:var(--text2);
                      margin-bottom:8px; letter-spacing:0.5px; }}
.detail-stat {{ display:flex; justify-content:space-between; font-size:12px; padding:2px 0; }}
.detail-stat .val {{ color:var(--accent); font-weight:600; }}

.trace-list {{ padding:0; }}
.trace-item {{ display:flex; align-items:flex-start; padding:5px 8px; margin-bottom:2px;
               border-radius:4px; background:var(--bg); font-size:11px;
               font-family:"SF Mono",Menlo,monospace; gap:6px; line-height:1.4; }}
.trace-step {{ color:var(--text2); flex-shrink:0; width:28px; }}
.trace-body {{ flex:1; overflow:hidden; }}
.trace-state {{ font-weight:600; }}
.trace-ops {{ color:var(--text2); font-size:10px; margin-top:1px; }}
.trace-tools {{ font-size:10px; color:var(--purple); margin-top:1px; }}

.op-guard {{ color:var(--accent); }}
.op-effect {{ color:var(--green); }}

svg {{ width:100%; height:100%; }}
.link-channel {{ stroke:var(--accent); stroke-width:1.5; fill:none; opacity:0.6; }}
.link-resource {{ stroke:var(--green); stroke-width:1; fill:none; opacity:0.4;
                  stroke-dasharray:4,3; }}
.node-agent {{ fill:transparent; stroke-width:2; cursor:pointer; }}
.node-agent:hover {{ stroke-width:3; filter:brightness(1.3); }}
.node-agent.selected {{ stroke-width:3; filter:drop-shadow(0 0 6px rgba(88,166,255,0.5)); }}
.node-resource {{ fill:transparent; stroke:var(--red); stroke-width:1.5; cursor:pointer; rx:4; }}
.node-resource:hover {{ stroke-width:2.5; stroke:var(--orange); }}
.node-resource.selected {{ stroke:var(--orange); stroke-width:2.5; filter:drop-shadow(0 0 6px rgba(210,153,34,0.5)); }}
.node-label {{ font-size:11px; fill:var(--text); text-anchor:middle; pointer-events:none; }}
.node-sub {{ font-size:9px; fill:var(--text2); text-anchor:middle; pointer-events:none; }}
.node-icon {{ fill:var(--text); pointer-events:none; }}
.link-arrow {{ fill:var(--accent); opacity:0.6; }}

.zoom-bar {{ position:absolute; bottom:12px; left:50%; transform:translateX(-50%);
             background:var(--bg3); border:1px solid var(--border); border-radius:6px;
             display:flex; align-items:center; padding:4px 10px; gap:8px; font-size:12px; }}
.zoom-bar button {{ background:none; border:1px solid var(--border); color:var(--text);
                    width:26px; height:26px; border-radius:4px; cursor:pointer; font-size:14px; }}
.zoom-bar button:hover {{ background:var(--border); }}
.zoom-bar .zoom-level {{ color:var(--text2); min-width:40px; text-align:center; }}
</style>
</head>
<body>
<div class="app">

  <div class="left-panel">
    <div class="header">
      <span class="title">{page_title}</span>
      <span class="badge {status_class}">{status_text}</span>
      <span class="meta">{duration} | {agent_count} agents</span>
    </div>
    <div class="panel-header">Agents</div>
    <div class="agent-list" id="agentList"></div>
    <div class="panel-header">Channels</div>
    <div class="channel-list" id="channelList"></div>
    <div class="summary-box" id="summaryBox"></div>
    <div id="simPanel"></div>
  </div>

  <div class="center" id="graphContainer">
    <div class="zoom-bar">
      <button id="zoomOut">&minus;</button>
      <span class="zoom-level" id="zoomLevel">100%</span>
      <button id="zoomIn">+</button>
      <button id="zoomReset" style="font-size:11px;width:auto;padding:0 8px;">Reset</button>
    </div>
  </div>

  <div class="right-panel" id="detailPanel">
    <div class="detail-placeholder">Click an agent to view its execution trace</div>
  </div>

</div>

<script src="https://d3js.org/d3.v7.min.js"></script>
<script>
const DATA = {graph_data};
let selectedId = null;
let selectedChannelId = null;
const agentElements = {{}};
const channelElements = {{}};

// ========== LEFT PANEL: AGENTS ==========
(function buildAgentList() {{
  const list = document.getElementById("agentList");
  DATA.agents.forEach(a => {{
    const div = document.createElement("div");
    div.className = "agent-item";
    div.dataset.agentId = a.id;
    div.innerHTML = `
      <span class="agent-status status-${{a.status}}"></span>
      <span class="agent-name">${{a.id}}</span>
      <span class="agent-steps">${{a.steps}} steps</span>`;
    div.addEventListener("click", () => selectAgentFromList(a.id));
    agentElements[a.id] = div;
    list.appendChild(div);
  }});
}})();

// ========== LEFT PANEL: CHANNELS ==========
(function buildChannelList() {{
  const list = document.getElementById("channelList");
  DATA.channels.forEach(ch => {{
    const div = document.createElement("div");
    div.className = "channel-item";
    div.dataset.channelId = ch.id;
    div.innerHTML = `
      <div class="channel-name"><span>${{ch.id}}</span><span class="ch-count">${{ch.msg_count}} ops</span></div>
      <div class="channel-route">${{ch.from.join(", ")}} &rarr; ${{ch.to.join(", ")}}</div>`;
    div.addEventListener("click", () => selectChannel(ch.id));
    channelElements[ch.id] = div;
    list.appendChild(div);
  }});
}})();

// ========== LEFT PANEL: SUMMARY ==========
(function buildSummary() {{
  const box = document.getElementById("summaryBox");
  const s = DATA.summary;
  box.innerHTML = `
    <div class="summary-row"><span>Status</span><span class="val" style="color:${{s.success ? 'var(--green)' : 'var(--red)'}}">${{s.success ? 'SUCCESS' : 'FAILED'}}</span></div>
    <div class="summary-row"><span>Duration</span><span class="val">${{s.duration}}s</span></div>
    <div class="summary-row"><span>Total Steps</span><span class="val">${{s.steps}}</span></div>
    <div class="summary-row"><span>Agents</span><span class="val">${{s.agent_count}}</span></div>
    <div class="summary-row"><span>Channels</span><span class="val">${{s.channel_count}}</span></div>
    <div class="summary-row"><span>Resources</span><span class="val">${{s.resource_count}}</span></div>`;
}})();

// ========== LEFT PANEL: SIMULATION ==========
(function buildSimPanel() {{
  if (!DATA.sim) return;
  const panel = document.getElementById("simPanel");
  panel.className = "sim-panel";
  const sim = DATA.sim;
  const p = sim.progress;

  function renderItems(obj) {{
    return Object.entries(obj).map(([k, v]) =>
      `<span class="sim-item ${{v ? 'done' : 'pending'}}">${{v ? '\\u2713' : '\\u2022'}} ${{k}}</span>`
    ).join("");
  }}

  function formatTitle(key) {{
    return key.replace(/_/g, ' ').replace(/\\b[a-z]/g, c => c.toUpperCase());
  }}

  let html = '<div class="panel-header" style="padding:0 0 6px">Simulation</div>';
  Object.entries(p).forEach(([key, value]) => {{
    if (key === "all_complete") return;
    if (typeof value === "object" && value !== null) {{
      html += `<div class="sim-section"><div class="sim-section-title">${{formatTitle(key)}}</div><div class="sim-items">${{renderItems(value)}}</div></div>`;
    }}
  }});
  if (p.all_complete) {{
    html += '<div class="sim-complete">\\u2705 COMPLETE</div>';
  }} else {{
    html += '<div class="sim-incomplete">\\u23F3 INCOMPLETE</div>';
  }}
  if (sim.violations && sim.violations.length > 0) {{
    html += `<div class="sim-section" style="margin-top:8px"><div class="sim-section-title" style="color:var(--red)">Violations (${{sim.violations.length}})</div>`;
    sim.violations.forEach(v => {{
      html += `<div class="sim-violation">\\u26A0 ${{v.agent}}/${{v.tool}}: ${{v.type}}<br><span style="color:var(--text2);font-size:10px">${{v.message}}</span></div>`;
    }});
    html += '</div>';
  }}
  panel.innerHTML = html;
}})();

// ========== SELECTION LOGIC ==========
function clearSelections() {{
  Object.values(agentElements).forEach(el => el.classList.remove("selected"));
  Object.values(channelElements).forEach(el => el.classList.remove("selected"));
  d3.selectAll(".node-agent, .node-resource").classed("selected", false);
  selectedId = null;
  selectedChannelId = null;
}}

function selectAgentFromList(agentId) {{
  clearSelections();
  selectedId = agentId;
  if (agentElements[agentId]) agentElements[agentId].classList.add("selected");
  agentNodes.select("circle").classed("selected", d => d.id === agentId);
  showAgentTrace(agentId);
}}

function selectChannel(chId) {{
  clearSelections();
  if (chId === selectedChannelId) {{
    document.getElementById("detailPanel").innerHTML =
      '<div class="detail-placeholder">Click an agent to view its execution trace</div>';
    return;
  }}
  selectedChannelId = chId;
  if (channelElements[chId]) channelElements[chId].classList.add("selected");
  showChannelDetail(chId);
}}

// ========== RIGHT PANEL: AGENT TRACE ==========
function opsHtml(guards, effects) {{
  let parts = [];
  guards.forEach(g => parts.push(`<span class="op-guard">${{g}}</span>`));
  effects.forEach(e => parts.push(`<span class="op-effect">${{e}}</span>`));
  return parts.join(" ");
}}

function showAgentTrace(agentId) {{
  const panel = document.getElementById("detailPanel");
  const a = DATA.agents.find(x => x.id === agentId);
  const trace = DATA.traces[agentId] || [];
  if (!a) return;

  const statusColor = a.status === "completed" ? "var(--green)" : "var(--red)";

  let traceHtml;
  if (trace.length === 0) {{
    traceHtml = '<div style="font-size:12px;color:var(--text2);padding:8px">No state transitions recorded</div>';
  }} else {{
    traceHtml = trace.map(t => {{
      const ops = (t.guards && t.guards.length) || (t.effects && t.effects.length)
        ? `<div class="trace-ops">${{opsHtml(t.guards || [], t.effects || [])}}</div>` : "";
      const tools = t.tool_calls && t.tool_calls.length
        ? `<div class="trace-tools">${{t.tool_calls.map(tc => {{
            const name = tc.name || tc.tool_name || "tool";
            return name;
          }}).join(", ")}}</div>` : "";
      return `<div class="trace-item">
        <span class="trace-step">#${{t.step}}</span>
        <div class="trace-body">
          <span class="trace-state">${{t.from}} &rarr; ${{t.to}}</span>
          ${{ops}}${{tools}}
        </div>
      </div>`;
    }}).join("");
  }}

  panel.innerHTML = `
    <div class="detail-header">
      <span class="name">${{a.id}}</span>
      <span class="type-badge type-agent">Agent</span>
      <span class="type-badge" style="background:${{statusColor}}22;color:${{statusColor}}">${{a.status}}</span>
    </div>
    <div class="detail-section">
      <h4>Execution</h4>
      <div class="detail-stat"><span>Status</span><span class="val" style="color:${{statusColor}}">${{a.status}}</span></div>
      <div class="detail-stat"><span>State Transitions</span><span class="val">${{a.steps}}</span></div>
      <div class="detail-stat"><span>Tool Calls</span><span class="val">${{a.tool_calls}}</span></div>
      ${{a.final_state ? `<div class="detail-stat"><span>Final State</span><span class="val">${{a.final_state}}</span></div>` : ""}}
    </div>
    <div class="detail-section" style="border-bottom:none">
      <h4>Trace (${{trace.length}} transitions)</h4>
      <div class="trace-list">${{traceHtml}}</div>
    </div>`;
}}

// ========== RIGHT PANEL: CHANNEL DETAIL ==========
function showChannelDetail(chId) {{
  const panel = document.getElementById("detailPanel");
  const ch = DATA.channels.find(x => x.id === chId);
  if (!ch) return;

  const labelsHtml = ch.labels.length
    ? ch.labels.map(l => `<span style="background:var(--bg);padding:1px 6px;border-radius:3px;border:1px solid var(--border);font-size:11px;font-family:monospace;color:var(--orange);margin-right:4px">${{l}}</span>`).join("")
    : '<span style="color:var(--text2)">unlabeled</span>';

  // Collect send/recv from trace
  const timeline = [];
  Object.entries(DATA.traces).forEach(([agentId, trace]) => {{
    trace.forEach(t => {{
      (t.guards || []).forEach(g => {{
        if (g.startsWith("recv(") && g.includes(chId)) {{
          const label = g.match(/recv\\([^,]+,([^)]+)\\)/);
          timeline.push({{ type: "recv", agent: agentId, step: t.step, label: label ? label[1] : "" }});
        }}
      }});
      (t.effects || []).forEach(e => {{
        if (e.startsWith("send(") && e.includes(chId)) {{
          const label = e.match(/send\\([^,]+,([^)]+)\\)/);
          timeline.push({{ type: "send", agent: agentId, step: t.step, label: label ? label[1] : "" }});
        }}
      }});
    }});
  }});
  timeline.sort((a, b) => a.step - b.step);

  const timelineHtml = timeline.length
    ? timeline.map(t => {{
        const cls = t.type === "send" ? "op-effect" : "op-guard";
        const icon = t.type === "send" ? "&uarr;" : "&darr;";
        return `<div class="trace-item"><span class="trace-step">#${{t.step}}</span><span class="${{cls}}" style="flex-shrink:0">${{icon}}</span><div class="trace-body"><span class="trace-state">${{t.agent}}</span><div class="trace-ops">label=${{t.label}}</div></div></div>`;
      }}).join("")
    : '<div style="font-size:12px;color:var(--text2);padding:4px">No messages</div>';

  panel.innerHTML = `
    <div class="detail-header">
      <span class="name">${{ch.id}}</span>
      <span class="type-badge type-channel">Channel</span>
    </div>
    <div class="detail-section">
      <h4>Route</h4>
      <div class="detail-stat"><span>From</span><span class="val">${{ch.from.join(", ")}}</span></div>
      <div class="detail-stat"><span>To</span><span class="val">${{ch.to.join(", ")}}</span></div>
    </div>
    <div class="detail-section">
      <h4>Labels</h4>
      <div style="padding:2px 0">${{labelsHtml}}</div>
    </div>
    <div class="detail-section" style="border-bottom:none">
      <h4>Message Timeline (${{timeline.length}})</h4>
      <div class="trace-list">${{timelineHtml}}</div>
    </div>`;
}}

// ========== RIGHT PANEL: RESOURCE DETAIL ==========
function showResourceDetail(resId) {{
  const panel = document.getElementById("detailPanel");
  const r = DATA.resources.find(x => x.id === resId);
  if (!r) return;
  const typeClass = r.type === "Lock" ? "type-lock" : "type-counter";

  // Collect acquire/release from trace
  const ops = [];
  Object.entries(DATA.traces).forEach(([agentId, trace]) => {{
    trace.forEach(t => {{
      (t.guards || []).forEach(g => {{
        if (g.includes(resId)) ops.push({{ type: "guard", agent: agentId, step: t.step, op: g }});
      }});
      (t.effects || []).forEach(e => {{
        if (e.includes(resId)) ops.push({{ type: "effect", agent: agentId, step: t.step, op: e }});
      }});
    }});
  }});
  ops.sort((a, b) => a.step - b.step);

  const opsHtml = ops.length
    ? ops.map(o => `<div class="trace-item"><span class="trace-step">#${{o.step}}</span><span class="${{o.type === 'guard' ? 'op-guard' : 'op-effect'}}" style="flex-shrink:0">${{o.type === 'guard' ? '&#x2193;' : '&#x2191;'}}</span><div class="trace-body"><span class="trace-state">${{o.agent}}</span><div class="trace-ops">${{o.op}}</div></div></div>`).join("")
    : '<div style="font-size:12px;color:var(--text2);padding:4px">No operations</div>';

  panel.innerHTML = `
    <div class="detail-header">
      <span class="name">${{r.id}}</span>
      <span class="type-badge ${{typeClass}}">${{r.type}}</span>
    </div>
    <div class="detail-section">
      <h4>Configuration</h4>
      <div class="detail-stat"><span>Type</span><span class="val">${{r.type}}</span></div>
      ${{r.initial !== null && r.initial !== undefined ? `<div class="detail-stat"><span>Initial Value</span><span class="val">${{r.initial}}</span></div>` : ""}}
    </div>
    <div class="detail-section">
      <h4>Contending Agents (${{r.contenders.length}})</h4>
      ${{r.contenders.length
        ? r.contenders.map(a => `<div style="font-size:12px;font-family:monospace;padding:2px 6px">${{a}}</div>`).join("")
        : '<div style="font-size:12px;color:var(--text2)">No contention</div>'}}
    </div>
    <div class="detail-section" style="border-bottom:none">
      <h4>Operations (${{ops.length}})</h4>
      <div class="trace-list">${{opsHtml}}</div>
    </div>`;
}}

// ========== D3 GRAPH ==========
const container = document.getElementById("graphContainer");
const W = container.clientWidth || 800;
const H = container.clientHeight || 600;

const svg = d3.select("#graphContainer").insert("svg", ".zoom-bar")
  .attr("width", W).attr("height", H);

const g = svg.append("g");

const zoom = d3.zoom().scaleExtent([0.3, 3]).on("zoom", (e) => {{
  g.attr("transform", e.transform);
  document.getElementById("zoomLevel").textContent = Math.round(e.transform.k * 100) + "%";
}});
svg.call(zoom);
document.getElementById("zoomIn").onclick = () => svg.transition().call(zoom.scaleBy, 1.3);
document.getElementById("zoomOut").onclick = () => svg.transition().call(zoom.scaleBy, 0.77);
document.getElementById("zoomReset").onclick = () => svg.transition().call(zoom.transform, d3.zoomIdentity);

g.append("defs").append("marker")
  .attr("id", "arrowCh").attr("viewBox", "0 -4 8 8")
  .attr("refX", 8).attr("refY", 0)
  .attr("markerWidth", 6).attr("markerHeight", 6)
  .attr("orient", "auto")
  .append("path").attr("d", "M0,-3L8,0L0,3").attr("class", "link-arrow");

const nodes = DATA.nodes.map(d => ({{...d}}));
const agentR = 28;
const resSize = 20;

function agentStroke(status) {{
  if (status === "completed") return "var(--green)";
  if (status === "error") return "var(--red)";
  return "var(--text2)";
}}

const pairBuckets = {{}};
DATA.links.filter(l => l.type === "channel").forEach(l => {{
  const key = [l.source, l.target].sort().join("||");
  if (!pairBuckets[key]) pairBuckets[key] = [];
  pairBuckets[key].push(l);
}});
Object.values(pairBuckets).forEach(group => {{
  const n = group.length;
  group.forEach((l, i) => {{ l.curve = n === 1 ? 0 : (i - (n - 1) / 2) * 60; }});
}});

const simulation = d3.forceSimulation(nodes)
  .force("link", d3.forceLink(DATA.links).id(d => d.id).distance(d =>
    d.type === "resource" ? 100 : 180))
  .force("charge", d3.forceManyBody().strength(d => d.type === "resource" ? -200 : -500))
  .force("center", d3.forceCenter(W / 2, H / 2))
  .force("collision", d3.forceCollide().radius(d => d.type === "agent" ? agentR + 20 : resSize + 15));

const linkLayer = g.append("g");
const nodeLayer = g.append("g");

const link = linkLayer.selectAll(".link")
  .data(DATA.links).join("path")
  .attr("class", d => d.type === "channel" ? "link-channel" : "link-resource")
  .attr("marker-end", d => d.type === "channel" ? "url(#arrowCh)" : null);

const agentNodes = nodeLayer.selectAll(".agent-g")
  .data(nodes.filter(n => n.type === "agent")).join("g")
  .attr("class", "agent-g").style("cursor", "pointer");

agentNodes.append("circle")
  .attr("class", "node-agent").attr("r", agentR)
  .style("stroke", d => agentStroke(d.status));

agentNodes.append("text")
  .attr("class", "node-icon")
  .attr("text-anchor", "middle").attr("dominant-baseline", "central")
  .attr("font-size", "18px")
  .text("\U0001F464");

agentNodes.append("text")
  .attr("class", "node-label").attr("dy", agentR + 14).text(d => d.id);

agentNodes.append("text")
  .attr("class", "node-sub").attr("dy", agentR + 26)
  .text(d => d.steps + " steps");

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
  .text(d => d.rtype === "Lock" ? "\U0001F512" : "\U0001F522");

resNodes.append("text")
  .attr("class", "node-label").attr("dy", resSize + 14).text(d => d.id);

resNodes.append("text")
  .attr("class", "node-sub").attr("dy", resSize + 26)
  .text(d => d.rtype + (d.initial !== null && d.initial !== undefined ? " = " + d.initial : ""));

const drag = d3.drag()
  .on("start", (e, d) => {{ if (!e.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; }})
  .on("drag", (e, d) => {{ d.fx = e.x; d.fy = e.y; }})
  .on("end", (e, d) => {{ if (!e.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; }});
agentNodes.call(drag);
resNodes.call(drag);

agentNodes.on("click", (e, d) => {{
  e.stopPropagation();
  clearSelections();
  selectedId = d.id;
  if (agentElements[d.id]) agentElements[d.id].classList.add("selected");
  agentNodes.select("circle").classed("selected", n => n.id === d.id);
  showAgentTrace(d.id);
}});
resNodes.on("click", (e, d) => {{
  e.stopPropagation();
  clearSelections();
  selectedId = d.id;
  resNodes.select("rect").classed("selected", n => n.id === d.id);
  showResourceDetail(d.id);
}});
svg.on("click", () => {{
  clearSelections();
  document.getElementById("detailPanel").innerHTML =
    '<div class="detail-placeholder">Click an agent to view its execution trace</div>';
}});

function getNodeR(d) {{
  const n = nodes.find(x => x.id === (typeof d === "string" ? d : d.id));
  return n && n.type === "resource" ? resSize + 2 : agentR + 2;
}}

function computePath(d) {{
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

  return `M${{sX}},${{sY}} Q${{cx}},${{cy}} ${{eX}},${{eY}}`;
}}

simulation.on("tick", () => {{
  link.attr("d", computePath);
  agentNodes.attr("transform", d => `translate(${{d.x}},${{d.y}})`);
  resNodes.attr("transform", d => `translate(${{d.x}},${{d.y}})`);
}});

if (DATA.agents.length > 0) {{
  selectAgentFromList(DATA.agents[0].id);
}}
</script>
</body>
</html>"""


def save_run_html(
    ir: dict,
    run_result: RunResult,
    output_path: str | Path,
    title: str = "",
    sim=None,
) -> Path:
    """Render IR + RunResult to execution trace HTML and write to file."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = render_run_html(ir, run_result, title=title, sim=sim)
    output_path.write_text(content, encoding="utf-8")
    return output_path
