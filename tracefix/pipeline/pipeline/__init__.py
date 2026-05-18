"""Pipeline modules for TLA+ verification (self-contained, PlusCal-based).

Re-exports commonly used symbols so external consumers can do:
    from tracefix.pipeline.pipeline import validate_ir, generate_pluscal_scaffold, ...
"""

from tracefix.pipeline.pipeline.validator import ValidationResult, validate_ir
from tracefix.pipeline.pipeline.pluscal_generator import generate_pluscal_scaffold, generate_tlc_config
from tracefix.pipeline.pipeline.pluscal_compiler import PlusCaLResult, translate_pluscal
from tracefix.pipeline.pipeline.tlc_runner import TLCResult, run_tlc
from tracefix.pipeline.pipeline.trace_parser import TraceStep, parse_trace
from tracefix.pipeline.pipeline.error_formatter import format_tlc_error

__all__ = [
    "ValidationResult",
    "validate_ir",
    "generate_pluscal_scaffold",
    "generate_tlc_config",
    "PlusCaLResult",
    "translate_pluscal",
    "TLCResult",
    "run_tlc",
    "TraceStep",
    "parse_trace",
    "format_tlc_error",
]
