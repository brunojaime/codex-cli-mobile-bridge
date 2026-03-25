import 'package:codex_mobile_frontend/src/models/agent_configuration.dart';
import 'package:codex_mobile_frontend/src/models/chat_message.dart';
import 'package:codex_mobile_frontend/src/models/chat_session_summary.dart';
import 'package:codex_mobile_frontend/src/models/current_run_execution.dart';
import 'package:codex_mobile_frontend/src/models/job_status_response.dart';
import 'package:codex_mobile_frontend/src/models/session_detail.dart';
import 'package:codex_mobile_frontend/src/services/api_client.dart';
import 'package:codex_mobile_frontend/src/state/chat_controller.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test(
      'job snapshots update the active recent run and keep completed rows stable',
      () async {
    final controller = ChatController(
      apiClient: _RunHistoryApiClient(),
    );

    await controller.selectSession('session-a');
    controller.applyJobSnapshotForTesting(
      const JobStatusResponse(
        jobId: 'job-generator-active',
        sessionId: 'session-a',
        status: 'completed',
        elapsedSeconds: 4,
        agentId: AgentId.generator,
        agentType: AgentType.generator,
        latestActivity: 'Generator finished.',
      ),
    );

    final session = controller.currentSession;
    expect(session, isNotNull);
    expect(session!.currentRun, isNotNull);
    expect(session.currentRun!.state, CurrentRunStageState.completed);
    expect(session.recentRuns, hasLength(2));
    expect(session.recentRuns.first.runId, 'run-active');
    expect(
      session.recentRuns.first.stages.first.state,
      CurrentRunStageState.completed,
    );
    expect(
      session.recentRuns.first.stages.first.latestActivity,
      'Generator finished.',
    );
    expect(session.recentRuns.last.runId, 'run-done');
    expect(
      session.recentRuns.last.stages.first.state,
      CurrentRunStageState.completed,
    );

    controller.dispose();
  });
}

class _RunHistoryApiClient extends ApiClient {
  _RunHistoryApiClient() : super(baseUrl: 'http://localhost:8000');

  static final DateTime _timestamp = DateTime.utc(2026, 1, 1, 12);

  @override
  Future<List<ChatSessionSummary>> listSessions() async {
    return <ChatSessionSummary>[
      ChatSessionSummary(
        id: 'session-a',
        title: 'Chat A',
        workspacePath: '/workspace/a',
        workspaceName: 'Workspace A',
        agentConfiguration: kDefaultAgentConfiguration,
        createdAt: _timestamp,
        updatedAt: _timestamp,
        activeAgentRunId: 'run-active',
      ),
    ];
  }

  @override
  Future<SessionDetail> getSession(String sessionId) async {
    const activeRun = CurrentRunExecution(
      runId: 'run-active',
      state: CurrentRunStageState.running,
      isActive: true,
      stages: <CurrentRunStageExecution>[
        CurrentRunStageExecution(
          stage: CurrentRunStageId.generator,
          state: CurrentRunStageState.running,
          configured: true,
          attemptCount: 1,
          maxTurns: 2,
          jobId: 'job-generator-active',
        ),
        CurrentRunStageExecution(
          stage: CurrentRunStageId.reviewer,
          state: CurrentRunStageState.disabled,
          configured: false,
        ),
        CurrentRunStageExecution(
          stage: CurrentRunStageId.summary,
          state: CurrentRunStageState.disabled,
          configured: false,
        ),
      ],
    );
    const completedRun = CurrentRunExecution(
      runId: 'run-done',
      state: CurrentRunStageState.completed,
      isActive: false,
      stages: <CurrentRunStageExecution>[
        CurrentRunStageExecution(
          stage: CurrentRunStageId.generator,
          state: CurrentRunStageState.completed,
          configured: true,
          attemptCount: 1,
          maxTurns: 2,
          jobId: 'job-generator-done',
        ),
        CurrentRunStageExecution(
          stage: CurrentRunStageId.reviewer,
          state: CurrentRunStageState.disabled,
          configured: false,
        ),
        CurrentRunStageExecution(
          stage: CurrentRunStageId.summary,
          state: CurrentRunStageState.disabled,
          configured: false,
        ),
      ],
    );

    return SessionDetail(
      id: sessionId,
      title: 'Chat A',
      workspacePath: '/workspace/a',
      workspaceName: 'Workspace A',
      agentConfiguration: kDefaultAgentConfiguration,
      activeAgentRunId: 'run-active',
      currentRun: activeRun,
      recentRuns: const <CurrentRunExecution>[
        activeRun,
        completedRun,
      ],
      createdAt: _timestamp,
      updatedAt: _timestamp,
      messages: const <ChatMessage>[],
    );
  }
}
