import '../models/agent_configuration.dart';
import '../models/job_status_response.dart';
import 'chat_notification_service.dart';

const _genericReplyPreview = 'La respuesta está lista. Tocá para leerla.';
const _genericFailurePreview =
    'La tarea necesita atención. Tocá para ver el detalle.';
const _genericCancelledPreview = 'La tarea se detuvo. Tocá para ver el estado.';

ChatCompletedNotification buildChatCompletedNotification({
  required JobStatusResponse snapshot,
  required String workspaceName,
  required String sessionTitle,
  String? configuredAgentLabel,
  ChatNotificationTarget? target,
}) {
  final normalizedWorkspaceName =
      _normalizeOptionalText(workspaceName) ?? 'Codex Remote';
  final normalizedSessionTitle = _normalizeOptionalText(sessionTitle) ?? 'Chat';
  final resolvedAgentLabel = resolveNotificationAgentLabel(
    snapshot,
    configuredAgentLabel: configuredAgentLabel,
  );

  return ChatCompletedNotification(
    id: target?.notificationId ?? stableNotificationId(snapshot.sessionId),
    target: target,
    title: normalizedWorkspaceName,
    body: [
      '$normalizedSessionTitle · ${_statusLine(snapshot.status, resolvedAgentLabel)}',
      _notificationPreview(snapshot),
    ].join('\n'),
    channel: snapshot.resolvedNotificationChannel,
    summary: '$resolvedAgentLabel • $normalizedSessionTitle',
  );
}

ChatCompletedNotification buildRunCompletedNotification({
  required JobStatusResponse snapshot,
  required String runId,
  required String workspaceName,
  required String sessionTitle,
  ChatNotificationTarget? target,
}) {
  final normalizedWorkspaceName =
      _normalizeOptionalText(workspaceName) ?? 'Codex Remote';
  final normalizedSessionTitle = _normalizeOptionalText(sessionTitle) ?? 'Chat';

  return ChatCompletedNotification(
    id: target?.notificationId ?? stableNotificationId(snapshot.sessionId),
    target: target,
    title: normalizedWorkspaceName,
    body: [
      '$normalizedSessionTitle · ${_runStatusLine(snapshot.status)}',
      _notificationPreview(snapshot),
    ].join('\n'),
    channel: ChatNotificationChannel.generic,
    summary: '${_runStatusLine(snapshot.status)} • $normalizedSessionTitle',
  );
}

String _runStatusLine(String status) {
  return switch (status) {
    'failed' => 'El trabajo necesita atención',
    'cancelled' => 'Trabajo cancelado',
    _ => 'Trabajo finalizado',
  };
}

String resolveNotificationAgentLabel(
  JobStatusResponse snapshot, {
  String? configuredAgentLabel,
}) {
  final explicitLabel = _normalizeOptionalText(configuredAgentLabel) ??
      _normalizeOptionalText(snapshot.agentLabel);
  if (explicitLabel != null) {
    return explicitLabel;
  }
  if (snapshot.resolvedNotificationChannel == ChatNotificationChannel.generic) {
    return 'Codex';
  }

  return switch (snapshot.agentId) {
    AgentId.user => 'User',
    AgentId.generator => 'Generator',
    AgentId.reviewer => 'Reviewer',
    AgentId.summary => 'Summary',
    AgentId.supervisor => 'Supervisor',
    AgentId.qa => 'QA',
    AgentId.ux => 'UX',
    AgentId.seniorEngineer => 'Senior Engineer',
    AgentId.scraper => 'Scraper',
  };
}

String _statusLine(String status, String resolvedAgentLabel) {
  return switch (status) {
    'failed' => '$resolvedAgentLabel necesita atención',
    'cancelled' => '$resolvedAgentLabel cancelado',
    _ => 'Respuesta lista',
  };
}

String _notificationPreview(JobStatusResponse snapshot) {
  final rawPreview = switch (snapshot.status) {
    'failed' => snapshot.error,
    'cancelled' => snapshot.latestActivity,
    _ => snapshot.response ?? snapshot.latestActivity,
  };
  final normalizedPreview = _normalizeOptionalText(rawPreview);
  if (normalizedPreview == null) {
    return switch (snapshot.status) {
      'failed' => _genericFailurePreview,
      'cancelled' => _genericCancelledPreview,
      _ => _genericReplyPreview,
    };
  }

  final characters = normalizedPreview.runes.toList();
  return characters.length <= 160
      ? normalizedPreview
      : '${String.fromCharCodes(characters.take(157))}...';
}

String? _normalizeOptionalText(String? value) {
  if (value == null) {
    return null;
  }

  final normalized = value
      .replaceAll(RegExp(r'[`#*_>]'), '')
      .replaceAllMapped(RegExp(r'\[([^\]]+)\]\([^)]*\)'), (match) => match[1]!)
      .replaceAll(RegExp(r'\s+'), ' ')
      .trim();
  if (normalized.isEmpty) {
    return null;
  }
  return normalized;
}
