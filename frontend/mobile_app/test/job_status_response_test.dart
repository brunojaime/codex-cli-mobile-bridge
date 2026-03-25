import 'package:codex_mobile_frontend/src/models/agent_configuration.dart';
import 'package:codex_mobile_frontend/src/models/job_status_response.dart';
import 'package:codex_mobile_frontend/src/services/chat_notification_service.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('parses well-formed payloads and preserves agent metadata', () {
    final snapshot = JobStatusResponse.fromJson(<String, dynamic>{
      'job_id': 'job-1',
      'session_id': 'session-a',
      'status': 'completed',
      'elapsed_seconds': 3,
      'agent_id': 'reviewer',
      'agent_type': 'reviewer',
      'agent_label': 'Audit Bot',
      'response': 'Looks good.',
      'updated_at': DateTime.utc(2026, 1, 1).toIso8601String(),
    });

    expect(snapshot.jobId, 'job-1');
    expect(snapshot.sessionId, 'session-a');
    expect(snapshot.status, 'completed');
    expect(snapshot.elapsedSeconds, 3);
    expect(snapshot.agentId, AgentId.reviewer);
    expect(snapshot.agentType, AgentType.reviewer);
    expect(snapshot.agentLabel, 'Audit Bot');
    expect(
        snapshot.resolvedNotificationChannel, ChatNotificationChannel.reviewer);
  });

  test('falls back safely for missing or malformed payload fields', () {
    final snapshot = JobStatusResponse.fromJson(<String, dynamic>{
      'job_id': 42,
      'status': 'not-real',
      'elapsed_seconds': '-9',
      'agent_id': 'mystery',
      'agent_type': 'weird',
      'response': 99,
      'updated_at': 'not-a-date',
    });

    expect(snapshot.jobId, '');
    expect(snapshot.sessionId, '');
    expect(snapshot.status, 'pending');
    expect(snapshot.elapsedSeconds, 0);
    expect(snapshot.agentId, AgentId.generator);
    expect(snapshot.agentType, AgentType.generator);
    expect(snapshot.agentLabel, isNull);
    expect(snapshot.response, '99');
    expect(snapshot.updatedAt, isNull);
    expect(
        snapshot.resolvedNotificationChannel, ChatNotificationChannel.generic);
  });

  test(
      'infers reviewer channel and agent from agent_type when agent_id is missing',
      () {
    final snapshot = JobStatusResponse.fromJson(<String, dynamic>{
      'job_id': 'job-2',
      'session_id': 'session-a',
      'status': 'failed',
      'elapsed_seconds': 7.8,
      'agent_type': 'reviewer',
      'error': true,
    });

    expect(snapshot.elapsedSeconds, 7);
    expect(snapshot.agentId, AgentId.reviewer);
    expect(snapshot.agentType, AgentType.reviewer);
    expect(snapshot.error, 'true');
    expect(
        snapshot.resolvedNotificationChannel, ChatNotificationChannel.reviewer);
  });

  test('serializes normalized payloads predictably', () {
    final snapshot = JobStatusResponse.fromJson(<String, dynamic>{
      'job_id': 'job-3',
      'session_id': 'session-a',
      'status': 'completed',
      'elapsed_seconds': '5',
      'agent_id': 'summary',
      'agent_type': 'summary',
      'latest_activity': 'Done',
    });

    expect(snapshot.toJson(), <String, dynamic>{
      'job_id': 'job-3',
      'session_id': 'session-a',
      'status': 'completed',
      'elapsed_seconds': 5,
      'agent_id': 'summary',
      'agent_type': 'summary',
      'latest_activity': 'Done',
    });
  });
}
