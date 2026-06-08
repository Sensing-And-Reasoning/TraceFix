"""PlusCal to TLA+ translation via pcal.trans.

Runs the PlusCal translator from tla2tools.jar to convert PlusCal algorithm
blocks in Protocol.tla into standard TLA+ (modifying the file in place in
a temp directory).
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
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
class PlusCaLResult:
    """Result of PlusCal translation."""

    success: bool
    translated_tla: str = ""  # full .tla content after pcal.trans
    error_message: str = ""  # pcal.trans error with line numbers


def translate_pluscal(
    tla_content: str,
    cfg_content: str = "",
    *,
    java_path: str = JAVA_PATH,
    tla2tools_jar: str = TLA2TOOLS_JAR,
) -> PlusCaLResult:
    """Translate PlusCal algorithm in a .tla file to TLA+.

    Creates a temp directory, writes the .tla (and optional .cfg),
    runs pcal.trans, and reads back the translated file.

    Args:
        tla_content: Protocol.tla content with PlusCal algorithm block.
        cfg_content: Optional Protocol.cfg content (needed by some translators).
        java_path: Path to Java 17 binary.
        tla2tools_jar: Path to tla2tools.jar.

    Returns:
        PlusCaLResult with success flag and either translated content or error.
    """
    if not Path(tla2tools_jar).exists():
        return PlusCaLResult(
            success=False,
            error_message=f"tla2tools.jar not found at {tla2tools_jar}. {JAR_MISSING_HINT}",
        )

    with tempfile.TemporaryDirectory(prefix="pcal_") as tmpdir:
        spec_path = os.path.join(tmpdir, "Protocol.tla")

        with open(spec_path, "w") as f:
            f.write(tla_content)

        if cfg_content:
            cfg_path = os.path.join(tmpdir, "Protocol.cfg")
            with open(cfg_path, "w") as f:
                f.write(cfg_content)

        cmd = [
            java_path,
            "-cp",
            tla2tools_jar,
            "pcal.trans",
            "Protocol.tla",
        ]

        try:
            proc = subprocess.run(
                cmd,
                cwd=tmpdir,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            return PlusCaLResult(
                success=False,
                error_message="PlusCal translation timed out after 30 seconds.",
            )
        except (FileNotFoundError, OSError) as e:
            return PlusCaLResult(
                success=False,
                error_message=f"Could not run Java at '{java_path}' ({e}). {JAVA_MISSING_HINT}",
            )

        combined_output = proc.stdout + "\n" + proc.stderr

        # pcal.trans modifies the file in place on success
        # Check for errors in output
        if proc.returncode != 0 or _has_pcal_error(combined_output):
            error_msg = _extract_pcal_error(combined_output, tla_content)
            return PlusCaLResult(
                success=False,
                error_message=error_msg,
            )

        # Read back the translated file
        try:
            with open(spec_path, "r") as f:
                translated = f.read()
        except OSError:
            return PlusCaLResult(
                success=False,
                error_message="Failed to read translated file after pcal.trans.",
            )

        # Verify translation actually happened (look for TLA+ translation block)
        if "\\* BEGIN TRANSLATION" not in translated:
            # pcal.trans may have succeeded silently but not translated
            return PlusCaLResult(
                success=False,
                error_message=(
                    "pcal.trans ran but no translation block found. "
                    f"Output: {combined_output[:500]}"
                ),
            )

        return PlusCaLResult(
            success=True,
            translated_tla=translated,
        )


def _has_pcal_error(output: str) -> bool:
    """Check if pcal.trans output contains error indicators."""
    error_patterns = [
        "Unrecoverable error",
        "-- Error",
        "error found",
        "Unexpected end of file",
        "expected",
        "Parse error",
        "was not closed",
    ]
    output_lower = output.lower()
    for pat in error_patterns:
        if pat.lower() in output_lower:
            return True
    return False


def _extract_pcal_error(output: str, tla_content: str) -> str:
    """Extract a useful error message from pcal.trans output.

    Includes line numbers and surrounding context from the source.
    """
    lines_out = output.strip().split("\n")

    # Find error-relevant lines
    error_lines: list[str] = []
    for line in lines_out:
        # Skip blank lines and non-error lines
        stripped = line.strip()
        if not stripped:
            continue
        # Include lines with error indicators or line numbers
        if any(
            kw in stripped.lower()
            for kw in ["error", "line", "expected", "unexpected", "parse", "unrecoverable"]
        ):
            error_lines.append(stripped)
        elif re.match(r"^\d+\.", stripped):
            # Lines starting with line numbers (pcal.trans format)
            error_lines.append(stripped)

    if error_lines:
        msg = "\n".join(error_lines[:15])
    else:
        # Fallback: return last non-empty lines of output
        non_empty = [l for l in lines_out if l.strip()]
        msg = "\n".join(non_empty[-10:]) if non_empty else output[:500]

    # Try to extract line number and add source context
    line_match = re.search(r"line (\d+)", msg, re.IGNORECASE)
    if line_match:
        line_num = int(line_match.group(1))
        source_lines = tla_content.split("\n")
        start = max(0, line_num - 3)
        end = min(len(source_lines), line_num + 2)
        context_lines = []
        for i in range(start, end):
            marker = ">>>" if i + 1 == line_num else "   "
            context_lines.append(f"{marker} {i + 1:4d} | {source_lines[i]}")
        msg += "\n\nSource context:\n" + "\n".join(context_lines)

    return msg
