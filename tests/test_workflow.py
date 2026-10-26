import json

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from moderation_demo.catalog import Catalog
from moderation_demo.domain import ReviewResult
from moderation_demo.graph import build_graph, initial_state
from moderation_demo.models import ScriptedBackend
from moderation_demo.tools import make_tools


@pytest.fixture
def catalog():
    return Catalog()


class SequenceBackend:
    identity = {"kind": "test"}

    def __init__(self, replies):
        self.replies = iter(replies)

    def invoke(self, messages):
        # Each invocation is a new message. Reusing the very same AIMessage object
        # would reuse its assigned ID and intentionally trigger add_messages replacement.
        return next(self.replies).model_copy(deep=True, update={"id": None})


def run(catalog, backend, case_id="threat-direct", **limits):
    case = catalog.cases[case_id]
    graph = build_graph(catalog, backend, make_tools(catalog, case_id), **limits)
    return graph.invoke(initial_state(case, backend))


@pytest.mark.parametrize("case_id", list(Catalog().cases))
def test_scripted_fixtures_exercise_tool_protocol_and_validation(catalog, case_id):
    """This tests reference-answer REPLAY, not model classification accuracy."""
    case = catalog.cases[case_id]
    state = run(catalog, ScriptedBackend(case, catalog), case_id)
    assert state["status"] == "completed"
    assert state["model_calls"] == 4
    assert state["tool_calls"] == 3
    requests = [
        call
        for message in state["messages"]
        if isinstance(message, AIMessage)
        for call in message.tool_calls
    ]
    responses = [message for message in state["messages"] if isinstance(message, ToolMessage)]
    assert [call["name"] for call in requests] == [
        "get_case_context",
        "search_policies",
        "get_policy",
    ]
    assert [message.tool_call_id for message in responses] == [call["id"] for call in requests]
    assert all(message.status == "success" for message in responses)
    assert catalog.check_result(ReviewResult.model_validate(state["result"]), case) == []


@pytest.mark.parametrize("tamper", ["evidence", "version", "section", "quote"])
def test_fabricated_evidence_or_citations_never_become_results(catalog, tamper):
    answer = catalog.cases["threat-direct"].reference_result.model_dump()
    if tamper == "evidence":
        answer["input_evidence"][0]["quote"] = "This was not in the submitted text."
    elif tamper == "version":
        answer["policy_citations"][0]["version"] = "999"
    elif tamper == "section":
        answer["policy_citations"][0]["section_id"] = "missing"
    else:
        answer["policy_citations"][0]["quote"] = "This policy quote is invented."
    invalid = AIMessage(content=json.dumps(answer))
    state = run(catalog, SequenceBackend([invalid, invalid]))
    assert state["status"] == "failed"
    assert state["result"] is None
    assert state["repair_attempts"] == 1
    assert state["errors"]


def test_format_repair_is_bounded_and_valid_answer_can_recover(catalog):
    valid = AIMessage(content=catalog.cases["threat-direct"].reference_result.model_dump_json())
    state = run(catalog, SequenceBackend([AIMessage(content="not JSON"), valid]))
    assert state["status"] == "completed"
    assert state["repair_attempts"] == 1
    assert state["model_calls"] == 2
    assert state["errors"] == []


@pytest.mark.parametrize(
    "name,args",
    [
        ("unknown_tool", {}),
        ("get_policy", {"policy_id": "P-THREAT"}),
        ("get_policy", {"policy_id": "missing", "version": "1.0"}),
        ("get_case_context", {"requested_case_id": "privacy-self"}),
    ],
)
def test_tool_errors_are_paired_with_the_request_and_visible_to_model(catalog, name, args):
    call = AIMessage(
        content="",
        tool_calls=[
            {
                "name": name,
                "args": args,
                "id": "call-1",
                "type": "tool_call",
            }
        ],
    )
    valid = AIMessage(content=catalog.cases["threat-direct"].reference_result.model_dump_json())
    state = run(catalog, SequenceBackend([call, valid]))
    tool_reply = next(m for m in state["messages"] if isinstance(m, ToolMessage))
    assert tool_reply.tool_call_id == "call-1"
    assert tool_reply.status == "error"
    assert json.loads(tool_reply.content)["ok"] is False
    assert state["status"] == "completed"


def test_multiple_tool_requests_are_executed_and_counted(catalog):
    call = AIMessage(
        content="",
        tool_calls=[
            {"name": "search_policies", "args": {"query": "威胁"}, "id": "a", "type": "tool_call"},
            {
                "name": "get_case_context",
                "args": {"requested_case_id": "threat-direct"},
                "id": "b",
                "type": "tool_call",
            },
        ],
    )
    valid = AIMessage(content=catalog.cases["threat-direct"].reference_result.model_dump_json())
    state = run(catalog, SequenceBackend([call, valid]))
    assert state["tool_calls"] == 2
    assert [m.tool_call_id for m in state["messages"] if isinstance(m, ToolMessage)] == ["a", "b"]


@pytest.mark.parametrize(
    "limits,error",
    [
        ({"max_model_calls": 2}, "model call budget exhausted"),
        ({"max_tool_calls": 1}, "tool call budget exhausted"),
    ],
)
def test_nonterminating_tool_loop_stops_without_business_result(catalog, limits, error):
    class LoopBackend:
        identity = {"kind": "test"}

        def invoke(self, messages):
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "search_policies",
                        "args": {"query": "威胁"},
                        "id": f"loop-{len(messages)}",
                        "type": "tool_call",
                    }
                ],
            )

    state = run(catalog, LoopBackend(), **limits)
    assert state["status"] == "failed"
    assert state["result"] is None
    assert state["errors"] == [error]


def test_service_failure_is_not_presented_as_content_needing_review(catalog):
    class BrokenBackend:
        identity = {"kind": "test"}

        def invoke(self, messages):
            raise ConnectionError("a sensitive SDK error body")

    state = run(catalog, BrokenBackend())
    assert state["status"] == "failed"
    assert state["result"] is None
    assert "sensitive" not in str(state)


def test_input_evidence_cannot_come_only_from_context(catalog):
    case = catalog.cases["privacy-harassment"]
    result = case.reference_result.model_copy(deep=True)
    result.input_evidence[0].quote = "小王未公开或同意披露此号码。"
    assert result.input_evidence[0].quote in case.context
    assert catalog.check_result(result, case)


def test_checker_does_not_claim_semantic_support(catalog):
    # A real but irrelevant citation passes literal checks. Human review/evaluation must
    # assess entailment; this intentionally documents the validator's practical limit.
    case = catalog.cases["threat-direct"]
    result = case.reference_result.model_copy(deep=True)
    policy = catalog.get_policy("P-PRIVACY", "1.0")[0]
    result.policy_citations[0].policy_id = policy.policy_id
    result.policy_citations[0].quote = policy.rule
    assert catalog.check_result(result, case) == []


def test_search_can_return_no_evidence_and_lookup_is_versioned(catalog):
    assert catalog.search("zzzz_nonexistent") == []
    assert catalog.get_policy("P-THREAT", "999") == []
    assert catalog.search("人身威胁")[0]["policy_id"] == "P-THREAT"
