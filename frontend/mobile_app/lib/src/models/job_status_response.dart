import 'agent_configuration.dart';
import '../services/chat_notification_service.dart';

class JobStatusResponse {
  const JobStatusResponse({
    required this.jobId,
    required this.sessionId,
    required this.status,
    required this.elapsedSeconds,
    this.agentId = AgentId.generator,
    this.agentType = AgentType.generator,
    this.agentLabel,
    this.notificationChannel,
    this.response,
    this.error,
    this.providerSessionId,
    this.phase,
    this.latestActivity,
    this.updatedAt,
    this.completedAt,
  });

  final String jobId;
  final String sessionId;
  final String status;
  final int elapsedSeconds;
  final AgentId agentId;
  final AgentType agentType;
  final String? agentLabel;
  final ChatNotificationChannel? notificationChannel;
  final String? response;
  final String? error;
  final String? providerSessionId;
  final String? phase;
  final String? latestActivity;
  final DateTime? updatedAt;
  final DateTime? completedAt;

  bool get isTerminal =>
      status == 'completed' || status == 'failed' || status == 'cancelled';

  ChatNotificationChannel get resolvedNotificationChannel =>
      notificationChannel ?? _defaultNotificationChannelForAgent(agentId);

  factory JobStatusResponse.fromJson(Map<String, dynamic> json) {
    final rawAgentId = _readText(json['agent_id']);
    final rawAgentType = _readText(json['agent_type']);
    final parsedAgentId = _resolveAgentId(rawAgentId, rawAgentType);
    return JobStatusResponse(
      jobId: _readText(json['job_id']) ?? '',
      sessionId: _readText(json['session_id']) ?? '',
      status: _normalizeStatus(_readText(json['status'])),
      elapsedSeconds: _readElapsedSeconds(json['elapsed_seconds']),
      agentId: parsedAgentId,
      agentType: _resolveAgentType(parsedAgentId, rawAgentType),
      agentLabel: _readText(json['agent_label']),
      notificationChannel:
          _resolveNotificationChannel(rawAgentId, rawAgentType),
      response: _readPayloadText(json['response']),
      error: _readPayloadText(json['error']),
      providerSessionId: _readText(json['provider_session_id']),
      phase: _readText(json['phase']),
      latestActivity: _readPayloadText(json['latest_activity']),
      updatedAt: _readDateTime(json['updated_at']),
      completedAt: _readDateTime(json['completed_at']),
    );
  }

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'job_id': jobId,
      'session_id': sessionId,
      'status': status,
      'elapsed_seconds': elapsedSeconds,
      'agent_id': agentIdToJson(agentId),
      'agent_type': agentTypeToJson(agentType),
      if (agentLabel != null) 'agent_label': agentLabel,
      if (response != null) 'response': response,
      if (error != null) 'error': error,
      if (providerSessionId != null) 'provider_session_id': providerSessionId,
      if (phase != null) 'phase': phase,
      if (latestActivity != null) 'latest_activity': latestActivity,
      if (updatedAt != null) 'updated_at': updatedAt!.toIso8601String(),
      if (completedAt != null) 'completed_at': completedAt!.toIso8601String(),
    };
  }

  JobStatusResponse copyWith({
    String? jobId,
    String? sessionId,
    String? status,
    int? elapsedSeconds,
    AgentId? agentId,
    AgentType? agentType,
    String? agentLabel,
    ChatNotificationChannel? notificationChannel,
    String? response,
    String? error,
    String? providerSessionId,
    String? phase,
    String? latestActivity,
    DateTime? updatedAt,
    DateTime? completedAt,
  }) {
    return JobStatusResponse(
      jobId: jobId ?? this.jobId,
      sessionId: sessionId ?? this.sessionId,
      status: status ?? this.status,
      elapsedSeconds: elapsedSeconds ?? this.elapsedSeconds,
      agentId: agentId ?? this.agentId,
      agentType: agentType ?? this.agentType,
      agentLabel: agentLabel ?? this.agentLabel,
      notificationChannel: notificationChannel ?? this.notificationChannel,
      response: response ?? this.response,
      error: error ?? this.error,
      providerSessionId: providerSessionId ?? this.providerSessionId,
      phase: phase ?? this.phase,
      latestActivity: latestActivity ?? this.latestActivity,
      updatedAt: updatedAt ?? this.updatedAt,
      completedAt: completedAt ?? this.completedAt,
    );
  }
}

String? _readText(Object? value) {
  if (value is! String) {
    return null;
  }
  final trimmed = value.trim();
  return trimmed.isEmpty ? null : trimmed;
}

String? _readPayloadText(Object? value) {
  if (value == null) {
    return null;
  }
  if (value is String) {
    return value;
  }
  if (value is num || value is bool) {
    return value.toString();
  }
  return null;
}

int _readElapsedSeconds(Object? value) {
  if (value is int) {
    return value < 0 ? 0 : value;
  }
  if (value is num) {
    return value.isNegative ? 0 : value.toInt();
  }
  if (value is String) {
    final parsed = int.tryParse(value.trim());
    if (parsed != null && parsed >= 0) {
      return parsed;
    }
  }
  return 0;
}

DateTime? _readDateTime(Object? value) {
  final raw = _readText(value);
  if (raw == null) {
    return null;
  }
  return DateTime.tryParse(raw);
}

String _normalizeStatus(String? rawStatus) {
  return switch (rawStatus) {
    'pending' => 'pending',
    'running' => 'running',
    'completed' => 'completed',
    'failed' => 'failed',
    'cancelled' => 'cancelled',
    _ => 'pending',
  };
}

AgentId _resolveAgentId(String? rawAgentId, String? rawAgentType) {
  final parsedAgentId = tryAgentIdFromJson(rawAgentId);
  if (parsedAgentId != null) {
    return parsedAgentId;
  }

  return switch (tryAgentTypeFromJson(rawAgentType)) {
    AgentType.human => AgentId.user,
    AgentType.reviewer => AgentId.reviewer,
    AgentType.summary => AgentId.summary,
    AgentType.supervisor => AgentId.supervisor,
    AgentType.qa => AgentId.qa,
    AgentType.ux => AgentId.ux,
    AgentType.seniorEngineer => AgentId.seniorEngineer,
    _ => AgentId.generator,
  };
}

AgentType _resolveAgentType(AgentId resolvedAgentId, String? rawAgentType) {
  final parsedAgentType = tryAgentTypeFromJson(rawAgentType);
  if (parsedAgentType != null) {
    return parsedAgentType;
  }

  return switch (resolvedAgentId) {
    AgentId.user => AgentType.human,
    AgentId.reviewer => AgentType.reviewer,
    AgentId.summary => AgentType.summary,
    AgentId.supervisor => AgentType.supervisor,
    AgentId.qa => AgentType.qa,
    AgentId.ux => AgentType.ux,
    AgentId.seniorEngineer => AgentType.seniorEngineer,
    AgentId.generator => AgentType.generator,
  };
}

ChatNotificationChannel _defaultNotificationChannelForAgent(AgentId agentId) {
  return switch (agentId) {
    AgentId.reviewer => ChatNotificationChannel.reviewer,
    AgentId.summary => ChatNotificationChannel.summary,
    AgentId.supervisor => ChatNotificationChannel.generator,
    AgentId.qa => ChatNotificationChannel.generator,
    AgentId.ux => ChatNotificationChannel.generator,
    AgentId.seniorEngineer => ChatNotificationChannel.generator,
    AgentId.user => ChatNotificationChannel.generic,
    AgentId.generator => ChatNotificationChannel.generator,
  };
}

ChatNotificationChannel _resolveNotificationChannel(
  String? rawAgentId,
  String? rawAgentType,
) {
  final parsedAgentId = tryAgentIdFromJson(rawAgentId);
  if (parsedAgentId != null) {
    return _defaultNotificationChannelForAgent(parsedAgentId);
  }

  return switch (tryAgentTypeFromJson(rawAgentType)) {
    AgentType.reviewer => ChatNotificationChannel.reviewer,
    AgentType.summary => ChatNotificationChannel.summary,
    AgentType.supervisor => ChatNotificationChannel.generator,
    AgentType.qa => ChatNotificationChannel.generator,
    AgentType.ux => ChatNotificationChannel.generator,
    AgentType.seniorEngineer => ChatNotificationChannel.generator,
    AgentType.generator => ChatNotificationChannel.generator,
    _ => ChatNotificationChannel.generic,
  };
}
