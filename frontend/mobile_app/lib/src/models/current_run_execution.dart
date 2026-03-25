enum CurrentRunStageId {
  generator,
  reviewer,
  summary,
  supervisor,
  qa,
  ux,
  seniorEngineer,
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
    required this.stages,
    this.startedAt,
    this.updatedAt,
    this.completedAt,
  });

  final String runId;
  final CurrentRunStageState state;
  final bool isActive;
  final DateTime? startedAt;
  final DateTime? updatedAt;
  final DateTime? completedAt;
  final List<CurrentRunStageExecution> stages;

  factory CurrentRunExecution.fromJson(Map<String, dynamic> json) {
    final rawStages = json['stages'] as List<dynamic>? ?? const <dynamic>[];
    return CurrentRunExecution(
      runId: _readString(json['run_id']) ?? '',
      state: currentRunStageStateFromJson(json['state'] as String?),
      isActive: _readBool(json['is_active']) ?? false,
      startedAt: _readDateTime(json['started_at']),
      updatedAt: _readDateTime(json['updated_at']),
      completedAt: _readDateTime(json['completed_at']),
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
    DateTime? startedAt,
    DateTime? updatedAt,
    DateTime? completedAt,
    List<CurrentRunStageExecution>? stages,
  }) {
    return CurrentRunExecution(
      runId: runId ?? this.runId,
      state: state ?? this.state,
      isActive: isActive ?? this.isActive,
      startedAt: startedAt ?? this.startedAt,
      updatedAt: updatedAt ?? this.updatedAt,
      completedAt: completedAt ?? this.completedAt,
      stages: stages ?? this.stages,
    );
  }
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

DateTime? _readDateTime(Object? value) {
  final raw = _readString(value);
  if (raw == null || raw.isEmpty) {
    return null;
  }
  return DateTime.tryParse(raw);
}
