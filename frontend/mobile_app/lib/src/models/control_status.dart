class ControlServiceStatus {
  const ControlServiceStatus({
    required this.loaded,
    required this.activeState,
    required this.subState,
    required this.mainPid,
    required this.restartCount,
    this.startedAt,
    this.detail,
  });

  final bool loaded;
  final String activeState;
  final String subState;
  final int mainPid;
  final int restartCount;
  final String? startedAt;
  final String? detail;

  bool get isRunning => loaded && activeState == 'active';

  factory ControlServiceStatus.fromJson(Map<String, dynamic> json) {
    return ControlServiceStatus(
      loaded: json['loaded'] as bool? ?? false,
      activeState: json['active_state'] as String? ?? 'unknown',
      subState: json['sub_state'] as String? ?? 'unknown',
      mainPid: json['main_pid'] as int? ?? 0,
      restartCount: json['restart_count'] as int? ?? 0,
      startedAt: json['started_at'] as String?,
      detail: json['detail'] as String?,
    );
  }
}

class ControlRestartAction {
  const ControlRestartAction({
    required this.id,
    required this.environment,
    required this.mode,
    required this.status,
    required this.stage,
    required this.detail,
  });

  final String id;
  final String environment;
  final String mode;
  final String status;
  final String stage;
  final String detail;

  bool get isTerminal => status == 'completed' || status == 'failed';

  factory ControlRestartAction.fromJson(Map<String, dynamic> json) {
    return ControlRestartAction(
      id: json['id'] as String,
      environment: json['environment'] as String,
      mode: json['mode'] as String? ?? 'graceful',
      status: json['status'] as String? ?? 'queued',
      stage: json['stage'] as String? ?? 'queued',
      detail: json['detail'] as String? ?? '',
    );
  }
}

class ControlEnvironmentStatus {
  const ControlEnvironmentStatus({
    required this.name,
    required this.displayName,
    required this.serviceName,
    required this.backendUrl,
    required this.service,
    required this.backendReachable,
    this.backendHealth,
    this.backendError,
    this.activeJobCount,
    this.activeJobs = const <Map<String, dynamic>>[],
    this.activeSessionCount,
    this.inFlightMessageCount,
    this.drainRequested,
    this.activeAction,
  });

  final String name;
  final String displayName;
  final String serviceName;
  final String backendUrl;
  final ControlServiceStatus service;
  final bool backendReachable;
  final Map<String, dynamic>? backendHealth;
  final String? backendError;
  final int? activeJobCount;
  final List<Map<String, dynamic>> activeJobs;
  final int? activeSessionCount;
  final int? inFlightMessageCount;
  final bool? drainRequested;
  final ControlRestartAction? activeAction;

  bool get isHealthy => service.isRunning && backendReachable;

  factory ControlEnvironmentStatus.fromJson(Map<String, dynamic> json) {
    return ControlEnvironmentStatus(
      name: json['name'] as String,
      displayName: json['display_name'] as String,
      serviceName: json['service_name'] as String,
      backendUrl: json['backend_url'] as String,
      service: ControlServiceStatus.fromJson(
        json['service'] as Map<String, dynamic>? ?? <String, dynamic>{},
      ),
      backendReachable: json['backend_reachable'] as bool? ?? false,
      backendHealth: json['backend_health'] as Map<String, dynamic>?,
      backendError: json['backend_error'] as String?,
      activeJobCount: json['active_job_count'] as int?,
      activeJobs: (json['active_jobs'] as List<dynamic>? ?? <dynamic>[])
          .map((item) => item as Map<String, dynamic>)
          .toList(),
      activeSessionCount: json['active_session_count'] as int?,
      inFlightMessageCount: json['in_flight_message_count'] as int?,
      drainRequested: json['drain_requested'] as bool?,
      activeAction: json['active_action'] == null
          ? null
          : ControlRestartAction.fromJson(
              json['active_action'] as Map<String, dynamic>,
            ),
    );
  }
}

class CodexControlStatus {
  const CodexControlStatus({
    required this.available,
    required this.authenticated,
    this.version,
    this.detail,
  });

  final bool available;
  final bool authenticated;
  final String? version;
  final String? detail;

  factory CodexControlStatus.fromJson(Map<String, dynamic> json) {
    return CodexControlStatus(
      available: json['available'] as bool? ?? false,
      authenticated: json['authenticated'] as bool? ?? false,
      version: json['version'] as String?,
      detail: json['detail'] as String?,
    );
  }
}

class ControlSnapshot {
  const ControlSnapshot({required this.environments, required this.codex});

  final List<ControlEnvironmentStatus> environments;
  final CodexControlStatus codex;

  factory ControlSnapshot.fromJson(Map<String, dynamic> json) {
    return ControlSnapshot(
      environments: (json['environments'] as List<dynamic>? ?? <dynamic>[])
          .map(
            (item) =>
                ControlEnvironmentStatus.fromJson(item as Map<String, dynamic>),
          )
          .toList(),
      codex: CodexControlStatus.fromJson(
        json['codex'] as Map<String, dynamic>? ?? <String, dynamic>{},
      ),
    );
  }
}
