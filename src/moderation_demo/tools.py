"""The three tool names are new designs, not recovered historical interfaces."""

from langchain_core.tools import tool

from moderation_demo.catalog import Catalog


def make_tools(catalog: Catalog, case_id: str):
    @tool
    def search_policies(query: str) -> dict:
        """Search teaching policies using keywords; returns IDs, versions and simple scores."""
        return {"ok": True, "matches": catalog.search(query)}

    @tool
    def get_policy(policy_id: str, version: str) -> dict:
        """Get complete clauses, exceptions and examples for an exact policy ID and version."""
        policies = catalog.get_policy(policy_id, version)
        if not policies:
            return {"ok": False, "error": "policy ID/version not found"}
        return {"ok": True, "clauses": [p.model_dump() for p in policies]}

    @tool
    def get_case_context(requested_case_id: str) -> dict:
        """Get supplied context for this case only. Missing context must not be invented."""
        if requested_case_id != case_id:
            return {"ok": False, "error": "only the active case is available"}
        context = catalog.cases[case_id].context
        return {"ok": True, "available": context is not None, "context": context}

    return [search_policies, get_policy, get_case_context]
