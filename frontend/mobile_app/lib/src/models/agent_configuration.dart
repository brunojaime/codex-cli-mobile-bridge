enum AgentId {
  user,
  generator,
  reviewer,
  summary,
  supervisor,
  qa,
  ux,
  seniorEngineer,
  scraper,
}

enum AgentType {
  human,
  generator,
  reviewer,
  summary,
  supervisor,
  qa,
  ux,
  seniorEngineer,
  scraper,
}

enum AgentTriggerSource {
  user,
  generator,
  reviewer,
  summary,
  supervisor,
  qa,
  ux,
  seniorEngineer,
  scraper,
  system,
}

enum AgentVisibilityMode { visible, collapsed, hidden }

enum AgentDisplayMode { showAll, collapseSpecialists, summaryOnly }

enum AgentPreset { solo, review, triad, supervisor }

enum SummaryStrategyMode { deterministic, supervisorWindow }

enum TurnBudgetMode { eachAgent, supervisorOnly }

const List<AgentId> kLegacyAgentIds = <AgentId>[
  AgentId.generator,
  AgentId.reviewer,
  AgentId.summary,
];

const List<AgentId> kSupervisorMemberAgentIds = <AgentId>[
  AgentId.qa,
  AgentId.ux,
  AgentId.seniorEngineer,
  AgentId.scraper,
];

const List<AgentId> kConfigurableAgentIds = <AgentId>[
  AgentId.generator,
  AgentId.reviewer,
  AgentId.summary,
  AgentId.supervisor,
  AgentId.qa,
  AgentId.ux,
  AgentId.seniorEngineer,
  AgentId.scraper,
];

bool agentEnabledForPreset(AgentId agentId, AgentPreset preset) {
  return switch (preset) {
    AgentPreset.solo => agentId == AgentId.generator,
    AgentPreset.review =>
      agentId == AgentId.generator || agentId == AgentId.reviewer,
    AgentPreset.triad => kLegacyAgentIds.contains(agentId),
    AgentPreset.supervisor => agentId == AgentId.supervisor ||
        kSupervisorMemberAgentIds.contains(agentId),
  };
}

const List<AgentDefinition> kDefaultAgentDefinitions = <AgentDefinition>[
  AgentDefinition(
    agentId: AgentId.generator,
    agentType: AgentType.generator,
    enabled: true,
    label: 'Generator',
    prompt:
        'You are the primary implementation Codex. Continue the task directly, produce concrete progress, and keep the output practical.',
    visibility: AgentVisibilityMode.visible,
    maxTurns: 2,
  ),
  AgentDefinition(
    agentId: AgentId.reviewer,
    agentType: AgentType.reviewer,
    enabled: false,
    label: 'Reviewer',
    prompt:
        'You are reviewing the generator Codex output. Produce the next prompt that should be sent back to the generator so the implementation improves with more code, fixes, tests, or validation. Reply only with that next prompt.',
    visibility: AgentVisibilityMode.collapsed,
    maxTurns: 1,
  ),
  AgentDefinition(
    agentId: AgentId.summary,
    agentType: AgentType.summary,
    enabled: false,
    label: 'Summary',
    prompt:
        'You are the summary Codex. Summarize the latest generator progress and any reviewer feedback into a concise user-facing update with next steps.',
    visibility: AgentVisibilityMode.visible,
    maxTurns: 1,
    triggerInterval: 0,
  ),
  AgentDefinition(
    agentId: AgentId.supervisor,
    agentType: AgentType.supervisor,
    enabled: false,
    label: 'Supervisor',
    prompt:
        'You are the Supervisor Codex. Own the project plan, decide which specialist should act next, and make sure the work is completed correctly. Keep an explicit phased plan current at every turn. Specialists report back only to you. Reply with strict JSON using this schema only: {"status":"continue"|"complete","plan":["step 1","step 2"],"next_agent_id":"qa"|"ux"|"senior_engineer"|"scraper"|null,"instruction":"what the next agent should do","user_response":"brief update for the user"}. Use status=complete only when the project is done or no further specialist work is needed.',
    visibility: AgentVisibilityMode.visible,
    maxTurns: 10,
  ),
  AgentDefinition(
    agentId: AgentId.qa,
    agentType: AgentType.qa,
    enabled: false,
    label: 'QA',
    prompt:
        'You are the QA Codex working for the supervisor. Focus on validation, test coverage, regressions, edge cases, and release risk. Reply to the supervisor with concrete findings, test recommendations, and blockers.',
    visibility: AgentVisibilityMode.collapsed,
    maxTurns: 8,
  ),
  AgentDefinition(
    agentId: AgentId.ux,
    agentType: AgentType.ux,
    enabled: false,
    label: 'UX',
    prompt:
        'You are the UX Codex working for the supervisor. Focus on user flow, clarity, copy, accessibility, interaction quality, layout consistency, and product usability. Reply to the supervisor with concrete UX feedback and recommendations.',
    visibility: AgentVisibilityMode.collapsed,
    maxTurns: 8,
  ),
  AgentDefinition(
    agentId: AgentId.seniorEngineer,
    agentType: AgentType.seniorEngineer,
    enabled: false,
    label: 'Senior Engineer',
    prompt:
        'You are the Senior Engineering Codex working for the supervisor. Focus on architecture, correctness, implementation strategy, maintainability, and delivery risk. Reply to the supervisor with concrete technical guidance, implementation notes, and critical tradeoffs.',
    visibility: AgentVisibilityMode.collapsed,
    maxTurns: 8,
  ),
  AgentDefinition(
    agentId: AgentId.scraper,
    agentType: AgentType.scraper,
    enabled: false,
    label: 'Scraper',
    prompt:
        'You are the Scraper Codex working for the supervisor. Focus on public web extraction, scraper strategy, parser robustness, structured data capture, and source constraints. Prefer direct HTTP or JSON endpoints before browser automation. Reply to the supervisor with concrete extraction findings, implementation notes, and scraping risks.',
    visibility: AgentVisibilityMode.collapsed,
    maxTurns: 8,
  ),
];

const AgentConfiguration kDefaultAgentConfiguration = AgentConfiguration(
  preset: AgentPreset.solo,
  displayMode: AgentDisplayMode.showAll,
  turnBudgetMode: TurnBudgetMode.eachAgent,
  summaryStrategy: SummaryStrategy(
    mode: SummaryStrategyMode.deterministic,
    deterministicInterval: 4,
    supervisorWindowStart: 3,
    supervisorWindowEnd: 6,
  ),
  agents: kDefaultAgentDefinitions,
  supervisorMemberIds: kSupervisorMemberAgentIds,
);

const Object _noAgentDefinitionModelChange = Object();

class AgentDefinition {
  const AgentDefinition({
    required this.agentId,
    required this.agentType,
    required this.enabled,
    required this.label,
    required this.prompt,
    required this.visibility,
    required this.maxTurns,
    this.triggerInterval = 0,
    this.model,
    this.providerSessionId,
  });

  final AgentId agentId;
  final AgentType agentType;
  final bool enabled;
  final String label;
  final String prompt;
  final AgentVisibilityMode visibility;
  final int maxTurns;
  final int triggerInterval;
  final String? model;
  final String? providerSessionId;

  factory AgentDefinition.fromJson(Map<String, dynamic> json) {
    final agentId = tryAgentIdFromJson(_readString(json['agent_id']));
    return AgentDefinition(
      agentId: agentId ?? AgentId.generator,
      agentType: agentTypeFromJson(
        _readString(json['agent_type']) ?? 'generator',
      ),
      enabled: _readBool(json['enabled']) ?? false,
      label: _readString(json['label']) ?? '',
      prompt: _readString(json['prompt']) ?? '',
      model: _readString(json['model']),
      visibility: agentVisibilityFromJson(
        _readString(json['visibility']) ?? 'visible',
      ),
      maxTurns: _readInt(json['max_turns']) ?? 0,
      triggerInterval: _readInt(json['trigger_interval']) ?? 0,
      providerSessionId: _readString(json['provider_session_id']),
    );
  }

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'agent_id': agentIdToJson(agentId),
      'agent_type': agentTypeToJson(agentType),
      'enabled': enabled,
      'label': label,
      'prompt': prompt,
      if (model != null) 'model': model,
      'visibility': agentVisibilityToJson(visibility),
      'max_turns': maxTurns,
      'trigger_interval': triggerInterval,
    };
  }

  AgentDefinition copyWith({
    bool? enabled,
    String? label,
    String? prompt,
    Object? model = _noAgentDefinitionModelChange,
    AgentVisibilityMode? visibility,
    int? maxTurns,
    int? triggerInterval,
    String? providerSessionId,
  }) {
    return AgentDefinition(
      agentId: agentId,
      agentType: agentType,
      enabled: enabled ?? this.enabled,
      label: label ?? this.label,
      prompt: prompt ?? this.prompt,
      model: identical(model, _noAgentDefinitionModelChange)
          ? this.model
          : model as String?,
      visibility: visibility ?? this.visibility,
      maxTurns: maxTurns ?? this.maxTurns,
      triggerInterval: triggerInterval ?? this.triggerInterval,
      providerSessionId: providerSessionId ?? this.providerSessionId,
    );
  }
}

class AgentConfiguration {
  const AgentConfiguration({
    required this.preset,
    required this.displayMode,
    required this.turnBudgetMode,
    required this.summaryStrategy,
    required this.agents,
    this.supervisorMemberIds = const <AgentId>[],
  });

  final AgentPreset preset;
  final AgentDisplayMode displayMode;
  final TurnBudgetMode turnBudgetMode;
  final SummaryStrategy summaryStrategy;
  final List<AgentDefinition> agents;
  final List<AgentId> supervisorMemberIds;

  factory AgentConfiguration.fromJson(Map<String, dynamic> json) {
    final rawAgents = json['agents'] is List<dynamic>
        ? json['agents'] as List<dynamic>
        : const <dynamic>[];
    final rawSupervisorMembers = json['supervisor_member_ids'] is List<dynamic>
        ? json['supervisor_member_ids'] as List<dynamic>
        : const <dynamic>[];
    final rawSummaryStrategy = json['summary_strategy'];
    final parsedPreset =
        agentPresetFromJson(_readString(json['preset']) ?? 'solo');
    final defaults = <AgentId, AgentDefinition>{
      for (final agent in kDefaultAgentDefinitions) agent.agentId: agent,
    };
    final parsedAgents = <AgentId, AgentDefinition>{};
    for (final item in rawAgents) {
      if (item is! Map) {
        continue;
      }
      final normalizedMap = <String, dynamic>{
        for (final entry in item.entries)
          if (entry.key is String) entry.key as String: entry.value,
      };
      final agentId =
          tryAgentIdFromJson(_readString(normalizedMap['agent_id']));
      if (agentId == null || agentId == AgentId.user) {
        continue;
      }
      final fallback = defaults[agentId]!;
      final parsedAgentType =
          tryAgentTypeFromJson(_readString(normalizedMap['agent_type']));
      final parsedVisibility = tryAgentVisibilityFromJson(
        _readString(normalizedMap['visibility']),
      );
      final agent = AgentDefinition(
        agentId: agentId,
        agentType: parsedAgentType ?? fallback.agentType,
        enabled: _readBool(normalizedMap['enabled']) ?? fallback.enabled,
        label: _readString(normalizedMap['label']) ?? fallback.label,
        prompt: _readString(normalizedMap['prompt']) ?? fallback.prompt,
        model: _readString(normalizedMap['model']) ?? fallback.model,
        visibility: parsedVisibility ?? fallback.visibility,
        maxTurns: _readInt(normalizedMap['max_turns']) ?? fallback.maxTurns,
        triggerInterval:
            _readInt(normalizedMap['trigger_interval']) ??
            fallback.triggerInterval,
        providerSessionId: _readString(normalizedMap['provider_session_id']) ??
            fallback.providerSessionId,
      );
      parsedAgents[agent.agentId] = agent;
    }
    final parsedSupervisorMembers = rawSupervisorMembers
        .map((item) => tryAgentIdFromJson(_readString(item)))
        .whereType<AgentId>()
        .where((agentId) => kSupervisorMemberAgentIds.contains(agentId))
        .toSet()
        .toList(growable: false);
    final fallbackSummaryStrategy = SummaryStrategy(
      mode: parsedPreset == AgentPreset.supervisor
          ? SummaryStrategyMode.supervisorWindow
          : SummaryStrategyMode.deterministic,
      deterministicInterval: 4,
      supervisorWindowStart: 3,
      supervisorWindowEnd: 6,
    );
    return AgentConfiguration(
      preset: parsedPreset,
      displayMode: agentDisplayModeFromJson(
          _readString(json['display_mode']) ?? 'show_all'),
      turnBudgetMode: turnBudgetModeFromJson(
        _readString(json['turn_budget_mode']) ?? 'each_agent',
      ),
      summaryStrategy: rawSummaryStrategy is Map
          ? SummaryStrategy.fromJson(<String, dynamic>{
              for (final entry in rawSummaryStrategy.entries)
                if (entry.key is String) entry.key as String: entry.value,
            })
          : fallbackSummaryStrategy,
      supervisorMemberIds: parsedSupervisorMembers.isEmpty
          ? kSupervisorMemberAgentIds
          : parsedSupervisorMembers,
      agents: kDefaultAgentDefinitions
          .map((agent) => parsedAgents[agent.agentId] ?? agent)
          .toList(),
    );
  }

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'preset': agentPresetToJson(preset),
      'display_mode': agentDisplayModeToJson(displayMode),
      'turn_budget_mode': turnBudgetModeToJson(turnBudgetMode),
      'summary_strategy': summaryStrategy.toJson(),
      'supervisor_member_ids':
          supervisorMemberIds.map(agentIdToJson).toList(growable: false),
      'agents': agents.map((agent) => agent.toJson()).toList(),
    };
  }

  AgentConfiguration copyWith({
    AgentPreset? preset,
    AgentDisplayMode? displayMode,
    TurnBudgetMode? turnBudgetMode,
    SummaryStrategy? summaryStrategy,
    List<AgentDefinition>? agents,
    List<AgentId>? supervisorMemberIds,
  }) {
    return AgentConfiguration(
      preset: preset ?? this.preset,
      displayMode: displayMode ?? this.displayMode,
      turnBudgetMode: turnBudgetMode ?? this.turnBudgetMode,
      summaryStrategy: summaryStrategy ?? this.summaryStrategy,
      agents: agents ?? this.agents,
      supervisorMemberIds: supervisorMemberIds ?? this.supervisorMemberIds,
    );
  }

  AgentDefinition? byId(AgentId agentId) {
    for (final agent in agents) {
      if (agent.agentId == agentId) {
        return agent;
      }
    }
    return null;
  }
}

class SummaryStrategy {
  const SummaryStrategy({
    required this.mode,
    required this.deterministicInterval,
    required this.supervisorWindowStart,
    required this.supervisorWindowEnd,
  });

  final SummaryStrategyMode mode;
  final int deterministicInterval;
  final int supervisorWindowStart;
  final int supervisorWindowEnd;

  factory SummaryStrategy.fromJson(Map<String, dynamic> json) {
    return SummaryStrategy(
      mode: summaryStrategyModeFromJson(
        _readString(json['mode']) ?? 'deterministic',
      ),
      deterministicInterval: _readInt(json['deterministic_interval']) ?? 4,
      supervisorWindowStart: _readInt(json['supervisor_window_start']) ?? 3,
      supervisorWindowEnd: _readInt(json['supervisor_window_end']) ?? 6,
    );
  }

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'mode': summaryStrategyModeToJson(mode),
      'deterministic_interval': deterministicInterval,
      'supervisor_window_start': supervisorWindowStart,
      'supervisor_window_end': supervisorWindowEnd,
    };
  }

  SummaryStrategy copyWith({
    SummaryStrategyMode? mode,
    int? deterministicInterval,
    int? supervisorWindowStart,
    int? supervisorWindowEnd,
  }) {
    return SummaryStrategy(
      mode: mode ?? this.mode,
      deterministicInterval: deterministicInterval ?? this.deterministicInterval,
      supervisorWindowStart: supervisorWindowStart ?? this.supervisorWindowStart,
      supervisorWindowEnd: supervisorWindowEnd ?? this.supervisorWindowEnd,
    );
  }
}

AgentId? tryAgentIdFromJson(String? value) {
  switch (value) {
    case 'user':
      return AgentId.user;
    case 'generator':
      return AgentId.generator;
    case 'reviewer':
      return AgentId.reviewer;
    case 'summary':
      return AgentId.summary;
    case 'supervisor':
      return AgentId.supervisor;
    case 'qa':
      return AgentId.qa;
    case 'ux':
      return AgentId.ux;
    case 'senior_engineer':
      return AgentId.seniorEngineer;
    case 'scraper':
    case 'scrapper':
      return AgentId.scraper;
    default:
      return null;
  }
}

AgentId agentIdFromJson(String value) {
  return tryAgentIdFromJson(value) ?? AgentId.generator;
}

String agentIdToJson(AgentId value) {
  return switch (value) {
    AgentId.user => 'user',
    AgentId.generator => 'generator',
    AgentId.reviewer => 'reviewer',
    AgentId.summary => 'summary',
    AgentId.supervisor => 'supervisor',
    AgentId.qa => 'qa',
    AgentId.ux => 'ux',
    AgentId.seniorEngineer => 'senior_engineer',
    AgentId.scraper => 'scraper',
  };
}

AgentType? tryAgentTypeFromJson(String? value) {
  switch (value) {
    case 'human':
      return AgentType.human;
    case 'generator':
      return AgentType.generator;
    case 'reviewer':
      return AgentType.reviewer;
    case 'summary':
      return AgentType.summary;
    case 'supervisor':
      return AgentType.supervisor;
    case 'qa':
      return AgentType.qa;
    case 'ux':
      return AgentType.ux;
    case 'senior_engineer':
      return AgentType.seniorEngineer;
    case 'scraper':
    case 'scrapper':
      return AgentType.scraper;
    default:
      return null;
  }
}

AgentType agentTypeFromJson(String value) {
  return tryAgentTypeFromJson(value) ?? AgentType.generator;
}

String agentTypeToJson(AgentType value) {
  return switch (value) {
    AgentType.human => 'human',
    AgentType.generator => 'generator',
    AgentType.reviewer => 'reviewer',
    AgentType.summary => 'summary',
    AgentType.supervisor => 'supervisor',
    AgentType.qa => 'qa',
    AgentType.ux => 'ux',
    AgentType.seniorEngineer => 'senior_engineer',
    AgentType.scraper => 'scraper',
  };
}

AgentTriggerSource agentTriggerSourceFromJson(String value) {
  return switch (value) {
    'generator' => AgentTriggerSource.generator,
    'reviewer' => AgentTriggerSource.reviewer,
    'summary' => AgentTriggerSource.summary,
    'supervisor' => AgentTriggerSource.supervisor,
    'qa' => AgentTriggerSource.qa,
    'ux' => AgentTriggerSource.ux,
    'senior_engineer' => AgentTriggerSource.seniorEngineer,
    'scraper' => AgentTriggerSource.scraper,
    'scrapper' => AgentTriggerSource.scraper,
    'system' => AgentTriggerSource.system,
    _ => AgentTriggerSource.user,
  };
}

String agentTriggerSourceToJson(AgentTriggerSource value) {
  return switch (value) {
    AgentTriggerSource.user => 'user',
    AgentTriggerSource.generator => 'generator',
    AgentTriggerSource.reviewer => 'reviewer',
    AgentTriggerSource.summary => 'summary',
    AgentTriggerSource.supervisor => 'supervisor',
    AgentTriggerSource.qa => 'qa',
    AgentTriggerSource.ux => 'ux',
    AgentTriggerSource.seniorEngineer => 'senior_engineer',
    AgentTriggerSource.scraper => 'scraper',
    AgentTriggerSource.system => 'system',
  };
}

AgentVisibilityMode? tryAgentVisibilityFromJson(String? value) {
  switch (value) {
    case 'visible':
      return AgentVisibilityMode.visible;
    case 'collapsed':
      return AgentVisibilityMode.collapsed;
    case 'hidden':
      return AgentVisibilityMode.hidden;
    default:
      return null;
  }
}

AgentVisibilityMode agentVisibilityFromJson(String value) {
  return tryAgentVisibilityFromJson(value) ?? AgentVisibilityMode.visible;
}

String agentVisibilityToJson(AgentVisibilityMode value) {
  return switch (value) {
    AgentVisibilityMode.visible => 'visible',
    AgentVisibilityMode.collapsed => 'collapsed',
    AgentVisibilityMode.hidden => 'hidden',
  };
}

AgentDisplayMode agentDisplayModeFromJson(String value) {
  return switch (value) {
    'collapse_specialists' => AgentDisplayMode.collapseSpecialists,
    'summary_only' => AgentDisplayMode.summaryOnly,
    _ => AgentDisplayMode.showAll,
  };
}

String agentDisplayModeToJson(AgentDisplayMode value) {
  return switch (value) {
    AgentDisplayMode.showAll => 'show_all',
    AgentDisplayMode.collapseSpecialists => 'collapse_specialists',
    AgentDisplayMode.summaryOnly => 'summary_only',
  };
}

AgentPreset agentPresetFromJson(String value) {
  return switch (value) {
    'review' => AgentPreset.review,
    'triad' => AgentPreset.triad,
    'supervisor' => AgentPreset.supervisor,
    _ => AgentPreset.solo,
  };
}

String agentPresetToJson(AgentPreset value) {
  return switch (value) {
    AgentPreset.solo => 'solo',
    AgentPreset.review => 'review',
    AgentPreset.triad => 'triad',
    AgentPreset.supervisor => 'supervisor',
  };
}

SummaryStrategyMode summaryStrategyModeFromJson(String value) {
  return switch (value) {
    'supervisor_window' => SummaryStrategyMode.supervisorWindow,
    _ => SummaryStrategyMode.deterministic,
  };
}

String summaryStrategyModeToJson(SummaryStrategyMode value) {
  return switch (value) {
    SummaryStrategyMode.deterministic => 'deterministic',
    SummaryStrategyMode.supervisorWindow => 'supervisor_window',
  };
}

TurnBudgetMode turnBudgetModeFromJson(String value) {
  return switch (value) {
    'supervisor_only' => TurnBudgetMode.supervisorOnly,
    _ => TurnBudgetMode.eachAgent,
  };
}

String turnBudgetModeToJson(TurnBudgetMode value) {
  return switch (value) {
    TurnBudgetMode.eachAgent => 'each_agent',
    TurnBudgetMode.supervisorOnly => 'supervisor_only',
  };
}

String? _readString(Object? value) {
  if (value == null) {
    return null;
  }
  if (value is String) {
    return value;
  }
  return '$value';
}

int? _readInt(Object? value) {
  if (value is int) {
    return value;
  }
  if (value is double) {
    return value.toInt();
  }
  if (value is String) {
    return int.tryParse(value.trim());
  }
  return null;
}

bool? _readBool(Object? value) {
  if (value is bool) {
    return value;
  }
  if (value is String) {
    switch (value.trim().toLowerCase()) {
      case 'true':
        return true;
      case 'false':
        return false;
      default:
        return null;
    }
  }
  return null;
}
