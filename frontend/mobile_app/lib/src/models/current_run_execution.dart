import 'agent_configuration.dart';

enum CurrentRunStageId {
  generator,
  reviewer,
  summary,
  supervisor,
  qa,
  ux,
  seniorEngineer,
  scraper,
}

enum CurrentRunStageState {
  disabled,
  waiting,
  notScheduled,
  queued,
  running,
  completed,
  failed,
  cancelled,
  stale,
  skipped,
}

CurrentRunStageId currentRunStageIdFromJson(String? value) {
  switch (value) {
    case 'reviewer':
      return CurrentRunStageId.reviewer;
    case 'summary':
      return CurrentRunStageId.summary;
    case 'supervisor':
      return CurrentRunStageId.supervisor;
    case 'qa':
      return CurrentRunStageId.qa;
    case 'ux':
      return CurrentRunStageId.ux;
    case 'senior_engineer':
      return CurrentRunStageId.seniorEngineer;
    case 'scraper':
      return CurrentRunStageId.scraper;
    default:
      return CurrentRunStageId.generator;
  }
}

CurrentRunStageState currentRunStageStateFromJson(String? value) {
  switch (value) {
    case 'disabled':
      return CurrentRunStageState.disabled;
    case 'waiting':
      return CurrentRunStageState.waiting;
    case 'not_scheduled':
      return CurrentRunStageState.notScheduled;
    case 'queued':
      return CurrentRunStageState.queued;
    case 'running':
      return CurrentRunStageState.running;
    case 'completed':
      return CurrentRunStageState.completed;
    case 'failed':
      return CurrentRunStageState.failed;
    case 'cancelled':
      return CurrentRunStageState.cancelled;
    case 'stale':
      return CurrentRunStageState.stale;
    case 'skipped':
      return CurrentRunStageState.skipped;
    default:
      return CurrentRunStageState.waiting;
  }
}

class CurrentRunStageExecution {
  const CurrentRunStageExecution({
    required this.stage,
    required this.state,
    this.configured = false,
    this.attemptCount = 0,
    this.maxTurns = 0,
    this.hasTurnBudget = false,
    this.messageId,
    this.jobId,
    this.jobStatus,
    this.latestActivity,
    this.startedAt,
    this.updatedAt,
    this.completedAt,
  });

  final CurrentRunStageId stage;
  final CurrentRunStageState state;
  final bool configured;
  final int attemptCount;
  final int maxTurns;
  final bool hasTurnBudget;
  final String? messageId;
  final String? jobId;
  final String? jobStatus;
  final String? latestActivity;
  final DateTime? startedAt;
  final DateTime? updatedAt;
  final DateTime? completedAt;

  factory CurrentRunStageExecution.fromJson(Map<String, dynamic> json) {
    return CurrentRunStageExecution(
      stage: currentRunStageIdFromJson(json['stage'] as String?),
      state: currentRunStageStateFromJson(json['state'] as String?),
      configured: _readBool(json['configured']) ?? false,
      attemptCount: _readInt(json['attempt_count']) ?? 0,
      maxTurns: _readInt(json['max_turns']) ?? 0,
      hasTurnBudget: _readBool(json['has_turn_budget']) ?? false,
      messageId: _readString(json['message_id']),
      jobId: _readString(json['job_id']),
      jobStatus: _readString(json['job_status']),
      latestActivity: _readString(json['latest_activity']),
      startedAt: _readDateTime(json['started_at']),
      updatedAt: _readDateTime(json['updated_at']),
      completedAt: _readDateTime(json['completed_at']),
    );
  }

  CurrentRunStageExecution copyWith({
    CurrentRunStageId? stage,
    CurrentRunStageState? state,
    bool? configured,
    int? attemptCount,
    int? maxTurns,
    bool? hasTurnBudget,
    String? messageId,
    String? jobId,
    String? jobStatus,
    String? latestActivity,
    DateTime? startedAt,
    DateTime? updatedAt,
    DateTime? completedAt,
  }) {
    return CurrentRunStageExecution(
      stage: stage ?? this.stage,
      state: state ?? this.state,
      configured: configured ?? this.configured,
      attemptCount: attemptCount ?? this.attemptCount,
      maxTurns: maxTurns ?? this.maxTurns,
      hasTurnBudget: hasTurnBudget ?? this.hasTurnBudget,
      messageId: messageId ?? this.messageId,
      jobId: jobId ?? this.jobId,
      jobStatus: jobStatus ?? this.jobStatus,
      latestActivity: latestActivity ?? this.latestActivity,
      startedAt: startedAt ?? this.startedAt,
      updatedAt: updatedAt ?? this.updatedAt,
      completedAt: completedAt ?? this.completedAt,
    );
  }
}

class CurrentRunExecution {
  const CurrentRunExecution({
    required this.runId,
    required this.state,
    required this.isActive,
    this.preset = AgentPreset.solo,
    this.turnBudgetMode,
    required this.stages,
    this.startedAt,
    this.updatedAt,
    this.completedAt,
    this.participantAgentIds = const <AgentId>[],
    this.callCount = 0,
  });

  final String runId;
  final CurrentRunStageState state;
  final bool isActive;
  final AgentPreset preset;
  final TurnBudgetMode? turnBudgetMode;
  final DateTime? startedAt;
  final DateTime? updatedAt;
  final DateTime? completedAt;
  final List<AgentId> participantAgentIds;
  final int callCount;
  final List<CurrentRunStageExecution> stages;

  factory CurrentRunExecution.fromJson(Map<String, dynamic> json) {
    final rawStages = json['stages'] as List<dynamic>? ?? const <dynamic>[];
    return CurrentRunExecution(
      runId: _readString(json['run_id']) ?? '',
      state: currentRunStageStateFromJson(json['state'] as String?),
      isActive: _readBool(json['is_active']) ?? false,
      preset: agentPresetFromJson(_readString(json['preset']) ?? 'solo'),
      turnBudgetMode: _readString(json['turn_budget_mode']) == null
          ? null
          : turnBudgetModeFromJson(
              _readString(json['turn_budget_mode']) ?? 'each_agent',
            ),
      startedAt: _readDateTime(json['started_at']),
      updatedAt: _readDateTime(json['updated_at']),
      completedAt: _readDateTime(json['completed_at']),
      participantAgentIds:
          (json['participant_agent_ids'] as List<dynamic>? ?? const <dynamic>[])
              .map((item) => tryAgentIdFromJson(_readString(item)))
              .whereType<AgentId>()
              .toList(growable: false),
      callCount: _readInt(json['call_count']) ?? 0,
      stages: rawStages
          .whereType<Map<dynamic, dynamic>>()
          .map((item) => CurrentRunStageExecution.fromJson(
                <String, dynamic>{
                  for (final entry in item.entries)
                    if (entry.key is String) entry.key as String: entry.value,
                },
              ))
          .toList(growable: false),
    );
  }

  CurrentRunExecution copyWith({
    String? runId,
    CurrentRunStageState? state,
    bool? isActive,
    AgentPreset? preset,
    Object? turnBudgetMode = _copyWithSentinel,
    DateTime? startedAt,
    DateTime? updatedAt,
    DateTime? completedAt,
    List<AgentId>? participantAgentIds,
    int? callCount,
    List<CurrentRunStageExecution>? stages,
  }) {
    return CurrentRunExecution(
      runId: runId ?? this.runId,
      state: state ?? this.state,
      isActive: isActive ?? this.isActive,
      preset: preset ?? this.preset,
      turnBudgetMode: identical(turnBudgetMode, _copyWithSentinel)
          ? this.turnBudgetMode
          : turnBudgetMode as TurnBudgetMode?,
      startedAt: startedAt ?? this.startedAt,
      updatedAt: updatedAt ?? this.updatedAt,
      completedAt: completedAt ?? this.completedAt,
      participantAgentIds: participantAgentIds ?? this.participantAgentIds,
      callCount: callCount ?? this.callCount,
      stages: stages ?? this.stages,
    );
  }
}

const Object _copyWithSentinel = Object();

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

DateTime? _readDateTime(Object? value) {
  final raw = _readString(value);
  if (raw == null || raw.isEmpty) {
    return null;
  }
  return DateTime.tryParse(raw);
}
