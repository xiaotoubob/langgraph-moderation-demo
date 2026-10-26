"""A reducer/state experiment, deliberately separate from the moderation agent."""

from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, AnyMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages


class LabState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    status: str
    result: str
    model_calls: int


def build_lab(checkpointer):
    def draft(state: LabState):
        return {
            "messages": [AIMessage(content="Draft: checking the case.", id="answer-1")],
            "status": "drafted",
            "result": "draft result",
        }

    def revise(state: LabState):
        # The same message ID replaces that message. result has no reducer and overwrites.
        # model_calls is omitted from both updates, so its initial value is preserved.
        return {
            "messages": [AIMessage(content="Revised: checking is complete.", id="answer-1")],
            "status": "revised",
            "result": "revised result",
        }

    graph = StateGraph(LabState)
    graph.add_node("draft", draft)
    graph.add_node("revise", revise)
    graph.add_edge(START, "draft")
    graph.add_edge("draft", "revise")
    graph.add_edge("revise", END)
    return graph.compile(checkpointer=checkpointer)
