import 'package:codex_mobile_frontend/src/models/agent_configuration.dart';
import 'package:codex_mobile_frontend/src/models/chat_message.dart';
import 'package:codex_mobile_frontend/src/models/chat_session_summary.dart';
import 'package:codex_mobile_frontend/src/models/current_run_execution.dart';
import 'package:codex_mobile_frontend/src/models/job_status_response.dart';
import 'package:codex_mobile_frontend/src/models/session_detail.dart';
import 'package:codex_mobile_frontend/src/services/api_client.dart';
import 'package:codex_mobile_frontend/src/services/chat_notification_service.dart';
import 'package:codex_mobile_frontend/src/state/chat_controller.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('duplicate terminal snapshots notify only once', () async {
    final notificationService = _RecordingNotificationService();
    final controller = ChatController(
      apiClient: _NotificationApiClient(),
      notificationService: notificationService,
    );

    await controller.selectSession('session-a');
    controller.applyJobSnapshotForTesting(
      const JobStatusResponse(
        jobId: 'job-1',
        sessionId: 'session-a',
        status: 'completed',
        elapsedSeconds: 2,
        agentId: AgentId.generator,
        agentType: AgentType.generator,
        response: 'Done.',
      ),
    );
    controller.applyJobSnapshotForTesting(
      const JobStatusResponse(
        jobId: 'job-1',
        sessionId: 'session-a',
        status: 'completed',
        elapsedSeconds: 2,
        agentId: AgentId.generator,
        agentType: AgentType.generator,
        response: 'Done.',
      ),
    );

    await Future<void>.delayed(Duration.zero);

    expect(notificationService.notifications, hasLength(1));
    expect(
      notificationService.notifications.single.body,
      contains('Generator reply ready'),
    );

    controller.dispose();
  });

  test('cancelled jobs do not notify and block later terminal spam', () async {
    final notificationService = _RecordingNotificationService();
    final controller = ChatController(
      apiClient: _NotificationApiClient(),
      notificationService: notificationService,
    );

    await controller.selectSession('session-a');
    controller.applyJobSnapshotForTesting(
      const JobStatusResponse(
        jobId: 'job-2',
        sessionId: 'session-a',
        status: 'cancelled',
        elapsedSeconds: 1,
        agentId: AgentId.generator,
        agentType: AgentType.generator,
        latestActivity: 'Cancelled by user.',
      ),
    );
    controller.applyJobSnapshotForTesting(
      const JobStatusResponse(
        jobId: 'job-2',
        sessionId: 'session-a',
        status: 'failed',
        elapsedSeconds: 1,
        agentId: AgentId.generator,
        agentType: AgentType.generator,
        error: 'Should not notify after cancellation.',
      ),
    );

    await Future<void>.delayed(Duration.zero);

    expect(notificationService.notifications, isEmpty);

    controller.dispose();
  });

  test('failed jobs notify with reviewer label from session configuration',
      () async {
    final notificationService = _RecordingNotificationService();
    final controller = ChatController(
      apiClient: _NotificationApiClient(
        configuration: kDefaultAgentConfiguration.copyWith(
          preset: AgentPreset.review,
          agents: kDefaultAgentDefinitions.map((agent) {
            if (agent.agentId == AgentId.reviewer) {
              return agent.copyWith(enabled: true, label: 'Safety Reviewer');
            }
            return agent;
          }).toList(),
        ),
      ),
      notificationService: notificationService,
    );

    await controller.selectSession('session-a');
    controller.applyJobSnapshotForTesting(
      const JobStatusResponse(
        jobId: 'job-3',
        sessionId: 'session-a',
        status: 'failed',
        elapsedSeconds: 5,
        agentId: AgentId.reviewer,
        agentType: AgentType.reviewer,
        error: '',
      ),
    );

    await Future<void>.delayed(Duration.zero);

    expect(notificationService.notifications, hasLength(1));
    expect(
      notificationService.notifications.single.channel,
      ChatNotificationChannel.reviewer,
    );
    expect(
      notificationService.notifications.single.body,
      contains('Safety Reviewer failed'),
    );
    expect(
      notificationService.notifications.single.body,
      contains('Open the app to inspect the error details.'),
    );

    controller.dispose();
  });

  test('multi-agent run notifies only after the run closes', () async {
    final notificationService = _RecordingNotificationService();
    final apiClient = _NotificationApiClient(
      activeRunId: 'run-1',
      currentRun: _runExecution(
        runId: 'run-1',
        isActive: true,
        state: CurrentRunStageState.running,
        participantAgentIds: const <AgentId>[
          AgentId.generator,
          AgentId.reviewer,
        ],
      ),
      messages: <ChatMessage>[
        _message(
          id: 'message-generator',
          jobId: 'job-generator',
          runId: 'run-1',
          agentId: AgentId.generator,
          agentType: AgentType.generator,
        ),
      ],
    );
    final controller = ChatController(
      apiClient: apiClient,
      notificationService: notificationService,
    );

    await controller.selectSession('session-a');
    controller.applyJobSnapshotForTesting(
      const JobStatusResponse(
        jobId: 'job-generator',
        sessionId: 'session-a',
        status: 'completed',
        elapsedSeconds: 4,
        agentId: AgentId.generator,
        agentType: AgentType.generator,
        runId: 'run-1',
        response: 'Generator finished.',
      ),
    );

    await Future<void>.delayed(Duration.zero);
    expect(notificationService.notifications, isEmpty);

    apiClient
      ..activeRunId = null
      ..currentRun = null
      ..recentRuns = <CurrentRunExecution>[
        _runExecution(
          runId: 'run-1',
          isActive: false,
          state: CurrentRunStageState.completed,
          participantAgentIds: const <AgentId>[
            AgentId.generator,
            AgentId.reviewer,
          ],
        ),
      ];
    await controller.selectSession('session-a');
    await Future<void>.delayed(Duration.zero);

    expect(notificationService.notifications, hasLength(1));
    expect(
      notificationService.notifications.single.channel,
      ChatNotificationChannel.generic,
    );
    expect(
      notificationService.notifications.single.body,
      contains('Codex run complete'),
    );
    expect(
      notificationService.notifications.single.body,
      isNot(contains('Generator reply ready')),
    );

    controller.dispose();
  });
}

class _NotificationApiClient extends ApiClient {
  _NotificationApiClient({
    this.configuration = kDefaultAgentConfiguration,
    this.activeRunId,
    this.currentRun,
    this.messages = const <ChatMessage>[],
  }) : super(baseUrl: 'http://localhost:8000');

  final AgentConfiguration configuration;
  String? activeRunId;
  CurrentRunExecution? currentRun;
  List<CurrentRunExecution> recentRuns = const <CurrentRunExecution>[];
  List<ChatMessage> messages;
  static final DateTime _timestamp = DateTime.utc(2026, 1, 1);

  @override
  Future<List<ChatSessionSummary>> listSessions() async {
    return <ChatSessionSummary>[
      ChatSessionSummary(
        id: 'session-a',
        title: 'Chat A',
        workspacePath: '/workspace/a',
        workspaceName: 'Workspace A',
        agentConfiguration: configuration,
        activeAgentRunId: activeRunId,
        createdAt: _timestamp,
        updatedAt: _timestamp,
      ),
    ];
  }

  @override
  Future<SessionDetail> getSession(String sessionId) async {
    return SessionDetail(
      id: sessionId,
      title: 'Chat A',
      workspacePath: '/workspace/a',
      workspaceName: 'Workspace A',
      agentConfiguration: configuration,
      activeAgentRunId: activeRunId,
      currentRun: currentRun,
      recentRuns: recentRuns,
      createdAt: _timestamp,
      updatedAt: _timestamp,
      messages: messages,
    );
  }
}

class _RecordingNotificationService implements ChatNotificationService {
  final List<ChatCompletedNotification> notifications =
      <ChatCompletedNotification>[];

  @override
  Future<void> initialize() async {}

  @override
  Future<void> showChatCompleted(ChatCompletedNotification notification) async {
    notifications.add(notification);
  }
}

ChatMessage _message({
  required String id,
  required String jobId,
  required String runId,
  required AgentId agentId,
  required AgentType agentType,
}) {
  return ChatMessage(
    id: id,
    text: '',
    isUser: false,
    authorType: ChatMessageAuthorType.assistant,
    agentId: agentId,
    agentType: agentType,
    runId: runId,
    status: ChatMessageStatus.pending,
    createdAt: _NotificationApiClient._timestamp,
    updatedAt: _NotificationApiClient._timestamp,
    jobId: jobId,
    jobStatus: 'running',
  );
}

CurrentRunExecution _runExecution({
  required String runId,
  required bool isActive,
  required CurrentRunStageState state,
  required List<AgentId> participantAgentIds,
}) {
  return CurrentRunExecution(
    runId: runId,
    state: state,
    isActive: isActive,
    preset: AgentPreset.review,
    participantAgentIds: participantAgentIds,
    stages: const <CurrentRunStageExecution>[],
  );
}
