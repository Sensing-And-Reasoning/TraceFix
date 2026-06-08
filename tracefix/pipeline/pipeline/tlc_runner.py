"""TLC model checker runner."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from .toolchain import (
    JAR_MISSING_HINT,
    JAVA_MISSING_HINT,
    resolve_java,
    resolve_jar,
)

JAVA_PATH = resolve_java()
TLA2TOOLS_JAR = resolve_jar()


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
    if not Path(tla2tools_jar).exists():
        return TLCResult(
            success=False,
            violation_type="error",
            error_trace=f"tla2tools.jar not found at {tla2tools_jar}. {JAR_MISSING_HINT}",
            raw_output="",
        )

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
                error_trace=(
                    "TLC timed out. Remedies: (1) raise --timeout if the protocol is "
                    "correct but complex; (2) lower the channel bound in Protocol.cfg to "
                    "shrink the state space; (3) reduce agent count or message complexity; "
                    "(4) check for an unintended unbounded loop in the PlusCal bodies."
                ),
                raw_output=partial_out,
                stats={"timeout": True, "elapsed_seconds": round(elapsed, 2)},
            )
        except (FileNotFoundError, OSError) as e:
            return TLCResult(
                success=False,
                violation_type="error",
                error_trace=f"Could not run Java at '{java_path}' ({e}). {JAVA_MISSING_HINT}",
                raw_output="",
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

    # Positive success confirmation. A verifier must *prove* a pass, never infer
    # one from the absence of error markers — a false "success" silently ships an
    # unverified protocol. TLC prints this exact pair only on a clean run, so we
    # require it before declaring success.
    if "Model checking completed" in raw_output and (
        "No error has been found" in raw_output or "0 errors" in raw_output
    ):
        return TLCResult(success=True, raw_output=raw_output, stats=stats)

    # No recognized verdict and no positive completion signal. Fail closed:
    # report an error rather than guessing success (the old heuristic — "states
    # generated and no 'Error' substring" — could pass a truncated or unfamiliar
    # TLC failure off as verified).
    return TLCResult(
        success=False,
        violation_type="error",
        error_trace=_extract_error(raw_output) or "Could not determine TLC verdict from output.",
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
