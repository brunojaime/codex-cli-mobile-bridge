"""Requirement intake before implementation, sharing the acceptance ledger."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class RequirementCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: str = Field(pattern=r"^[a-zA-Z0-9_.:-]{1,160}$")
    description: str = Field(min_length=1, max_length=600)


class RequirementDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    requirement_id: str = Field(pattern=r"^[a-zA-Z0-9_.-]{1,100}$")
    project_id: str = Field(pattern=r"^[a-zA-Z0-9_.-]{1,120}$")
    source_ref: str = Field(min_length=1, max_length=500)
    text: str = Field(min_length=1, max_length=10000)
    environment: Literal["local", "dev", "qa"] = "dev"
    criteria: list[RequirementCriterion] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def unique_criteria(self):
        if len({c.id for c in self.criteria}) != len(self.criteria):
            raise ValueError("Requirement criterion IDs must be unique")
        return self


class RequirementFromSource(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    requirement_id: str = Field(pattern=r"^[a-zA-Z0-9_.-]{1,100}$")
    project_id: str = Field(pattern=r"^[a-zA-Z0-9_.-]{1,120}$")
    environment: Literal["local", "dev", "qa"] = "dev"
    criteria: list[RequirementCriterion] = Field(min_length=1, max_length=30)


class RequirementRevision(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    definition: RequirementDefinition
    reason: str = Field(min_length=1, max_length=2000)
    decision_ref: str = Field(min_length=1, max_length=500)


class ManualAcceptanceReview(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    evidence_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    outcome: Literal["confirmed", "still_failing", "inconclusive"]
    note: str = Field(min_length=1, max_length=2000)
    decision_ref: str = Field(min_length=1, max_length=500)
    # An operator-recorded attribution, never a cryptographically verified identity.
    actor_label: str = Field(min_length=1, max_length=120)
    observed_target: dict[str, str] | None = None
