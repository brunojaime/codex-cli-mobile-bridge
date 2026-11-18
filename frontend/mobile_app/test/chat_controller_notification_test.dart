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
      contains('Respuesta lista'),
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
      contains('Safety Reviewer necesita atención'),
    );
    expect(
      notificationService.notifications.single.body,
      contains('La tarea necesita atención. Tocá para ver el detalle.'),
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
      ..messages = <ChatMessage>[
        _message(
                id: 'message-reviewer',
                jobId: 'job-reviewer',
                runId: 'run-1',
                agentId: AgentId.reviewer,
                agentType: AgentType.reviewer)
            .copyWith(
                status: ChatMessageStatus.completed,
                jobStatus: 'completed',
                text: 'Revisión final lista.'),
      ]
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
      contains('Trabajo finalizado'),
    );
    expect(
      notificationService.notifications.single.body,
      isNot(contains('Respuesta lista')),
    );

    expect(notificationService.notifications.single.body,
        contains('Revisión final lista.'));
    expect(
        notificationService.notifications.single.target?.jobId, 'job-reviewer');
    expect(notificationService.notifications.single.target?.messageId,
        'message-reviewer');
    controller.applyJobSnapshotForTesting(const JobStatusResponse(
        jobId: 'job-late-terminal',
        sessionId: 'session-a',
        status: 'completed',
        elapsedSeconds: 2,
        runId: 'run-1',
        response: 'Late duplicate stage'));
    await Future<void>.delayed(Duration.zero);
    expect(notificationService.notifications, hasLength(1));
    controller.dispose();
  });

  test('legacy jobs also wait for an active Generator Reviewer run', () async {
    final notifications = _RecordingNotificationService();
    final api = _NotificationApiClient(activeRunId: 'run-legacy');
    final controller =
        ChatController(apiClient: api, notificationService: notifications);
    await controller.selectSession('session-a');
    controller.applyJobSnapshotForTesting(const JobStatusResponse(
        jobId: 'legacy-job',
        sessionId: 'session-a',
        status: 'completed',
        elapsedSeconds: 1,
        response: 'Intermediate result'));
    await Future<void>.delayed(Duration.zero);
    expect(notifications.notifications, isEmpty);
    controller.applyJobSnapshotForTesting(const JobStatusResponse(
        jobId: 'legacy-reviewer',
        sessionId: 'session-a',
        status: 'completed',
        elapsedSeconds: 1,
        response: 'Resultado final de la revisión'));
    await Future<void>.delayed(Duration.zero);
    expect(notifications.notifications, isEmpty);
    api.activeRunId = null;
    await controller.selectSession('session-a');
    await Future<void>.delayed(Duration.zero);
    expect(notifications.notifications, hasLength(1));
    expect(notifications.notifications.single.body,
        contains('Resultado final de la revisión'));
    controller.applyJobSnapshotForTesting(const JobStatusResponse(
        jobId: 'next-work',
        sessionId: 'session-a',
        status: 'completed',
        elapsedSeconds: 1,
        response: 'Otro trabajo terminado'));
    await Future<void>.delayed(Duration.zero);
    expect(notifications.notifications, hasLength(2));
    controller.dispose();
  });
  test('waits until other chats in the same project finish', () async {
    final notifications = _RecordingNotificationService();
    final api = _NotificationApiClient()..otherChatActive = true;
    final controller =
        ChatController(apiClient: api, notificationService: notifications);
    await controller.refreshSessions();
    await controller.selectSession('session-a');
    controller.applyJobSnapshotForTesting(const JobStatusResponse(
        jobId: 'job-project',
        sessionId: 'session-a',
        status: 'completed',
        elapsedSeconds: 1,
        response: 'Listo'));
    await Future<void>.delayed(Duration.zero);
    expect(notifications.notifications, isEmpty);
    api.otherChatActive = false;
    await controller.refreshSessions();
    await Future<void>.delayed(Duration.zero);
    expect(notifications.notifications, hasLength(1));
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
  bool otherChatActive = false;
  CurrentRunExecution? currentRun;
  List<CurrentRunExecution> recentRuns = const <CurrentRunExecution>[];
  List<ChatMessage> messages;
  static final DateTime _timestamp = DateTime.utc(2026, 1, 1);

  @override
  Future<List<ChatSessionSummary>> listSessions() async {
    return <ChatSessionSummary>[
      ChatSessionSummary(
          id: 'session-b',
          title: 'Chat B',
          workspacePath: '/workspace/a',
          workspaceName: 'Workspace A',
          hasPendingMessages: otherChatActive,
          createdAt: _timestamp,
          updatedAt: _timestamp),
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
  Future<SessionDetail> getSession(
    String sessionId, {
    String? before,
    int? limit,
    bool fullTranscript = false,
  }) async {
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
