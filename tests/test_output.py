from __future__ import annotations

import json
import sys
from io import StringIO

from cited_cli.output.formatter import OutputContext, print_error, print_result, print_success


def test_print_result_json(capsys):
    ctx = OutputContext(json_mode=True)
    print_result({"key": "value"}, ctx)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["key"] == "value"


def test_print_success_json(capsys):
    ctx = OutputContext(json_mode=True)
    print_success("done", ctx)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["status"] == "ok"
    assert data["message"] == "done"


def test_print_result_human(capsys):
    ctx = OutputContext(json_mode=False)
    print_result(
        {"key": "value"},
        ctx,
        human_formatter=lambda d, c: c.print(f"Key is {d['key']}"),
    )
    captured = capsys.readouterr()
    assert "Key is value" in captured.out
