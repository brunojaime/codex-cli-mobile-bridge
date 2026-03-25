import 'dart:convert';
import 'dart:typed_data';

import 'package:codex_mobile_frontend/main.dart';
import 'package:codex_mobile_frontend/src/models/agent_configuration.dart';
import 'package:codex_mobile_frontend/src/models/agent_profile.dart';
import 'package:codex_mobile_frontend/src/models/chat_message.dart';
import 'package:codex_mobile_frontend/src/models/chat_session_summary.dart';
import 'package:codex_mobile_frontend/src/models/job_status_response.dart';
import 'package:codex_mobile_frontend/src/models/session_detail.dart';
import 'package:codex_mobile_frontend/src/screens/chat_screen.dart';
import 'package:codex_mobile_frontend/src/services/api_client.dart';
import 'package:codex_mobile_frontend/src/services/chat_notification_service.dart';
import 'package:codex_mobile_frontend/src/services/text_to_speech_player.dart';
import 'package:codex_mobile_frontend/src/state/chat_controller.dart';
import 'package:codex_mobile_frontend/src/utils/chat_message_visibility.dart';
import 'package:codex_mobile_frontend/src/widgets/chat_bubble.dart';
import 'package:cross_file/cross_file.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  testWidgets('renders Codex Remote shell', (tester) async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    await tester.pumpWidget(
      const CodexMobileApp(initialApiBaseUrl: 'http://localhost:8000'),
    );

    expect(find.text('Codex Remote'), findsOneWidget);
    expect(find.textContaining('local machine'), findsOneWidget);
    expect(find.byIcon(Icons.mic_rounded), findsOneWidget);
    expect(find.byIcon(Icons.upload_file_outlined), findsNothing);
    expect(find.byIcon(Icons.download_for_offline_outlined), findsNothing);
  });

  testWidgets('collapses secondary app bar actions on narrow screens', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    tester.view.physicalSize = const Size(320, 780);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      const CodexMobileApp(initialApiBaseUrl: 'http://localhost:8000'),
    );
    await tester.pump();

    expect(find.byIcon(Icons.hub_outlined), findsOneWidget);
    expect(find.byIcon(Icons.more_vert), findsOneWidget);
    expect(find.byIcon(Icons.computer), findsNothing);
    expect(find.byIcon(Icons.add), findsNothing);
    expect(find.byIcon(Icons.upload_file_outlined), findsNothing);
    expect(find.byIcon(Icons.download_for_offline_outlined), findsNothing);
  });

  testWidgets('renders assistant options as quick actions', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ChatBubble(
            message: ChatMessage(
              id: 'assistant-1',
              text: '1. Summarize the repo\n2. Show changed files',
              isUser: false,
              authorType: ChatMessageAuthorType.assistant,
              status: ChatMessageStatus.completed,
              createdAt: DateTime.utc(2026, 1, 1),
              updatedAt: DateTime.utc(2026, 1, 1),
              jobStatus: 'completed',
              jobPhase: 'Completed',
            ),
          ),
        ),
      ),
    );

    expect(find.text('Quick options'), findsOneWidget);
    expect(find.text('Summarize the repo'), findsOneWidget);
    expect(find.text('Show changed files'), findsOneWidget);
  });

  testWidgets(
      'supervisor-only agent studio uses registry selection and hides specialist turn budgets',
      (tester) async {
    tester.view.physicalSize = const Size(1280, 1600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final fakeApiClient = _FakeApiClient();
    final controller = ChatController(
      apiClient: fakeApiClient,
      notificationService: const NoopChatNotificationService(),
    );
    fakeApiClient._sessionConfigurations['session-a'] =
        kDefaultAgentConfiguration.copyWith(
      preset: AgentPreset.supervisor,
      displayMode: AgentDisplayMode.collapseSpecialists,
      turnBudgetMode: TurnBudgetMode.supervisorOnly,
      supervisorMemberIds: const <AgentId>[AgentId.qa, AgentId.seniorEngineer],
      agents: kDefaultAgentDefinitions.map((agent) {
        if (agent.agentId == AgentId.supervisor) {
          return agent.copyWith(enabled: true, maxTurns: 4);
        }
        if (agent.agentId == AgentId.qa ||
            agent.agentId == AgentId.seniorEngineer) {
          return agent.copyWith(enabled: true, maxTurns: 2);
        }
        return agent.copyWith(
          enabled: agent.agentId == AgentId.generator ? false : agent.enabled,
          maxTurns: 0,
        );
      }).toList(growable: false),
    );
    await controller.selectSession('session-a');

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

    await tester.tap(find.byIcon(Icons.account_tree_outlined));
    await tester.pumpAndSettle();

    expect(find.text('Turn budget mode'), findsOneWidget);
    expect(find.text('Supervisor only'), findsWidgets);
    expect(
      find.textContaining('selected specialists can be called whenever'),
      findsOneWidget,
    );
    expect(
      find.textContaining('Specialist turn budgets are preserved'),
      findsOneWidget,
    );
    expect(
      find.textContaining(
          'Selection is controlled by the supervisor registry above.'),
      findsNWidgets(4),
    );
    expect(find.text('Turn budget'), findsNWidgets(4));
    expect(find.text('Scraper'), findsWidgets);

    controller.dispose();
  });

  testWidgets('renders validation blocks and file reference chips',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ChatBubble(
            message: ChatMessage(
              id: 'assistant-2',
              text:
                  'Updated [docker-compose.yml](/tmp/docker-compose.yml) and [README.md](/tmp/README.md).\n\nValidation:\n- backend tests -> 8 passed\n- flutter analyze -> no issues found',
              isUser: false,
              authorType: ChatMessageAuthorType.assistant,
              status: ChatMessageStatus.completed,
              createdAt: DateTime.utc(2026, 1, 1),
              updatedAt: DateTime.utc(2026, 1, 1),
              jobStatus: 'completed',
              jobPhase: 'Completed',
            ),
          ),
        ),
      ),
    );

    expect(find.text('docker-compose.yml'), findsOneWidget);
    expect(find.text('README.md'), findsOneWidget);
    expect(find.text('Validation'), findsOneWidget);
    expect(find.text('backend tests'), findsOneWidget);
    expect(find.text('8 passed'), findsOneWidget);
    expect(find.text('flutter analyze'), findsOneWidget);
  });

  testWidgets('dispatches inline link taps through the chat bubble callback', (
    tester,
  ) async {
    var tappedTarget = '';

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ChatBubble(
            message: ChatMessage(
              id: 'assistant-3',
              text: 'Open [README.md](/tmp/README.md)',
              isUser: false,
              authorType: ChatMessageAuthorType.assistant,
              status: ChatMessageStatus.completed,
              createdAt: DateTime.utc(2026, 1, 1),
              updatedAt: DateTime.utc(2026, 1, 1),
              jobStatus: 'completed',
              jobPhase: 'Completed',
            ),
            onLinkTap: (target) async {
              tappedTarget = target;
            },
          ),
        ),
      ),
    );

    await tester.tap(find.text('README.md'));
    await tester.pump();

    expect(tappedTarget, '/tmp/README.md');
  });

  testWidgets('renders reviewer codex user bubble with distinct label', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ChatBubble(
            message: ChatMessage(
              id: 'reviewer-1',
              text: 'Ask the generator Codex to add integration coverage.',
              isUser: true,
              authorType: ChatMessageAuthorType.reviewerCodex,
              status: ChatMessageStatus.completed,
              createdAt: DateTime.utc(2026, 1, 1),
              updatedAt: DateTime.utc(2026, 1, 1),
              jobStatus: 'completed',
              jobPhase: 'Prompt ready',
            ),
          ),
        ),
      ),
    );

    expect(find.text('CODEX REVIEWER'), findsOneWidget);
    expect(
      find.text('Ask the generator Codex to add integration coverage.'),
      findsOneWidget,
    );
  });

  testWidgets('renders summary agent assistant bubble with its own label', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ChatBubble(
            message: ChatMessage(
              id: 'summary-1',
              text: 'Summary response for the user.',
              isUser: false,
              authorType: ChatMessageAuthorType.assistant,
              agentId: AgentId.summary,
              agentType: AgentType.summary,
              status: ChatMessageStatus.completed,
              createdAt: DateTime.utc(2026, 1, 1),
              updatedAt: DateTime.utc(2026, 1, 1),
              jobStatus: 'completed',
              jobPhase: 'Completed',
            ),
          ),
        ),
      ),
    );

    expect(find.text('SUMMARY'), findsOneWidget);
    expect(find.text('Summary response for the user.'), findsOneWidget);
  });

  testWidgets('renders submission unknown bubble with recovery actions', (
    tester,
  ) async {
    var retried = false;
    var dismissed = false;

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ChatBubble(
            message: ChatMessage(
              id: 'unknown-1',
              text: 'Automatic recovery stopped to avoid duplicate execution.',
              isUser: false,
              authorType: ChatMessageAuthorType.assistant,
              status: ChatMessageStatus.submissionUnknown,
              createdAt: DateTime.utc(2026, 1, 1),
              updatedAt: DateTime.utc(2026, 1, 1),
            ),
            onRecoverUnknownSubmission: () async {
              retried = true;
            },
            onCancelUnknownSubmission: () async {
              dismissed = true;
            },
          ),
        ),
      ),
    );

    expect(find.text('Retry follow-up'), findsOneWidget);
    expect(find.text('Dismiss'), findsOneWidget);

    await tester.tap(find.text('Retry follow-up'));
    await tester.pump();
    expect(retried, isTrue);

    await tester.tap(find.text('Dismiss'));
    await tester.pump();
    expect(dismissed, isTrue);
  });

  testWidgets(
      'renders recovery lineage text for superseded and retried messages',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Column(
            children: <Widget>[
              ChatBubble(
                message: ChatMessage(
                  id: 'old-unknown',
                  text: 'Old uncertain follow-up.',
                  isUser: false,
                  authorType: ChatMessageAuthorType.assistant,
                  status: ChatMessageStatus.cancelled,
                  reasonCode: ChatMessageReasonCode.manualRetryRequested,
                  recoveryAction: MessageRecoveryAction.retry,
                  supersededByMessageId: 'retry-1',
                  createdAt: DateTime.utc(2026, 1, 1),
                  updatedAt: DateTime.utc(2026, 1, 1),
                ),
              ),
              ChatBubble(
                message: ChatMessage(
                  id: 'retry-1',
                  text: 'New attempt.',
                  isUser: false,
                  authorType: ChatMessageAuthorType.assistant,
                  status: ChatMessageStatus.completed,
                  reasonCode: ChatMessageReasonCode.manualRetryRequested,
                  recoveryAction: MessageRecoveryAction.retry,
                  recoveredFromMessageId: 'old-unknown',
                  createdAt: DateTime.utc(2026, 1, 1),
                  updatedAt: DateTime.utc(2026, 1, 1),
                ),
              ),
            ],
          ),
        ),
      ),
    );

    expect(
      find.textContaining('A manual retry was requested for this follow-up.'),
      findsNWidgets(2),
    );
    expect(
      find.textContaining(
        'This uncertain follow-up was superseded by a manual retry.',
      ),
      findsOneWidget,
    );
    expect(
      find.textContaining('Manual retry of an earlier uncertain follow-up.'),
      findsOneWidget,
    );
  });

  test('agent configuration falls back to safe defaults for malformed data',
      () {
    final configuration = AgentConfiguration.fromJson(
      <String, dynamic>{
        'preset': 'invalid',
        'display_mode': 'summary_only',
        'agents': <dynamic>[
          <String, dynamic>{
            'agent_id': 'generator',
            'agent_type': 'generator',
            'enabled': true,
            'label': 'Builder',
            'prompt': 'Build',
            'visibility': 'visible',
            'max_turns': 3,
          },
          'not-a-map',
        ],
      },
    );

    expect(configuration.preset, AgentPreset.solo);
    expect(configuration.displayMode, AgentDisplayMode.summaryOnly);
    expect(configuration.turnBudgetMode, TurnBudgetMode.eachAgent);
    expect(configuration.agents.length, kDefaultAgentDefinitions.length);
    expect(
      configuration.agents.map((agent) => agent.agentId).toList(),
      kDefaultAgentDefinitions.map((agent) => agent.agentId).toList(),
    );
    expect(configuration.byId(AgentId.generator)?.label, 'Builder');
    expect(configuration.byId(AgentId.reviewer)?.enabled, isFalse);
    expect(configuration.byId(AgentId.summary)?.enabled, isFalse);
    expect(
      configuration.byId(AgentId.supervisor)?.enabled,
      kDefaultAgentConfiguration.byId(AgentId.supervisor)?.enabled,
    );
    expect(
      configuration.byId(AgentId.qa)?.label,
      kDefaultAgentConfiguration.byId(AgentId.qa)?.label,
    );
  });

  test(
      'unknown agent ids are ignored instead of overwriting generator defaults',
      () {
    final configuration = AgentConfiguration.fromJson(
      <String, dynamic>{
        'preset': 'triad',
        'display_mode': 'show_all',
        'agents': <dynamic>[
          <String, dynamic>{
            'agent_id': 'rogue',
            'agent_type': 'reviewer',
            'enabled': true,
            'label': 'Rogue',
            'prompt': 'Should be ignored',
            'visibility': 'hidden',
            'max_turns': 9,
          },
        ],
      },
    );

    expect(configuration.byId(AgentId.generator)?.label, 'Generator');
    expect(configuration.byId(AgentId.generator)?.enabled, isTrue);
    expect(configuration.byId(AgentId.reviewer)?.enabled, isFalse);
    expect(configuration.byId(AgentId.summary)?.enabled, isFalse);
  });

  test('supervisor turn budget mode parses and serializes cleanly', () {
    final configuration = AgentConfiguration.fromJson(
      <String, dynamic>{
        'preset': 'supervisor',
        'display_mode': 'collapse_specialists',
        'turn_budget_mode': 'supervisor_only',
        'supervisor_member_ids': const <String>['qa', 'senior_engineer'],
        'agents': kDefaultAgentDefinitions
            .map((agent) => agent.toJson())
            .toList(growable: false),
      },
    );

    expect(configuration.preset, AgentPreset.supervisor);
    expect(configuration.turnBudgetMode, TurnBudgetMode.supervisorOnly);
    expect(
      configuration.supervisorMemberIds,
      <AgentId>[AgentId.qa, AgentId.seniorEngineer],
    );
    expect(configuration.toJson()['turn_budget_mode'], 'supervisor_only');
  });

  test('legacy session summaries render with default solo agent config', () {
    final summary = ChatSessionSummary.fromJson(
      <String, dynamic>{
        'id': 'session-legacy',
        'title': 'Legacy',
        'workspace_path': '/workspace/legacy',
        'workspace_name': 'Legacy',
        'created_at': DateTime.utc(2026, 1, 1).toIso8601String(),
        'updated_at': DateTime.utc(2026, 1, 1).toIso8601String(),
        'agent_configuration': 'broken',
      },
    );

    expect(summary.agentConfiguration.preset, AgentPreset.solo);
    expect(summary.agentConfiguration.byId(AgentId.generator)?.enabled, isTrue);
    expect(summary.agentConfiguration.byId(AgentId.reviewer)?.enabled, isFalse);
  });

  test('chat message parsing tolerates partial legacy recovery payloads', () {
    final message = ChatMessage.fromJson(
      <String, dynamic>{
        'id': 'legacy-recovery',
        'role': 'assistant',
        'content': 'Legacy',
        'status': 'submission_unknown',
        'reason_code': 'not-a-valid-reason',
        'recovery_action': 'retry',
        'created_at': DateTime.utc(2026, 1, 1).toIso8601String(),
        'updated_at': DateTime.utc(2026, 1, 1).toIso8601String(),
      },
    );

    expect(message.status, ChatMessageStatus.submissionUnknown);
    expect(message.reasonCode, isNull);
    expect(message.recoveryAction, MessageRecoveryAction.retry);
    expect(message.recoveredFromMessageId, isNull);
    expect(message.supersededByMessageId, isNull);
  });

  test('job status parsing keeps agent metadata for notifications', () {
    final snapshot = JobStatusResponse.fromJson(
      <String, dynamic>{
        'job_id': 'job-reviewer',
        'session_id': 'session-a',
        'status': 'completed',
        'elapsed_seconds': 3,
        'agent_id': 'reviewer',
        'agent_type': 'reviewer',
        'response': 'Looks good.',
      },
    );

    expect(snapshot.agentId, AgentId.reviewer);
    expect(snapshot.agentType, AgentType.reviewer);
  });

  test('speech sanitizer strips markdown and code fences safely', () {
    expect(
      sanitizeTextForSpeech(
        'Open [README.md](/tmp/readme)\n\n```dart\nprint("debug");\n```\nUse `flutter test` now.',
      ),
      'Open README.md Use flutter test now.',
    );
  });

  testWidgets('renders reason code text for superseded runs', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ChatBubble(
            message: ChatMessage(
              id: 'superseded-1',
              text: 'Superseded placeholder.',
              isUser: false,
              authorType: ChatMessageAuthorType.assistant,
              status: ChatMessageStatus.cancelled,
              reasonCode: ChatMessageReasonCode.supersededByNewerRun,
              createdAt: DateTime.utc(2026, 1, 1),
              updatedAt: DateTime.utc(2026, 1, 1),
            ),
          ),
        ),
      ),
    );

    expect(
      find.text(
        'Superseded by a newer run before this follow-up could be resumed.',
      ),
      findsOneWidget,
    );
  });

  test('preset helper enables only the expected agents', () {
    expect(agentEnabledForPreset(AgentId.generator, AgentPreset.solo), isTrue);
    expect(agentEnabledForPreset(AgentId.reviewer, AgentPreset.solo), isFalse);
    expect(agentEnabledForPreset(AgentId.reviewer, AgentPreset.review), isTrue);
    expect(agentEnabledForPreset(AgentId.summary, AgentPreset.review), isFalse);
    expect(agentEnabledForPreset(AgentId.summary, AgentPreset.triad), isTrue);
  });

  test('visibility filtering respects display modes and hidden messages', () {
    final messages = <ChatMessage>[
      _message(
        id: 'human',
        isUser: true,
        authorType: ChatMessageAuthorType.human,
        agentId: AgentId.user,
        agentType: AgentType.human,
      ),
      _message(
        id: 'human-generator',
        isUser: true,
        authorType: ChatMessageAuthorType.human,
        agentId: AgentId.generator,
        agentType: AgentType.generator,
      ),
      _message(id: 'generator'),
      _message(
        id: 'reviewer',
        isUser: true,
        authorType: ChatMessageAuthorType.reviewerCodex,
        agentId: AgentId.reviewer,
        agentType: AgentType.reviewer,
        visibility: AgentVisibilityMode.collapsed,
      ),
      _message(
        id: 'summary',
        agentId: AgentId.summary,
        agentType: AgentType.summary,
      ),
      _message(
        id: 'hidden-reviewer',
        isUser: true,
        authorType: ChatMessageAuthorType.reviewerCodex,
        agentId: AgentId.reviewer,
        agentType: AgentType.reviewer,
        visibility: AgentVisibilityMode.hidden,
      ),
    ];

    expect(
      filterVisibleMessages(
        messages,
        displayMode: AgentDisplayMode.showAll,
      ).map((message) => message.id),
      <String>['human', 'human-generator', 'generator', 'reviewer', 'summary'],
    );
    expect(
      filterVisibleMessages(
        messages,
        displayMode: AgentDisplayMode.collapseSpecialists,
      ).map((message) => message.id),
      <String>['human', 'human-generator', 'generator', 'summary'],
    );
    expect(
      filterVisibleMessages(
        messages,
        displayMode: AgentDisplayMode.summaryOnly,
      ).map((message) => message.id),
      <String>['human', 'human-generator', 'summary'],
    );
  });

  test('chat controller sends audio to the captured session override',
      () async {
    final fakeApiClient = _FakeApiClient();
    final controller = ChatController(
      apiClient: fakeApiClient,
      notificationService: const NoopChatNotificationService(),
    );

    await controller.selectSession('session-b');
    final didSend = await controller.sendAudioMessage(
      XFile.fromData(Uint8List.fromList(const <int>[1, 2, 3]),
          name: 'voice-note.m4a'),
      sessionIdOverride: 'session-a',
      workspacePathOverride: '/workspace/a',
    );

    expect(didSend, isTrue);
    expect(fakeApiClient.lastAudioSessionId, 'session-a');
    expect(fakeApiClient.lastAudioWorkspacePath, '/workspace/a');
    expect(controller.selectedSessionId, 'session-b');

    controller.dispose();
  });

  test('chat controller keeps overlapping audio sends isolated across chats',
      () async {
    final fakeApiClient = _FakeApiClient(
      audioSendDelays: <String, Duration>{
        'session-a': const Duration(milliseconds: 40),
        'session-b': const Duration(milliseconds: 5),
      },
    );
    final controller = ChatController(
      apiClient: fakeApiClient,
      notificationService: const NoopChatNotificationService(),
    );

    await controller.selectSession('session-a');
    final firstSend = controller.sendAudioMessage(
      XFile.fromData(
        Uint8List.fromList(const <int>[1, 2, 3]),
        name: 'voice-a.m4a',
      ),
      sessionIdOverride: 'session-a',
      workspacePathOverride: '/workspace/a',
    );

    await controller.selectSession('session-b');
    final secondSend = controller.sendAudioMessage(
      XFile.fromData(
        Uint8List.fromList(const <int>[4, 5, 6]),
        name: 'voice-b.m4a',
      ),
      sessionIdOverride: 'session-b',
      workspacePathOverride: '/workspace/b',
    );

    final results =
        await Future.wait<bool>(<Future<bool>>[firstSend, secondSend]);

    expect(results, everyElement(isTrue));
    expect(controller.selectedSessionId, 'session-b');
    expect(
      fakeApiClient.audioSends
          .map((send) => '${send.sessionId}:${send.workspacePath}')
          .toList(),
      <String>[
        'session-a:/workspace/a',
        'session-b:/workspace/b',
      ],
    );

    controller.dispose();
  });

  test('chat controller updates per-chat agent configuration', () async {
    final fakeApiClient = _FakeApiClient();
    final controller = ChatController(
      apiClient: fakeApiClient,
      notificationService: const NoopChatNotificationService(),
    );

    await controller.selectSession('session-a');
    final didUpdate = await controller.updateAgentConfiguration(
      kDefaultAgentConfiguration.copyWith(
        preset: AgentPreset.review,
        displayMode: AgentDisplayMode.summaryOnly,
        agents: kDefaultAgentDefinitions.map((agent) {
          if (agent.agentId == AgentId.reviewer) {
            return agent.copyWith(enabled: true);
          }
          return agent;
        }).toList(),
      ),
    );

    expect(didUpdate, isTrue);
    expect(fakeApiClient.lastAgentConfiguration?.preset, AgentPreset.review);
    expect(
      fakeApiClient.lastAgentConfiguration?.displayMode,
      AgentDisplayMode.summaryOnly,
    );
    expect(
      controller.currentSession?.agentConfiguration.displayMode,
      AgentDisplayMode.summaryOnly,
    );

    controller.dispose();
  });

  test('chat controller keeps per-chat agent configuration isolated', () async {
    final fakeApiClient = _FakeApiClient();
    final controller = ChatController(
      apiClient: fakeApiClient,
      notificationService: const NoopChatNotificationService(),
    );

    await controller.selectSession('session-a');
    final didUpdate = await controller.updateAgentConfiguration(
      kDefaultAgentConfiguration.copyWith(
        preset: AgentPreset.review,
        displayMode: AgentDisplayMode.summaryOnly,
        agents: kDefaultAgentDefinitions.map((agent) {
          if (agent.agentId == AgentId.reviewer) {
            return agent.copyWith(enabled: true, label: 'A Reviewer');
          }
          return agent;
        }).toList(),
      ),
    );
    expect(didUpdate, isTrue);

    await controller.selectSession('session-b');
    expect(
        controller.currentSession?.agentConfiguration.preset, AgentPreset.solo);
    expect(
      controller.currentSession?.agentConfiguration
          .byId(AgentId.reviewer)
          ?.enabled,
      isFalse,
    );

    await controller.selectSession('session-a');
    expect(
      controller.currentSession?.agentConfiguration.preset,
      AgentPreset.review,
    );
    expect(
      controller.currentSession?.agentConfiguration
          .byId(AgentId.reviewer)
          ?.label,
      'A Reviewer',
    );

    controller.dispose();
  });

  test('chat controller recovers uncertain follow-up state', () async {
    final fakeApiClient = _FakeApiClient();
    final controller = ChatController(
      apiClient: fakeApiClient,
      notificationService: const NoopChatNotificationService(),
    );

    await controller.selectSession('session-a');
    final didRecover = await controller.recoverMessage(
      'message-unknown',
      action: MessageRecoveryAction.retry,
    );

    expect(didRecover, isTrue);
    expect(fakeApiClient.lastRecoveredMessageId, 'message-unknown');
    expect(fakeApiClient.lastRecoveryAction, MessageRecoveryAction.retry);
    expect(controller.currentSession?.messages, isNotEmpty);
    expect(
      controller.currentSession?.messages.first.status,
      ChatMessageStatus.submissionPending,
    );

    controller.dispose();
  });

  test('chat controller saves full agent profile packs', () async {
    final fakeApiClient = _FakeApiClient();
    final controller = ChatController(
      apiClient: fakeApiClient,
      notificationService: const NoopChatNotificationService(),
    );

    final configuration = kDefaultAgentConfiguration.copyWith(
      preset: AgentPreset.triad,
      displayMode: AgentDisplayMode.summaryOnly,
      agents: kDefaultAgentDefinitions.map((agent) {
        if (agent.agentId == AgentId.generator) {
          return agent.copyWith(
            label: 'Agent Creator',
            prompt: 'Design reusable agent packs.',
          );
        }
        if (agent.agentId == AgentId.reviewer) {
          return agent.copyWith(enabled: true, label: 'Pack Reviewer');
        }
        return agent.copyWith(enabled: true, label: 'Pack Summary');
      }).toList(),
    );

    final profile = await controller.createAgentProfile(
      name: 'Agent Creator Pack',
      description: 'Designs and critiques reusable packs.',
      colorHex: '#F28C28',
      configuration: configuration,
    );

    expect(profile, isNotNull);
    expect(fakeApiClient.lastCreatedAgentProfileConfiguration?.preset,
        AgentPreset.triad);
    expect(
      fakeApiClient.lastCreatedAgentProfileConfiguration?.displayMode,
      AgentDisplayMode.summaryOnly,
    );
    expect(
        controller.agentProfiles.any((item) => item.id == profile!.id), isTrue);

    controller.dispose();
  });

  test('chat controller auto-imports agent creator blueprints', () async {
    final fakeApiClient = _FakeApiClient();
    fakeApiClient.sessionOverrides['session-a'] = SessionDetail(
      id: 'session-a',
      title: 'Chat A',
      workspacePath: '/workspace/a',
      workspaceName: 'A',
      agentProfileId: 'agent_creator',
      agentProfileName: 'Agent Creator',
      agentProfileColor: '#F28C28',
      createdAt: _FakeApiClient._timestamp,
      updatedAt: _FakeApiClient._timestamp,
      messages: <ChatMessage>[
        ChatMessage(
          id: 'creator-message',
          text: '''
Built the draft.

```agent-profile
{
  "id": "api_guardian",
  "name": "API Guardian",
  "description": "Reviews API changes for regressions.",
  "color_hex": "#1188AA",
  "prompt": "Review API changes for regressions, compatibility risks, and release blockers."
}
```
''',
          isUser: false,
          authorType: ChatMessageAuthorType.assistant,
          status: ChatMessageStatus.completed,
          createdAt: _FakeApiClient._timestamp,
          updatedAt: _FakeApiClient._timestamp,
        ),
      ],
    );
    final controller = ChatController(
      apiClient: fakeApiClient,
      notificationService: const NoopChatNotificationService(),
    );

    await controller.refreshAgentProfiles();
    await controller.selectSession('session-a');

    expect(fakeApiClient.importedProfiles, hasLength(1));
    expect(fakeApiClient.importedProfiles.single.id, 'api_guardian');
    expect(
      controller.agentProfiles.any((profile) => profile.id == 'api_guardian'),
      isTrue,
    );

    controller.dispose();
  });

  test('chat controller applies full agent profile packs to the session',
      () async {
    final fakeApiClient = _FakeApiClient();
    final controller = ChatController(
      apiClient: fakeApiClient,
      notificationService: const NoopChatNotificationService(),
    );

    await controller.selectSession('session-a');
    final didApply = await controller.applyAgentProfile('agent-pack');

    expect(didApply, isTrue);
    expect(fakeApiClient.lastAppliedAgentProfileId, 'agent-pack');
    expect(controller.currentSession?.agentProfileName, 'Agent Pack');
    expect(controller.currentSession?.agentConfiguration.preset,
        AgentPreset.review);
    expect(
      controller.currentSession?.agentConfiguration.displayMode,
      AgentDisplayMode.collapseSpecialists,
    );
    expect(
      controller.currentSession?.agentConfiguration
          .byId(AgentId.reviewer)
          ?.label,
      'Pack Reviewer',
    );

    controller.dispose();
  });

  test('chat controller exports and imports agent profiles as JSON', () async {
    final fakeApiClient = _FakeApiClient();
    final controller = ChatController(
      apiClient: fakeApiClient,
      notificationService: const NoopChatNotificationService(),
    );

    final exportedJson = await controller.exportAgentProfilesAsJson();
    expect(exportedJson, isNotNull);
    expect(exportedJson, contains('agent-pack'));

    final didImport = await controller.importAgentProfilesFromJson(
      exportedJson!,
    );
    expect(didImport, isTrue);
    expect(fakeApiClient.importedProfiles, isNotEmpty);

    controller.dispose();
  });

  test('api client serializes and deserializes agent configuration round trip',
      () async {
    Map<String, dynamic>? receivedBody;
    final client = ApiClient(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        receivedBody = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(
          jsonEncode(<String, dynamic>{
            'id': 'session-a',
            'title': 'Chat A',
            'workspace_path': '/workspace/a',
            'workspace_name': 'A',
            'created_at': DateTime.utc(2026, 1, 1).toIso8601String(),
            'updated_at': DateTime.utc(2026, 1, 1).toIso8601String(),
            'messages': const <dynamic>[],
            'agent_configuration': receivedBody,
          }),
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );
    final session = await client.updateAgentConfiguration(
      'session-a',
      configuration: kDefaultAgentConfiguration.copyWith(
        preset: AgentPreset.review,
        displayMode: AgentDisplayMode.collapseSpecialists,
        agents: kDefaultAgentDefinitions.map((agent) {
          if (agent.agentId == AgentId.reviewer) {
            return agent.copyWith(enabled: true);
          }
          return agent;
        }).toList(),
      ),
    );

    expect(receivedBody?['preset'], 'review');
    expect(receivedBody?['display_mode'], 'collapse_specialists');
    expect(receivedBody?['turn_budget_mode'], 'each_agent');
    expect(
      (receivedBody?['agents'] as List<dynamic>).length,
      kDefaultAgentDefinitions.length,
    );
    expect(session.agentConfiguration.preset, AgentPreset.review);
    expect(
      session.agentConfiguration.displayMode,
      AgentDisplayMode.collapseSpecialists,
    );
    expect(
      session.agentConfiguration.agents.length,
      kDefaultAgentDefinitions.length,
    );
    expect(session.agentConfiguration.byId(AgentId.reviewer)?.enabled, isTrue);
    expect(
      session.agentConfiguration.byId(AgentId.supervisor)?.label,
      kDefaultAgentConfiguration.byId(AgentId.supervisor)?.label,
    );
  });

  test('api client serializes and deserializes agent profile packs', () async {
    Map<String, dynamic>? receivedBody;
    final configuration = kDefaultAgentConfiguration.copyWith(
      preset: AgentPreset.review,
      displayMode: AgentDisplayMode.collapseSpecialists,
      agents: kDefaultAgentDefinitions.map((agent) {
        if (agent.agentId == AgentId.generator) {
          return agent.copyWith(
            label: 'Pack Generator',
            prompt: 'Execute the saved pack.',
          );
        }
        if (agent.agentId == AgentId.reviewer) {
          return agent.copyWith(enabled: true, label: 'Pack Reviewer');
        }
        return agent.copyWith(enabled: false);
      }).toList(),
    );
    final client = ApiClient(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        receivedBody = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(
          jsonEncode(<String, dynamic>{
            'id': 'agent-pack',
            'name': 'Agent Pack',
            'description': 'Stored full studio pack.',
            'color_hex': '#1188AA',
            'prompt': 'Execute the saved pack.',
            'is_builtin': false,
            'configuration': receivedBody?['configuration'],
          }),
          201,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    final profile = await client.createAgentProfile(
      name: 'Agent Pack',
      description: 'Stored full studio pack.',
      colorHex: '#1188AA',
      configuration: configuration,
    );

    expect(receivedBody?['configuration']['preset'], 'review');
    expect(
        receivedBody?['configuration']['display_mode'], 'collapse_specialists');
    expect(receivedBody?['configuration']['turn_budget_mode'], 'each_agent');
    expect(profile.configuration.preset, AgentPreset.review);
    expect(
      profile.configuration.byId(AgentId.reviewer)?.label,
      'Pack Reviewer',
    );
  });

  test('chat controller builds reviewer-specific completion notifications',
      () async {
    final controller = ChatController(
      apiClient: _FakeApiClient(),
      notificationService: const NoopChatNotificationService(),
    );

    await controller.selectSession('session-a');
    final notification = controller.buildTerminalNotificationForTesting(
      const JobStatusResponse(
        jobId: 'job-reviewer',
        sessionId: 'session-a',
        status: 'completed',
        elapsedSeconds: 2,
        agentId: AgentId.reviewer,
        agentType: AgentType.reviewer,
        response: 'Add one more test around the retry path.',
      ),
    );

    expect(notification, isNotNull);
    expect(notification.title, 'A');
    expect(notification.channel, ChatNotificationChannel.reviewer);
    expect(notification.body, contains('Reviewer reply ready'));
    expect(notification.summary, 'Reviewer • Chat A');

    controller.dispose();
  });
}

class _FakeApiClient extends ApiClient {
  _FakeApiClient({
    this.audioSendDelays = const <String, Duration>{},
  }) : super(baseUrl: 'http://localhost:8000');

  String? lastAudioSessionId;
  String? lastAudioWorkspacePath;
  AgentConfiguration? lastAgentConfiguration;
  AgentConfiguration? lastCreatedAgentProfileConfiguration;
  String? lastAppliedAgentProfileId;
  List<AgentProfile> importedProfiles = <AgentProfile>[];
  String? lastRecoveredMessageId;
  MessageRecoveryAction? lastRecoveryAction;
  final Map<String, Duration> audioSendDelays;
  final List<_RecordedAudioSend> audioSends = <_RecordedAudioSend>[];
  final Map<String, AgentConfiguration> _sessionConfigurations =
      <String, AgentConfiguration>{};
  final Map<String, SessionDetail> sessionOverrides = <String, SessionDetail>{};
  final List<AgentProfile> _agentProfiles = <AgentProfile>[
    AgentProfile(
      id: 'default',
      name: 'Generator',
      description: 'Default generator.',
      colorHex: '#55D6BE',
      prompt: kDefaultAgentDefinitions.first.prompt,
      configuration: kDefaultAgentConfiguration,
      isBuiltin: true,
    ),
    AgentProfile(
      id: 'agent-pack',
      name: 'Agent Pack',
      description: 'Full stored pack.',
      colorHex: '#1188AA',
      prompt: 'Execute the saved pack.',
      configuration: kDefaultAgentConfiguration.copyWith(
        preset: AgentPreset.review,
        displayMode: AgentDisplayMode.collapseSpecialists,
        agents: kDefaultAgentDefinitions.map((agent) {
          if (agent.agentId == AgentId.generator) {
            return agent.copyWith(
              label: 'Agent Pack',
              prompt: 'Execute the saved pack.',
            );
          }
          if (agent.agentId == AgentId.reviewer) {
            return agent.copyWith(enabled: true, label: 'Pack Reviewer');
          }
          return agent.copyWith(enabled: false);
        }).toList(),
      ),
    ),
  ];

  static final DateTime _timestamp = DateTime.utc(2026, 1, 1);

  @override
  Future<List<ChatSessionSummary>> listSessions() async {
    return <ChatSessionSummary>[
      ChatSessionSummary(
        id: 'session-a',
        title: 'Chat A',
        workspacePath: '/workspace/a',
        workspaceName: 'A',
        agentProfileId: 'default',
        agentProfileName: 'Generator',
        agentProfileColor: '#55D6BE',
        createdAt: _timestamp,
        updatedAt: _timestamp,
      ),
      ChatSessionSummary(
        id: 'session-b',
        title: 'Chat B',
        workspacePath: '/workspace/b',
        workspaceName: 'B',
        agentProfileId: 'default',
        agentProfileName: 'Generator',
        agentProfileColor: '#55D6BE',
        createdAt: _timestamp,
        updatedAt: _timestamp,
      ),
    ];
  }

  @override
  Future<List<AgentProfile>> listAgentProfiles() async {
    return List<AgentProfile>.from(_agentProfiles);
  }

  @override
  Future<List<AgentProfile>> exportAgentProfiles() async {
    return List<AgentProfile>.from(
      _agentProfiles.where((profile) => !profile.isBuiltin),
    );
  }

  @override
  Future<SessionDetail> getSession(String sessionId) async {
    final override = sessionOverrides[sessionId];
    if (override != null) {
      return override;
    }
    return SessionDetail(
      id: sessionId,
      title: sessionId == 'session-a' ? 'Chat A' : 'Chat B',
      workspacePath: sessionId == 'session-a' ? '/workspace/a' : '/workspace/b',
      workspaceName: sessionId == 'session-a' ? 'A' : 'B',
      agentProfileId: 'default',
      agentProfileName: 'Generator',
      agentProfileColor: '#55D6BE',
      agentConfiguration:
          _sessionConfigurations[sessionId] ?? kDefaultAgentConfiguration,
      createdAt: _timestamp,
      updatedAt: _timestamp,
      messages: const <ChatMessage>[],
    );
  }

  @override
  Future<JobStatusResponse> sendAudioMessage(
    XFile audioFile, {
    String? sessionId,
    String? workspacePath,
    String? language,
  }) async {
    lastAudioSessionId = sessionId;
    lastAudioWorkspacePath = workspacePath;
    audioSends.add(
      _RecordedAudioSend(
        sessionId: sessionId,
        workspacePath: workspacePath,
        filename: audioFile.name,
      ),
    );
    await Future<void>.delayed(audioSendDelays[sessionId] ?? Duration.zero);
    return JobStatusResponse(
      jobId: 'job-audio-${audioSends.length}',
      sessionId: sessionId ?? 'session-a',
      status: 'pending',
      elapsedSeconds: 0,
    );
  }

  @override
  Future<SessionDetail> updateAutoMode(
    String sessionId, {
    required bool enabled,
    required int maxTurns,
    String? reviewerPrompt,
  }) async {
    return SessionDetail(
      id: sessionId,
      title: sessionId == 'session-a' ? 'Chat A' : 'Chat B',
      workspacePath: sessionId == 'session-a' ? '/workspace/a' : '/workspace/b',
      workspaceName: sessionId == 'session-a' ? 'A' : 'B',
      agentProfileId: 'default',
      agentProfileName: 'Generator',
      agentProfileColor: '#55D6BE',
      autoModeEnabled: enabled,
      autoMaxTurns: maxTurns,
      autoReviewerPrompt: reviewerPrompt,
      createdAt: _timestamp,
      updatedAt: _timestamp,
      messages: const <ChatMessage>[],
    );
  }

  @override
  Future<SessionDetail> updateAgentConfiguration(
    String sessionId, {
    required AgentConfiguration configuration,
  }) async {
    lastAgentConfiguration = configuration;
    _sessionConfigurations[sessionId] = configuration;
    return SessionDetail(
      id: sessionId,
      title: sessionId == 'session-a' ? 'Chat A' : 'Chat B',
      workspacePath: sessionId == 'session-a' ? '/workspace/a' : '/workspace/b',
      workspaceName: sessionId == 'session-a' ? 'A' : 'B',
      agentProfileId: 'default',
      agentProfileName: 'Generator',
      agentProfileColor: '#55D6BE',
      agentConfiguration: configuration,
      createdAt: _timestamp,
      updatedAt: _timestamp,
      messages: const <ChatMessage>[],
    );
  }

  @override
  Future<AgentProfile> createAgentProfile({
    required String name,
    required String description,
    required String colorHex,
    required AgentConfiguration configuration,
  }) async {
    lastCreatedAgentProfileConfiguration = configuration;
    final profile = AgentProfile(
      id: 'created-pack',
      name: name,
      description: description,
      colorHex: colorHex,
      prompt: configuration.byId(AgentId.generator)?.prompt ?? '',
      configuration: configuration,
    );
    _agentProfiles.add(profile);
    return profile;
  }

  @override
  Future<SessionDetail> applyAgentProfile(
    String sessionId, {
    required String profileId,
  }) async {
    lastAppliedAgentProfileId = profileId;
    final profile = _agentProfiles.firstWhere((item) => item.id == profileId);
    _sessionConfigurations[sessionId] = profile.configuration;
    return SessionDetail(
      id: sessionId,
      title: sessionId == 'session-a' ? 'Chat A' : 'Chat B',
      workspacePath: sessionId == 'session-a' ? '/workspace/a' : '/workspace/b',
      workspaceName: sessionId == 'session-a' ? 'A' : 'B',
      agentProfileId: profile.id,
      agentProfileName: profile.name,
      agentProfileColor: profile.colorHex,
      agentConfiguration: profile.configuration,
      createdAt: _timestamp,
      updatedAt: _timestamp,
      messages: const <ChatMessage>[],
    );
  }

  @override
  Future<List<AgentProfile>> importAgentProfiles(
    List<AgentProfile> profiles,
  ) async {
    importedProfiles = List<AgentProfile>.from(profiles);
    _agentProfiles.addAll(profiles);
    return profiles;
  }

  @override
  Future<SessionDetail> recoverMessage(
    String sessionId,
    String messageId, {
    required MessageRecoveryAction action,
  }) async {
    lastRecoveredMessageId = messageId;
    lastRecoveryAction = action;
    return SessionDetail(
      id: sessionId,
      title: sessionId == 'session-a' ? 'Chat A' : 'Chat B',
      workspacePath: sessionId == 'session-a' ? '/workspace/a' : '/workspace/b',
      workspaceName: sessionId == 'session-a' ? 'A' : 'B',
      agentProfileId: 'default',
      agentProfileName: 'Generator',
      agentProfileColor: '#55D6BE',
      createdAt: _timestamp,
      updatedAt: _timestamp,
      messages: <ChatMessage>[
        ChatMessage(
          id: 'retry-message',
          text: '',
          isUser: false,
          authorType: ChatMessageAuthorType.assistant,
          status: ChatMessageStatus.submissionPending,
          createdAt: _timestamp,
          updatedAt: _timestamp,
        ),
      ],
    );
  }
}

class _RecordedAudioSend {
  const _RecordedAudioSend({
    required this.sessionId,
    required this.workspacePath,
    required this.filename,
  });

  final String? sessionId;
  final String? workspacePath;
  final String filename;
}

ChatMessage _message({
  required String id,
  bool isUser = false,
  ChatMessageAuthorType authorType = ChatMessageAuthorType.assistant,
  AgentId agentId = AgentId.generator,
  AgentType agentType = AgentType.generator,
  AgentVisibilityMode visibility = AgentVisibilityMode.visible,
}) {
  return ChatMessage(
    id: id,
    text: id,
    isUser: isUser,
    authorType: authorType,
    agentId: agentId,
    agentType: agentType,
    visibility: visibility,
    status: ChatMessageStatus.completed,
    createdAt: DateTime.utc(2026, 1, 1),
    updatedAt: DateTime.utc(2026, 1, 1),
  );
}
