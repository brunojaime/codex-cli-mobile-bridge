import 'package:codex_mobile_frontend/src/models/chat_message.dart';
import 'package:codex_mobile_frontend/src/models/chat_session_summary.dart';
import 'package:codex_mobile_frontend/src/models/codex_tooling.dart';
import 'package:codex_mobile_frontend/src/models/session_detail.dart';
import 'package:codex_mobile_frontend/src/screens/chat_screen.dart';
import 'package:codex_mobile_frontend/src/services/api_client.dart';
import 'package:codex_mobile_frontend/src/services/chat_notification_service.dart';
import 'package:codex_mobile_frontend/src/state/chat_controller.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('normalizeSelectedCodexMcpServerIds keeps only selectable known ids',
      () {
    final normalized = normalizeSelectedCodexMcpServerIds(
      _toolingSnapshot(
        installState: 'disabled',
        serverPresent: true,
        configMatches: false,
        externalServerStatus: 'disabled',
        externalServerSelectable: false,
      ),
      <String>{
        'project-catalog',
        'github',
        'ghost-server',
      },
    );

    expect(normalized, isEmpty);
    expect(
      normalizeSelectedCodexMcpServerIds(
        _toolingSnapshot(
          installState: 'matching',
          serverPresent: true,
          configMatches: true,
        ),
        <String>{
          'project-catalog',
          'github',
          'ghost-server',
        },
      ),
      <String>{'project-catalog', 'github'},
    );
    expect(
      normalizeSelectedCodexMcpServerIds(null, <String>{'ghost-server'}),
      isEmpty,
    );
  });

  testWidgets('Codex tools sheet installs a repo MCP app and enables it',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1280, 900);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = ChatController(
      apiClient: _McpToolsTestApiClient(),
      notificationService: const NoopChatNotificationService(),
    );
    addTearDown(controller.dispose);
    await controller.refreshSessions();
    await controller.selectSession('session-a');

    final initialTooling = _toolingSnapshot(installState: 'missing');
    final installedTooling = _toolingSnapshot(installState: 'matching');
    var installCallCount = 0;

    await tester.pumpWidget(
      MaterialApp(
        home: ChatScreen(
          initialApiBaseUrl: 'http://localhost:8000',
          notificationService: const NoopChatNotificationService(),
          controllerOverride: controller,
          enableServerBootstrap: false,
          initialCodexTooling: initialTooling,
          codexMcpAppInstallerOverride: (app) async {
            expect(app.appId, 'project-catalog');
            installCallCount += 1;
            return installedTooling;
          },
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Codex tools'));
    await tester.pumpAndSettle();

    expect(find.text('Available MCP apps'), findsOneWidget);
    expect(find.text('Project Catalog'), findsOneWidget);
    expect(find.text('missing'), findsOneWidget);
    expect(find.text('Install & enable'), findsOneWidget);

    await tester.tap(find.text('Install & enable'));
    await tester.pump();
    await tester.pumpAndSettle();

    expect(installCallCount, 1);
    expect(find.text('Enabled for run'), findsOneWidget);
    expect(find.textContaining('Installed into Codex'), findsOneWidget);
  });

  testWidgets('Codex tools sheet can open an MCP app full-screen',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1280, 900);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = ChatController(
      apiClient: _McpToolsTestApiClient(),
      notificationService: const NoopChatNotificationService(),
    );
    addTearDown(controller.dispose);
    await controller.refreshSessions();
    await controller.selectSession('session-a');

    await tester.pumpWidget(
      MaterialApp(
        home: ChatScreen(
          initialApiBaseUrl: 'http://localhost:8000',
          notificationService: const NoopChatNotificationService(),
          controllerOverride: controller,
          enableServerBootstrap: false,
          initialCodexTooling: _toolingSnapshot(installState: 'matching'),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Codex tools'));
    await tester.pumpAndSettle();

    expect(find.text('Open app'), findsOneWidget);
    await tester.tap(find.text('Open app'));
    await tester.pumpAndSettle();

    expect(find.byTooltip('Close app'), findsOneWidget);
    expect(
      find.text(
          'This MCP app is open full-screen. Close it to return to chat.'),
      findsOneWidget,
    );

    await tester.tap(find.byTooltip('Close app'));
    await tester.pumpAndSettle();

    expect(find.byTooltip('Close app'), findsNothing);
  });

  testWidgets('composer command can open an MCP app and infer a focus hint',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1280, 900);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = ChatController(
      apiClient: _McpToolsTestApiClient(),
      notificationService: const NoopChatNotificationService(),
    );
    addTearDown(controller.dispose);
    await controller.refreshSessions();
    await controller.selectSession('session-a');

    await tester.pumpWidget(
      MaterialApp(
        home: ChatScreen(
          initialApiBaseUrl: 'http://localhost:8000',
          notificationService: const NoopChatNotificationService(),
          controllerOverride: controller,
          enableServerBootstrap: false,
          initialCodexTooling: _toolingSnapshot(installState: 'matching'),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.enterText(
        find.byType(TextField).first, 'open project catalog for alpha');
    await tester.pump();
    expect(find.byIcon(Icons.arrow_upward_rounded), findsWidgets);
    await tester.tap(find.byIcon(Icons.arrow_upward_rounded).first);
    await tester.pumpAndSettle();

    expect(find.byTooltip('Close app'), findsOneWidget);
    expect(find.text('Project Catalog'), findsWidgets);
    expect(find.text('focused'), findsOneWidget);
  });

  testWidgets('Codex tools sheet shows drifted apps and reconciles them',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1280, 900);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = ChatController(
      apiClient: _McpToolsTestApiClient(),
      notificationService: const NoopChatNotificationService(),
    );
    addTearDown(controller.dispose);
    await controller.refreshSessions();
    await controller.selectSession('session-a');

    final driftedTooling = _toolingSnapshot(
      installState: 'drifted',
      serverPresent: true,
      driftSummary:
          'args differ between the stored Codex config and the repo app spec',
    );
    final reconciledTooling = _toolingSnapshot(installState: 'matching');
    var installCallCount = 0;

    await tester.pumpWidget(
      MaterialApp(
        home: ChatScreen(
          initialApiBaseUrl: 'http://localhost:8000',
          notificationService: const NoopChatNotificationService(),
          controllerOverride: controller,
          enableServerBootstrap: false,
          initialCodexTooling: driftedTooling,
          codexMcpAppInstallerOverride: (app) async {
            expect(app.appId, 'project-catalog');
            installCallCount += 1;
            return reconciledTooling;
          },
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Codex tools'));
    await tester.pumpAndSettle();

    expect(find.text('drifted'), findsOneWidget);
    expect(find.text('Reconcile & enable'), findsOneWidget);
    expect(
      find.textContaining('args differ between the stored Codex config'),
      findsOneWidget,
    );

    await tester.ensureVisible(find.text('Reconcile & enable'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Reconcile & enable'));
    await tester.pump();
    await tester.pumpAndSettle();

    expect(installCallCount, 1);
    expect(find.text('Enabled for run'), findsOneWidget);
    expect(find.textContaining('Installed into Codex'), findsOneWidget);
  });

  testWidgets('Configured server chip for matching repo app remains selectable',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1280, 900);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = ChatController(
      apiClient: _McpToolsTestApiClient(),
      notificationService: const NoopChatNotificationService(),
    );
    addTearDown(controller.dispose);
    await controller.refreshSessions();
    await controller.selectSession('session-a');

    await tester.pumpWidget(
      MaterialApp(
        home: ChatScreen(
          initialApiBaseUrl: 'http://localhost:8000',
          notificationService: const NoopChatNotificationService(),
          controllerOverride: controller,
          enableServerBootstrap: false,
          initialCodexTooling: _toolingSnapshot(
            installState: 'matching',
            serverPresent: true,
            configMatches: true,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Codex tools'));
    await tester.pumpAndSettle();

    final chip = tester.widget<FilterChip>(
      find.widgetWithText(FilterChip, 'project-catalog'),
    );
    expect(chip.onSelected, isNotNull);
  });

  testWidgets(
      'Configured server chip for unhealthy repo app is disabled while external servers remain selectable',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1280, 900);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = ChatController(
      apiClient: _McpToolsTestApiClient(),
      notificationService: const NoopChatNotificationService(),
    );
    addTearDown(controller.dispose);
    await controller.refreshSessions();
    await controller.selectSession('session-a');

    await tester.pumpWidget(
      MaterialApp(
        home: ChatScreen(
          initialApiBaseUrl: 'http://localhost:8000',
          notificationService: const NoopChatNotificationService(),
          controllerOverride: controller,
          enableServerBootstrap: false,
          initialCodexTooling: _toolingSnapshot(
            installState: 'disabled',
            serverPresent: true,
            configMatches: false,
            driftSummary:
                'args differ between the stored Codex config and the repo app spec',
            disabledReason: '{"Authorization":"[redacted]"}',
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Codex tools'));
    await tester.pumpAndSettle();

    final repoChip = tester.widget<FilterChip>(
      find.widgetWithText(FilterChip, 'project-catalog'),
    );
    final externalChip = tester.widget<FilterChip>(
      find.widgetWithText(FilterChip, 'github'),
    );
    expect(repoChip.onSelected, isNull);
    expect(externalChip.onSelected, isNotNull);
    expect(find.text('Reconcile & enable'), findsOneWidget);
  });

  testWidgets(
      'Configured external server chip is disabled when the server is disabled',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1280, 900);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = ChatController(
      apiClient: _McpToolsTestApiClient(),
      notificationService: const NoopChatNotificationService(),
    );
    addTearDown(controller.dispose);
    await controller.refreshSessions();
    await controller.selectSession('session-a');

    await tester.pumpWidget(
      MaterialApp(
        home: ChatScreen(
          initialApiBaseUrl: 'http://localhost:8000',
          notificationService: const NoopChatNotificationService(),
          controllerOverride: controller,
          enableServerBootstrap: false,
          initialCodexTooling: _toolingSnapshot(
            installState: 'matching',
            serverPresent: true,
            configMatches: true,
            externalServerStatus: 'disabled',
            externalServerSelectable: false,
            externalServerSelectableReason:
                'This external MCP server is disabled in Codex. Re-enable it before selecting it.',
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Codex tools'));
    await tester.pumpAndSettle();

    final repoChip = tester.widget<FilterChip>(
      find.widgetWithText(FilterChip, 'project-catalog'),
    );
    final externalChip = tester.widget<FilterChip>(
      find.widgetWithText(FilterChip, 'github'),
    );
    expect(repoChip.onSelected, isNotNull);
    expect(externalChip.onSelected, isNull);
  });

  testWidgets(
      'Configured external server chip is disabled when the server is unreadable',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1280, 900);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = ChatController(
      apiClient: _McpToolsTestApiClient(),
      notificationService: const NoopChatNotificationService(),
    );
    addTearDown(controller.dispose);
    await controller.refreshSessions();
    await controller.selectSession('session-a');

    await tester.pumpWidget(
      MaterialApp(
        home: ChatScreen(
          initialApiBaseUrl: 'http://localhost:8000',
          notificationService: const NoopChatNotificationService(),
          controllerOverride: controller,
          enableServerBootstrap: false,
          initialCodexTooling: _toolingSnapshot(
            installState: 'matching',
            serverPresent: true,
            configMatches: true,
            externalServerStatus: 'unreadable',
            externalServerSelectable: false,
            externalServerSelectableReason:
                'Codex reported this external MCP server, but its stored config is unreadable. Fix the stored Codex server entry before selecting it.',
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Codex tools'));
    await tester.pumpAndSettle();

    final repoChip = tester.widget<FilterChip>(
      find.widgetWithText(FilterChip, 'project-catalog'),
    );
    final externalChip = tester.widget<FilterChip>(
      find.widgetWithText(FilterChip, 'github'),
    );
    expect(repoChip.onSelected, isNotNull);
    expect(externalChip.onSelected, isNull);
  });

  testWidgets(
      'Codex tools sheet shows incomplete inventory message and disables all MCP server chips',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1280, 900);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = ChatController(
      apiClient: _McpToolsTestApiClient(),
      notificationService: const NoopChatNotificationService(),
    );
    addTearDown(controller.dispose);
    await controller.refreshSessions();
    await controller.selectSession('session-a');

    await tester.pumpWidget(
      MaterialApp(
        home: ChatScreen(
          initialApiBaseUrl: 'http://localhost:8000',
          notificationService: const NoopChatNotificationService(),
          controllerOverride: controller,
          enableServerBootstrap: false,
          initialCodexTooling: _toolingSnapshot(
            installState: 'matching',
            serverPresent: true,
            configMatches: true,
            mcpServerInventoryComplete: false,
            mcpError: 'Partial MCP list failed.',
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Codex tools'));
    await tester.pumpAndSettle();

    expect(
      find.textContaining(
        'Codex MCP inventory is incomplete, so direct MCP server selection is temporarily unavailable.',
      ),
      findsOneWidget,
    );
    expect(find.textContaining('Partial MCP list failed.'), findsOneWidget);

    final repoChip = tester.widget<FilterChip>(
      find.widgetWithText(FilterChip, 'project-catalog'),
    );
    final externalChip = tester.widget<FilterChip>(
      find.widgetWithText(FilterChip, 'github'),
    );
    expect(repoChip.onSelected, isNull);
    expect(externalChip.onSelected, isNull);
  });

  testWidgets('Codex tools sheet shows disabled matching apps as re-enable',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1280, 900);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = ChatController(
      apiClient: _McpToolsTestApiClient(),
      notificationService: const NoopChatNotificationService(),
    );
    addTearDown(controller.dispose);
    await controller.refreshSessions();
    await controller.selectSession('session-a');

    await tester.pumpWidget(
      MaterialApp(
        home: ChatScreen(
          initialApiBaseUrl: 'http://localhost:8000',
          notificationService: const NoopChatNotificationService(),
          controllerOverride: controller,
          enableServerBootstrap: false,
          initialCodexTooling: _toolingSnapshot(
            installState: 'disabled',
            serverPresent: true,
            configMatches: true,
            disabledReason: 'Authorization: [redacted]',
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Codex tools'));
    await tester.pumpAndSettle();

    expect(find.text('disabled'), findsOneWidget);
    expect(find.text('Re-enable & use'), findsOneWidget);
    expect(
      find.textContaining('exists but is disabled'),
      findsOneWidget,
    );
  });

  testWidgets('Codex tools sheet shows disabled drifted apps as reconcile',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1280, 900);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = ChatController(
      apiClient: _McpToolsTestApiClient(),
      notificationService: const NoopChatNotificationService(),
    );
    addTearDown(controller.dispose);
    await controller.refreshSessions();
    await controller.selectSession('session-a');

    await tester.pumpWidget(
      MaterialApp(
        home: ChatScreen(
          initialApiBaseUrl: 'http://localhost:8000',
          notificationService: const NoopChatNotificationService(),
          controllerOverride: controller,
          enableServerBootstrap: false,
          initialCodexTooling: _toolingSnapshot(
            installState: 'disabled',
            serverPresent: true,
            configMatches: false,
            driftSummary:
                'args differ between the stored Codex config and the repo app spec',
            disabledReason: '{"Authorization":"[redacted]"}',
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Codex tools'));
    await tester.pumpAndSettle();

    expect(find.text('disabled-drifted'), findsOneWidget);
    expect(find.text('Reconcile & enable'), findsOneWidget);
    expect(
      find.textContaining('disabled and no longer matches this repo app'),
      findsOneWidget,
    );
  });
}

CodexToolingSnapshot _toolingSnapshot({
  required String installState,
  bool serverPresent = false,
  bool serverPresenceKnown = true,
  bool? configMatches,
  String? driftSummary,
  String? disabledReason,
  bool mcpServerInventoryComplete = true,
  String? mcpError,
  String externalServerStatus = 'healthy',
  bool externalServerSelectable = true,
  String? externalServerSelectableReason,
}) {
  final sharedInventoryReason = mcpServerInventoryComplete
      ? null
      : 'Codex MCP inventory is incomplete, so direct MCP server selection is temporarily unavailable. ${mcpError ?? "Retry `codex mcp list` when the CLI is healthy."}';
  final repoServerSelectable =
      mcpServerInventoryComplete && installState == 'matching';
  return CodexToolingSnapshot(
    status: const CodexStatus(
      cliAvailable: true,
      command: 'codex',
      statusSummary: 'Logged in using ChatGPT',
    ),
    mcpServers: <CodexMcpServer>[
      CodexMcpServer(
        serverId: 'project-catalog',
        summary:
            'project-catalog: uv run python -m mcp_apps.project_catalog.server',
        source: 'repo_app',
        backingAppId: 'project-catalog',
        status: installState,
        selectable: repoServerSelectable,
        selectableReason: repoServerSelectable
            ? null
            : sharedInventoryReason ??
                'Repo-backed server must be fixed from the app card first.',
      ),
      CodexMcpServer(
        serverId: 'github',
        summary: 'github: GitHub connector available',
        source: 'external',
        status: externalServerStatus,
        selectable: mcpServerInventoryComplete && externalServerSelectable,
        selectableReason:
            sharedInventoryReason ?? externalServerSelectableReason,
      ),
    ],
    mcpApps: <CodexMcpApp>[
      CodexMcpApp(
        appId: 'project-catalog',
        name: 'Project Catalog',
        description: 'List local projects',
        recommendedServerId: 'project-catalog',
        transport: 'stdio',
        command: 'uv',
        specPath: '/repo/mcp_apps/project_catalog/app.json',
        args: const <String>[
          'run',
          'python',
          '-m',
          'mcp_apps.project_catalog.server',
        ],
        env: const <String, String>{
          'PROJECTS_ROOT': '/projects',
        },
        installed: installState == 'matching',
        installState: installState,
        serverPresent: serverPresent,
        serverPresenceKnown: serverPresenceKnown,
        configMatches: configMatches,
        tools: const <CodexMcpAppTool>[
          CodexMcpAppTool(name: 'list_projects'),
        ],
        preview: const CodexMcpAppPreview(
          toolName: 'list_projects',
          result: <String, Object?>{
            'project_count': 1,
            'projects': <Map<String, Object?>>[
              <String, Object?>{
                'name': 'alpha',
                'detected_languages': <String>['Dart'],
                'signature_files': <String>['README.md'],
              },
            ],
          },
        ),
        driftSummary: driftSummary,
        disabledReason: disabledReason,
      ),
    ],
    mcpServerInventoryComplete: mcpServerInventoryComplete,
    mcpError: mcpError,
  );
}

class _McpToolsTestApiClient extends ApiClient {
  _McpToolsTestApiClient() : super(baseUrl: 'http://localhost:8000');

  static final DateTime _timestamp = DateTime.utc(2026, 1, 1);

  @override
  Future<List<ChatSessionSummary>> listSessions() async {
    return <ChatSessionSummary>[
      ChatSessionSummary(
        id: 'session-a',
        title: 'Chat A',
        workspacePath: '/workspace/a',
        workspaceName: 'Workspace A',
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
      createdAt: _timestamp,
      updatedAt: _timestamp,
      messages: const <ChatMessage>[],
    );
  }
}
