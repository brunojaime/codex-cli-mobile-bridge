import 'dart:async';

import 'package:codex_mobile_frontend/src/models/agent_configuration.dart';
import 'package:codex_mobile_frontend/src/models/chat_message.dart';
import 'package:codex_mobile_frontend/src/models/chat_session_summary.dart';
import 'package:codex_mobile_frontend/src/models/reviewer_lifecycle_state.dart';
import 'package:codex_mobile_frontend/src/models/session_detail.dart';
import 'package:codex_mobile_frontend/src/services/api_client.dart';
import 'package:codex_mobile_frontend/src/services/chat_notification_service.dart';
import 'package:codex_mobile_frontend/src/state/chat_controller.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('selectSession keeps reviewer state visible while detail is loading',
      () async {
    final apiClient = _DelayedSessionApiClient();
    final controller = ChatController(
      apiClient: apiClient,
      notificationService: const NoopChatNotificationService(),
    );

    await controller.refreshSessions();
    final selectionFuture = controller.selectSession('session-a');
    await Future<void>.delayed(Duration.zero);

    expect(
      controller.currentSession?.reviewerState,
      ReviewerLifecycleState.running,
    );

    apiClient.complete();
    await selectionFuture;

    expect(
      controller.currentSession?.reviewerState,
      ReviewerLifecycleState.completed,
    );

    controller.dispose();
  });
}

class _DelayedSessionApiClient extends ApiClient {
  _DelayedSessionApiClient() : super(baseUrl: 'http://localhost:8000');

  final Completer<void> _detailCompleter = Completer<void>();
  static final DateTime _timestamp = DateTime.utc(2026, 1, 1);

  void complete() {
    if (!_detailCompleter.isCompleted) {
      _detailCompleter.complete();
    }
  }

  @override
  Future<List<ChatSessionSummary>> listSessions() async {
    return <ChatSessionSummary>[
      ChatSessionSummary(
        id: 'session-a',
        title: 'Chat A',
        workspacePath: '/workspace/a',
        workspaceName: 'Workspace A',
        agentConfiguration: kDefaultAgentConfiguration,
        reviewerState: ReviewerLifecycleState.running,
        createdAt: _timestamp,
        updatedAt: _timestamp,
      ),
    ];
  }

  @override
  Future<SessionDetail> getSession(String sessionId) async {
    await _detailCompleter.future;
    return SessionDetail(
      id: sessionId,
      title: 'Chat A',
      workspacePath: '/workspace/a',
      workspaceName: 'Workspace A',
      agentConfiguration: kDefaultAgentConfiguration,
      reviewerState: ReviewerLifecycleState.completed,
      createdAt: _timestamp,
      updatedAt: _timestamp,
      messages: const <ChatMessage>[],
    );
  }
}
