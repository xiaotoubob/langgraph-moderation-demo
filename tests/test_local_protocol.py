"""Exercise the REAL SDK adapter against a local stub, not an actual Qwen model."""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

import pytest

from moderation_demo.catalog import Catalog
from moderation_demo.domain import Case
from moderation_demo.graph import build_graph, initial_state
from moderation_demo.models import LocalBackend
from moderation_demo.tools import make_tools


@pytest.mark.parametrize("custom_input", [False, True])
def test_openai_compatible_adapter_round_trips_tool_messages(monkeypatch, custom_input):
    catalog = Catalog()
    fixture = catalog.cases["threat-direct"]
    case = (
        Case(case_id="custom-input", text=fixture.text, context=None) if custom_input else fixture
    )
    catalog.cases[case.case_id] = case
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            assert self.path == "/v1/chat/completions"
            requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            if len(requests) == 1:
                message = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "context-1",
                            "type": "function",
                            "function": {
                                "name": "get_case_context",
                                "arguments": json.dumps({"requested_case_id": case.case_id}),
                            },
                        }
                    ],
                }
            else:
                message = {
                    "role": "assistant",
                    "content": fixture.reference_result.model_dump_json(),
                }
            payload = json.dumps(
                {
                    "id": f"completion-{len(requests)}",
                    "object": "chat.completion",
                    "created": 1,
                    "model": "protocol-test-model",
                    "choices": [
                        {
                            "index": 0,
                            "message": message,
                            "finish_reason": "tool_calls" if len(requests) == 1 else "stop",
                        }
                    ],
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("MODERATION_MODEL", "protocol-test-model")
    monkeypatch.setenv("MODERATION_BASE_URL", f"http://127.0.0.1:{server.server_port}/v1")
    monkeypatch.setenv("MODERATION_API_KEY", "local-test-not-a-secret")
    try:
        tools = make_tools(catalog, case.case_id)
        backend = LocalBackend(tools)
        graph = build_graph(catalog, backend, tools)
        state = graph.invoke(initial_state(case, backend))
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
    assert state["status"] == "completed"
    assert state["model_calls"] == 2
    assert state["tool_calls"] == 1
    assert {item["function"]["name"] for item in requests[0]["tools"]} == {
        "search_policies",
        "get_policy",
        "get_case_context",
    }
    submitted = json.loads(requests[0]["messages"][-1]["content"])
    assert submitted == {"case_id": case.case_id, "text": case.text}
    assert "reference_result" not in json.dumps(requests)
    assert requests[1]["messages"][-1]["role"] == "tool"
    assert requests[1]["messages"][-1]["tool_call_id"] == "context-1"
