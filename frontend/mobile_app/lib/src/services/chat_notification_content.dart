import '../models/agent_configuration.dart';
import '../models/job_status_response.dart';
import 'chat_notification_service.dart';

const _genericReplyPreview = 'Open the app to inspect the latest reply.';
const _genericFailurePreview = 'Open the app to inspect the error details.';
const _genericCancelledPreview = 'Open the app to inspect the latest state.';

ChatCompletedNotification buildChatCompletedNotification({
  required JobStatusResponse snapshot,
  required String workspaceName,
  required String sessionTitle,
  String? configuredAgentLabel,
}) {
  final normalizedWorkspaceName =
      _normalizeOptionalText(workspaceName) ?? 'Codex Remote';
  final normalizedSessionTitle = _normalizeOptionalText(sessionTitle) ?? 'Chat';
  final resolvedAgentLabel = resolveNotificationAgentLabel(
    snapshot,
    configuredAgentLabel: configuredAgentLabel,
  );

  return ChatCompletedNotification(
    id: snapshot.jobId.hashCode,
    title: normalizedWorkspaceName,
    body: [
      _statusLine(snapshot.status, resolvedAgentLabel),
      normalizedSessionTitle,
      _notificationPreview(snapshot),
    ].join('\n'),
    channel: snapshot.resolvedNotificationChannel,
    summary: '$resolvedAgentLabel • $normalizedSessionTitle',
  );
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
    'failed' => '$resolvedAgentLabel failed',
    'cancelled' => '$resolvedAgentLabel cancelled',
    _ => '$resolvedAgentLabel reply ready',
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

  return normalizedPreview.length <= 220
      ? normalizedPreview
      : '${normalizedPreview.substring(0, 217)}...';
}

String? _normalizeOptionalText(String? value) {
  if (value == null) {
    return null;
  }

  final normalized = value.replaceAll(RegExp(r'\s+'), ' ').trim();
  if (normalized.isEmpty) {
    return null;
  }
  return normalized;
}
