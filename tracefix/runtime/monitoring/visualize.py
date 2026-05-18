"""IR + RunResult → self-contained HTML visualization (swarm-ide dark theme).

Generates a three-panel page:
  Left:   Agent list (with execution status) + channel list + summary
  Center: D3 force-directed topology graph (agents, resources, channels)
  Right:  Per-agent tool-call trace (click an agent to view)
"""

from __future__ import annotations

import html
import json
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tracefix.runtime.monitoring.orchestrator import RunResult


def _escape(text: str) -> str:
    return html.escape(text, quote=True)


def _build_data(ir: dict, run_result: RunResult, sim=None) -> str:
    """Build JSON data embedding topology (from IR) + execution trace (from RunResult)."""
    agents_ir = ir.get("agents", [])
    resources_ir = ir.get("resources", [])
    channels_ir = ir.get("channels", [])
    states_ir = ir.get("states", {})

    # Index agent results by id
    ar_by_id = {ar.agent_id: ar for ar in run_result.agent_results}

    # --- Summary ---
    summary = {
        "success": run_result.success,
        "duration": round(run_result.duration, 1),
        "error": run_result.error,
        "agent_count": len(agents_ir),
        "channel_count": len(channels_ir),
        "resource_count": len(resources_ir),
    }

    # --- Graph nodes ---
    nodes = []
    for agent in agents_ir:
        aid = agent["id"]
        ar = ar_by_id.get(aid)
        status = ar.status if ar else "unknown"
        steps = ar.steps if ar else 0
        nodes.append({
            "id": aid, "type": "agent", "status": status, "steps": steps,
        })
    for res in resources_ir:
        nodes.append({
            "id": res["id"], "type": "resource",
            "rtype": res.get("type", "Lock"),
            "initial": res.get("initial_value"),
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

    # Resource usage links (derived from states: which agents acquire/release)
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

    # Fallback: derive resource usage from execution trace if states are missing
    if resources_ir and not any(resource_users.values()) and run_result:
        for ar in run_result.agent_results:
            for tc in ar.trace:
                if tc.tool_name in ("acquire_lock", "release_lock"):
                    lock_id = tc.arguments.get("lock_id", "")
                    if lock_id in resource_users:
                        resource_users[lock_id].add(ar.agent_id)

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
        channels_data.append({
            "id": ch["id"],
            "from": froms,
            "to": tos,
            "labels": ch.get("labels", []),
        })

    # --- Agent panel data ---
    agents_data = []
    for agent in agents_ir:
        aid = agent["id"]
        ar = ar_by_id.get(aid)
        # Count tool call types
        tool_counts: dict[str, int] = {}
        if ar:
            for tc in ar.trace:
                tool_counts[tc.tool_name] = tool_counts.get(tc.tool_name, 0) + 1

        agents_data.append({
            "id": aid,
            "initial_state": agent.get("initial_state", ""),
            "tools": agent.get("tools", []),
            "status": ar.status if ar else "unknown",
            "steps": ar.steps if ar else 0,
            "duration": round(ar.duration, 1) if ar else 0,
            "error": ar.error if ar else None,
            "tool_counts": tool_counts,
        })

    # --- Resources data ---
    resources_data = []
    for res in resources_ir:
        contenders = sorted(resource_users.get(res["id"], set()))
        resources_data.append({
            "id": res["id"],
            "type": res.get("type", "Lock"),
            "initial": res.get("initial_value"),
            "contenders": contenders,
        })

    # --- Per-agent traces ---
    traces: dict[str, list[dict]] = {}
    for ar in run_result.agent_results:
        agent_trace = []
        for tc in ar.trace:
            agent_trace.append({
                "round": tc.round,
                "tool": tc.tool_name,
                "args": tc.arguments,
                "result": tc.result,
                "elapsed": round(tc.elapsed, 2),
                "timestamp": tc.timestamp,
            })
        traces[ar.agent_id] = agent_trace

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

    data = {
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


def render_html(ir: dict, run_result: RunResult, title: str = "", sim=None) -> str:
    """Generate a self-contained HTML page visualizing IR topology + execution trace."""
    page_title = _escape(title) if title else "Runtime B Execution Trace"
    graph_data = _build_data(ir, run_result, sim=sim)

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

/* --- Layout: left panel | center graph | right detail panel --- */
.app {{ display:flex; height:100vh; }}
.left-panel {{ width:260px; background:var(--bg2); border-right:1px solid var(--border);
               display:flex; flex-direction:column; flex-shrink:0; }}
.center {{ flex:1; position:relative; }}
.right-panel {{ width:380px; background:var(--bg2); border-left:1px solid var(--border);
                overflow-y:auto; flex-shrink:0; }}

/* --- Header bar --- */
.header {{ height:40px; background:var(--bg3); border-bottom:1px solid var(--border);
           display:flex; align-items:center; padding:0 14px; font-size:13px; font-weight:600; gap:8px; }}
.header .title {{ color:var(--text); }}
.header .badge {{ font-size:11px; padding:2px 8px; border-radius:10px; }}
.badge-success {{ background:var(--green); color:var(--bg); }}
.badge-fail {{ background:var(--red); color:#fff; }}
.header .meta {{ margin-left:auto; font-size:11px; color:var(--text2); font-weight:400; }}

/* --- Left panel: agent list + channels + summary --- */
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
.status-timeout {{ background:var(--orange); }}
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

/* --- Sim panel --- */
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

/* --- Right panel: trace detail --- */
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

/* --- Trace items --- */
.trace-list {{ padding:0; }}
.trace-item {{ display:flex; align-items:flex-start; padding:5px 8px; margin-bottom:2px;
               border-radius:4px; background:var(--bg); font-size:11px;
               font-family:"SF Mono",Menlo,monospace; gap:6px; line-height:1.4; }}
.trace-round {{ color:var(--text2); flex-shrink:0; width:28px; }}
.trace-body {{ flex:1; overflow:hidden; }}
.trace-tool {{ font-weight:600; }}
.trace-args {{ color:var(--text2); font-size:10px; overflow:hidden;
               text-overflow:ellipsis; white-space:nowrap; max-width:220px; }}
.trace-result {{ font-size:10px; margin-top:1px; }}
.trace-elapsed {{ color:var(--text2); flex-shrink:0; font-size:10px; }}

/* Tool-specific colors */
.tool-acquire-acquired {{ color:var(--green); }}
.tool-acquire-busy {{ color:var(--orange); }}
.tool-acquire-already {{ color:var(--accent); }}
.tool-release {{ color:var(--text2); }}
.tool-send {{ color:var(--green); }}
.tool-receive-ok {{ color:var(--accent); }}
.tool-receive-timeout {{ color:var(--orange); }}
.tool-done {{ color:var(--green); }}
.tool-domain {{ color:var(--purple); }}
.tool-error {{ color:var(--red); }}

/* --- SVG graph --- */
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

  <!-- Left Panel: Agents + Channels + Summary -->
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
      <span class="agent-steps">${{a.steps}}</span>`;
    div.addEventListener("click", () => selectAgentFromList(a.id));
    agentElements[a.id] = div;
    list.appendChild(div);
  }});
}})();

// ========== LEFT PANEL: CHANNELS ==========
(function buildChannelList() {{
  const list = document.getElementById("channelList");
  DATA.channels.forEach(ch => {{
    // Count messages for this channel
    let msgCount = 0;
    Object.values(DATA.traces).forEach(trace => {{
      trace.forEach(tc => {{
        if ((tc.tool === "send_message" || tc.tool === "receive_message") && tc.args.channel_id === ch.id) msgCount++;
      }});
    }});
    const div = document.createElement("div");
    div.className = "channel-item";
    div.dataset.channelId = ch.id;
    div.innerHTML = `
      <div class="channel-name"><span>${{ch.id}}</span><span class="ch-count">${{msgCount}} msgs</span></div>
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
      `<span class="sim-item ${{v ? 'done' : 'pending'}}">${{v ? '\u2713' : '\u2022'}} ${{k}}</span>`
    ).join("");
  }}

  function formatTitle(key) {{
    return key.replace(/_/g, ' ').replace(/\b[a-z]/g, c => c.toUpperCase());
  }}

  let html = '<div class="panel-header" style="padding:0 0 6px">Simulation</div>';

  // Render all dict-valued progress sections generically
  Object.entries(p).forEach(([key, value]) => {{
    if (key === "all_complete") return;
    if (typeof value === "object" && value !== null) {{
      html += `<div class="sim-section"><div class="sim-section-title">${{formatTitle(key)}}</div><div class="sim-items">${{renderItems(value)}}</div></div>`;
    }}
  }});

  if (p.all_complete) {{
    html += '<div class="sim-complete">\u2705 COMPLETE</div>';
  }} else {{
    html += '<div class="sim-incomplete">\u23F3 INCOMPLETE</div>';
  }}

  if (sim.violations && sim.violations.length > 0) {{
    html += `<div class="sim-section" style="margin-top:8px"><div class="sim-section-title" style="color:var(--red)">Violations (${{sim.violations.length}})</div>`;
    sim.violations.forEach(v => {{
      html += `<div class="sim-violation">\u26A0 ${{v.agent}}/${{v.tool}}: ${{v.type}}<br><span style="color:var(--text2);font-size:10px">${{v.message}}</span></div>`;
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
  // Highlight graph node
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
function toolClass(tc) {{
  const name = tc.tool;
  const status = tc.result.status || "";
  if (name === "acquire_lock") {{
    if (status === "acquired") return "tool-acquire-acquired";
    if (status === "busy") return "tool-acquire-busy";
    if (status === "already_held") return "tool-acquire-already";
  }}
  if (name === "release_lock") return "tool-release";
  if (name === "send_message") return "tool-send";
  if (name === "receive_message") {{
    return status === "received" ? "tool-receive-ok" : "tool-receive-timeout";
  }}
  if (name === "signal_done") return "tool-done";
  if (status === "error") return "tool-error";
  return "tool-domain";
}}

function toolIcon(tc) {{
  const name = tc.tool;
  const status = tc.result.status || "";
  if (name === "acquire_lock") {{
    if (status === "acquired") return "&#x2713;";
    if (status === "busy") return "&#x23F3;";
    return "&#x1F517;";
  }}
  if (name === "release_lock") return "&#x1F513;";
  if (name === "send_message") return "&uarr;";
  if (name === "receive_message") return status === "received" ? "&darr;" : "&#x23F0;";
  if (name === "signal_done") return "&#x2714;";
  return "&#x25CF;";
}}

function formatResult(tc) {{
  const name = tc.tool;
  const r = tc.result;
  const status = r.status || "?";
  if (name === "acquire_lock") return status;
  if (name === "release_lock") return "released";
  if (name === "send_message") return "sent";
  if (name === "receive_message") {{
    if (status === "received") return 'label="' + (r.label || "") + '"';
    return "timeout";
  }}
  if (name === "signal_done") return "done";
  // Domain tool
  if (status === "ok") return "ok";
  if (status === "error") return r.message || "error";
  return status;
}}

function formatArgs(tc) {{
  const name = tc.tool;
  const a = tc.args;
  if (name === "acquire_lock" || name === "release_lock") return a.lock_id || "";
  if (name === "send_message") return (a.channel_id || "") + ' label="' + (a.label || "") + '"';
  if (name === "receive_message") return a.channel_id || "";
  if (name === "signal_done") return "";
  // Domain tool: compact args
  const s = JSON.stringify(a);
  return s.length > 60 ? s.slice(0, 57) + "..." : s;
}}

function showAgentTrace(agentId) {{
  const panel = document.getElementById("detailPanel");
  const a = DATA.agents.find(x => x.id === agentId);
  const trace = DATA.traces[agentId] || [];
  if (!a) return;

  // Stats
  const tc = a.tool_counts || {{}};
  const statsHtml = Object.entries(tc).map(([k, v]) =>
    `<div class="detail-stat"><span>${{k}}</span><span class="val">${{v}}</span></div>`
  ).join("");

  // Trace items
  let traceHtml;
  if (trace.length === 0) {{
    traceHtml = '<div style="font-size:12px;color:var(--text2);padding:8px">No tool calls recorded</div>';
  }} else {{
    traceHtml = trace.map(tc => {{
      const cls = toolClass(tc);
      const icon = toolIcon(tc);
      const argsStr = formatArgs(tc);
      const resultStr = formatResult(tc);
      return `<div class="trace-item">
        <span class="trace-round">R${{String(tc.round).padStart(2, '0')}}</span>
        <span class="${{cls}}" style="flex-shrink:0">${{icon}}</span>
        <div class="trace-body">
          <span class="trace-tool ${{cls}}">${{tc.tool}}</span>
          ${{argsStr ? `<div class="trace-args">${{argsStr}}</div>` : ""}}
          <div class="trace-result ${{cls}}">&rarr; ${{resultStr}}</div>
        </div>
        <span class="trace-elapsed">${{tc.elapsed}}s</span>
      </div>`;
    }}).join("");
  }}

  const statusColor = a.status === "completed" ? "var(--green)" : a.status === "timeout" ? "var(--orange)" : "var(--red)";

  panel.innerHTML = `
    <div class="detail-header">
      <span class="name">${{a.id}}</span>
      <span class="type-badge type-agent">Agent</span>
      <span class="type-badge" style="background:${{statusColor}}22;color:${{statusColor}}">${{a.status}}</span>
    </div>
    <div class="detail-section">
      <h4>Execution</h4>
      <div class="detail-stat"><span>Status</span><span class="val" style="color:${{statusColor}}">${{a.status}}</span></div>
      <div class="detail-stat"><span>Tool Calls</span><span class="val">${{a.steps}}</span></div>
      <div class="detail-stat"><span>Duration</span><span class="val">${{a.duration}}s</span></div>
      ${{a.error ? `<div class="detail-stat"><span>Error</span><span class="val" style="color:var(--red)">${{a.error}}</span></div>` : ""}}
    </div>
    ${{statsHtml ? `<div class="detail-section"><h4>Tool Breakdown</h4>${{statsHtml}}</div>` : ""}}
    <div class="detail-section" style="border-bottom:none">
      <h4>Trace (${{trace.length}} calls)</h4>
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

  // Collect all send/receive entries for this channel into a unified timeline
  const timeline = [];
  Object.entries(DATA.traces).forEach(([agentId, trace]) => {{
    trace.forEach((tc, idx) => {{
      if (tc.tool === "send_message" && tc.args.channel_id === chId) {{
        timeline.push({{ type: "send", agent: agentId, label: tc.args.label, round: tc.round, order: idx, body: tc.args.body || "" }});
      }}
      if (tc.tool === "receive_message" && tc.args.channel_id === chId) {{
        timeline.push({{ type: "recv", agent: agentId, status: tc.result.status, label: tc.result.label || "", round: tc.round, order: idx, body: tc.result.body || "" }});
      }}
    }});
  }});
  timeline.sort((a, b) => a.order - b.order);

  const sends = timeline.filter(t => t.type === "send");
  const recvs = timeline.filter(t => t.type === "recv");

  const timelineHtml = timeline.length
    ? timeline.map(t => {{
        if (t.type === "send") {{
          return `<div class="trace-item"><span class="trace-round">R${{String(t.round).padStart(2,'0')}}</span><span class="tool-send" style="flex-shrink:0">&uarr;</span><div class="trace-body"><span class="trace-tool tool-send">${{t.agent}}</span><div class="trace-args">label=<span style="color:var(--orange)">${{t.label}}</span>${{t.body ? ' body="'+t.body+'"' : ''}}</div></div></div>`;
        }} else {{
          const ok = t.status === "received";
          return `<div class="trace-item"><span class="trace-round">R${{String(t.round).padStart(2,'0')}}</span><span class="${{ok?'tool-receive-ok':'tool-receive-timeout'}}" style="flex-shrink:0">&darr;</span><div class="trace-body"><span class="trace-tool ${{ok?'tool-receive-ok':'tool-receive-timeout'}}">${{t.agent}}</span><div class="trace-args">${{ok ? 'label=<span style="color:var(--accent)">'+t.label+'</span>' : '<span style="color:var(--orange)">'+t.status+'</span>'}}${{t.body ? ' body="'+t.body+'"' : ''}}</div></div></div>`;
        }}
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
    <div class="detail-section">
      <h4>Stats</h4>
      <div class="detail-stat"><span>Sends</span><span class="val">${{sends.length}}</span></div>
      <div class="detail-stat"><span>Receives</span><span class="val">${{recvs.length}}</span></div>
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

  // Collect relevant trace entries
  const acquires = [];
  const releases = [];
  Object.entries(DATA.traces).forEach(([agentId, trace]) => {{
    trace.forEach(tc => {{
      if (tc.tool === "acquire_lock" && tc.args.lock_id === resId) {{
        acquires.push({{ agent: agentId, status: tc.result.status, round: tc.round }});
      }}
      if (tc.tool === "release_lock" && tc.args.lock_id === resId) {{
        releases.push({{ agent: agentId, round: tc.round }});
      }}
    }});
  }});

  const acqHtml = acquires.length
    ? acquires.map(a => `<div class="trace-item"><span class="trace-round">R${{String(a.round).padStart(2,'0')}}</span><span class="tool-acquire-${{a.status === 'acquired' ? 'acquired' : a.status === 'busy' ? 'busy' : 'already'}}">&#x1F512;</span><span class="trace-body"><span class="trace-tool">${{a.agent}}</span> &rarr; <span>${{a.status}}</span></span></div>`).join("")
    : '<div style="font-size:12px;color:var(--text2);padding:4px">None</div>';
  const relHtml = releases.length
    ? releases.map(a => `<div class="trace-item"><span class="trace-round">R${{String(a.round).padStart(2,'0')}}</span><span class="tool-release">&#x1F513;</span><span class="trace-body"><span class="trace-tool">${{a.agent}}</span> &rarr; released</span></div>`).join("")
    : '<div style="font-size:12px;color:var(--text2);padding:4px">None</div>';

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
    <div class="detail-section">
      <h4>Acquire Operations (${{acquires.length}})</h4>
      <div class="trace-list">${{acqHtml}}</div>
    </div>
    <div class="detail-section" style="border-bottom:none">
      <h4>Release Operations (${{releases.length}})</h4>
      <div class="trace-list">${{relHtml}}</div>
    </div>`;
}}

// ========== D3 GRAPH ==========
const container = document.getElementById("graphContainer");
const W = container.clientWidth || 800;
const H = container.clientHeight || 600;

const svg = d3.select("#graphContainer").insert("svg", ".zoom-bar")
  .attr("width", W).attr("height", H);

const g = svg.append("g");

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

// Build graph
const nodes = DATA.nodes.map(d => ({{...d}}));
const agentR = 28;
const resSize = 20;

// Status → stroke color for agent nodes
function agentStroke(status) {{
  if (status === "completed") return "var(--green)";
  if (status === "error") return "var(--red)";
  if (status === "timeout") return "var(--orange)";
  return "var(--text2)";
}}

// Assign curvature to parallel channel links
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

// Agent nodes
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
  .text(d => d.steps + " calls");

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
  .text(d => d.rtype + (d.initial !== null && d.initial !== undefined ? " = " + d.initial : ""));

// Drag
const drag = d3.drag()
  .on("start", (e, d) => {{ if (!e.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; }})
  .on("drag", (e, d) => {{ d.fx = e.x; d.fy = e.y; }})
  .on("end", (e, d) => {{ if (!e.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; }});
agentNodes.call(drag);
resNodes.call(drag);

// Click handlers
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
  selectAgentFromList(DATA.agents[0].id);
}}
</script>
</body>
</html>"""


def save_html(
    ir: dict,
    run_result: RunResult,
    output_path: str | Path,
    title: str = "",
    sim=None,
) -> Path:
    """Render IR + RunResult to HTML and write to file. Returns the output path."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = render_html(ir, run_result, title=title, sim=sim)
    output_path.write_text(content, encoding="utf-8")
    return output_path
