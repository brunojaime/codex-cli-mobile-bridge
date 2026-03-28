import 'package:codex_mobile_frontend/src/models/agent_configuration.dart';
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

  test('refreshAppState reloads workspaces, profiles, and current session',
      () async {
    final apiClient = _MutableRefreshApiClient();
    final controller = ChatController(
      apiClient: apiClient,
      notificationService: const NoopChatNotificationService(),
    );

    await controller.refreshSessions();
    await controller.selectSession('session-a');

    apiClient
      ..workspaceName = 'Workspace B'
      ..workspacePath = '/workspace/b'
      ..sessionTitle = 'Chat B'
      ..agentProfiles = <AgentProfile>[
        _testAgentProfile(
          id: 'generator',
          name: 'Generator',
          colorHex: '#55D6BE',
        ),
        _testAgentProfile(
          id: 'reviewer',
          name: 'Reviewer',
          colorHex: '#8CA8FF',
        ),
      ];

    await controller.refreshAppState();

    expect(controller.selectedSessionId, 'session-a');
    expect(controller.currentSession?.title, 'Chat B');
    expect(controller.currentSession?.workspaceName, 'Workspace B');
    expect(
      controller.workspaces.map((workspace) => workspace.name),
      <String>['Workspace B'],
    );
    expect(
      controller.agentProfiles.map((profile) => profile.name),
      <String>['Generator', 'Reviewer'],
    );

    controller.dispose();
  });
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

class _MutableRefreshApiClient extends ApiClient {
  _MutableRefreshApiClient() : super(baseUrl: 'http://localhost:8000');

  static final DateTime _timestamp = DateTime.utc(2026, 1, 1);

  String sessionTitle = 'Chat A';
  String workspacePath = '/workspace/a';
  String workspaceName = 'Workspace A';
  List<AgentProfile> agentProfiles = <AgentProfile>[
    _testAgentProfile(
      id: 'generator',
      name: 'Generator',
      colorHex: '#55D6BE',
    ),
  ];

  @override
  Future<List<ChatSessionSummary>> listSessions() async {
    return <ChatSessionSummary>[
      ChatSessionSummary(
        id: 'session-a',
        title: sessionTitle,
        workspacePath: workspacePath,
        workspaceName: workspaceName,
        agentProfileId: 'generator',
        agentProfileName: 'Generator',
        agentProfileColor: '#55D6BE',
        createdAt: _timestamp,
        updatedAt: _timestamp,
      ),
    ];
  }

  @override
  Future<List<Workspace>> listWorkspaces() async {
    return <Workspace>[
      Workspace(
        name: workspaceName,
        path: workspacePath,
      ),
    ];
  }

  @override
  Future<SessionDetail> getSession(String sessionId) async {
    return SessionDetail(
      id: sessionId,
      title: sessionTitle,
      workspacePath: workspacePath,
      workspaceName: workspaceName,
      createdAt: _timestamp,
      updatedAt: _timestamp,
      messages: const <ChatMessage>[],
    );
  }

  @override
  Future<List<AgentProfile>> listAgentProfiles() async {
    return agentProfiles;
  }
}

AgentProfile _testAgentProfile({
  required String id,
  required String name,
  required String colorHex,
}) {
  return AgentProfile(
    id: id,
    name: name,
    description: '$name profile',
    colorHex: colorHex,
    prompt: 'Prompt for $name',
    configuration: kDefaultAgentConfiguration,
    isBuiltin: true,
  );
}
