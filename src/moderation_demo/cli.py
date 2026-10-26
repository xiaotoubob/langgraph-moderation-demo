"""Run, pause, inspect and resume the same persisted graph from separate processes."""

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from uuid import uuid4

from langgraph.checkpoint.sqlite import SqliteSaver

from moderation_demo.catalog import Catalog
from moderation_demo.checkpoint_lab import build_lab
from moderation_demo.domain import Case
from moderation_demo.graph import build_graph, initial_state
from moderation_demo.models import LocalBackend, ScriptedBackend
from moderation_demo.tools import make_tools


def emit(value, *, file=sys.stdout):
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str), file=file)


def thread_config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}, "recursion_limit": 50}


def describe_state(snapshot, *, messages=False) -> dict:
    state = snapshot.values
    result = {
        "checkpoint_id": snapshot.config["configurable"].get("checkpoint_id"),
        "next": list(snapshot.next),
        "status": state.get("status"),
        "model_calls": state.get("model_calls"),
        "tool_calls": state.get("tool_calls"),
        "repair_attempts": state.get("repair_attempts"),
        "message_count": len(state.get("messages", [])),
        "result": state.get("result"),
        "errors": state.get("errors", []),
    }
    if messages:
        result["messages"] = [message.model_dump() for message in state.get("messages", [])]
    return result


def load_saved_case(saver: SqliteSaver, config: dict) -> tuple[Case, dict]:
    saved = saver.get_tuple(config)
    if saved is None or "case" not in saved.checkpoint["channel_values"]:
        raise ValueError("no moderation checkpoint for this thread; check --db and --thread")
    values = saved.checkpoint["channel_values"]
    return Case.model_validate(values["case"]), values["backend"]


def execute(graph, graph_input, config: dict, thread_id: str) -> int:
    for update in graph.stream(graph_input, config, stream_mode="updates"):
        for node, changes in update.items():
            if node == "__interrupt__":
                continue
            details = {key: value for key, value in changes.items() if key != "messages"}
            details["message_types"] = [m.type for m in changes.get("messages", [])]
            for message in changes.get("messages", []):
                if getattr(message, "tool_calls", None):
                    details["requested_tools"] = [call["name"] for call in message.tool_calls]
            emit({"node": node, "updates": details}, file=sys.stderr)
    snapshot = graph.get_state(config)
    paused = bool(snapshot.next)
    emit(
        {
            "thread_id": thread_id,
            "backend": snapshot.values["backend"],
            "paused": paused,
            **describe_state(snapshot),
        }
    )
    return 0 if paused or snapshot.values.get("status") == "completed" else 1


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="教学用 LangGraph 审核 baseline")
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("cases", help="list teaching fixtures")
    for name in ("run", "resume", "history", "lab"):
        command = commands.add_parser(name)
        command.add_argument("--db", type=Path, default=Path(".local/checkpoints.sqlite"))
        command.add_argument(
            "--thread",
            default=None if name in ("run", "lab") else argparse.SUPPRESS,
            required=name in ("resume", "history"),
        )
        if name == "run":
            input_group = command.add_mutually_exclusive_group()
            input_group.add_argument("--case", default=None)
            input_group.add_argument("--text", help="custom submitted text (local backend only)")
            command.add_argument("--context", help="supplied context for --text")
            command.add_argument("--backend", choices=["scripted", "local"], default="scripted")
            command.add_argument("--pause-before", choices=["validate"])
        if name == "history":
            command.add_argument("--messages", action="store_true")
    return result


def run_command(args) -> int:
    catalog = Catalog()
    if args.command == "cases":
        emit(
            [
                {
                    "case_id": case.case_id,
                    "text": case.text,
                    "reference_decision": case.reference_result.decision,
                }
                for case in catalog.cases.values()
            ]
        )
        return 0
    if args.command in ("resume", "history") and not args.db.is_file():
        raise ValueError("checkpoint database does not exist")
    args.db.parent.mkdir(parents=True, exist_ok=True)
    thread_id = args.thread or f"{args.command}-{uuid4().hex[:12]}"
    config = thread_config(thread_id)
    with SqliteSaver.from_conn_string(str(args.db)) as saver:
        if args.command == "lab":
            if saver.get_tuple(config) is not None:
                raise ValueError("thread already exists; use a new --thread")
            graph = build_lab(saver)
            graph.invoke({"messages": [], "status": "new", "result": "", "model_calls": 0}, config)
            emit(
                {
                    "thread_id": thread_id,
                    "history": [
                        describe_state(snapshot, messages=True)
                        for snapshot in reversed(list(graph.get_state_history(config)))
                    ],
                }
            )
            return 0
        if args.command == "run":
            if saver.get_tuple(config) is not None:
                raise ValueError("thread already exists; use resume or a new --thread")
            if args.text is not None:
                if args.backend != "local":
                    raise ValueError(
                        "custom --text requires --backend local; scripted only replays fixtures"
                    )
                case = Case(case_id=f"input-{thread_id}", text=args.text, context=args.context)
                catalog.cases[case.case_id] = case
            else:
                if args.context is not None:
                    raise ValueError("--context is only used together with --text")
                case_id = args.case or "threat-direct"
                if case_id not in catalog.cases:
                    raise ValueError("unknown case; run `moderation-demo cases` to list case IDs")
                case = catalog.cases[case_id]
            tools = make_tools(catalog, case.case_id)
            backend = (
                ScriptedBackend(case, catalog)
                if args.backend == "scripted"
                else LocalBackend(tools)
            )
            graph = build_graph(
                catalog,
                backend,
                tools,
                saver,
                pause_before=[args.pause_before] if args.pause_before else None,
            )
            return execute(graph, initial_state(case, backend), config, thread_id)
        case, identity = load_saved_case(saver, config)
        # Resolve context from the saved case, not a potentially edited fixture on disk.
        catalog.cases[case.case_id] = case
        tools = make_tools(catalog, case.case_id)
        if args.command == "history":
            # History inspection needs no live model, network request or API credential.
            graph = build_graph(catalog, ScriptedBackend(case, catalog), tools, saver)
            emit(
                [
                    describe_state(snapshot, messages=args.messages)
                    for snapshot in reversed(list(graph.get_state_history(config)))
                ]
            )
            return 0
        backend = (
            ScriptedBackend(case, catalog)
            if identity["kind"] == "scripted"
            else LocalBackend(tools, identity)
        )
        graph = build_graph(catalog, backend, tools, saver)
        snapshot = graph.get_state(config)
        if not snapshot.next:
            raise ValueError("thread is already terminal; inspect history or start a new thread")
        return execute(graph, None, config, thread_id)


def main() -> int:
    args = parser().parse_args()
    try:
        return run_command(args)
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
