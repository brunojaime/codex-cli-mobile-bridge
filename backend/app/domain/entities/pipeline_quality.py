"""Versioned, provider-neutral contracts for executable delivery evidence."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CheckDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-zA-Z0-9_.-]{1,100}$")
    argv: list[str] = Field(min_length=1, max_length=40)
    cwd: str = "."
    timeout_seconds: int = Field(default=120, ge=1, le=1800)
    required: bool = True


class AcceptanceCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-zA-Z0-9_.:-]{1,160}$")
    description: str = Field(min_length=1, max_length=4000)
    check_ids: list[str] = Field(default_factory=list, max_length=40)
    decision_pending: str | None = Field(default=None, max_length=1000)
    feedback_item_id: str | None = Field(default=None, max_length=160)


class QualityContract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    project_id: str = Field(pattern=r"^[a-zA-Z0-9_.-]{1,120}$")
    environment: Literal["local", "dev", "qa"] = "dev"
    criteria: list[AcceptanceCriterion] = Field(min_length=1, max_length=100)
    checks: list[CheckDefinition] = Field(default_factory=list, max_length=60)
    dependencies: list[str] = Field(default_factory=list, max_length=60)
    component_ids: list[str] = Field(default_factory=list, max_length=60)
    max_attempts: int = Field(default=6, ge=1, le=20)

    @model_validator(mode="after")
    def references(self) -> "QualityContract":
        ids = [c.id for c in self.checks]
        if len(set(ids)) != len(ids) or len({c.id for c in self.criteria}) != len(
            self.criteria
        ):
            raise ValueError("Duplicate check or criterion ID")
        for criterion in self.criteria:
            if set(criterion.check_ids) - set(ids):
                raise ValueError("Criterion refers to an unknown check")
        for check in self.checks:
            if any(not arg or len(arg) > 2000 or "\x00" in arg for arg in check.argv):
                raise ValueError("Invalid command argument")
        return self
