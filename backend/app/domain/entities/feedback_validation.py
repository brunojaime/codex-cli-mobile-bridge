"""Explicit, versioned acceptance plan for an existing feedback parent."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class RequiredObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-zA-Z0-9_.-]{1,100}$")
    criterion_id: str
    check_id: str
    description: str = Field(min_length=1, max_length=600)


class FeedbackValidationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    request_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    packet_id: str
    # A minimized summary prepared from the original evidence; originals never go to Jev.
    semantic_brief: str = Field(min_length=1, max_length=1500)
    observations: list[RequiredObservation] = Field(min_length=1, max_length=30)
    scope: Literal["local", "deployed"]
    target: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_plan(self):
        if len({o.id for o in self.observations}) != len(self.observations):
            raise ValueError("Observation IDs must be unique")
        if self.scope == "deployed":
            if set(self.target) != {"environment", "origin", "release_id"}:
                raise ValueError(
                    "Deployed checks need environment, origin and release_id"
                )
            from urllib.parse import urlsplit

            origin = urlsplit(self.target["origin"])
            if (
                origin.scheme != "https"
                or not origin.hostname
                or origin.username
                or origin.password
                or origin.path not in ("", "/")
                or origin.query
                or origin.fragment
            ):
                raise ValueError("Use an HTTPS origin without credentials or path")
            if (
                self.target["environment"] not in {"dev", "qa"}
                or not self.target["release_id"].strip()
            ):
                raise ValueError("Select an identified DEV/QA release")
        elif self.target:
            raise ValueError("Local checks do not claim deployment identity")
        return self
