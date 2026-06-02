"""CLI: launch the coordination service (the authority node).

    python -m tracefix.runtime.coordination --workspace <ws> --port 8780

Loads ir.json (+ optional states.json), builds the UNCHANGED
ProtocolMonitor -> StateTracker -> CoordinationContext (identical to the
orchestrators), and serves it to remote agent nodes.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from tracefix.runtime.monitoring.coord import CoordinationContext
from tracefix.runtime.monitoring.monitor import ProtocolMonitor
from tracefix.runtime.monitoring.state_tracker import StateTracker
from tracefix.runtime.coordination.service import CoordinationService
from tracefix.runtime.workspace_layout import spec_path


def _load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text())


async def _serve(args: argparse.Namespace) -> None:
    ws = Path(args.workspace)
    ir = _load_json(spec_path(ws, "ir.json"))

    monitor = ProtocolMonitor(ir)
    tracker = None
    states_path = spec_path(ws, "states.json")
    if states_path.exists():
        tracker = StateTracker(_load_json(states_path))

    coord = CoordinationContext(ir, monitor, tracker=tracker, correction=True)
    service = CoordinationService(coord, host=args.host, port=args.port,
                                  verbose=args.verbose)
    await service.start()
    print(f"[coord] CoordinationService on http://{args.host}:{args.port} | "
          f"agents={len(ir['agents'])} channels={len(ir.get('channels', []))} "
          f"resources={len(ir.get('resources', []))} | workspace={ws}",
          file=sys.stderr)
    await service.serve_forever()


def main() -> None:
    p = argparse.ArgumentParser(
        prog="python -m tracefix.runtime.coordination",
        description="Launch the tracefix coordination service (authority node).",
    )
    p.add_argument("--workspace", required=True,
                   help="Verified workspace dir (ir.json [+ states.json])")
    p.add_argument("--host", default="127.0.0.1",
                   help="Bind host (use 0.0.0.0 for multi-machine; default loopback)")
    p.add_argument("--port", type=int, default=8780)
    p.add_argument("--verbose", action="store_true", help="Log every RPC")
    args = p.parse_args()
    try:
        asyncio.run(_serve(args))
    except KeyboardInterrupt:
        print("\n[coord] stopped", file=sys.stderr)


if __name__ == "__main__":
    main()
