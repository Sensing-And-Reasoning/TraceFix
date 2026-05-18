"""TLC model checker runner."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

JAVA_PATH = "/opt/homebrew/opt/openjdk@17/bin/java"
TLA2TOOLS_JAR = str(Path(__file__).parent.parent.parent / "lib" / "tla2tools.jar")


@dataclass
class TLCResult:
    success: bool
    violation_type: str | None = None  # "deadlock", "safety", "liveness", "error"
    error_trace: str | None = None
    raw_output: str = ""
    stats: dict = field(default_factory=dict)


def run_tlc(
    tla_spec: str,
    tlc_config: str,
    timeout: int = 600,
    java_path: str = JAVA_PATH,
    tla2tools_jar: str = TLA2TOOLS_JAR,
) -> TLCResult:
    """Run TLC model checker on a TLA+ spec.

    Args:
        tla_spec: TLA+ specification content
        tlc_config: TLC configuration file content
        timeout: Timeout in seconds
        java_path: Path to Java 17 binary
        tla2tools_jar: Path to tla2tools.jar

    Returns:
        TLCResult with success/failure info and parsed output
    """
    with tempfile.TemporaryDirectory(prefix="tlc_v3_") as tmpdir:
        spec_path = os.path.join(tmpdir, "Protocol.tla")
        cfg_path = os.path.join(tmpdir, "Protocol.cfg")

        with open(spec_path, "w") as f:
            f.write(tla_spec)
        with open(cfg_path, "w") as f:
            f.write(tlc_config)

        cmd = [
            java_path,
            "-Xmx4g",
            "-cp", tla2tools_jar,
            "tlc2.TLC",
            "-config", "Protocol.cfg",
            "-workers", "auto",
            "Protocol.tla",
        ]

        start_time = time.time()
        try:
            proc = subprocess.run(
                cmd,
                cwd=tmpdir,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            elapsed = time.time() - start_time
            raw_output = proc.stdout + "\n" + proc.stderr
        except subprocess.TimeoutExpired as e:
            # subprocess.run kills the process and stores partial output on the exception.
            # e.stdout/e.stderr may be bytes even when text=True was requested.
            def _decode(b) -> str:
                if b is None:
                    return ""
                return b.decode("utf-8", errors="replace") if isinstance(b, bytes) else b
            partial_out = _decode(e.stdout) + "\n" + _decode(e.stderr)
            elapsed = time.time() - start_time
            return TLCResult(
                success=False,
                violation_type="error",
                error_trace="TLC timed out",
                raw_output=partial_out,
                stats={"timeout": True, "elapsed_seconds": round(elapsed, 2)},
            )

    return _parse_tlc_output(raw_output, elapsed)


def _parse_tlc_output(raw_output: str, elapsed: float) -> TLCResult:
    """Parse TLC output to determine result."""
    stats = {"elapsed_seconds": round(elapsed, 2)}

    # Parse state counts
    m = re.search(r"(\d+) states generated, (\d+) distinct states found", raw_output)
    if m:
        stats["states_generated"] = int(m.group(1))
        stats["distinct_states"] = int(m.group(2))

    # Check for assertion failures (PlusCal assert evaluated to FALSE)
    if "Assert evaluated to FALSE" in raw_output:
        return TLCResult(
            success=False,
            violation_type="safety",
            error_trace=_extract_trace(raw_output),
            raw_output=raw_output,
            stats=stats,
        )

    # Check for TLC errors (semantic, parsing, unknown operator, etc.)
    if "Error: " in raw_output and ("TLC threw an unexpected exception" in raw_output
                                     or "Semantic error" in raw_output
                                     or "Parsing error" in raw_output
                                     or "Unknown operator" in raw_output):
        return TLCResult(
            success=False,
            violation_type="error",
            error_trace=_extract_error(raw_output),
            raw_output=raw_output,
            stats=stats,
        )

    # Deadlock
    if "Deadlock reached" in raw_output or "deadlock reached" in raw_output.lower():
        return TLCResult(
            success=False,
            violation_type="deadlock",
            error_trace=_extract_trace(raw_output),
            raw_output=raw_output,
            stats=stats,
        )

    # Safety violation (invariant violated)
    if "is violated" in raw_output:
        if "Temporal properties were violated" in raw_output:
            return TLCResult(
                success=False,
                violation_type="liveness",
                error_trace=_extract_trace(raw_output),
                raw_output=raw_output,
                stats=stats,
            )
        return TLCResult(
            success=False,
            violation_type="safety",
            error_trace=_extract_trace(raw_output),
            raw_output=raw_output,
            stats=stats,
        )

    # Liveness violation
    if "Temporal properties were violated" in raw_output:
        return TLCResult(
            success=False,
            violation_type="liveness",
            error_trace=_extract_trace(raw_output),
            raw_output=raw_output,
            stats=stats,
        )

    # Check for successful completion
    if "Model checking completed" in raw_output or "finished" in raw_output.lower():
        # Also check there were no errors
        if "Error" not in raw_output or "0 errors" in raw_output:
            return TLCResult(
                success=True,
                raw_output=raw_output,
                stats=stats,
            )

    # If we got states but no error, likely success
    # But only if there's no "Error" in the output
    if stats.get("states_generated", 0) > 0 and "Error" not in raw_output:
        return TLCResult(
            success=True,
            raw_output=raw_output,
            stats=stats,
        )

    # Fallback: check for explicit errors
    if "Error" in raw_output:
        return TLCResult(
            success=False,
            violation_type="error",
            error_trace=_extract_error(raw_output),
            raw_output=raw_output,
            stats=stats,
        )

    return TLCResult(
        success=False,
        violation_type="error",
        error_trace="Could not determine TLC result",
        raw_output=raw_output,
        stats=stats,
    )


def _extract_trace(raw_output: str) -> str:
    """Extract the counterexample trace from TLC output."""
    lines = raw_output.split("\n")
    trace_lines = []
    in_trace = False
    for line in lines:
        if "State 1:" in line or "Error: " in line:
            in_trace = True
        if in_trace:
            trace_lines.append(line)
        if in_trace and line.strip() == "" and len(trace_lines) > 3:
            # Check if we're past the trace
            pass
    if trace_lines:
        return "\n".join(trace_lines)
    return raw_output


def _extract_error(raw_output: str) -> str:
    """Extract error message from TLC output."""
    lines = raw_output.split("\n")
    error_lines = []
    in_error = False
    for line in lines:
        if "Error:" in line or "error:" in line.lower():
            in_error = True
        if in_error:
            error_lines.append(line)
    if error_lines:
        return "\n".join(error_lines[:30])
    return raw_output[:2000]
