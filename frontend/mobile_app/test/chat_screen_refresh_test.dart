import 'package:codex_mobile_frontend/src/models/agent_configuration.dart';
import 'package:codex_mobile_frontend/src/models/agent_profile.dart';
import 'package:codex_mobile_frontend/src/models/chat_message.dart';
import 'package:codex_mobile_frontend/src/models/chat_session_summary.dart';
import 'package:codex_mobile_frontend/src/models/session_detail.dart';
import 'package:codex_mobile_frontend/src/models/workspace.dart';
import 'package:codex_mobile_frontend/src/screens/chat_screen.dart';
import 'package:codex_mobile_frontend/src/services/api_client.dart';
import 'package:codex_mobile_frontend/src/services/chat_notification_service.dart';
import 'package:codex_mobile_frontend/src/state/chat_controller.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('pull to refresh reloads app data used for chats and projects',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final apiClient = _RefreshTrackingApiClient();
    final controller = ChatController(
      apiClient: apiClient,
      notificationService: const NoopChatNotificationService(),
    );
    addTearDown(controller.dispose);

    await controller.refreshSessions();
    await controller.selectSession('session-a');

    expect(controller.workspaces, isEmpty);
    expect(controller.agentProfiles, isEmpty);
    expect(apiClient.listSessionsCallCount, 1);
    expect(apiClient.getSessionCallCount, 1);
    expect(apiClient.listWorkspacesCallCount, 0);
    expect(apiClient.listAgentProfilesCallCount, 0);

    await tester.pumpWidget(
      MaterialApp(
        home: ChatScreen(
          initialApiBaseUrl: 'http://localhost:8000',
          notificationService: const NoopChatNotificationService(),
          controllerOverride: controller,
          enableServerBootstrap: false,
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.drag(
      find.byKey(kChatScreenBodyScrollViewKey),
      const Offset(0, 300),
    );
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    await tester.pumpAndSettle();

    expect(apiClient.listSessionsCallCount, 2);
    expect(apiClient.getSessionCallCount, 2);
    expect(apiClient.listWorkspacesCallCount, 1);
    expect(apiClient.listAgentProfilesCallCount, 1);
    expect(
      controller.workspaces.map((workspace) => workspace.name),
      <String>['Workspace B'],
    );
    expect(
      controller.agentProfiles.map((profile) => profile.name),
      <String>['Generator'],
    );
  });
}

class _RefreshTrackingApiClient extends ApiClient {
  _RefreshTrackingApiClient() : super(baseUrl: 'http://localhost:8000');

  static final DateTime _timestamp = DateTime.utc(2026, 1, 1);

  int listSessionsCallCount = 0;
  int getSessionCallCount = 0;
  int listWorkspacesCallCount = 0;
  int listAgentProfilesCallCount = 0;

  @override
  Future<List<ChatSessionSummary>> listSessions() async {
    listSessionsCallCount += 1;
    return <ChatSessionSummary>[
      ChatSessionSummary(
        id: 'session-a',
        title: 'Chat A',
        workspacePath: '/workspace/b',
        workspaceName: 'Workspace B',
        agentProfileId: 'generator',
        agentProfileName: 'Generator',
        agentProfileColor: '#55D6BE',
        createdAt: _timestamp,
        updatedAt: _timestamp,
      ),
    ];
  }

  @override
  Future<SessionDetail> getSession(String sessionId) async {
    getSessionCallCount += 1;
    return SessionDetail(
      id: sessionId,
      title: 'Chat A',
      workspacePath: '/workspace/b',
      workspaceName: 'Workspace B',
      createdAt: _timestamp,
      updatedAt: _timestamp,
      messages: <ChatMessage>[
        ChatMessage(
          id: 'assistant-1',
          text: 'Assistant update',
          isUser: false,
          authorType: ChatMessageAuthorType.assistant,
          status: ChatMessageStatus.completed,
          createdAt: _timestamp,
          updatedAt: _timestamp,
        ),
      ],
    );
  }

  @override
  Future<List<Workspace>> listWorkspaces() async {
    listWorkspacesCallCount += 1;
    return const <Workspace>[
      Workspace(
        name: 'Workspace B',
        path: '/workspace/b',
      ),
    ];
  }

  @override
  Future<List<AgentProfile>> listAgentProfiles() async {
    listAgentProfilesCallCount += 1;
    return <AgentProfile>[
      AgentProfile(
        id: 'generator',
        name: 'Generator',
        description: 'Default generator',
        colorHex: '#55D6BE',
        prompt: 'Prompt',
        configuration: kDefaultAgentConfiguration,
        isBuiltin: true,
      ),
    ];
  }
}
