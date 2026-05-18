"""File-based workspace for the agentic verification loop.

Each agent run gets its own directory with real files:
  ir.json, Protocol.tla, Protocol.cfg, tlc_output.log, etc.
The agent "works in a directory" like a developer.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from uuid import uuid4

@dataclass
class RepairAttempt:
    """Record of a single IR repair attempt."""

    attempt: int  # 1-indexed
    success: bool  # repair produced valid IR?
    violation_type: str = ""  # error that triggered repair
    # post-repair verification (filled by subsequent validate/compile/tlc)
    ir_valid: bool | None = None
    tlc_passed: bool | None = None
    new_violation_type: str = ""


@dataclass
class RunResult:
    """Structured result of a verification run."""

    # IR validation
    ir_valid: bool | None = None
    ir_errors: list[str] = field(default_factory=list)

    # TLA+ compilation
    tla_compiled: bool | None = None
    tla_lines: int = 0

    # TLC verification (latest run)
    tlc_status: str | None = None  # "pass", "fail", "error", None
    tlc_violation_type: str = ""  # "deadlock", "safety", "liveness", ""
    tlc_states_generated: int = 0
    tlc_distinct_states: int = 0
    tlc_elapsed_seconds: float = 0.0

    # Repair tracking
    repairs: list[RepairAttempt] = field(default_factory=list)

    # Final verdict
    final_passed: bool = False
    passed_at_repair: int = -1  # -1=never, 0=initial, 1..N=after Nth repair

    def to_dict(self) -> dict:
        return asdict(self)


# Known workspace files and their roles
KNOWN_FILES = {
    "task.md": "Task description",
    "ir.json": "IR v3 specification",
    "Protocol.tla": "TLA+ specification",
    "Protocol.cfg": "TLC configuration",
    "Protocol_translated.tla": "Translated TLA+ (written by verify_spec)",
    "states.json": "Per-agent state machine (written by extract_states)",
    "tlc_output.log": "Raw TLC output",
    "tlc_error.md": "Formatted TLC error",
    "session.json": "Session record",
}

# Files downstream of ir.json — cleared when IR changes
DOWNSTREAM_OF_IR = ["Protocol.tla", "Protocol.cfg", "tlc_output.log", "tlc_error.md"]


class Workspace:
    """A file-based workspace directory for one agent session.

    All artifacts are real files in ``<base_dir>/{session_id}/``.
    The CLI passes ``v3_agent_test/results/<experiment_ts>/workspaces`` as base_dir.
    Tools read/write files via this object.
    """

    def __init__(self, session_id: str | None = None, base_dir: str = "v3_agent_test/results/default/workspaces"):
        if session_id is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            session_id = f"{ts}_{uuid4().hex[:8]}"

        self.session_id = session_id
        self.root = Path(base_dir) / session_id
        self.root.mkdir(parents=True, exist_ok=True)

        # Structured result tracking
        self.result = RunResult()

        # IR version history counter
        self._ir_version: int = 0

        # In-memory counters (ephemeral, serialized into session.json at end)
        self.repair_count: int = 0
        self.total_tool_calls: int = 0
        self.total_inner_llm_calls: int = 0
        # Primary model (the agent loop): charged at args.model pricing
        self.total_prompt_tokens: int = 0
        self.total_completion_tokens: int = 0
        self.total_cached_tokens: int = 0
        # Summarizer model (context compression): charged at summarizer_model pricing
        self.summarizer_prompt_tokens: int = 0
        self.summarizer_completion_tokens: int = 0
        self.summarizer_cached_tokens: int = 0

    # ------------------------------------------------------------------
    # Path resolution with traversal protection
    # ------------------------------------------------------------------

    def path(self, filename: str) -> Path:
        """Resolve a relative path within the workspace.

        Raises ValueError on path traversal attempts.
        """
        resolved = (self.root / filename).resolve()
        if not str(resolved).startswith(str(self.root.resolve())):
            raise ValueError(f"Path traversal denied: {filename}")
        return resolved

    # ------------------------------------------------------------------
    # Generic file I/O
    # ------------------------------------------------------------------

    def write_file(self, filename: str, content: str) -> None:
        """Write content to a file in the workspace, creating parent dirs.

        When ir.json is written:
          1. The current ir.json (if any) is backed up to history/ir_v{N}.json
          2. If Protocol.tla exists, it's also saved to history/spec_v{N}.tla
          3. The TLC result status is recorded in history/v{N}_meta.json
          4. Downstream artifacts are cleared
        """
        p = self.path(filename)
        p.parent.mkdir(parents=True, exist_ok=True)

        # Backup ir.json + related artifacts before overwriting
        if filename == "ir.json":
            self._backup_ir_version()

        p.write_text(content, encoding="utf-8")

        # Auto-clear downstream artifacts when ir.json changes
        if filename == "ir.json":
            for downstream in DOWNSTREAM_OF_IR:
                dp = self.root / downstream
                if dp.exists():
                    dp.unlink()

    def _backup_ir_version(self) -> None:
        """Backup current ir.json and related artifacts to history/v{N}/ before overwriting."""
        ir_path = self.root / "ir.json"
        if not ir_path.exists():
            return  # nothing to backup (first write)

        self._ir_version += 1
        v = self._ir_version
        version_dir = self.root / "history" / f"v{v}"
        version_dir.mkdir(parents=True, exist_ok=True)

        # Backup ir.json
        shutil.copy2(ir_path, version_dir / "ir.json")

        # Backup TLA+ spec and config if they exist (will be cleared by downstream cleanup)
        for fname in ("Protocol.tla", "Protocol.cfg"):
            src = self.root / fname
            if src.exists():
                shutil.copy2(src, version_dir / fname)

        # Backup TLC output if it exists
        for fname in ("tlc_output.log", "tlc_error.md"):
            src = self.root / fname
            if src.exists():
                shutil.copy2(src, version_dir / fname)

        # Record metadata: TLC status at this version
        meta = {
            "version": v,
            "timestamp": datetime.now().isoformat(),
            "tlc_status": self.result.tlc_status,
            "violation_type": self.result.tlc_violation_type,
            "repair_count": self.repair_count,
        }
        (version_dir / "meta.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )

    def _backup_protocol_attempt(self) -> Path | None:
        """Archive current Protocol.tla + error files to history/attempt_{N}/.

        Called when verify_spec fails. Coexists with _backup_ir_version()
        which uses history/v{N}/ — naming prefixes don't conflict.
        Returns the created directory, or None if Protocol.tla doesn't exist.
        """
        tla_src = self.root / "Protocol.tla"
        if not tla_src.exists():
            return None

        history_dir = self.root / "history"
        existing = sorted(history_dir.glob("attempt_*")) if history_dir.exists() else []
        nums = []
        for d in existing:
            try:
                nums.append(int(d.name.split("_", 1)[1]))
            except (ValueError, IndexError):
                pass
        next_num = (max(nums) + 1) if nums else 1

        attempt_dir = history_dir / f"attempt_{next_num}"
        attempt_dir.mkdir(parents=True, exist_ok=True)

        shutil.copy2(tla_src, attempt_dir / "Protocol.tla")
        for fname in ("tlc_error.md", "tlc_output.log"):
            src = self.root / fname
            if src.exists():
                shutil.copy2(src, attempt_dir / fname)

        return attempt_dir

    def read_file(self, filename: str) -> str | None:
        """Read a file from the workspace. Returns None if not found."""
        p = self.path(filename)
        if not p.exists():
            return None
        return p.read_text(encoding="utf-8")

    def list_files(self) -> list[str]:
        """List all files in the workspace, relative to root."""
        files = []
        for p in sorted(self.root.rglob("*")):
            if p.is_file():
                files.append(str(p.relative_to(self.root)))
        return files

    # ------------------------------------------------------------------
    # Typed accessors
    # ------------------------------------------------------------------

    def read_ir(self) -> dict | None:
        """Read ir.json and parse as dict. Returns None if absent or invalid."""
        content = self.read_file("ir.json")
        if content is None:
            return None
        try:
            data = json.loads(content)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None

    def write_ir(self, ir_data: dict) -> None:
        """Write IR dict as formatted JSON to ir.json."""
        self.write_file("ir.json", json.dumps(ir_data, indent=2, ensure_ascii=False))

    def read_tla(self) -> str | None:
        """Read Protocol.tla."""
        return self.read_file("Protocol.tla")

    def read_cfg(self) -> str | None:
        """Read Protocol.cfg."""
        return self.read_file("Protocol.cfg")

    # ------------------------------------------------------------------
    # Snapshot for session recording
    # ------------------------------------------------------------------

    def snapshot(self) -> dict:
        """JSON-serializable snapshot of workspace state."""
        ir = self.read_ir()
        return {
            "session_id": self.session_id,
            "workspace_path": str(self.root),
            "files": self.list_files(),
            "has_ir": ir is not None,
            "has_tla_spec": (self.root / "Protocol.tla").exists(),
            "has_tlc_output": (self.root / "tlc_output.log").exists(),
            "has_tlc_error": (self.root / "tlc_error.md").exists(),
            "repair_count": self.repair_count,
            "total_tool_calls": self.total_tool_calls,
            "total_inner_llm_calls": self.total_inner_llm_calls,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_cached_tokens": self.total_cached_tokens,
            "summarizer_prompt_tokens": self.summarizer_prompt_tokens,
            "summarizer_completion_tokens": self.summarizer_completion_tokens,
            "summarizer_cached_tokens": self.summarizer_cached_tokens,
            "result": self.result.to_dict(),
        }
