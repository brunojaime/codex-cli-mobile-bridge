from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import re

from backend.app.domain.entities.agent_configuration import (
    AgentConfiguration,
    AgentId,
    AgentPreset,
    SUPERVISOR_MEMBER_AGENT_IDS,
    TurnBudgetMode,
)
from backend.app.domain.entities.job import utc_now


_MAX_AGENT_PROFILE_NAME_LENGTH = 40
_MAX_AGENT_PROFILE_DESCRIPTION_LENGTH = 240
_MAX_AGENT_PROFILE_PROMPT_LENGTH = 12_000
_HEX_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")

DEFAULT_AGENT_PROFILE_ID = "default"
AGENT_CREATOR_PROFILE_ID = "agent_creator"
SUPERVISOR_AGENT_PROFILE_ID = "supervisor"
QA_AGENT_PROFILE_ID = "qa"
UX_AGENT_PROFILE_ID = "ux"
SENIOR_ENGINEER_AGENT_PROFILE_ID = "senior_engineer"
SCRAPER_AGENT_PROFILE_ID = "scraper"
PROVIDER_AGENT_PROFILE_ID = "provider"
ADMIN_AGENT_PROFILE_ID = "admin"
DEFAULT_AGENT_PROFILE_COLOR = "#55D6BE"
AGENT_CREATOR_PROFILE_COLOR = "#F28C28"
SUPERVISOR_AGENT_PROFILE_COLOR = "#43C6DB"
QA_AGENT_PROFILE_COLOR = "#FFB347"
UX_AGENT_PROFILE_COLOR = "#6FD6A8"
SENIOR_ENGINEER_AGENT_PROFILE_COLOR = "#A78BFA"
SCRAPER_AGENT_PROFILE_COLOR = "#0F766E"
PROVIDER_AGENT_PROFILE_COLOR = "#1D4ED8"
ADMIN_AGENT_PROFILE_COLOR = "#B91C1C"

DEFAULT_AGENT_CREATOR_PROMPT = (
    "You are Agent Creator Codex. Help the user design a reusable Codex agent "
    "for this app. Ask concise follow-up questions only when important "
    "requirements are missing. When the agent definition is clear, return a "
    "short human-readable summary followed by exactly one fenced code block "
    "labeled agent-profile containing a JSON object that the app can import "
    "directly as a persistent agent profile. The JSON must use this shape: "
    '{"id":"stable_snake_case_id","name":"Agent Name","description":"short '
    'description","color_hex":"#RRGGBB","prompt":"system prompt","configuration":'
    '{"preset":"solo"|"review"|"triad"|"supervisor","display_mode":"show_all"|'
    '"collapse_specialists"|"summary_only","turn_budget_mode":"each_agent"|'
    '"supervisor_only","supervisor_member_ids":["qa","ux","senior_engineer",'
    '"scraper"],"agents":[{"agent_id":"generator"|"reviewer"|"summary"|'
    '"supervisor"|"qa"|"ux"|"senior_engineer"|"scraper","agent_type":"generator"|'
    '"reviewer"|"summary"|"supervisor"|"qa"|"ux"|"senior_engineer"|"scraper",'
    '"enabled":true,"label":"Label","prompt":"Prompt","visibility":"visible"|'
    '"collapsed"|"hidden","max_turns":1}]}}. '
    "Always use scraper, never scrapper. Include configuration only when the "
    "agent needs non-default multi-agent behavior; otherwise omit configuration "
    "and provide a strong solo-agent prompt. Keep the agent practical, with "
    "clear boundaries, inputs, outputs, and operating rules."
)

DEFAULT_PROVIDER_PROMPT = (
    "You are Provider Codex. Act as the operational lead for a provider "
    "organization using this platform. Help with onboarding, scheduling, "
    "capacity, service delivery, billing handoff, escalations, incidents, "
    "partner coordination, and operational reporting. Be concrete and "
    "execution-focused. When information is missing, ask only for the details "
    "that materially block progress. Prefer checklists, tradeoffs, ownership, "
    "risks, and the next operational action."
)

DEFAULT_ADMIN_PROMPT = (
    "You are Admin Codex. Act as the platform administrator. Help with "
    "workspace setup, access control, policy decisions, environment "
    "configuration, release coordination, auditability, support triage, "
    "tenant-level settings, and operational governance. Be explicit about "
    "permissions, blast radius, rollback plans, and safe defaults. When "
    "recommending changes, separate what is safe now from what requires human "
    "approval."
)


@dataclass(slots=True)
class AgentProfile:
    id: str
    name: str
    description: str
    color_hex: str
    prompt: str
    configuration: AgentConfiguration | None = None
    is_builtin: bool = False
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def normalized(self) -> "AgentProfile":
        profile_id = self.id.strip()
        if not profile_id:
            raise ValueError("Agent profile id must be non-empty.")

        name = " ".join(self.name.split()).strip()
        if not name:
            raise ValueError("Agent profile name must be non-empty.")
        if len(name) > _MAX_AGENT_PROFILE_NAME_LENGTH:
            raise ValueError(
                f"Agent profile name exceeds {_MAX_AGENT_PROFILE_NAME_LENGTH} characters."
            )

        description = " ".join(self.description.split()).strip()
        if len(description) > _MAX_AGENT_PROFILE_DESCRIPTION_LENGTH:
            raise ValueError(
                "Agent profile description exceeds "
                f"{_MAX_AGENT_PROFILE_DESCRIPTION_LENGTH} characters."
            )

        prompt = self.prompt.strip()
        if not prompt:
            raise ValueError("Agent profile prompt must be non-empty.")
        if len(prompt) > _MAX_AGENT_PROFILE_PROMPT_LENGTH:
            raise ValueError(
                f"Agent profile prompt exceeds {_MAX_AGENT_PROFILE_PROMPT_LENGTH} characters."
            )

        color_hex = self.color_hex.strip().upper()
        if not _HEX_COLOR_PATTERN.fullmatch(color_hex):
            raise ValueError("Agent profile color must use the #RRGGBB format.")

        configuration = _normalized_profile_configuration(
            name=name,
            prompt=prompt,
            configuration=self.configuration,
        )
        prompt = configuration.agents[_primary_profile_agent_id(configuration)].prompt

        return AgentProfile(
            id=profile_id,
            name=name,
            description=description,
            color_hex=color_hex,
            prompt=prompt,
            configuration=configuration,
            is_builtin=self.is_builtin,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    def to_dict(self) -> dict[str, object]:
        normalized = self.normalized()
        return {
            "id": normalized.id,
            "name": normalized.name,
            "description": normalized.description,
            "color_hex": normalized.color_hex,
            "prompt": normalized.prompt,
            "configuration": normalized.configuration.to_dict()
            if normalized.configuration is not None
            else None,
            "is_builtin": normalized.is_builtin,
            "created_at": normalized.created_at.isoformat(),
            "updated_at": normalized.updated_at.isoformat(),
        }

    def resolved_configuration(self) -> AgentConfiguration:
        return self.normalized().configuration or _legacy_profile_configuration(
            name=self.name,
            prompt=self.prompt,
        )


def _legacy_profile_configuration(
    *,
    name: str,
    prompt: str,
) -> AgentConfiguration:
    configuration = AgentConfiguration.default()
    configuration.agents[AgentId.GENERATOR].label = name
    configuration.agents[AgentId.GENERATOR].prompt = prompt
    return configuration.normalized()


def _normalized_profile_configuration(
    *,
    name: str,
    prompt: str,
    configuration: AgentConfiguration | None,
) -> AgentConfiguration:
    if configuration is None:
        return _legacy_profile_configuration(
            name=name,
            prompt=prompt,
        )

    normalized = configuration.normalized()
    sanitized_agents = {
        agent_id: definition.normalized()
        for agent_id, definition in normalized.agents.items()
    }
    for definition in sanitized_agents.values():
        definition.provider_session_id = None

    return AgentConfiguration(
        preset=normalized.preset,
        display_mode=normalized.display_mode,
        turn_budget_mode=normalized.turn_budget_mode,
        agents=sanitized_agents,
        supervisor_member_ids=normalized.supervisor_member_ids,
    ).normalized()


def _primary_profile_agent_id(configuration: AgentConfiguration) -> AgentId:
    normalized = configuration.normalized()
    if normalized.preset == AgentPreset.SUPERVISOR:
        return AgentId.SUPERVISOR
    return AgentId.GENERATOR


def _standalone_specialist_configuration(
    *,
    specialist_id: AgentId,
    label: str,
) -> AgentConfiguration:
    configuration = AgentConfiguration.default()
    configuration.agents[AgentId.GENERATOR].label = label
    configuration.agents[AgentId.GENERATOR].prompt = configuration.agents[specialist_id].prompt
    return configuration.normalized()


def _supervisor_configuration() -> AgentConfiguration:
    configuration = AgentConfiguration.default()
    configuration.preset = AgentPreset.SUPERVISOR
    configuration.turn_budget_mode = TurnBudgetMode.EACH_AGENT
    configuration.supervisor_member_ids = tuple(SUPERVISOR_MEMBER_AGENT_IDS)
    return configuration.normalized()


def builtin_agent_profiles() -> list[AgentProfile]:
    default_configuration = AgentConfiguration.default()
    agent_creator_configuration = AgentConfiguration.default()
    agent_creator_configuration.agents[AgentId.GENERATOR].label = "Agent Creator"
    agent_creator_configuration.agents[AgentId.GENERATOR].prompt = DEFAULT_AGENT_CREATOR_PROMPT
    supervisor_configuration = _supervisor_configuration()
    provider_configuration = AgentConfiguration.default()
    provider_configuration.agents[AgentId.GENERATOR].label = "Provider"
    provider_configuration.agents[AgentId.GENERATOR].prompt = DEFAULT_PROVIDER_PROMPT
    admin_configuration = AgentConfiguration.default()
    admin_configuration.agents[AgentId.GENERATOR].label = "Admin"
    admin_configuration.agents[AgentId.GENERATOR].prompt = DEFAULT_ADMIN_PROMPT
    qa_configuration = _standalone_specialist_configuration(
        specialist_id=AgentId.QA,
        label="QA",
    )
    ux_configuration = _standalone_specialist_configuration(
        specialist_id=AgentId.UX,
        label="UX",
    )
    senior_engineering_configuration = _standalone_specialist_configuration(
        specialist_id=AgentId.SENIOR_ENGINEER,
        label="Senior Engineer",
    )
    scraper_configuration = _standalone_specialist_configuration(
        specialist_id=AgentId.SCRAPER,
        label="Scraper",
    )
    return [
        AgentProfile(
            id=DEFAULT_AGENT_PROFILE_ID,
            name="Generator",
            description="Default implementation agent for general coding work.",
            color_hex=DEFAULT_AGENT_PROFILE_COLOR,
            prompt=default_configuration.agents[AgentId.GENERATOR].prompt,
            configuration=default_configuration,
            is_builtin=True,
        ).normalized(),
        AgentProfile(
            id=AGENT_CREATOR_PROFILE_ID,
            name="Agent Creator",
            description=(
                "Designs reusable Codex agents, their prompts, and their operating rules."
            ),
            color_hex=AGENT_CREATOR_PROFILE_COLOR,
            prompt=DEFAULT_AGENT_CREATOR_PROMPT,
            configuration=agent_creator_configuration,
            is_builtin=True,
        ).normalized(),
        AgentProfile(
            id=SUPERVISOR_AGENT_PROFILE_ID,
            name="Supervisor",
            description=(
                "Owns the project plan, delegates to specialists, and drives the work "
                "to completion."
            ),
            color_hex=SUPERVISOR_AGENT_PROFILE_COLOR,
            prompt=supervisor_configuration.agents[AgentId.SUPERVISOR].prompt,
            configuration=supervisor_configuration,
            is_builtin=True,
        ).normalized(),
        AgentProfile(
            id=PROVIDER_AGENT_PROFILE_ID,
            name="Provider",
            description=(
                "Runs provider-side operations, delivery workflows, escalations, and "
                "service coordination."
            ),
            color_hex=PROVIDER_AGENT_PROFILE_COLOR,
            prompt=DEFAULT_PROVIDER_PROMPT,
            configuration=provider_configuration,
            is_builtin=True,
        ).normalized(),
        AgentProfile(
            id=ADMIN_AGENT_PROFILE_ID,
            name="Admin",
            description=(
                "Owns platform administration, access control, governance, and safe "
                "operational changes."
            ),
            color_hex=ADMIN_AGENT_PROFILE_COLOR,
            prompt=DEFAULT_ADMIN_PROMPT,
            configuration=admin_configuration,
            is_builtin=True,
        ).normalized(),
        AgentProfile(
            id=QA_AGENT_PROFILE_ID,
            name="QA",
            description="Validates correctness, regressions, and test coverage.",
            color_hex=QA_AGENT_PROFILE_COLOR,
            prompt=qa_configuration.agents[AgentId.GENERATOR].prompt,
            configuration=qa_configuration,
            is_builtin=True,
        ).normalized(),
        AgentProfile(
            id=UX_AGENT_PROFILE_ID,
            name="UX",
            description="Reviews usability, accessibility, copy, and product flow.",
            color_hex=UX_AGENT_PROFILE_COLOR,
            prompt=ux_configuration.agents[AgentId.GENERATOR].prompt,
            configuration=ux_configuration,
            is_builtin=True,
        ).normalized(),
        AgentProfile(
            id=SENIOR_ENGINEER_AGENT_PROFILE_ID,
            name="Senior Engineer",
            description=(
                "Reviews architecture, implementation strategy, maintainability, and "
                "delivery risk."
            ),
            color_hex=SENIOR_ENGINEER_AGENT_PROFILE_COLOR,
            prompt=senior_engineering_configuration.agents[AgentId.GENERATOR].prompt,
            configuration=senior_engineering_configuration,
            is_builtin=True,
        ).normalized(),
        AgentProfile(
            id=SCRAPER_AGENT_PROFILE_ID,
            name="Scraper",
            description=(
                "Inspects public websites, chooses extraction methods, and builds "
                "or repairs scrapers."
            ),
            color_hex=SCRAPER_AGENT_PROFILE_COLOR,
            prompt=scraper_configuration.agents[AgentId.GENERATOR].prompt,
            configuration=scraper_configuration,
            is_builtin=True,
        ).normalized(),
    ]


def builtin_agent_profiles_by_id() -> dict[str, AgentProfile]:
    return {
        profile.id: profile
        for profile in builtin_agent_profiles()
    }
