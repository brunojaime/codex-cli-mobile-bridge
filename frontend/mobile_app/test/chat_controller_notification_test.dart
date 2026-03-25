import 'package:codex_mobile_frontend/src/models/agent_configuration.dart';
import 'package:codex_mobile_frontend/src/models/chat_message.dart';
import 'package:codex_mobile_frontend/src/models/chat_session_summary.dart';
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
}

class _NotificationApiClient extends ApiClient {
  _NotificationApiClient({
    this.configuration = kDefaultAgentConfiguration,
  }) : super(baseUrl: 'http://localhost:8000');

  final AgentConfiguration configuration;
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
      createdAt: _timestamp,
      updatedAt: _timestamp,
      messages: const <ChatMessage>[],
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
