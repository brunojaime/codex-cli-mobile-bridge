import 'package:codex_mobile_frontend/src/models/chat_message.dart';
import 'package:codex_mobile_frontend/src/models/agent_profile.dart';
import 'package:codex_mobile_frontend/src/models/chat_session_summary.dart';
import 'package:codex_mobile_frontend/src/models/session_detail.dart';
import 'package:codex_mobile_frontend/src/models/workspace.dart';
import 'package:codex_mobile_frontend/src/services/api_client.dart';
import 'package:codex_mobile_frontend/src/services/chat_notification_service.dart';
import 'package:codex_mobile_frontend/src/state/chat_controller.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test(
    'initialize keeps sessions and workspaces usable when agent profiles fail',
    () async {
      final controller = ChatController(
        apiClient: _FailingAgentProfilesApiClient(),
        notificationService: const NoopChatNotificationService(),
      );

      await controller.initialize();

      expect(controller.sessions, hasLength(1));
      expect(controller.workspaces, hasLength(1));
      expect(controller.selectedSessionId, 'session-a');
      expect(controller.currentSession?.id, 'session-a');
      expect(controller.currentSession?.title, 'Chat A');
      expect(controller.isLoading, isFalse);
      expect(controller.errorText, contains('Agent profiles are unavailable.'));

      controller.dispose();
    },
  );
}

class _FailingAgentProfilesApiClient extends ApiClient {
  _FailingAgentProfilesApiClient() : super(baseUrl: 'http://localhost:8000');

  static final DateTime _timestamp = DateTime.utc(2026, 1, 1);

  @override
  Future<List<ChatSessionSummary>> listSessions() async {
    return <ChatSessionSummary>[
      ChatSessionSummary(
        id: 'session-a',
        title: 'Chat A',
        workspacePath: '/workspace/a',
        workspaceName: 'Workspace A',
        agentProfileId: 'default',
        agentProfileName: 'Generator',
        agentProfileColor: '#55D6BE',
        createdAt: _timestamp,
        updatedAt: _timestamp,
      ),
    ];
  }

  @override
  Future<List<Workspace>> listWorkspaces() async {
    return const <Workspace>[
      Workspace(
        name: 'Workspace A',
        path: '/workspace/a',
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
      createdAt: _timestamp,
      updatedAt: _timestamp,
      messages: const <ChatMessage>[],
    );
  }

  @override
  Future<List<AgentProfile>> listAgentProfiles() {
    throw Exception('404 Not Found: /agent-profiles');
  }
}
