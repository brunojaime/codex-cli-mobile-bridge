import 'package:codex_mobile_frontend/src/models/current_run_execution.dart';
import 'package:codex_mobile_frontend/src/models/session_detail.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('parses current run payloads with stage details', () {
    final session = SessionDetail.fromJson(<String, dynamic>{
      'id': 'session-a',
      'title': 'Chat A',
      'workspace_path': '/workspace/a',
      'workspace_name': 'Workspace A',
      'created_at': DateTime.utc(2026, 1, 1).toIso8601String(),
      'updated_at': DateTime.utc(2026, 1, 1).toIso8601String(),
      'messages': const <dynamic>[],
      'current_run': <String, dynamic>{
        'run_id': 'run-123',
        'state': 'running',
        'is_active': true,
        'started_at': DateTime.utc(2026, 1, 1, 11, 58).toIso8601String(),
        'updated_at': DateTime.utc(2026, 1, 1, 12).toIso8601String(),
        'stages': <dynamic>[
          <String, dynamic>{
            'stage': 'generator',
            'state': 'running',
            'configured': true,
            'attempt_count': 2,
            'max_turns': 3,
            'job_id': 'job-1',
            'latest_activity': 'Streaming',
            'started_at': DateTime.utc(2026, 1, 1, 11, 58).toIso8601String(),
          },
        ],
      },
      'recent_runs': <dynamic>[
        <String, dynamic>{
          'run_id': 'run-123',
          'state': 'running',
          'is_active': true,
          'updated_at': DateTime.utc(2026, 1, 1, 12).toIso8601String(),
          'stages': <dynamic>[
            <String, dynamic>{
              'stage': 'generator',
              'state': 'running',
              'configured': true,
              'attempt_count': 2,
              'max_turns': 3,
            },
          ],
        },
      ],
    });

    expect(session.currentRun, isNotNull);
    expect(session.currentRun!.runId, 'run-123');
    expect(session.currentRun!.state, CurrentRunStageState.running);
    expect(session.currentRun!.isActive, isTrue);
    expect(session.currentRun!.startedAt, DateTime.utc(2026, 1, 1, 11, 58));
    expect(session.currentRun!.stages, hasLength(1));
    expect(
      session.currentRun!.stages.single.stage,
      CurrentRunStageId.generator,
    );
    expect(
      session.currentRun!.stages.single.state,
      CurrentRunStageState.running,
    );
    expect(session.currentRun!.stages.single.attemptCount, 2);
    expect(session.currentRun!.stages.single.maxTurns, 3);
    expect(session.recentRuns, hasLength(1));
  });

  test('falls back safely for malformed current run payloads', () {
    final session = SessionDetail.fromJson(<String, dynamic>{
      'id': 'session-a',
      'title': 'Chat A',
      'workspace_path': '/workspace/a',
      'workspace_name': 'Workspace A',
      'created_at': DateTime.utc(2026, 1, 1).toIso8601String(),
      'updated_at': DateTime.utc(2026, 1, 1).toIso8601String(),
      'messages': const <dynamic>[],
      'current_run': <String, dynamic>{
        'run_id': 42,
        'state': 'weird',
        'is_active': 'nope',
        'updated_at': 'bad-date',
        'stages': <dynamic>[
          <String, dynamic>{
            'stage': 'mystery',
            'state': 'weird',
            'configured': 'not-bool',
            'attempt_count': 'oops',
            'max_turns': 'still-bad',
            'job_status': 99,
          },
          'ignore-me',
        ],
      },
      'recent_runs': <dynamic>[
        'ignore-me',
      ],
    });

    expect(session.currentRun, isNotNull);
    expect(session.currentRun!.runId, '42');
    expect(session.currentRun!.state, CurrentRunStageState.waiting);
    expect(session.currentRun!.isActive, isFalse);
    expect(session.currentRun!.updatedAt, isNull);
    expect(session.currentRun!.stages, hasLength(1));
    expect(
      session.currentRun!.stages.single.stage,
      CurrentRunStageId.generator,
    );
    expect(
      session.currentRun!.stages.single.state,
      CurrentRunStageState.waiting,
    );
    expect(session.currentRun!.stages.single.configured, isFalse);
    expect(session.currentRun!.stages.single.attemptCount, 0);
    expect(session.currentRun!.stages.single.maxTurns, 0);
    expect(session.currentRun!.stages.single.jobStatus, '99');
    expect(session.recentRuns, isEmpty);
  });
}
