from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


_MAX_AGENT_LABEL_LENGTH = 40
_MAX_AGENT_PROMPT_LENGTH = 12_000
_MAX_AGENT_MODEL_LENGTH = 120

_DEFAULT_GENERATOR_PROMPT = (
    "You are the primary implementation Codex. Continue the task directly, "
    "produce concrete progress, and keep the output practical."
)
_DEFAULT_REVIEWER_PROMPT = (
    "You are reviewing the generator Codex output. Produce the next prompt "
    "that should be sent back to the generator so the implementation improves "
    "with more code, fixes, tests, or validation. Reply only with that next prompt."
)
_DEFAULT_SUMMARY_PROMPT = (
    "You are the summary Codex. Summarize the latest generator progress and any "
    "reviewer feedback into a concise user-facing update with next steps."
)
_DEFAULT_SUPERVISOR_PROMPT = (
    "You are the Supervisor Codex. Own the project plan, decide which specialist "
    "should act next, and make sure the work is completed correctly. Keep an "
    "explicit phased plan current at every turn. Specialists report back only "
    "to you. Reply with strict JSON using this schema only: "
    '{"status":"continue"|"complete","plan":["step 1","step 2"],'
    '"next_agent_id":"qa"|"ux"|"senior_engineer"|"scraper"|null,'
    '"instruction":"what the next agent should do","user_response":"brief update for the user",'
    '"request_summary":true|false}. '
    "Use status=complete only when the project is done or no further specialist "
    "work is needed."
)
_DEFAULT_QA_PROMPT = (
    "You are the QA Codex working for the supervisor. Focus on validation, test "
    "coverage, regressions, edge cases, and release risk. Reply to the supervisor "
    "with concrete findings, test recommendations, and blockers."
)
_DEFAULT_UX_PROMPT = (
    "You are the UX Codex working for the supervisor. Focus on user flow, clarity, "
    "copy, accessibility, interaction quality, layout consistency, and product "
    "usability. Reply to the supervisor with concrete UX feedback and recommendations."
)
_DEFAULT_SENIOR_ENGINEERING_PROMPT = (
    "You are the Senior Engineering Codex working for the supervisor. Focus on "
    "architecture, correctness, implementation strategy, maintainability, and "
    "delivery risk. Reply to the supervisor with concrete technical guidance, "
    "implementation notes, and critical tradeoffs."
)
_DEFAULT_SCRAPER_PROMPT = (
    "You are the Scraper Codex working for the supervisor. Focus on public web "
    "extraction, scraper strategy, parser robustness, structured data capture, "
    "and source constraints. Prefer direct HTTP or JSON endpoints before browser "
    "automation. Reply to the supervisor with concrete extraction findings, "
    "implementation notes, and scraping risks."
)
_AGENT_ENUM_VALUE_ALIASES = {
    "scrapper": "scraper",
}


class AgentId(StrEnum):
    USER = "user"
    GENERATOR = "generator"
    REVIEWER = "reviewer"
    SUMMARY = "summary"
    SUPERVISOR = "supervisor"
    QA = "qa"
    UX = "ux"
    SENIOR_ENGINEER = "senior_engineer"
    SCRAPER = "scraper"


class AgentType(StrEnum):
    HUMAN = "human"
    GENERATOR = "generator"
    REVIEWER = "reviewer"
    SUMMARY = "summary"
    SUPERVISOR = "supervisor"
    QA = "qa"
    UX = "ux"
    SENIOR_ENGINEER = "senior_engineer"
    SCRAPER = "scraper"


class AgentVisibilityMode(StrEnum):
    VISIBLE = "visible"
    COLLAPSED = "collapsed"
    HIDDEN = "hidden"


class AgentDisplayMode(StrEnum):
    SHOW_ALL = "show_all"
    COLLAPSE_SPECIALISTS = "collapse_specialists"
    SUMMARY_ONLY = "summary_only"


class AgentTriggerSource(StrEnum):
    USER = "user"
    GENERATOR = "generator"
    REVIEWER = "reviewer"
    SUMMARY = "summary"
    SUPERVISOR = "supervisor"
    QA = "qa"
    UX = "ux"
    SENIOR_ENGINEER = "senior_engineer"
    SCRAPER = "scraper"
    SYSTEM = "system"


class AgentPreset(StrEnum):
    SOLO = "solo"
    REVIEW = "review"
    TRIAD = "triad"
    SUPERVISOR = "supervisor"


class SummaryStrategyMode(StrEnum):
    DETERMINISTIC = "deterministic"
    SUPERVISOR_WINDOW = "supervisor_window"


class TurnBudgetMode(StrEnum):
    EACH_AGENT = "each_agent"
    SUPERVISOR_ONLY = "supervisor_only"


LEGACY_AGENT_IDS = (
    AgentId.GENERATOR,
    AgentId.REVIEWER,
    AgentId.SUMMARY,
)
SUPERVISOR_MEMBER_AGENT_IDS = (
    AgentId.QA,
    AgentId.UX,
    AgentId.SENIOR_ENGINEER,
    AgentId.SCRAPER,
)
SUPERVISOR_AGENT_IDS = (
    AgentId.SUPERVISOR,
    *SUPERVISOR_MEMBER_AGENT_IDS,
)
CONFIGURABLE_AGENT_IDS = (
    *LEGACY_AGENT_IDS,
    *SUPERVISOR_AGENT_IDS,
)
_CONFIGURABLE_AGENT_ID_VALUES = {agent_id.value for agent_id in CONFIGURABLE_AGENT_IDS}
_SUPERVISOR_MEMBER_ID_VALUES = {agent_id.value for agent_id in SUPERVISOR_MEMBER_AGENT_IDS}

_DEFAULT_LABELS = {
    AgentId.GENERATOR: "Generator",
    AgentId.REVIEWER: "Reviewer",
    AgentId.SUMMARY: "Summary",
    AgentId.SUPERVISOR: "Supervisor",
    AgentId.QA: "QA",
    AgentId.UX: "UX",
    AgentId.SENIOR_ENGINEER: "Senior Engineer",
    AgentId.SCRAPER: "Scraper",
}
_DEFAULT_PROMPTS = {
    AgentId.GENERATOR: _DEFAULT_GENERATOR_PROMPT,
    AgentId.REVIEWER: _DEFAULT_REVIEWER_PROMPT,
    AgentId.SUMMARY: _DEFAULT_SUMMARY_PROMPT,
    AgentId.SUPERVISOR: _DEFAULT_SUPERVISOR_PROMPT,
    AgentId.QA: _DEFAULT_QA_PROMPT,
    AgentId.UX: _DEFAULT_UX_PROMPT,
    AgentId.SENIOR_ENGINEER: _DEFAULT_SENIOR_ENGINEERING_PROMPT,
    AgentId.SCRAPER: _DEFAULT_SCRAPER_PROMPT,
}
_DEFAULT_TYPES = {
    AgentId.GENERATOR: AgentType.GENERATOR,
    AgentId.REVIEWER: AgentType.REVIEWER,
    AgentId.SUMMARY: AgentType.SUMMARY,
    AgentId.SUPERVISOR: AgentType.SUPERVISOR,
    AgentId.QA: AgentType.QA,
    AgentId.UX: AgentType.UX,
    AgentId.SENIOR_ENGINEER: AgentType.SENIOR_ENGINEER,
    AgentId.SCRAPER: AgentType.SCRAPER,
}
_DEFAULT_VISIBILITY = {
    AgentId.GENERATOR: AgentVisibilityMode.VISIBLE,
    AgentId.REVIEWER: AgentVisibilityMode.COLLAPSED,
    AgentId.SUMMARY: AgentVisibilityMode.VISIBLE,
    AgentId.SUPERVISOR: AgentVisibilityMode.VISIBLE,
    AgentId.QA: AgentVisibilityMode.COLLAPSED,
    AgentId.UX: AgentVisibilityMode.COLLAPSED,
    AgentId.SENIOR_ENGINEER: AgentVisibilityMode.COLLAPSED,
    AgentId.SCRAPER: AgentVisibilityMode.COLLAPSED,
}
_DEFAULT_MAX_TURNS = {
    AgentId.GENERATOR: 2,
    AgentId.REVIEWER: 1,
    AgentId.SUMMARY: 1,
    AgentId.SUPERVISOR: 10,
    AgentId.QA: 8,
    AgentId.UX: 8,
    AgentId.SENIOR_ENGINEER: 8,
    AgentId.SCRAPER: 8,
}
_DEFAULT_TRIGGER_INTERVALS = {
    AgentId.GENERATOR: 0,
    AgentId.REVIEWER: 0,
    AgentId.SUMMARY: 0,
    AgentId.SUPERVISOR: 0,
    AgentId.QA: 0,
    AgentId.UX: 0,
    AgentId.SENIOR_ENGINEER: 0,
    AgentId.SCRAPER: 0,
}
_DEFAULT_DETERMINISTIC_SUMMARY_INTERVAL = 4
_DEFAULT_SUPERVISOR_SUMMARY_WINDOW_START = 3
_DEFAULT_SUPERVISOR_SUMMARY_WINDOW_END = 6


def _default_label(agent_id: AgentId) -> str:
    return _DEFAULT_LABELS[agent_id]


def _default_prompt(agent_id: AgentId) -> str:
    return _DEFAULT_PROMPTS[agent_id]


def _default_type(agent_id: AgentId) -> AgentType:
    return _DEFAULT_TYPES[agent_id]


def _default_visibility(agent_id: AgentId) -> AgentVisibilityMode:
    return _DEFAULT_VISIBILITY[agent_id]


def _default_max_turns(agent_id: AgentId) -> int:
    return _DEFAULT_MAX_TURNS[agent_id]


def _default_trigger_interval(agent_id: AgentId) -> int:
    return _DEFAULT_TRIGGER_INTERVALS[agent_id]


def _read_str_field(
    payload: dict[str, object],
    field_name: str,
    default: str,
) -> str:
    value = payload.get(field_name, default)
    if not isinstance(value, str):
        raise ValueError(f"Agent config field {field_name} must be a string.")
    return value


def _read_bool_field(
    payload: dict[str, object],
    field_name: str,
    default: bool,
) -> bool:
    value = payload.get(field_name, default)
    if not isinstance(value, bool):
        raise ValueError(f"Agent config field {field_name} must be a boolean.")
    return value


def _read_int_field(
    payload: dict[str, object],
    field_name: str,
    default: int,
) -> int:
    value = payload.get(field_name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Agent config field {field_name} must be an integer.")
    return value


def _read_optional_str_field(
    payload: dict[str, object],
    field_name: str,
    default: str | None,
) -> str | None:
    if field_name not in payload:
        return default
    value = payload[field_name]
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Agent config field {field_name} must be a string or null.")
    return value


def _read_supervisor_members(raw: object | None) -> tuple[AgentId, ...]:
    if raw is None:
        return tuple(SUPERVISOR_MEMBER_AGENT_IDS)
    if not isinstance(raw, list):
        raise ValueError("Supervisor member ids must be a list.")

    resolved: list[AgentId] = []
    seen: set[AgentId] = set()
    for item in raw:
        if not isinstance(item, str):
            raise ValueError("Supervisor member ids must be strings.")
        try:
            agent_id = AgentId(normalize_agent_enum_value(item))
        except ValueError as exc:
            raise ValueError("Supervisor member ids contain an unknown agent.") from exc
        if agent_id not in SUPERVISOR_MEMBER_AGENT_IDS:
            raise ValueError("Supervisor member ids must reference specialist agents only.")
        if agent_id in seen:
            continue
        seen.add(agent_id)
        resolved.append(agent_id)
    return tuple(resolved)


def normalize_agent_enum_value(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        return normalized
    return _AGENT_ENUM_VALUE_ALIASES.get(normalized.lower(), normalized)


def _preset_enabled(preset: AgentPreset, agent_id: AgentId) -> bool:
    if preset == AgentPreset.SOLO:
        return agent_id == AgentId.GENERATOR
    if preset == AgentPreset.REVIEW:
        return agent_id in {AgentId.GENERATOR, AgentId.REVIEWER}
    if preset == AgentPreset.TRIAD:
        return agent_id in LEGACY_AGENT_IDS
    return agent_id in {AgentId.SUPERVISOR, *SUPERVISOR_MEMBER_AGENT_IDS}


@dataclass(slots=True)
class AgentDefinition:
    agent_id: AgentId
    agent_type: AgentType
    enabled: bool
    label: str
    prompt: str
    visibility: AgentVisibilityMode
    max_turns: int
    trigger_interval: int = 0
    provider_session_id: str | None = None
    model: str | None = None

    def normalized(self) -> "AgentDefinition":
        label = " ".join(self.label.split()).strip()
        if not label:
            raise ValueError(f"Agent {self.agent_id.value} must have a non-empty label.")
        if len(label) > _MAX_AGENT_LABEL_LENGTH:
            raise ValueError(
                f"Agent {self.agent_id.value} label exceeds {_MAX_AGENT_LABEL_LENGTH} characters."
            )

        prompt = self.prompt.strip()
        if self.enabled and not prompt:
            raise ValueError(f"Enabled agent {self.agent_id.value} must have a non-empty prompt.")
        if len(prompt) > _MAX_AGENT_PROMPT_LENGTH:
            raise ValueError(
                f"Agent {self.agent_id.value} prompt exceeds {_MAX_AGENT_PROMPT_LENGTH} characters."
            )
        model = (self.model or "").strip() or None
        if model is not None and len(model) > _MAX_AGENT_MODEL_LENGTH:
            raise ValueError(
                f"Agent {self.agent_id.value} model exceeds {_MAX_AGENT_MODEL_LENGTH} characters."
            )

        if self.max_turns < 0:
            raise ValueError(f"Agent {self.agent_id.value} max_turns must be non-negative.")
        if self.trigger_interval < 0:
            raise ValueError(
                f"Agent {self.agent_id.value} trigger_interval must be non-negative."
            )

        expected_type = _default_type(self.agent_id)
        if self.agent_type != expected_type:
            raise ValueError(
                f"Agent {self.agent_id.value} must use type {expected_type.value}, "
                f"not {self.agent_type.value}."
            )

        return AgentDefinition(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            enabled=self.enabled,
            label=label,
            prompt=prompt,
            visibility=self.visibility,
            max_turns=self.max_turns,
            trigger_interval=(
                self.trigger_interval if self.agent_id == AgentId.SUMMARY else 0
            ),
            provider_session_id=(self.provider_session_id or "").strip() or None,
            model=model,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "agent_id": self.agent_id.value,
            "agent_type": self.agent_type.value,
            "enabled": self.enabled,
            "label": self.label,
            "prompt": self.prompt,
            "visibility": self.visibility.value,
            "max_turns": self.max_turns,
            "trigger_interval": self.trigger_interval,
            "provider_session_id": self.provider_session_id,
            "model": self.model,
        }


@dataclass(slots=True)
class SummaryStrategy:
    mode: SummaryStrategyMode = SummaryStrategyMode.DETERMINISTIC
    deterministic_interval: int = _DEFAULT_DETERMINISTIC_SUMMARY_INTERVAL
    supervisor_window_start: int = _DEFAULT_SUPERVISOR_SUMMARY_WINDOW_START
    supervisor_window_end: int = _DEFAULT_SUPERVISOR_SUMMARY_WINDOW_END

    def normalized(self, *, preset: AgentPreset) -> "SummaryStrategy":
        mode = (
            SummaryStrategyMode.SUPERVISOR_WINDOW
            if preset == AgentPreset.SUPERVISOR
            else SummaryStrategyMode.DETERMINISTIC
        )
        deterministic_interval = max(1, self.deterministic_interval)
        supervisor_window_start = max(1, self.supervisor_window_start)
        supervisor_window_end = max(supervisor_window_start, self.supervisor_window_end)
        return SummaryStrategy(
            mode=mode,
            deterministic_interval=deterministic_interval,
            supervisor_window_start=supervisor_window_start,
            supervisor_window_end=supervisor_window_end,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode.value,
            "deterministic_interval": self.deterministic_interval,
            "supervisor_window_start": self.supervisor_window_start,
            "supervisor_window_end": self.supervisor_window_end,
        }


def default_agent_definition(
    agent_id: AgentId,
    *,
    preset: AgentPreset = AgentPreset.SOLO,
) -> AgentDefinition:
    return AgentDefinition(
        agent_id=agent_id,
        agent_type=_default_type(agent_id),
        enabled=_preset_enabled(preset, agent_id),
        label=_default_label(agent_id),
        prompt=_default_prompt(agent_id),
        visibility=_default_visibility(agent_id),
        max_turns=_default_max_turns(agent_id),
        trigger_interval=_default_trigger_interval(agent_id),
    )


@dataclass(slots=True)
class AgentConfiguration:
    preset: AgentPreset = AgentPreset.SOLO
    display_mode: AgentDisplayMode = AgentDisplayMode.SHOW_ALL
    turn_budget_mode: TurnBudgetMode = TurnBudgetMode.EACH_AGENT
    agents: dict[AgentId, AgentDefinition] = field(default_factory=dict)
    supervisor_member_ids: tuple[AgentId, ...] = field(default_factory=tuple)
    summary_strategy: SummaryStrategy = field(default_factory=SummaryStrategy)

    def normalized(self) -> "AgentConfiguration":
        normalized_agents: dict[AgentId, AgentDefinition] = {}
        for agent_id in CONFIGURABLE_AGENT_IDS:
            candidate = self.agents.get(agent_id) or default_agent_definition(
                agent_id,
                preset=self.preset,
            )
            normalized_agents[agent_id] = candidate.normalized()
        summary_strategy = self.summary_strategy.normalized(preset=self.preset)
        summary_trigger_interval = (
            summary_strategy.deterministic_interval
            if summary_strategy.mode == SummaryStrategyMode.DETERMINISTIC
            else 0
        )

        supervisor_member_ids = tuple(
            agent_id
            for agent_id in self.supervisor_member_ids
            if agent_id in SUPERVISOR_MEMBER_AGENT_IDS
        )
        if not supervisor_member_ids:
            supervisor_member_ids = tuple(SUPERVISOR_MEMBER_AGENT_IDS)

        if self.preset == AgentPreset.SUPERVISOR:
            for agent_id in (AgentId.GENERATOR, AgentId.REVIEWER):
                normalized_agents[agent_id] = AgentDefinition(
                    agent_id=agent_id,
                    agent_type=_default_type(agent_id),
                    enabled=False,
                    label=normalized_agents[agent_id].label,
                    prompt=normalized_agents[agent_id].prompt,
                    visibility=normalized_agents[agent_id].visibility,
                    max_turns=0,
                    trigger_interval=0,
                    provider_session_id=normalized_agents[agent_id].provider_session_id,
                    model=normalized_agents[agent_id].model,
                ).normalized()

            summary = normalized_agents[AgentId.SUMMARY]
            normalized_agents[AgentId.SUMMARY] = AgentDefinition(
                agent_id=AgentId.SUMMARY,
                agent_type=AgentType.SUMMARY,
                enabled=summary.enabled,
                label=summary.label,
                prompt=summary.prompt or _DEFAULT_SUMMARY_PROMPT,
                visibility=summary.visibility,
                max_turns=max(1, summary.max_turns) if summary.enabled else 0,
                trigger_interval=summary_trigger_interval if summary.enabled else 0,
                provider_session_id=summary.provider_session_id,
                model=summary.model,
            ).normalized()

            supervisor = normalized_agents[AgentId.SUPERVISOR]
            normalized_agents[AgentId.SUPERVISOR] = AgentDefinition(
                agent_id=AgentId.SUPERVISOR,
                agent_type=AgentType.SUPERVISOR,
                enabled=True,
                label=supervisor.label,
                prompt=supervisor.prompt or _DEFAULT_SUPERVISOR_PROMPT,
                visibility=supervisor.visibility,
                max_turns=max(1, supervisor.max_turns),
                trigger_interval=0,
                provider_session_id=supervisor.provider_session_id,
                model=supervisor.model,
            ).normalized()

            for agent_id in SUPERVISOR_MEMBER_AGENT_IDS:
                specialist = normalized_agents[agent_id]
                selected = agent_id in supervisor_member_ids
                normalized_agents[agent_id] = AgentDefinition(
                    agent_id=agent_id,
                    agent_type=_default_type(agent_id),
                    enabled=selected,
                    label=specialist.label,
                    prompt=specialist.prompt or _default_prompt(agent_id),
                    visibility=specialist.visibility,
                    max_turns=max(1, specialist.max_turns) if selected else 0,
                    trigger_interval=0,
                    provider_session_id=specialist.provider_session_id,
                    model=specialist.model,
                ).normalized()

            return AgentConfiguration(
                preset=AgentPreset.SUPERVISOR,
                display_mode=self.display_mode,
                turn_budget_mode=self.turn_budget_mode,
                agents=normalized_agents,
                supervisor_member_ids=supervisor_member_ids,
                summary_strategy=summary_strategy,
            )

        normalized_agents[AgentId.GENERATOR] = AgentDefinition(
            agent_id=AgentId.GENERATOR,
            agent_type=AgentType.GENERATOR,
            enabled=True,
            label=normalized_agents[AgentId.GENERATOR].label,
            prompt=normalized_agents[AgentId.GENERATOR].prompt or _DEFAULT_GENERATOR_PROMPT,
            visibility=AgentVisibilityMode.VISIBLE,
            max_turns=max(1, normalized_agents[AgentId.GENERATOR].max_turns),
            trigger_interval=0,
            provider_session_id=normalized_agents[AgentId.GENERATOR].provider_session_id,
            model=normalized_agents[AgentId.GENERATOR].model,
        ).normalized()

        if self.display_mode == AgentDisplayMode.SUMMARY_ONLY:
            normalized_agents[AgentId.SUMMARY] = AgentDefinition(
                agent_id=AgentId.SUMMARY,
                agent_type=AgentType.SUMMARY,
                enabled=True,
                label=normalized_agents[AgentId.SUMMARY].label,
                prompt=normalized_agents[AgentId.SUMMARY].prompt or _DEFAULT_SUMMARY_PROMPT,
                visibility=normalized_agents[AgentId.SUMMARY].visibility,
                max_turns=max(1, normalized_agents[AgentId.SUMMARY].max_turns),
                trigger_interval=summary_trigger_interval,
                provider_session_id=normalized_agents[AgentId.SUMMARY].provider_session_id,
                model=normalized_agents[AgentId.SUMMARY].model,
            ).normalized()

        for agent_id in SUPERVISOR_AGENT_IDS:
            specialist = normalized_agents[agent_id]
            normalized_agents[agent_id] = AgentDefinition(
                agent_id=agent_id,
                agent_type=_default_type(agent_id),
                enabled=False,
                label=specialist.label,
                prompt=specialist.prompt or _default_prompt(agent_id),
                visibility=specialist.visibility,
                max_turns=0,
                trigger_interval=0,
                provider_session_id=specialist.provider_session_id,
                model=specialist.model,
            ).normalized()

        if not any(agent.enabled for agent in normalized_agents.values() if agent.agent_id != AgentId.GENERATOR):
            preset = AgentPreset.SOLO
        elif normalized_agents[AgentId.SUMMARY].enabled:
            preset = AgentPreset.TRIAD
        else:
            preset = AgentPreset.REVIEW

        return AgentConfiguration(
            preset=preset,
            display_mode=self.display_mode,
            turn_budget_mode=self.turn_budget_mode,
            agents=normalized_agents,
            supervisor_member_ids=supervisor_member_ids,
            summary_strategy=summary_strategy,
        )

    def to_dict(self) -> dict[str, object]:
        normalized = self.normalized()
        return {
            "preset": normalized.preset.value,
            "display_mode": normalized.display_mode.value,
            "turn_budget_mode": normalized.turn_budget_mode.value,
            "supervisor_member_ids": [
                agent_id.value for agent_id in normalized.supervisor_member_ids
            ],
            "summary_strategy": normalized.summary_strategy.to_dict(),
            "agents": {
                agent_id.value: definition.to_dict()
                for agent_id, definition in normalized.agents.items()
            },
        }

    @classmethod
    def default(cls) -> "AgentConfiguration":
        return cls(
            preset=AgentPreset.SOLO,
            display_mode=AgentDisplayMode.SHOW_ALL,
            turn_budget_mode=TurnBudgetMode.EACH_AGENT,
            agents={
                agent_id: default_agent_definition(agent_id, preset=AgentPreset.SOLO)
                for agent_id in CONFIGURABLE_AGENT_IDS
            },
            supervisor_member_ids=tuple(SUPERVISOR_MEMBER_AGENT_IDS),
            summary_strategy=SummaryStrategy().normalized(preset=AgentPreset.SOLO),
        ).normalized()

    @classmethod
    def from_legacy_auto_mode(
        cls,
        *,
        enabled: bool,
        max_turns: int,
        reviewer_prompt: str | None,
        reviewer_provider_session_id: str | None,
        generator_provider_session_id: str | None,
    ) -> "AgentConfiguration":
        configuration = cls.default()
        configuration.preset = AgentPreset.REVIEW if enabled else AgentPreset.SOLO
        configuration.turn_budget_mode = TurnBudgetMode.EACH_AGENT
        configuration.agents[AgentId.GENERATOR].provider_session_id = generator_provider_session_id
        configuration.agents[AgentId.REVIEWER].enabled = enabled
        configuration.agents[AgentId.REVIEWER].max_turns = max(0, max_turns)
        configuration.agents[AgentId.REVIEWER].prompt = (
            reviewer_prompt.strip() if reviewer_prompt and reviewer_prompt.strip() else _DEFAULT_REVIEWER_PROMPT
        )
        configuration.agents[AgentId.REVIEWER].provider_session_id = reviewer_provider_session_id
        configuration.agents[AgentId.SUMMARY].enabled = False
        configuration.agents[AgentId.SUMMARY].max_turns = 0
        return configuration.normalized()

    @classmethod
    def from_dict(cls, raw: dict[str, object] | None) -> "AgentConfiguration":
        if not raw:
            return cls.default()

        try:
            preset = AgentPreset(str(raw.get("preset") or AgentPreset.SOLO.value))
        except ValueError as exc:
            raise ValueError("Invalid agent preset.") from exc
        try:
            display_mode = AgentDisplayMode(
                str(raw.get("display_mode") or AgentDisplayMode.SHOW_ALL.value)
            )
        except ValueError as exc:
            raise ValueError("Invalid agent display mode.") from exc
        try:
            turn_budget_mode = TurnBudgetMode(
                str(raw.get("turn_budget_mode") or TurnBudgetMode.EACH_AGENT.value)
            )
        except ValueError as exc:
            raise ValueError("Invalid turn budget mode.") from exc

        raw_agents = raw.get("agents")
        if raw_agents is not None and not isinstance(raw_agents, dict):
            raise ValueError("Agent configuration must provide an object for agents.")
        if isinstance(raw_agents, dict):
            unknown_agent_ids = set(raw_agents) - _CONFIGURABLE_AGENT_ID_VALUES
            if unknown_agent_ids:
                raise ValueError("Agent configuration contains unknown agent ids.")

        supervisor_member_ids = _read_supervisor_members(raw.get("supervisor_member_ids"))
        raw_summary_strategy = raw.get("summary_strategy")
        if raw_summary_strategy is None:
            trigger_interval_fallback = _DEFAULT_DETERMINISTIC_SUMMARY_INTERVAL
            if isinstance(raw_agents, dict):
                summary_raw = raw_agents.get(AgentId.SUMMARY.value)
                if isinstance(summary_raw, dict):
                    trigger_interval_fallback = _read_int_field(
                        summary_raw,
                        "trigger_interval",
                        _DEFAULT_DETERMINISTIC_SUMMARY_INTERVAL,
                    )
            summary_strategy = SummaryStrategy(
                mode=(
                    SummaryStrategyMode.SUPERVISOR_WINDOW
                    if preset == AgentPreset.SUPERVISOR
                    else SummaryStrategyMode.DETERMINISTIC
                ),
                deterministic_interval=max(1, trigger_interval_fallback),
                supervisor_window_start=_DEFAULT_SUPERVISOR_SUMMARY_WINDOW_START,
                supervisor_window_end=_DEFAULT_SUPERVISOR_SUMMARY_WINDOW_END,
            )
        else:
            if not isinstance(raw_summary_strategy, dict):
                raise ValueError("Summary strategy must be an object.")
            try:
                raw_mode = raw_summary_strategy.get("mode")
                mode = SummaryStrategyMode(
                    str(
                        raw_mode
                        or (
                            SummaryStrategyMode.SUPERVISOR_WINDOW.value
                            if preset == AgentPreset.SUPERVISOR
                            else SummaryStrategyMode.DETERMINISTIC.value
                        )
                    )
                )
            except ValueError as exc:
                raise ValueError("Summary strategy contains an invalid mode.") from exc
            summary_strategy = SummaryStrategy(
                mode=mode,
                deterministic_interval=_read_int_field(
                    raw_summary_strategy,
                    "deterministic_interval",
                    _DEFAULT_DETERMINISTIC_SUMMARY_INTERVAL,
                ),
                supervisor_window_start=_read_int_field(
                    raw_summary_strategy,
                    "supervisor_window_start",
                    _DEFAULT_SUPERVISOR_SUMMARY_WINDOW_START,
                ),
                supervisor_window_end=_read_int_field(
                    raw_summary_strategy,
                    "supervisor_window_end",
                    _DEFAULT_SUPERVISOR_SUMMARY_WINDOW_END,
                ),
            )

        agents: dict[AgentId, AgentDefinition] = {}
        for agent_id in CONFIGURABLE_AGENT_IDS:
            default = default_agent_definition(agent_id, preset=preset)
            candidate_raw = raw_agents.get(agent_id.value) if isinstance(raw_agents, dict) else None
            if candidate_raw is None:
                agents[agent_id] = default
                continue
            if not isinstance(candidate_raw, dict):
                raise ValueError(f"Agent {agent_id.value} config must be an object.")
            try:
                candidate_id = AgentId(
                    normalize_agent_enum_value(
                        str(candidate_raw.get("agent_id") or agent_id.value)
                    )
                )
                candidate_type = AgentType(
                    normalize_agent_enum_value(
                        str(candidate_raw.get("agent_type") or _default_type(agent_id).value)
                    )
                )
                visibility = AgentVisibilityMode(
                    str(candidate_raw.get("visibility") or default.visibility.value)
                )
            except ValueError as exc:
                raise ValueError(f"Agent {agent_id.value} contains an invalid enum value.") from exc

            if candidate_id != agent_id:
                raise ValueError(f"Malformed config for agent {agent_id.value}.")

            agents[agent_id] = AgentDefinition(
                agent_id=candidate_id,
                agent_type=candidate_type,
                enabled=_read_bool_field(candidate_raw, "enabled", default.enabled),
                label=_read_str_field(candidate_raw, "label", default.label),
                prompt=_read_str_field(candidate_raw, "prompt", default.prompt),
                visibility=visibility,
                max_turns=_read_int_field(candidate_raw, "max_turns", default.max_turns),
                trigger_interval=_read_int_field(
                    candidate_raw,
                    "trigger_interval",
                    default.trigger_interval,
                ),
                provider_session_id=_read_optional_str_field(
                    candidate_raw,
                    "provider_session_id",
                    default.provider_session_id,
                ),
                model=_read_optional_str_field(
                    candidate_raw,
                    "model",
                    default.model,
                ),
            )

        return cls(
            preset=preset,
            display_mode=display_mode,
            turn_budget_mode=turn_budget_mode,
            agents=agents,
            supervisor_member_ids=supervisor_member_ids,
            summary_strategy=summary_strategy,
        ).normalized()


def derive_legacy_auto_mode_fields(
    configuration: AgentConfiguration,
) -> tuple[bool, int, str | None, str | None]:
    normalized = configuration.normalized()
    reviewer = normalized.agents[AgentId.REVIEWER]
    return (
        reviewer.enabled,
        reviewer.max_turns,
        reviewer.prompt or None,
        reviewer.provider_session_id,
    )
