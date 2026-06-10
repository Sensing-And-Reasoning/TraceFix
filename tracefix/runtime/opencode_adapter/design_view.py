"""Design-phase live view — the browser page for ``tracefix design --live``.

Renders the protocol being DESIGNED in real time: a phase rail (the skill's
Phase 0–5 workflow), the IR topology growing the moment ``ir.json`` is written,
the TLC verdict (PASS / FAIL + repair count), and a live activity feed of the
designer's tool calls. Same SSE transport as the runtime view
(``event_bus → live_server /api/events``); only the page differs.
"""

from __future__ import annotations

import html as _html

_PHASES = [
    ("toolchain", "Phase 0 · Toolchain check"),
    ("ir", "Phase 1 · IR design"),
    ("pluscal", "Phase 2 · PlusCal bodies"),
    ("verify", "Phase 3 · TLC verify + repair"),
    ("states", "Phase 4 · Extract states"),
    ("prompts", "Phase 5 · Agent prompts"),
]


def render_design_html(title: str = "", model: str = "") -> str:
    phase_items = "\n".join(
        f'<div class="phase" id="ph-{key}"><span class="dot"></span>'
        f'<span class="lbl">{label}</span><span class="note" id="ph-{key}-note"></span></div>'
        for key, label in _PHASES)
    safe_title = _html.escape(title or "tracefix design")
    safe_model = _html.escape(model or "")
    return _TEMPLATE.replace("__TITLE__", safe_title) \
                    .replace("__MODEL__", safe_model) \
                    .replace("__PHASES__", phase_items)


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>__TITLE__ — tracefix design</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
:root { --bg:#0d1117; --panel:#161b22; --border:#30363d; --text:#e6edf3;
        --text2:#8b949e; --accent:#58a6ff; --green:#3fb950; --red:#f85149;
        --orange:#d29922; --purple:#bc8cff; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--text); height:100vh; display:flex;
       flex-direction:column; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif; }
header { padding:10px 16px; border-bottom:1px solid var(--border); display:flex;
         align-items:center; gap:12px; }
header h1 { font-size:15px; margin:0; font-weight:600; }
header .model { color:var(--text2); font-size:12px; }
#status { margin-left:auto; font-size:12px; padding:3px 10px; border-radius:12px;
          background:var(--panel); border:1px solid var(--border); color:var(--text2); }
#status.ready { color:var(--green); border-color:var(--green); }
#status.failed { color:var(--red); border-color:var(--red); }
main { flex:1; display:grid; grid-template-columns: 260px 1fr 340px; min-height:0; }
section { border-right:1px solid var(--border); display:flex; flex-direction:column; min-height:0; }
section h2 { font-size:11px; text-transform:uppercase; letter-spacing:.08em;
             color:var(--text2); margin:0; padding:10px 14px 6px; }
/* phase rail */
.phase { display:flex; align-items:center; gap:10px; padding:9px 14px; font-size:13px;
         color:var(--text2); }
.phase .dot { width:10px; height:10px; border-radius:50%; background:var(--border);
              flex-shrink:0; }
.phase.active { color:var(--text); }
.phase.active .dot { background:var(--accent); box-shadow:0 0 8px var(--accent); }
.phase.done { color:var(--text); }
.phase.done .dot { background:var(--green); }
.phase.failed .dot { background:var(--red); }
.phase .note { margin-left:auto; font-size:11px; color:var(--text2); }
#verdict { margin:12px 14px; padding:10px 12px; border-radius:8px; font-size:13px;
           display:none; border:1px solid var(--border); }
#verdict.pass { display:block; border-color:var(--green); color:var(--green); }
#verdict.fail { display:block; border-color:var(--red); color:var(--red); }
#ready { margin:0 14px; padding:10px 12px; border-radius:8px; font-size:12px;
         display:none; border:1px dashed var(--green); color:var(--green);
         font-family:ui-monospace,Menlo,monospace; word-break:break-all; }
/* topology */
#graphwrap { flex:1; position:relative; min-height:0; }
#graph { width:100%; height:100%; }
#graph-hint { position:absolute; inset:0; display:flex; align-items:center;
              justify-content:center; color:var(--text2); font-size:13px; }
.nodelabel { font-size:11px; fill:var(--text); pointer-events:none; }
/* feed */
#feed { flex:1; overflow-y:auto; padding:6px 0; font:11px ui-monospace,Menlo,monospace; }
.ev { padding:3px 14px; display:flex; gap:8px; color:var(--text2); }
.ev .t { color:var(--text2); flex-shrink:0; }
.ev.tool .name { color:var(--accent); }
.ev.phase { color:var(--purple); }
.ev.verdict-pass { color:var(--green); }
.ev.verdict-fail { color:var(--red); }
.ev.prompt { color:var(--orange); }
</style>
</head>
<body>
<header>
  <h1>__TITLE__</h1><span class="model">__MODEL__</span>
  <span id="status">designing…</span>
</header>
<main>
  <section>
    <h2>Workflow</h2>
    __PHASES__
    <div id="verdict"></div>
    <div id="ready"></div>
  </section>
  <section>
    <h2>Protocol topology</h2>
    <div id="graphwrap">
      <svg id="graph"></svg>
      <div id="graph-hint">waiting for ir.json…</div>
    </div>
  </section>
  <section style="border-right:none">
    <h2>Designer activity</h2>
    <div id="feed"></div>
  </section>
</main>
<script>
const feed = document.getElementById("feed");
const statusEl = document.getElementById("status");
let evCount = 0;
function addFeed(cls, html) {
  evCount++;
  const d = document.createElement("div");
  d.className = "ev " + cls;
  d.innerHTML = '<span class="t">' + new Date().toLocaleTimeString() + "</span>" + html;
  feed.appendChild(d);
  if (feed.children.length > 400) feed.removeChild(feed.firstChild);
  feed.scrollTop = feed.scrollHeight;
}
const PH_ORDER = ["toolchain","ir","pluscal","verify","states","prompts"];
function setPhase(key, state, note) {
  const el = document.getElementById("ph-" + key);
  if (!el) return;
  el.classList.remove("active","done","failed");
  if (state) el.classList.add(state);
  if (note !== undefined)
    document.getElementById("ph-" + key + "-note").textContent = note;
  // everything before an active/done phase is done
  const idx = PH_ORDER.indexOf(key);
  for (let i = 0; i < idx; i++) {
    const prev = document.getElementById("ph-" + PH_ORDER[i]);
    if (prev && !prev.classList.contains("failed")) {
      prev.classList.remove("active"); prev.classList.add("done");
    }
  }
}

// ---- topology (renders/refreshes on design.ir) ----
function renderGraph(ir) {
  document.getElementById("graph-hint").style.display = "none";
  const svg = d3.select("#graph");
  svg.selectAll("*").remove();
  const box = document.getElementById("graphwrap").getBoundingClientRect();
  const W = box.width, H = box.height;
  svg.attr("viewBox", "0 0 " + W + " " + H);
  svg.append("defs").append("marker").attr("id","arrow").attr("viewBox","0 -5 10 10")
     .attr("refX", 22).attr("markerWidth",6).attr("markerHeight",6).attr("orient","auto")
     .append("path").attr("d","M0,-5L10,0L0,5").attr("fill","#8b949e");
  const nodes = [], links = [];
  (ir.agents||[]).forEach(a => nodes.push({id:a.id, kind:"agent"}));
  (ir.resources||[]).forEach(r => nodes.push({id:r.id, kind:r.type==="Counter"?"counter":"lock"}));
  (ir.channels||[]).forEach(c => {
    const f = Array.isArray(c.from)?c.from:[c.from], t = Array.isArray(c.to)?c.to:[c.to];
    f.forEach(ff => t.forEach(tt => links.push({source:ff, target:tt, label:(c.labels||[]).join(",")})));
  });
  const sim = d3.forceSimulation(nodes)
    .force("link", d3.forceLink(links).id(d=>d.id).distance(130))
    .force("charge", d3.forceManyBody().strength(-420))
    .force("center", d3.forceCenter(W/2, H/2))
    .force("collide", d3.forceCollide(42));
  const link = svg.append("g").selectAll("line").data(links).join("line")
    .attr("stroke","#8b949e").attr("stroke-width",1.2).attr("marker-end","url(#arrow)");
  const node = svg.append("g").selectAll("g").data(nodes).join("g");
  node.each(function(d){
    const g = d3.select(this);
    if (d.kind === "agent")
      g.append("circle").attr("r",16).attr("fill","#1f6feb").attr("stroke","#58a6ff");
    else
      g.append("rect").attr("x",-13).attr("y",-13).attr("width",26).attr("height",26)
       .attr("rx",5).attr("fill", d.kind==="counter" ? "#9e6a03" : "#6e4000")
       .attr("stroke","#d29922");
  });
  node.append("text").attr("class","nodelabel").attr("dy",30).attr("text-anchor","middle")
      .text(d=>d.id);
  sim.on("tick", () => {
    link.attr("x1",d=>d.source.x).attr("y1",d=>d.source.y)
        .attr("x2",d=>d.target.x).attr("y2",d=>d.target.y);
    node.attr("transform", d=>"translate("+d.x+","+d.y+")");
  });
}

// ---- SSE wiring ----
const es = new EventSource("/api/events");
es.addEventListener("design.tool", e => {
  const d = JSON.parse(e.data);
  addFeed("tool", '<span class="name">' + d.tool + "</span> " + (d.status||""));
});
es.addEventListener("design.phase", e => {
  const d = JSON.parse(e.data);
  setPhase(d.key, d.state || "active", d.note);
  addFeed("phase", "⟶ " + d.label);
});
es.addEventListener("design.ir", e => {
  const d = JSON.parse(e.data);
  renderGraph(d.ir);
  const n = (d.ir.agents||[]).length, r = (d.ir.resources||[]).length,
        c = (d.ir.channels||[]).length;
  addFeed("phase", "ir.json — " + n + " agents · " + r + " resources · " + c + " channels");
});
es.addEventListener("design.verdict", e => {
  const d = JSON.parse(e.data);
  const v = document.getElementById("verdict");
  if (d.tlc_passed) {
    v.className = "pass";
    v.textContent = "TLC PASS" + (d.repairs ? " · " + d.repairs + " repair(s)" : "");
    setPhase("verify", "done", d.repairs ? d.repairs + " repairs" : "");
    addFeed("verdict-pass", "TLC PASS");
  } else {
    v.className = "fail";
    v.textContent = "TLC FAIL — repairing (attempt " + (d.repairs ?? "?") + ")";
    setPhase("verify", "active", "attempt " + (d.repairs ?? "?"));
    addFeed("verdict-fail", "TLC FAIL → repair");
  }
});
es.addEventListener("design.prompt", e => {
  const d = JSON.parse(e.data);
  addFeed("prompt", "prompt ✓ " + d.agent);
  setPhase("prompts", "active", d.count + "/" + d.total);
});
es.addEventListener("design.done", e => {
  const d = JSON.parse(e.data);
  if (d.status === "ready") {
    statusEl.textContent = "READY";
    statusEl.className = "ready";
    PH_ORDER.forEach(k => setPhase(k, "done"));
    const r = document.getElementById("ready");
    r.style.display = "block";
    r.textContent = "tracefix run --workspace " + d.workspace;
  } else {
    statusEl.textContent = d.status;
    statusEl.className = "failed";
  }
  addFeed(d.status === "ready" ? "verdict-pass" : "verdict-fail", "design " + d.status);
});
es.onopen = () => addFeed("phase", "connected");
</script>
</body>
</html>
"""
