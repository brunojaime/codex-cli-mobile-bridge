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
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  testWidgets(
    'choose project opens even when the backend returns no agent profiles',
    (tester) async {
      SharedPreferences.setMockInitialValues(<String, Object>{});

      final controller = ChatController(
        apiClient: _NewChatPickerApiClient(),
        notificationService: const NoopChatNotificationService(),
      );
      await controller.refreshWorkspaces();
      addTearDown(controller.dispose);

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

      await tester.tap(find.widgetWithText(FilledButton, 'New Chat'));
      await tester.pumpAndSettle();

      expect(find.text('Choose Existing Project'), findsOneWidget);
      expect(find.text('Project Alpha'), findsOneWidget);
      expect(
          find.byType(DropdownButtonFormField<AgentProfile>), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'choose project still opens when agent profiles request fails',
    (tester) async {
      SharedPreferences.setMockInitialValues(<String, Object>{});

      final controller = ChatController(
        apiClient: _ThrowingAgentProfilesApiClient(),
        notificationService: const NoopChatNotificationService(),
      );
      await controller.refreshWorkspaces();
      addTearDown(controller.dispose);

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

      await tester.tap(find.widgetWithText(FilledButton, 'New Chat'));
      await tester.pumpAndSettle();

      expect(find.text('Choose Existing Project'), findsOneWidget);
      expect(find.text('Project Beta'), findsOneWidget);
      expect(
          find.byType(DropdownButtonFormField<AgentProfile>), findsOneWidget);
      expect(
        find.textContaining(
          'Agent profiles are unavailable. Using the built-in Generator profile for this new chat.',
        ),
        findsOneWidget,
      );
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'new chat uses the built-in Generator profile when agent profiles fail',
    (tester) async {
      SharedPreferences.setMockInitialValues(<String, Object>{});
      tester.view.physicalSize = const Size(1280, 900);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final apiClient = _CreateSessionFallbackApiClient();
      final controller = ChatController(
        apiClient: apiClient,
        notificationService: const NoopChatNotificationService(),
      );
      await controller.refreshSessions();
      await controller.refreshWorkspaces();
      await controller.selectSession('session-custom');
      addTearDown(controller.dispose);

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

      await tester.tap(find.byTooltip('Choose project for new chat'));
      await tester.pumpAndSettle();

      expect(find.text('Choose Existing Project'), findsOneWidget);
      expect(
        find.textContaining(
          'Agent profiles are unavailable. Using the built-in Generator profile for this new chat.',
        ),
        findsOneWidget,
      );

      await tester.tap(find.text('Project Gamma'));
      await tester.pumpAndSettle();

      expect(apiClient.createdSessionAgentProfileId, 'default');
      expect(apiClient.createdSessionAgentProfileId, isNot('custom-pack'));
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'new chat picker can disable turn summaries for the created session',
    (tester) async {
      SharedPreferences.setMockInitialValues(<String, Object>{});

      final apiClient = _CreateSessionFallbackApiClient();
      final controller = ChatController(
        apiClient: apiClient,
        notificationService: const NoopChatNotificationService(),
      );
      await controller.refreshWorkspaces();
      addTearDown(controller.dispose);

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

      await tester.tap(find.widgetWithText(FilledButton, 'New Chat'));
      await tester.pumpAndSettle();

      expect(find.text('Enable summarizer'), findsOneWidget);

      await tester.tap(find.byType(Switch).first);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Project Gamma'));
      await tester.pumpAndSettle();

      expect(apiClient.createdSessionTurnSummariesEnabled, isFalse);
    },
  );
}

class _NewChatPickerApiClient extends ApiClient {
  _NewChatPickerApiClient() : super(baseUrl: 'http://localhost:8000');

  @override
  Future<List<ChatSessionSummary>> listSessions() async {
    return const <ChatSessionSummary>[];
  }

  @override
  Future<List<Workspace>> listWorkspaces() async {
    return const <Workspace>[
      Workspace(
        name: 'Project Alpha',
        path: '/workspace/project-alpha',
      ),
    ];
  }

  @override
  Future<List<AgentProfile>> listAgentProfiles() async {
    return const <AgentProfile>[];
  }
}

class _ThrowingAgentProfilesApiClient extends ApiClient {
  _ThrowingAgentProfilesApiClient() : super(baseUrl: 'http://localhost:8000');

  @override
  Future<List<ChatSessionSummary>> listSessions() async {
    return const <ChatSessionSummary>[];
  }

  @override
  Future<List<Workspace>> listWorkspaces() async {
    return const <Workspace>[
      Workspace(
        name: 'Project Beta',
        path: '/workspace/project-beta',
      ),
    ];
  }

  @override
  Future<List<AgentProfile>> listAgentProfiles() async {
    throw Exception('404 Not Found: /agent-profiles');
  }
}

class _CreateSessionFallbackApiClient extends ApiClient {
  _CreateSessionFallbackApiClient() : super(baseUrl: 'http://localhost:8000');

  static final DateTime _timestamp = DateTime.utc(2026, 1, 1);
  String? createdSessionAgentProfileId;
  String? createdSessionWorkspacePath;
  bool? createdSessionTurnSummariesEnabled;
  SessionDetail? _createdSession;

  @override
  Future<List<ChatSessionSummary>> listSessions() async {
    return <ChatSessionSummary>[
      ChatSessionSummary(
        id: 'session-custom',
        title: 'Custom Chat',
        workspacePath: '/workspace/custom',
        workspaceName: 'Custom Workspace',
        agentProfileId: 'custom-pack',
        agentProfileName: 'Custom Pack',
        agentProfileColor: '#1188AA',
        createdAt: _timestamp,
        updatedAt: _timestamp,
      ),
      if (_createdSession != null)
        ChatSessionSummary(
          id: _createdSession!.id,
          title: _createdSession!.title,
          workspacePath: _createdSession!.workspacePath,
          workspaceName: _createdSession!.workspaceName,
          agentProfileId: _createdSession!.agentProfileId,
          agentProfileName: _createdSession!.agentProfileName,
          agentProfileColor: _createdSession!.agentProfileColor,
          createdAt: _createdSession!.createdAt,
          updatedAt: _createdSession!.updatedAt,
        ),
    ];
  }

  @override
  Future<List<Workspace>> listWorkspaces() async {
    return const <Workspace>[
      Workspace(
        name: 'Project Gamma',
        path: '/workspace/project-gamma',
      ),
    ];
  }

  @override
  Future<SessionDetail> getSession(String sessionId) async {
    if (_createdSession != null && _createdSession!.id == sessionId) {
      return _createdSession!;
    }
    return SessionDetail(
      id: sessionId,
      title: 'Custom Chat',
      workspacePath: '/workspace/custom',
      workspaceName: 'Custom Workspace',
      agentProfileId: 'custom-pack',
      agentProfileName: 'Custom Pack',
      agentProfileColor: '#1188AA',
      createdAt: _timestamp,
      updatedAt: _timestamp,
      messages: const <ChatMessage>[],
    );
  }

  @override
  Future<List<AgentProfile>> listAgentProfiles() async {
    throw Exception('404 Not Found: /agent-profiles');
  }

  @override
  Future<SessionDetail> createSession({
    String? title,
    String? workspacePath,
    String? agentProfileId,
    bool turnSummariesEnabled = false,
  }) async {
    createdSessionAgentProfileId = agentProfileId;
    createdSessionWorkspacePath = workspacePath;
    createdSessionTurnSummariesEnabled = turnSummariesEnabled;
    _createdSession = SessionDetail(
      id: 'session-generated',
      title: title ?? 'Project Gamma',
      workspacePath: workspacePath ?? '/workspace/project-gamma',
      workspaceName: 'Project Gamma',
      turnSummariesEnabled: turnSummariesEnabled,
      agentProfileId: agentProfileId ?? 'default',
      agentProfileName: agentProfileId == 'default' || agentProfileId == null
          ? 'Generator'
          : 'Unexpected',
      agentProfileColor: '#55D6BE',
      createdAt: _timestamp,
      updatedAt: _timestamp,
      messages: const <ChatMessage>[],
    );
    return _createdSession!;
  }
}
