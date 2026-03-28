import 'package:codex_mobile_frontend/src/models/agent_configuration.dart';
import 'package:codex_mobile_frontend/src/models/chat_message.dart';
import 'package:codex_mobile_frontend/src/models/chat_session_summary.dart';
import 'package:codex_mobile_frontend/src/models/conversation_product.dart';
import 'package:codex_mobile_frontend/src/models/current_run_execution.dart';
import 'package:codex_mobile_frontend/src/models/reviewer_lifecycle_state.dart';
import 'package:codex_mobile_frontend/src/models/session_detail.dart';
import 'package:codex_mobile_frontend/src/models/workspace.dart';
import 'package:codex_mobile_frontend/src/screens/chat_screen.dart';
import 'package:codex_mobile_frontend/src/services/api_client.dart';
import 'package:codex_mobile_frontend/src/services/chat_notification_service.dart';
import 'package:codex_mobile_frontend/src/services/server_profile_store.dart';
import 'package:codex_mobile_frontend/src/state/chat_controller.dart';
import 'package:codex_mobile_frontend/src/widgets/agent_studio_status_button.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:async';

void main() {
  testWidgets('conversation context sheet scrolls safely for long content',
      (WidgetTester tester) async {
    final longText = List<String>.filled(
      24,
      'This is a deliberately long conversation-product section used to verify the bottom sheet can scroll without overflowing on short viewports.',
    ).join(' ');
    await _pumpChatScreen(
      tester,
      width: 800,
      height: 420,
      session: _buildSession(
        messages: <ChatMessage>[
          _message(
            id: 'assistant-1',
            text: 'Assistant update',
          ),
        ],
        conversationProduct: ConversationProduct(
          statusLine: 'Generator running',
          description: longText,
          latestUpdate: longText,
          currentFocus: longText,
          nextStep: longText,
        ),
      ),
    );

    await tester.tap(find.byTooltip('What are we doing?'));
    await tester.pumpAndSettle();

    final bottomSheet = find.byType(BottomSheet);
    expect(
      find.descendant(
        of: bottomSheet,
        matching: find.text('Summary'),
      ),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('conversation-context-scroll-view')),
      findsOneWidget,
    );
    final bottomSheetScrollable = find.descendant(
      of: bottomSheet,
      matching: find.byType(Scrollable),
    );
    expect(bottomSheetScrollable, findsOneWidget);

    await tester.scrollUntilVisible(
      find.descendant(
        of: bottomSheet,
        matching: find.text('Next step'),
      ),
      120,
      scrollable: bottomSheetScrollable,
    );
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
  });

  testWidgets('agent studio model override can be set and cleared',
      (WidgetTester tester) async {
    final apiClient = _ChatScreenOverflowApiClient(
      _buildSession(
        messages: const <ChatMessage>[],
      ),
    );

    await _pumpChatScreen(
      tester,
      width: 800,
      session: apiClient.session,
      apiClient: apiClient,
    );

    await tester.tap(find.byType(AgentStudioStatusButton));
    await tester.pumpAndSettle();

    final agentStudioSheet = find.byType(BottomSheet);
    final agentStudioScrollable = find
        .descendant(
          of: agentStudioSheet,
          matching: find.byType(Scrollable),
        )
        .last;
    final saveButton = find.descendant(
      of: agentStudioSheet,
      matching: find.widgetWithText(FilledButton, 'Save'),
    );

    await tester.enterText(
      find.byKey(const ValueKey<String>('agent-model-generator')),
      'gpt-5.4-mini',
    );
    await tester.scrollUntilVisible(saveButton, 120,
        scrollable: agentStudioScrollable);
    await tester.tap(saveButton);
    await tester.pumpAndSettle();

    expect(
      apiClient.session.agentConfiguration.byId(AgentId.generator)?.model,
      'gpt-5.4-mini',
    );

    await tester.tap(find.byType(AgentStudioStatusButton));
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const ValueKey<String>('agent-model-generator')),
      '',
    );
    await tester.scrollUntilVisible(saveButton, 120,
        scrollable: agentStudioScrollable);
    await tester.tap(saveButton);
    await tester.pumpAndSettle();

    expect(
      apiClient.session.agentConfiguration.byId(AgentId.generator)?.model,
      isNull,
    );
    final generatorPayload = (apiClient.session.agentConfiguration
            .toJson()['agents'] as List<dynamic>)
        .cast<Map<String, dynamic>>()
        .firstWhere((agent) => agent['agent_id'] == 'generator');
    expect(generatorPayload.containsKey('model'), isFalse);
  });

  testWidgets(
      'sidebar session tile shows conversation product status and sanitized description',
      (WidgetTester tester) async {
    final session = _buildSession(
      title: 'Sanitized Chat',
      messages: const <ChatMessage>[],
      conversationProduct: const ConversationProduct(
        statusLine: 'Supervisor ready',
        description: 'Sanitized product update for the user.',
      ),
    );
    const rawPreview =
        'QA found a flaky snapshot and reviewer asked for more tests.';

    await _pumpChatScreen(
      tester,
      session: session,
      apiClient: _ChatScreenOverflowApiClient(
        session,
        lastMessagePreviewBySession: const <String, String?>{
          'session-a': rawPreview,
        },
      ),
      sidebarWorkspaces: const <Workspace>[
        Workspace(name: 'Workspace A', path: '/workspace/a'),
      ],
    );

    tester.state<ScaffoldState>(find.byType(Scaffold)).openDrawer();
    await tester.pumpAndSettle();

    final drawer = find.byType(Drawer);
    expect(
      find.descendant(
        of: drawer,
        matching: find.text('Supervisor ready', skipOffstage: false),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: drawer,
        matching: find.text(
          'Sanitized product update for the user.',
          skipOffstage: false,
        ),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: drawer,
        matching: find.text(rawPreview, skipOffstage: false),
      ),
      findsNothing,
    );
  });

  testWidgets('app bar subtitle includes conversation product status line',
      (WidgetTester tester) async {
    await _pumpChatScreen(
      tester,
      width: 800,
      session: _buildSession(
        messages: const <ChatMessage>[],
        conversationProduct: const ConversationProduct(
          statusLine: 'Supervisor queued next',
          description: 'Sanitized summary',
        ),
      ),
    );

    expect(find.textContaining('Supervisor queued next'), findsOneWidget);
  });

  testWidgets(
      'short viewport keeps reviewer banner, run history, empty state, and composer scrollable',
      (WidgetTester tester) async {
    await _pumpChatScreen(
      tester,
      session: _buildSession(messages: const <ChatMessage>[]),
    );

    expect(tester.takeException(), isNull);
    expect(find.byType(CustomScrollView), findsOneWidget);
    expect(find.text('Safety Reviewer running'), findsOneWidget);
    expect(find.text('Run history'), findsOneWidget);
    expect(find.text('Send a command to your local Codex CLI'), findsOneWidget);

    await tester.ensureVisible(
      find.text('Start a new Codex session', skipOffstage: false),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);

    await tester.ensureVisible(
      find.text('Safety Reviewer running', skipOffstage: false),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });

  testWidgets(
      'short viewport with messages still keeps status panels reachable by scrolling',
      (WidgetTester tester) async {
    await _pumpChatScreen(
      tester,
      session: _buildSession(
        messages: <ChatMessage>[
          _message(
            id: 'user-1',
            text: 'User prompt',
            isUser: true,
            authorType: ChatMessageAuthorType.human,
            agentId: AgentId.user,
            agentType: AgentType.human,
          ),
          _message(
            id: 'assistant-1',
            text: 'Assistant update',
          ),
        ],
      ),
    );

    expect(tester.takeException(), isNull);
    expect(find.text('Run history'), findsOneWidget);

    await tester.scrollUntilVisible(
      find.text('Assistant update'),
      120,
      scrollable: _chatBodyScrollable(),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);

    await tester.ensureVisible(
      find.text('Safety Reviewer running', skipOffstage: false),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });

  testWidgets(
      'keyboard inset keeps composer compressed while the body remains scrollable',
      (WidgetTester tester) async {
    await _pumpChatScreen(
      tester,
      keyboardInsetBottom: 220,
      session: _buildSession(
        messages: <ChatMessage>[
          _message(
            id: 'user-1',
            text: 'User ping',
            isUser: true,
            authorType: ChatMessageAuthorType.human,
            agentId: AgentId.user,
            agentType: AgentType.human,
          ),
          _message(
            id: 'assistant-1',
            text: 'Assistant reply',
          ),
        ],
      ),
    );

    expect(tester.takeException(), isNull);
    expect(find.text('Send a command to your local Codex CLI'), findsOneWidget);

    await tester.scrollUntilVisible(
      find.text('Assistant reply'),
      120,
      scrollable: _chatBodyScrollable(),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);

    await tester.ensureVisible(
      find.text('Run history', skipOffstage: false),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });

  testWidgets('messages can be collapsed independently in chat screen',
      (WidgetTester tester) async {
    await _pumpChatScreen(
      tester,
      session: _buildSession(
        messages: <ChatMessage>[
          _message(
            id: 'user-a',
            text:
                'User-authored note that should still be individually collapsible.',
            isUser: true,
            authorType: ChatMessageAuthorType.human,
            agentId: AgentId.user,
            agentType: AgentType.human,
          ),
          _message(
            id: 'assistant-a',
            text: 'First visible message',
          ),
          _message(
            id: 'assistant-b',
            text: 'Second visible message',
          ),
        ],
      ),
    );

    final userBubble = find.byKey(const ValueKey<String>('chat-bubble-user-a'));
    final firstBubble =
        find.byKey(const ValueKey<String>('chat-bubble-assistant-a'));
    final secondBubble =
        find.byKey(const ValueKey<String>('chat-bubble-assistant-b'));

    expect(tester.takeException(), isNull);
    await tester.scrollUntilVisible(
      find.textContaining(
        'User-authored note that should still be individually collapsible.',
      ),
      120,
      scrollable: _chatBodyScrollable(),
    );
    await tester.pumpAndSettle();
    await tester.drag(_chatBodyScrollable(), const Offset(0, 96));
    await tester.pumpAndSettle();

    expect(userBubble, findsOneWidget);
    expect(firstBubble, findsOneWidget);

    await tester.tap(
      find.descendant(
        of: userBubble,
        matching: find.text('Collapse'),
      ),
    );
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(
      find.descendant(of: userBubble, matching: find.text('Expand')),
      findsOneWidget,
    );
    expect(
      find.descendant(of: userBubble, matching: find.text('Message collapsed')),
      findsOneWidget,
    );
    expect(find.text('First visible message'), findsOneWidget);

    await tester.tap(
      find.descendant(
        of: firstBubble,
        matching: find.text('Collapse'),
      ),
    );
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(
      find.descendant(of: firstBubble, matching: find.text('Expand')),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: firstBubble,
        matching: find.text('Message collapsed'),
      ),
      findsOneWidget,
    );

    await tester.scrollUntilVisible(
      find.text('Second visible message'),
      120,
      scrollable: _chatBodyScrollable(),
    );
    await tester.pumpAndSettle();

    expect(secondBubble, findsOneWidget);
    expect(
      find.descendant(of: secondBubble, matching: find.text('Collapse')),
      findsOneWidget,
    );
    expect(find.text('Second visible message'), findsOneWidget);
  });

  testWidgets(
      'collapse specialists can switch back to show all messages from the placeholder',
      (WidgetTester tester) async {
    await _pumpChatScreen(
      tester,
      session: _buildSession(
        displayMode: AgentDisplayMode.collapseSpecialists,
        messages: <ChatMessage>[
          _message(
            id: 'reviewer-hidden',
            text: 'Reviewer-only content',
            isUser: true,
            authorType: ChatMessageAuthorType.reviewerCodex,
            agentId: AgentId.reviewer,
            agentType: AgentType.reviewer,
            visibility: AgentVisibilityMode.collapsed,
          ),
        ],
      ),
    );

    expect(tester.takeException(), isNull);
    expect(find.text('Start a new Codex session'), findsNothing);
    expect(find.text('Run history'), findsOneWidget);
    expect(find.text('Send a command to your local Codex CLI'), findsOneWidget);

    await tester.ensureVisible(
      find.text('Messages hidden in this view', skipOffstage: false),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(
      find.textContaining('Collapse specialists', skipOffstage: false),
      findsOneWidget,
    );
    await tester.scrollUntilVisible(
      find.text('Show all messages', skipOffstage: false),
      120,
      scrollable: _chatBodyScrollable(),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Show all messages', skipOffstage: false));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(find.text('Messages hidden in this view'), findsNothing);
    await tester.scrollUntilVisible(
      find.text('Reviewer-only content'),
      120,
      scrollable: _chatBodyScrollable(),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(find.text('Reviewer-only content'), findsOneWidget);
  });

  testWidgets(
      'summary only can switch back to show all messages from the placeholder',
      (WidgetTester tester) async {
    await _pumpChatScreen(
      tester,
      session: _buildSession(
        displayMode: AgentDisplayMode.summaryOnly,
        messages: <ChatMessage>[
          _message(
            id: 'generator-message',
            text: 'Generator content',
          ),
          _message(
            id: 'reviewer-message',
            text: 'Reviewer content',
            isUser: true,
            authorType: ChatMessageAuthorType.reviewerCodex,
            agentId: AgentId.reviewer,
            agentType: AgentType.reviewer,
          ),
        ],
      ),
    );

    expect(tester.takeException(), isNull);
    expect(find.text('Start a new Codex session'), findsNothing);
    expect(find.text('Run history'), findsOneWidget);
    expect(find.text('Send a command to your local Codex CLI'), findsOneWidget);

    await tester.ensureVisible(
      find.text('Messages hidden in this view', skipOffstage: false),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(
      find.textContaining('Summary only', skipOffstage: false),
      findsOneWidget,
    );
    await tester.scrollUntilVisible(
      find.text('Show all messages', skipOffstage: false),
      120,
      scrollable: _chatBodyScrollable(),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Show all messages', skipOffstage: false));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(find.text('Messages hidden in this view'), findsNothing);
    await tester.scrollUntilVisible(
      find.text('Generator content'),
      120,
      scrollable: _chatBodyScrollable(),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(find.text('Generator content'), findsOneWidget);
    expect(find.text('Reviewer content'), findsOneWidget);
  });

  testWidgets(
      'show all messages CTA keeps filtered placeholder visible through pending, failure, and retry recovery',
      (WidgetTester tester) async {
    final session = _buildSession(
      displayMode: AgentDisplayMode.collapseSpecialists,
      messages: <ChatMessage>[
        _message(
          id: 'reviewer-hidden',
          text: 'Reviewer-only content',
          isUser: true,
          authorType: ChatMessageAuthorType.reviewerCodex,
          agentId: AgentId.reviewer,
          agentType: AgentType.reviewer,
          visibility: AgentVisibilityMode.collapsed,
        ),
      ],
    );
    final pendingUpdate = Completer<SessionDetail>();
    final apiClient = _ChatScreenOverflowApiClient(
      session,
      onUpdateAgentConfiguration: (
        String sessionId,
        AgentConfiguration configuration,
      ) {
        return pendingUpdate.future;
      },
    );

    await _pumpChatScreen(
      tester,
      session: session,
      apiClient: apiClient,
    );

    await tester.scrollUntilVisible(
      find.text('Show all messages', skipOffstage: false),
      120,
      scrollable: _chatBodyScrollable(),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Show all messages', skipOffstage: false));
    await tester.pump();

    expect(tester.takeException(), isNull);
    expect(find.text('Messages hidden in this view'), findsOneWidget);
    expect(find.text('Updating view...'), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(find.text('Reviewer-only content'), findsNothing);
    expect(
      tester
          .widget<FilledButton>(
            find.widgetWithText(FilledButton, 'Updating view...'),
          )
          .onPressed,
      isNull,
    );
    expect(
      apiClient.session.agentConfiguration.displayMode,
      AgentDisplayMode.collapseSpecialists,
    );

    pendingUpdate.completeError(Exception('Simulated update failure'));
    await tester.pump();
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(find.text('Messages hidden in this view'), findsOneWidget);
    expect(
      find.textContaining('Failed to update agent configuration'),
      findsOneWidget,
    );
    expect(find.text('Reviewer-only content'), findsNothing);
    expect(
      apiClient.session.agentConfiguration.displayMode,
      AgentDisplayMode.collapseSpecialists,
    );

    apiClient.onUpdateAgentConfiguration = (
      String sessionId,
      AgentConfiguration configuration,
    ) async {
      return apiClient.applyAgentConfiguration(configuration);
    };

    await tester.scrollUntilVisible(
      find.text('Show all messages', skipOffstage: false),
      120,
      scrollable: _chatBodyScrollable(),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Show all messages', skipOffstage: false));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(find.text('Messages hidden in this view'), findsNothing);
    expect(
      find.textContaining('Failed to update agent configuration'),
      findsNothing,
    );
    await tester.scrollUntilVisible(
      find.text('Reviewer-only content'),
      120,
      scrollable: _chatBodyScrollable(),
    );
    await tester.pumpAndSettle();
    expect(find.text('Reviewer-only content'), findsOneWidget);
    expect(apiClient.session.agentConfiguration.displayMode,
        AgentDisplayMode.showAll);
  });

  testWidgets(
      'tall run history remains reachable in both directions on a short viewport with keyboard inset',
      (WidgetTester tester) async {
    await _pumpChatScreen(
      tester,
      keyboardInsetBottom: 220,
      session: _buildTallSession(),
    );

    expect(tester.takeException(), isNull);
    expect(find.byKey(kChatScreenBodyScrollViewKey), findsOneWidget);
    expect(find.text('Send a command to your local Codex CLI'), findsOneWidget);

    await tester.ensureVisible(
      find.text('Safety Reviewer running', skipOffstage: false),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);

    await tester.scrollUntilVisible(
      find.textContaining('Completed run run-0004', skipOffstage: false),
      180,
      scrollable: _chatBodyScrollable(),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);

    await tester.scrollUntilVisible(
      find.text('Tail message'),
      180,
      scrollable: _chatBodyScrollable(),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);

    await tester.ensureVisible(
      find.text('Safety Reviewer running', skipOffstage: false),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });

  testWidgets('sidebar can switch between active and archived chats',
      (WidgetTester tester) async {
    final activeSession = _buildSession(
      id: 'session-active',
      title: 'Active Chat',
      messages: const <ChatMessage>[],
    );
    final archivedSession = _buildSession(
      id: 'session-archived',
      title: 'Archived Chat',
      archivedAt: DateTime.utc(2026, 1, 1, 13),
      messages: const <ChatMessage>[],
    );

    await _pumpChatScreen(
      tester,
      session: activeSession,
      apiClient: _ChatScreenOverflowApiClient(
        activeSession,
        additionalSessions: <SessionDetail>[archivedSession],
      ),
      sidebarWorkspaces: const <Workspace>[
        Workspace(name: 'Workspace A', path: '/workspace/a'),
      ],
    );

    tester.state<ScaffoldState>(find.byType(Scaffold)).openDrawer();
    await tester.pumpAndSettle();

    final drawer = find.byType(Drawer);

    expect(
      find.descendant(
        of: drawer,
        matching: find.widgetWithText(ChoiceChip, 'Active'),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: drawer,
        matching: find.widgetWithText(ChoiceChip, 'Archived'),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: drawer,
        matching: find.text('Active Chat', skipOffstage: false),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: drawer,
        matching: find.text('Archived Chat', skipOffstage: false),
      ),
      findsNothing,
    );

    await tester.tap(
      find.descendant(
        of: drawer,
        matching: find.widgetWithText(ChoiceChip, 'Archived'),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.descendant(
        of: drawer,
        matching: find.text(
          'Archived chats across your pinned projects',
          skipOffstage: false,
        ),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: drawer,
        matching: find.text('Archived Chat', skipOffstage: false),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: drawer,
        matching: find.text('Active Chat', skipOffstage: false),
      ),
      findsNothing,
    );
  });

  testWidgets('sidebar project can be removed and stays removed after rebuild',
      (WidgetTester tester) async {
    SharedPreferences.setMockInitialValues(<String, Object>{});

    final session = _buildSession(
      title: 'Pinned Chat',
      messages: const <ChatMessage>[],
    );

    await _pumpChatScreen(
      tester,
      session: session,
      sidebarWorkspaces: const <Workspace>[
        Workspace(name: 'Workspace A', path: '/workspace/a'),
      ],
    );

    tester.state<ScaffoldState>(find.byType(Scaffold)).openDrawer();
    await tester.pumpAndSettle();

    final drawer = find.byType(Drawer);
    expect(
      find.descendant(
        of: drawer,
        matching: find.text('Workspace A', skipOffstage: false),
      ),
      findsOneWidget,
    );

    await tester.tap(
      find.byTooltip('Project actions for Workspace A'),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Remove project'));
    await tester.pumpAndSettle();

    expect(
      find.descendant(
        of: drawer,
        matching: find.text('Workspace A', skipOffstage: false),
      ),
      findsNothing,
    );
    expect(
      find.descendant(
        of: drawer,
        matching: find.text('No projects pinned yet', skipOffstage: false),
      ),
      findsOneWidget,
    );

    final preferences = await SharedPreferences.getInstance();
    expect(
      preferences.getStringList('sidebar_workspaces::http://localhost:8000'),
      isEmpty,
    );

    final persistedWorkspaces = await ServerProfileStore()
        .loadSidebarWorkspaces('http://localhost:8000');
    expect(persistedWorkspaces, isEmpty);

    await _pumpChatScreen(
      tester,
      session: session,
      sidebarWorkspaces: persistedWorkspaces,
    );

    tester.state<ScaffoldState>(find.byType(Scaffold)).openDrawer();
    await tester.pumpAndSettle();

    final rebuiltDrawer = find.byType(Drawer);
    expect(
      find.descendant(
        of: rebuiltDrawer,
        matching: find.text('Workspace A', skipOffstage: false),
      ),
      findsNothing,
    );
    expect(
      find.descendant(
        of: rebuiltDrawer,
        matching: find.text('No projects pinned yet', skipOffstage: false),
      ),
      findsOneWidget,
    );
  });
}

Finder _chatBodyScrollable() {
  return find
      .descendant(
        of: find.byKey(kChatScreenBodyScrollViewKey),
        matching: find.byType(Scrollable),
      )
      .first;
}

Future<void> _pumpChatScreen(
  WidgetTester tester, {
  required SessionDetail session,
  ApiClient? apiClient,
  List<Workspace> sidebarWorkspaces = const <Workspace>[],
  double width = 320,
  double height = 520,
  double keyboardInsetBottom = 0,
}) async {
  tester.view.physicalSize = Size(width, height);
  tester.view.devicePixelRatio = 1.0;
  tester.view.viewInsets = FakeViewPadding(bottom: keyboardInsetBottom);
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  addTearDown(tester.view.resetViewInsets);

  final controller = await _seedController(session, apiClient: apiClient);
  addTearDown(controller.dispose);

  await tester.pumpWidget(
    MaterialApp(
      home: ChatScreen(
        initialApiBaseUrl: 'http://localhost:8000',
        notificationService: const NoopChatNotificationService(),
        controllerOverride: controller,
        enableServerBootstrap: false,
        initialSidebarWorkspaces: sidebarWorkspaces,
      ),
    ),
  );
  await tester.pumpAndSettle();
}

Future<ChatController> _seedController(
  SessionDetail session, {
  ApiClient? apiClient,
}) async {
  final controller = ChatController(
    apiClient: apiClient ?? _ChatScreenOverflowApiClient(session),
    notificationService: const NoopChatNotificationService(),
  );
  await controller.refreshSessions();
  await controller.selectSession(session.id);
  return controller;
}

class _ChatScreenOverflowApiClient extends ApiClient {
  _ChatScreenOverflowApiClient(
    SessionDetail session, {
    List<SessionDetail> additionalSessions = const <SessionDetail>[],
    this.onUpdateAgentConfiguration,
    this.lastMessagePreviewBySession = const <String, String?>{},
  })  : _session = session,
        _sessions = <SessionDetail>[session, ...additionalSessions],
        super(baseUrl: 'http://localhost:8000');

  SessionDetail _session;
  final List<SessionDetail> _sessions;
  Future<SessionDetail> Function(
    String sessionId,
    AgentConfiguration configuration,
  )? onUpdateAgentConfiguration;
  final Map<String, String?> lastMessagePreviewBySession;

  SessionDetail get session => _session;

  @override
  Future<List<ChatSessionSummary>> listSessions() async {
    return _sessions
        .map(
          (session) => ChatSessionSummary(
            id: session.id,
            title: session.title,
            archivedAt: session.archivedAt,
            workspacePath: session.workspacePath,
            workspaceName: session.workspaceName,
            agentProfileId: session.agentProfileId,
            agentProfileName: session.agentProfileName,
            agentProfileColor: session.agentProfileColor,
            agentConfiguration: session.agentConfiguration,
            conversationProduct: session.conversationProduct,
            lastMessagePreview:
                lastMessagePreviewBySession.containsKey(session.id)
                    ? lastMessagePreviewBySession[session.id]
                    : _defaultLastMessagePreview(session),
            createdAt: session.createdAt,
            updatedAt: session.updatedAt,
            activeAgentRunId: session.activeAgentRunId,
          ),
        )
        .toList(growable: false);
  }

  @override
  Future<SessionDetail> getSession(String sessionId) async {
    return _sessions.firstWhere((session) => session.id == sessionId);
  }

  @override
  Future<SessionDetail> updateAgentConfiguration(
    String sessionId, {
    required AgentConfiguration configuration,
  }) async {
    final override = onUpdateAgentConfiguration;
    if (override != null) {
      return override(sessionId, configuration);
    }
    return applyAgentConfiguration(configuration, sessionId: sessionId);
  }

  SessionDetail applyAgentConfiguration(
    AgentConfiguration configuration, {
    String? sessionId,
  }) {
    final targetSessionId = sessionId ?? _session.id;
    final currentSession = _sessions.firstWhere(
      (session) => session.id == targetSessionId,
    );
    final updatedSession = currentSession.copyWith(
      agentConfiguration: configuration,
      updatedAt: currentSession.updatedAt.add(const Duration(seconds: 1)),
    );
    final sessionIndex = _sessions.indexWhere(
      (session) => session.id == targetSessionId,
    );
    _sessions[sessionIndex] = updatedSession;
    if (_session.id == targetSessionId) {
      _session = updatedSession;
    }
    return updatedSession;
  }

  String? _defaultLastMessagePreview(SessionDetail session) {
    for (final message in session.messages.reversed) {
      final trimmed = message.text.trim();
      if (trimmed.isNotEmpty) {
        return trimmed;
      }
    }
    return null;
  }
}

SessionDetail _buildSession({
  String id = 'session-a',
  String title = 'Chat A',
  DateTime? archivedAt,
  String workspacePath = '/workspace/a',
  String workspaceName = 'Workspace A',
  required List<ChatMessage> messages,
  AgentDisplayMode displayMode = AgentDisplayMode.showAll,
  ConversationProduct? conversationProduct,
}) {
  final configuration = kDefaultAgentConfiguration.copyWith(
    preset: AgentPreset.review,
    displayMode: displayMode,
    agents: kDefaultAgentDefinitions.map((agent) {
      if (agent.agentId == AgentId.reviewer) {
        return agent.copyWith(
          enabled: true,
          label: 'Safety Reviewer',
          visibility: AgentVisibilityMode.visible,
          maxTurns: 1,
        );
      }
      if (agent.agentId == AgentId.summary) {
        return agent.copyWith(enabled: false, maxTurns: 0);
      }
      return agent;
    }).toList(),
  );

  final now = DateTime.utc(2026, 1, 1, 12);
  return SessionDetail(
    id: id,
    title: title,
    archivedAt: archivedAt,
    workspacePath: workspacePath,
    workspaceName: workspaceName,
    agentProfileId: 'default',
    agentProfileName: 'Generator',
    agentProfileColor: '#55D6BE',
    createdAt: now,
    updatedAt: now,
    messages: messages,
    agentConfiguration: configuration,
    conversationProduct: conversationProduct,
    autoModeEnabled: true,
    autoMaxTurns: 1,
    activeAgentRunId: 'run-12345678',
    reviewerState: ReviewerLifecycleState.running,
    currentRun: const CurrentRunExecution(
      runId: 'run-12345678',
      state: CurrentRunStageState.running,
      isActive: true,
      stages: <CurrentRunStageExecution>[
        CurrentRunStageExecution(
          stage: CurrentRunStageId.generator,
          state: CurrentRunStageState.running,
          configured: true,
          attemptCount: 2,
          maxTurns: 3,
          latestActivity: 'Generator is still streaming output.',
        ),
        CurrentRunStageExecution(
          stage: CurrentRunStageId.reviewer,
          state: CurrentRunStageState.notScheduled,
          configured: true,
          maxTurns: 1,
        ),
        CurrentRunStageExecution(
          stage: CurrentRunStageId.summary,
          state: CurrentRunStageState.disabled,
          configured: false,
          maxTurns: 0,
        ),
      ],
    ),
    recentRuns: const <CurrentRunExecution>[
      CurrentRunExecution(
        runId: 'run-older',
        state: CurrentRunStageState.completed,
        isActive: false,
        stages: <CurrentRunStageExecution>[
          CurrentRunStageExecution(
            stage: CurrentRunStageId.generator,
            state: CurrentRunStageState.completed,
            configured: true,
            attemptCount: 1,
            maxTurns: 2,
          ),
          CurrentRunStageExecution(
            stage: CurrentRunStageId.reviewer,
            state: CurrentRunStageState.completed,
            configured: true,
            attemptCount: 1,
            maxTurns: 1,
          ),
          CurrentRunStageExecution(
            stage: CurrentRunStageId.summary,
            state: CurrentRunStageState.disabled,
            configured: false,
          ),
        ],
      ),
    ],
  );
}

SessionDetail _buildTallSession() {
  final now = DateTime.utc(2026, 1, 1, 12);
  final configuration = kDefaultAgentConfiguration.copyWith(
    preset: AgentPreset.review,
    agents: kDefaultAgentDefinitions.map((agent) {
      return switch (agent.agentId) {
        AgentId.generator => agent.copyWith(
            label: 'Primary Generator With Extended Delivery Stage',
          ),
        AgentId.reviewer => agent.copyWith(
            enabled: true,
            label: 'Safety Reviewer',
            visibility: AgentVisibilityMode.visible,
            maxTurns: 2,
          ),
        AgentId.summary => agent.copyWith(
            enabled: false,
            label: 'Summary Stage With Extended Visibility Label',
            maxTurns: 0,
          ),
        _ => agent,
      };
    }).toList(),
  );

  return SessionDetail(
    id: 'session-tall',
    title: 'Tall Chat',
    workspacePath: '/workspace/tall',
    workspaceName: 'Tall Workspace',
    agentProfileId: 'default',
    agentProfileName: 'Generator',
    agentProfileColor: '#55D6BE',
    createdAt: now,
    updatedAt: now,
    messages: <ChatMessage>[
      _message(
        id: 'user-tail',
        text: 'Tall run history prompt',
        isUser: true,
        authorType: ChatMessageAuthorType.human,
        agentId: AgentId.user,
        agentType: AgentType.human,
      ),
      _message(
        id: 'assistant-tail',
        text: 'Tail message',
      ),
    ],
    agentConfiguration: configuration,
    autoModeEnabled: true,
    autoMaxTurns: 2,
    activeAgentRunId: 'run-active',
    reviewerState: ReviewerLifecycleState.running,
    currentRun: _buildRun(
      runId: 'run-active',
      state: CurrentRunStageState.running,
      isActive: true,
      generatorState: CurrentRunStageState.running,
      reviewerState: CurrentRunStageState.notScheduled,
      summaryState: CurrentRunStageState.disabled,
      generatorAttempts: 2,
      generatorMaxTurns: 6,
      reviewerAttempts: 0,
      reviewerMaxTurns: 2,
      generatorActivity:
          'Generator is streaming a much longer progress narrative that wraps across multiple lines in a narrow viewport.',
      reviewerActivity:
          'Reviewer is queued after the generator finishes this expanded pipeline.',
    ),
    recentRuns: <CurrentRunExecution>[
      _buildRun(
        runId: 'run-0001',
        state: CurrentRunStageState.completed,
        isActive: false,
        generatorState: CurrentRunStageState.completed,
        reviewerState: CurrentRunStageState.completed,
        summaryState: CurrentRunStageState.disabled,
        generatorActivity:
            'Completed a large implementation pass with several validation steps and a long trailing note.',
        reviewerActivity:
            'Reviewer completed with an expanded safety review summary.',
      ),
      _buildRun(
        runId: 'run-0002',
        state: CurrentRunStageState.completed,
        isActive: false,
        generatorState: CurrentRunStageState.completed,
        reviewerState: CurrentRunStageState.completed,
        summaryState: CurrentRunStageState.disabled,
        generatorActivity:
            'Second completed run includes more verbose generator details for overflow coverage.',
        reviewerActivity:
            'Second reviewer pass also returns a long line of detail for wrapping coverage.',
      ),
      _buildRun(
        runId: 'run-0003',
        state: CurrentRunStageState.completed,
        isActive: false,
        generatorState: CurrentRunStageState.completed,
        reviewerState: CurrentRunStageState.completed,
        summaryState: CurrentRunStageState.disabled,
        generatorActivity:
            'Third completed run keeps the card growing well beyond the viewport height.',
        reviewerActivity:
            'Third reviewer result adds another wrapped block of status copy.',
      ),
      _buildRun(
        runId: 'run-0004',
        state: CurrentRunStageState.completed,
        isActive: false,
        generatorState: CurrentRunStageState.completed,
        reviewerState: CurrentRunStageState.completed,
        summaryState: CurrentRunStageState.disabled,
        generatorActivity:
            'Oldest run keeps the lower bound of the card reachable only by scrolling.',
        reviewerActivity:
            'Oldest reviewer summary remains visible after scrolling to the bottom and back up.',
      ),
    ],
  );
}

CurrentRunExecution _buildRun({
  required String runId,
  required CurrentRunStageState state,
  required bool isActive,
  required CurrentRunStageState generatorState,
  required CurrentRunStageState reviewerState,
  required CurrentRunStageState summaryState,
  int generatorAttempts = 1,
  int generatorMaxTurns = 2,
  int reviewerAttempts = 1,
  int reviewerMaxTurns = 1,
  String? generatorActivity,
  String? reviewerActivity,
}) {
  return CurrentRunExecution(
    runId: runId,
    state: state,
    isActive: isActive,
    stages: <CurrentRunStageExecution>[
      CurrentRunStageExecution(
        stage: CurrentRunStageId.generator,
        state: generatorState,
        configured: true,
        attemptCount: generatorAttempts,
        maxTurns: generatorMaxTurns,
        latestActivity: generatorActivity,
      ),
      CurrentRunStageExecution(
        stage: CurrentRunStageId.reviewer,
        state: reviewerState,
        configured: true,
        attemptCount: reviewerAttempts,
        maxTurns: reviewerMaxTurns,
        latestActivity: reviewerActivity,
      ),
      CurrentRunStageExecution(
        stage: CurrentRunStageId.summary,
        state: summaryState,
        configured: false,
        maxTurns: 0,
      ),
    ],
  );
}

ChatMessage _message({
  required String id,
  required String text,
  bool isUser = false,
  ChatMessageAuthorType authorType = ChatMessageAuthorType.assistant,
  AgentId agentId = AgentId.generator,
  AgentType agentType = AgentType.generator,
  AgentVisibilityMode visibility = AgentVisibilityMode.visible,
}) {
  final now = DateTime.utc(2026, 1, 1, 12);
  return ChatMessage(
    id: id,
    text: text,
    isUser: isUser,
    authorType: authorType,
    agentId: agentId,
    agentType: agentType,
    visibility: visibility,
    status: ChatMessageStatus.completed,
    createdAt: now,
    updatedAt: now,
    runId: 'run-12345678',
  );
}
