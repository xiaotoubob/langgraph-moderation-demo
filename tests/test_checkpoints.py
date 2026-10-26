from langgraph.checkpoint.sqlite import SqliteSaver

from moderation_demo.catalog import Catalog
from moderation_demo.checkpoint_lab import build_lab
from moderation_demo.graph import build_graph, initial_state
from moderation_demo.models import ScriptedBackend
from moderation_demo.tools import make_tools


def test_draft_revise_reducer_and_partial_updates(tmp_path):
    with SqliteSaver.from_conn_string(str(tmp_path / "lab.sqlite")) as saver:
        graph = build_lab(saver)
        config = {"configurable": {"thread_id": "lab"}}
        final = graph.invoke(
            {"messages": [], "status": "new", "result": "", "model_calls": 7}, config
        )
        history = list(graph.get_state_history(config))
    draft = next(
        snapshot.values for snapshot in history if snapshot.values.get("status") == "drafted"
    )
    assert draft["messages"][0].content == "Draft: checking the case."
    assert draft["result"] == "draft result"
    assert final["result"] == "revised result"
    assert len(final["messages"]) == 1
    assert final["messages"][0].id == "answer-1"
    assert final["messages"][0].content.startswith("Revised:")
    assert final["model_calls"] == 7  # omitted fields survive partial updates


def test_sqlite_reopen_resume_and_thread_isolation(tmp_path):
    catalog = Catalog()
    case = catalog.cases["threat-direct"]
    backend = ScriptedBackend(case, catalog)
    tools = make_tools(catalog, case.case_id)
    path = str(tmp_path / "checkpoints.sqlite")
    a = {"configurable": {"thread_id": "a"}}
    b = {"configurable": {"thread_id": "b"}}
    with SqliteSaver.from_conn_string(path) as saver:
        graph = build_graph(catalog, backend, tools, saver, pause_before=["validate"])
        graph.invoke(initial_state(case, backend), a)
        snapshot = graph.get_state(a)
        assert snapshot.next == ("validate",)
        assert snapshot.values["result"] is None
        paused_messages = len(snapshot.values["messages"])
        assert graph.get_state(b).values == {}
    # A fresh connection, graph and backend have no process-local conversation memory.
    with SqliteSaver.from_conn_string(path) as saver:
        graph = build_graph(catalog, ScriptedBackend(case, catalog), tools, saver)
        final = graph.invoke(None, a)
        assert final["status"] == "completed"
        assert final["model_calls"] == 4  # validation resumes without a new model request
        assert len(final["messages"]) == paused_messages
        other = catalog.cases["privacy-unclear"]
        other_backend = ScriptedBackend(other, catalog)
        other_graph = build_graph(catalog, other_backend, make_tools(catalog, other.case_id), saver)
        other_graph.invoke(initial_state(other, other_backend), b)
        assert other_graph.get_state(b).values["result"]["decision"] == "NEEDS_REVIEW"
        assert graph.get_state(a).values["result"]["decision"] == "VIOLATION"
        assert len(list(graph.get_state_history(a))) >= 9
