"""Local domain-tool execution: impl loading + per-agent schema filtering (offline)."""

from __future__ import annotations

import json

import pytest

from tracefix.runtime.domain_mcp.impl_loader import load_impls
from tracefix.runtime.domain_mcp.server import local_tool_schemas


def _write_impl(tmp_path, body: str):
    p = tmp_path / "tools_impl.py"
    p.write_text(body)
    return p


def test_load_impls_collects_public_functions(tmp_path):
    impls = load_impls(_write_impl(tmp_path, (
        "def charge_payment(amount):\n    return {'ok': True, 'txn': amount}\n"
        "def _helper():\n    return 1\n"
    )))
    assert impls.names == ["charge_payment"]   # private _helper excluded
    assert impls.has("charge_payment")
    assert impls.call("charge_payment", {"amount": 42}) == {"ok": True, "txn": 42}


def test_call_unknown_tool_raises(tmp_path):
    impls = load_impls(_write_impl(tmp_path, "def a():\n    return 1\n"))
    with pytest.raises(KeyError):
        impls.call("missing")


def test_load_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_impls(tmp_path / "nope.py")


def test_local_tool_schemas_filters_by_agent_and_impl(tmp_path):
    tools = [
        {"type": "function", "function": {
            "name": "charge_payment", "agent_ids": ["BILLING"], "x-impl": "local",
            "parameters": {"type": "object", "properties": {"amount": {"type": "number"}}}}},
        {"type": "function", "function": {
            "name": "send_email", "agent_ids": ["NOTIFIER"], "x-impl": "external",
            "parameters": {"type": "object", "properties": {}}}},
        {"type": "function", "function": {
            "name": "audit", "agent_ids": ["BILLING", "NOTIFIER"], "x-impl": "local",
            "parameters": {"type": "object", "properties": {}}}},
    ]
    p = tmp_path / "tools.json"
    p.write_text(json.dumps(tools))

    billing = [s["function"]["name"] for s in local_tool_schemas(p, "BILLING")]
    assert billing == ["charge_payment", "audit"]      # local + owned; external excluded
    notifier = [s["function"]["name"] for s in local_tool_schemas(p, "NOTIFIER")]
    assert notifier == ["audit"]                         # send_email is external → not here
    assert local_tool_schemas(p, "PICKER") == []        # owns nothing
