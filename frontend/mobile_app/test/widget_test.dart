import 'dart:typed_data';

import 'package:codex_mobile_frontend/main.dart';
import 'package:codex_mobile_frontend/src/models/chat_message.dart';
import 'package:codex_mobile_frontend/src/models/chat_session_summary.dart';
import 'package:codex_mobile_frontend/src/models/job_status_response.dart';
import 'package:codex_mobile_frontend/src/models/session_detail.dart';
import 'package:codex_mobile_frontend/src/services/api_client.dart';
import 'package:codex_mobile_frontend/src/services/chat_notification_service.dart';
import 'package:codex_mobile_frontend/src/state/chat_controller.dart';
import 'package:codex_mobile_frontend/src/widgets/chat_bubble.dart';
import 'package:cross_file/cross_file.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
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

  test('chat controller sends audio to the captured session override', () async {
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
}

class _FakeApiClient extends ApiClient {
  _FakeApiClient() : super(baseUrl: 'http://localhost:8000');

  String? lastAudioSessionId;
  String? lastAudioWorkspacePath;

  static final DateTime _timestamp = DateTime.utc(2026, 1, 1);

  @override
  Future<List<ChatSessionSummary>> listSessions() async {
    return <ChatSessionSummary>[
      ChatSessionSummary(
        id: 'session-a',
        title: 'Chat A',
        workspacePath: '/workspace/a',
        workspaceName: 'A',
        createdAt: _timestamp,
        updatedAt: _timestamp,
      ),
      ChatSessionSummary(
        id: 'session-b',
        title: 'Chat B',
        workspacePath: '/workspace/b',
        workspaceName: 'B',
        createdAt: _timestamp,
        updatedAt: _timestamp,
      ),
    ];
  }

  @override
  Future<SessionDetail> getSession(String sessionId) async {
    return SessionDetail(
      id: sessionId,
      title: sessionId == 'session-a' ? 'Chat A' : 'Chat B',
      workspacePath:
          sessionId == 'session-a' ? '/workspace/a' : '/workspace/b',
      workspaceName: sessionId == 'session-a' ? 'A' : 'B',
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
    return const JobStatusResponse(
      jobId: 'job-audio',
      sessionId: 'session-a',
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
      workspacePath:
          sessionId == 'session-a' ? '/workspace/a' : '/workspace/b',
      workspaceName: sessionId == 'session-a' ? 'A' : 'B',
      autoModeEnabled: enabled,
      autoMaxTurns: maxTurns,
      autoReviewerPrompt: reviewerPrompt,
      createdAt: _timestamp,
      updatedAt: _timestamp,
      messages: const <ChatMessage>[],
    );
  }
}
