"""A clearly labelled scripted replay and an OpenAI-compatible local model adapter."""

import json
import os
from typing import Protocol
from urllib.parse import urlsplit

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from moderation_demo.catalog import Catalog
from moderation_demo.domain import Case


class Backend(Protocol):
    identity: dict[str, str]

    def invoke(self, messages: list[BaseMessage]) -> AIMessage: ...


class ScriptedBackend:
    """Replay HUMAN reference answers. This is NOT a classifier or a quality test."""

    identity = {"kind": "scripted"}

    def __init__(self, case: Case, catalog: Catalog):
        self.case = case
        self.policy = next(
            (p for p in catalog.policies if p.policy_id == case.teaching_policy_id), None
        )

    def invoke(self, messages: list[BaseMessage]) -> AIMessage:
        if self.policy is None or self.case.reference_result is None:
            raise ValueError("scripted replay requires a teaching fixture with a reference answer")
        # Count messages rather than keeping hidden mutable state: process restart works.
        count = sum(isinstance(message, AIMessage) for message in messages)
        steps = [
            ("get_case_context", {"requested_case_id": self.case.case_id}),
            ("search_policies", {"query": self.policy.title}),
            ("get_policy", {"policy_id": self.policy.policy_id, "version": self.policy.version}),
        ]
        if count < len(steps):
            name, args = steps[count]
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": name,
                        "args": args,
                        "id": f"scripted-{count + 1}",
                        "type": "tool_call",
                    }
                ],
            )
        return AIMessage(content=self.case.reference_result.model_dump_json())


class LocalBackend:
    def __init__(self, tools: list[BaseTool], identity: dict[str, str] | None = None):
        if identity is None:
            model = os.environ.get("MODERATION_MODEL", "").strip()
            if not model:
                raise ValueError("set MODERATION_MODEL to the actual model name in your server")
            base_url = os.environ.get("MODERATION_BASE_URL", "").strip()
            if not base_url:
                raise ValueError(
                    "set MODERATION_BASE_URL to your server's OpenAI-compatible /v1 URL"
                )
            identity = {
                "kind": "local",
                "model": model,
                "base_url": base_url,
            }
        url = urlsplit(identity["base_url"])
        if (
            url.scheme not in ("http", "https")
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError("base URL must be HTTP(S) without credentials, query or fragment")
        self.identity = identity
        self.client = ChatOpenAI(
            model=identity["model"],
            base_url=identity["base_url"],
            api_key=os.environ.get("MODERATION_API_KEY") or "local-not-a-secret",
            temperature=0,
            timeout=60,
            max_retries=0,
            max_tokens=2048,
        ).bind_tools(tools)

    def invoke(self, messages: list[BaseMessage]) -> AIMessage:
        return self.client.invoke(messages)


def initial_message(case: Case) -> HumanMessage:
    return HumanMessage(
        content=json.dumps(case.model_input(), ensure_ascii=False),
        id=f"case-{case.case_id}",
    )
