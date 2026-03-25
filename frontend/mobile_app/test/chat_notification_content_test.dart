import 'package:codex_mobile_frontend/src/models/agent_configuration.dart';
import 'package:codex_mobile_frontend/src/models/job_status_response.dart';
import 'package:codex_mobile_frontend/src/services/chat_notification_content.dart';
import 'package:codex_mobile_frontend/src/services/chat_notification_service.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('builds generator completion notifications', () {
    final notification = buildChatCompletedNotification(
      snapshot: const JobStatusResponse(
        jobId: 'job-generator',
        sessionId: 'session-a',
        status: 'completed',
        elapsedSeconds: 2,
        agentId: AgentId.generator,
        agentType: AgentType.generator,
        response: 'Implemented the fix.',
      ),
      workspaceName: 'Workspace A',
      sessionTitle: 'Chat A',
    );

    expect(notification.channel, ChatNotificationChannel.generator);
    expect(notification.title, 'Workspace A');
    expect(notification.summary, 'Generator • Chat A');
    expect(notification.body, contains('Generator reply ready'));
  });

  test('builds reviewer and summary notifications with configured labels', () {
    final reviewerNotification = buildChatCompletedNotification(
      snapshot: const JobStatusResponse(
        jobId: 'job-reviewer',
        sessionId: 'session-a',
        status: 'completed',
        elapsedSeconds: 1,
        agentId: AgentId.reviewer,
        agentType: AgentType.reviewer,
        response: 'Add regression coverage.',
      ),
      workspaceName: 'Workspace A',
      sessionTitle: 'Chat A',
      configuredAgentLabel: 'QA Reviewer',
    );
    final summaryNotification = buildChatCompletedNotification(
      snapshot: const JobStatusResponse(
        jobId: 'job-summary',
        sessionId: 'session-a',
        status: 'completed',
        elapsedSeconds: 1,
        agentId: AgentId.summary,
        agentType: AgentType.summary,
        response: 'Implementation complete.',
      ),
      workspaceName: 'Workspace A',
      sessionTitle: 'Chat A',
    );

    expect(reviewerNotification.channel, ChatNotificationChannel.reviewer);
    expect(reviewerNotification.summary, 'QA Reviewer • Chat A');
    expect(reviewerNotification.body, contains('QA Reviewer reply ready'));
    expect(summaryNotification.channel, ChatNotificationChannel.summary);
    expect(summaryNotification.body, contains('Summary reply ready'));
  });

  test(
      'falls back to generic channel and safe copy for unknown agents and empty text',
      () {
    final snapshot = JobStatusResponse.fromJson(<String, dynamic>{
      'job_id': 'job-unknown',
      'session_id': 'session-a',
      'status': 'completed',
      'elapsed_seconds': 0,
      'agent_id': 'mystery',
      'response': '   ',
    });
    final notification = buildChatCompletedNotification(
      snapshot: snapshot,
      workspaceName: '   ',
      sessionTitle: '',
    );

    expect(notification.channel, ChatNotificationChannel.generic);
    expect(notification.title, 'Codex Remote');
    expect(notification.summary, 'Codex • Chat');
    expect(notification.body, contains('Codex reply ready'));
    expect(notification.body,
        contains('Open the app to inspect the latest reply.'));
  });

  test('formats failed notifications with generic fallback error preview', () {
    final notification = buildChatCompletedNotification(
      snapshot: const JobStatusResponse(
        jobId: 'job-failed',
        sessionId: 'session-a',
        status: 'failed',
        elapsedSeconds: 4,
        agentId: AgentId.generator,
        agentType: AgentType.generator,
      ),
      workspaceName: 'Workspace A',
      sessionTitle: 'Chat A',
    );

    expect(notification.channel, ChatNotificationChannel.generator);
    expect(notification.body, contains('Generator failed'));
    expect(notification.body,
        contains('Open the app to inspect the error details.'));
  });
}
