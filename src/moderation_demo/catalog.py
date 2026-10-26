"""Small, versioned teaching fixtures and deterministic reference checks."""

import json
import re
from pathlib import Path

from moderation_demo.domain import Case, Policy, ReviewResult

DEFAULT_DATA = Path(__file__).resolve().parent / "data"


class Catalog:
    def __init__(self, data_dir: Path = DEFAULT_DATA):
        self.policies = [
            Policy.model_validate(item)
            for item in json.loads((data_dir / "policies.json").read_text(encoding="utf-8"))
        ]
        cases = [
            Case.model_validate(item)
            for item in json.loads((data_dir / "cases.json").read_text(encoding="utf-8"))
        ]
        self.cases = {case.case_id: case for case in cases}
        if len(self.cases) != len(cases):
            raise ValueError("duplicate case_id")
        identities = [(p.policy_id, p.section_id, p.version) for p in self.policies]
        if len(set(identities)) != len(identities):
            raise ValueError("duplicate policy identity")

    def get_policy(self, policy_id: str, version: str) -> list[Policy]:
        return [p for p in self.policies if p.policy_id == policy_id and p.version == version]

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        # Deliberately simple: English words / Chinese characters, no embeddings or index.
        def tokens(text: str) -> set[str]:
            return set(re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", text.lower()))

        query_tokens = tokens(query)
        matches = []
        for policy in self.policies:
            searchable = " ".join([policy.title, policy.rule, *policy.keywords])
            score = len(query_tokens & tokens(searchable))
            if score:
                matches.append(
                    {
                        "policy_id": policy.policy_id,
                        "section_id": policy.section_id,
                        "version": policy.version,
                        "title": policy.title,
                        "source": policy.source,
                        "score": score,
                    }
                )
        return sorted(matches, key=lambda m: (-m["score"], m["policy_id"]))[:top_k]

    def check_result(self, result: ReviewResult, case: Case) -> list[str]:
        """Verify existence and literal matches, NOT whether a rule supports a conclusion."""
        errors = []
        for evidence in result.input_evidence:
            if evidence.quote not in case.text:
                errors.append(f"input evidence is not in the submitted text: {evidence.quote!r}")
        for citation in result.policy_citations:
            clauses = [
                p
                for p in self.get_policy(citation.policy_id, citation.version)
                if p.section_id == citation.section_id
            ]
            if not clauses:
                errors.append(
                    f"unknown policy/section/version: {citation.policy_id}/"
                    f"{citation.section_id}@{citation.version}"
                )
                continue
            # Quotes cannot straddle a rule/exception boundary or cite synthetic summaries.
            source_segments = [clauses[0].rule, *clauses[0].exceptions]
            if not any(citation.quote in segment for segment in source_segments):
                errors.append(f"policy quote is not verbatim: {citation.quote!r}")
        return errors
