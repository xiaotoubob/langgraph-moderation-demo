"""The business contract is independent of conversation messages and graph execution."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Policy(StrictModel):
    policy_id: str
    section_id: str
    version: str
    title: str
    rule: str
    exceptions: list[str]
    examples: dict[str, list[str]]
    keywords: list[str]
    source: str


class InputEvidence(StrictModel):
    quote: str = Field(min_length=1)


class PolicyCitation(StrictModel):
    policy_id: str
    section_id: str
    version: str
    quote: str = Field(min_length=1)


class ReviewResult(StrictModel):
    decision: Literal["ALLOW", "VIOLATION", "NEEDS_REVIEW"]
    input_evidence: list[InputEvidence]
    policy_citations: list[PolicyCitation]
    rationale: str = Field(min_length=1)
    review_reason: str | None = None

    @model_validator(mode="after")
    def check_decision_requirements(self):
        if self.decision == "VIOLATION" and (not self.input_evidence or not self.policy_citations):
            raise ValueError("VIOLATION requires input evidence and policy citations")
        if self.decision == "NEEDS_REVIEW" and not self.review_reason:
            raise ValueError("NEEDS_REVIEW requires a review_reason")
        if self.decision != "NEEDS_REVIEW" and self.review_reason is not None:
            raise ValueError("review_reason is only used for NEEDS_REVIEW")
        return self


class Case(StrictModel):
    case_id: str
    text: str = Field(min_length=1)
    context: str | None
    teaching_policy_id: str | None = None
    reference_result: ReviewResult | None = None

    def model_input(self) -> dict[str, str]:
        # Human reference answers and context never leak into the model's initial input.
        # Context is intentionally available through get_case_context for this lesson.
        return {"case_id": self.case_id, "text": self.text}
