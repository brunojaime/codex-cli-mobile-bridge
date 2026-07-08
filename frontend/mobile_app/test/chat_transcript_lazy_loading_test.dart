import 'dart:convert';

import 'package:codex_mobile_frontend/src/models/agent_configuration.dart';
import 'package:codex_mobile_frontend/src/models/chat_message.dart';
import 'package:codex_mobile_frontend/src/models/chat_session_summary.dart';
import 'package:codex_mobile_frontend/src/models/session_detail.dart';
import 'package:codex_mobile_frontend/src/services/api_client.dart';
import 'package:codex_mobile_frontend/src/state/chat_controller.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('SessionDetail parses transcript window metadata', () {
    final session = SessionDetail.fromJson(_sessionJson(
      messages: <Map<String, dynamic>>[_messageJson('user-2', isUser: true)],
      transcriptWindow: <String, dynamic>{
        'oldest_cursor': 'cursor-old',
        'newest_cursor': 'cursor-new',
        'has_older': true,
        'has_newer': false,
        'window_anchor_message_id': 'user-2',
        'is_partial': true,
      },
    ));

    expect(session.messages.single.id, 'user-2');
    expect(session.transcriptWindow.oldestCursor, 'cursor-old');
    expect(session.transcriptWindow.hasOlder, isTrue);
    expect(session.transcriptWindow.windowAnchorMessageId, 'user-2');
    expect(session.transcriptWindow.isPartial, isTrue);
  });

  test('ApiClient requests older transcript pages with cursor params',
      () async {
    Uri? capturedUri;
    final client = ApiClient(
      baseUrl: 'http://bridge.test',
      client: MockClient((request) async {
        capturedUri = request.url;
        return http.Response(jsonEncode(_sessionJson()), 200);
      }),
    );

    await client.getSession('session-1', before: 'cursor-a', limit: 25);

    expect(capturedUri?.path, '/sessions/session-1');
    expect(capturedUri?.queryParameters['before'], 'cursor-a');
    expect(capturedUri?.queryParameters['limit'], '25');
    expect(capturedUri?.queryParameters['transcript'], 'window');
  });

  test('ChatController prepends older messages and deduplicates overlap',
      () async {
    final apiClient = _PagedSessionApiClient();
    final controller = ChatController(apiClient: apiClient);

    await controller.refreshSessions();
    await controller.selectSession('session-1');

    expect(controller.messages.map((message) => message.id), <String>[
      'user-2',
      'assistant-2',
    ]);

    final loaded = await controller.loadOlderMessages();

    expect(loaded, isTrue);
    expect(controller.messages.map((message) => message.id), <String>[
      'assistant-1',
      'user-2',
      'assistant-2',
    ]);
    expect(controller.hasOlderMessages, isFalse);

    controller.dispose();
  });
}

class _PagedSessionApiClient extends ApiClient {
  _PagedSessionApiClient() : super(baseUrl: 'http://bridge.test');

  @override
  Future<List<ChatSessionSummary>> listSessions() async {
    return <ChatSessionSummary>[
      ChatSessionSummary(
        id: 'session-1',
        title: 'Chat',
        workspacePath: '/workspace',
        workspaceName: 'Workspace',
        agentConfiguration: kDefaultAgentConfiguration,
        createdAt: _timestamp(0),
        updatedAt: _timestamp(3),
      ),
    ];
  }

  @override
  Future<SessionDetail> getSession(
    String sessionId, {
    String? before,
    int? limit,
    bool fullTranscript = false,
  }) async {
    if (before != null) {
      return _sessionDetail(
        messages: <ChatMessage>[
          _message('assistant-1', 1),
          _message('user-2', 2, isUser: true),
        ],
        window: const TranscriptWindow(
          oldestCursor: 'cursor-assistant-1',
          newestCursor: 'cursor-user-2',
          hasOlder: false,
          hasNewer: true,
          isPartial: true,
        ),
      );
    }
    return _sessionDetail(
      messages: <ChatMessage>[
        _message('user-2', 2, isUser: true),
        _message('assistant-2', 3),
      ],
      window: const TranscriptWindow(
        oldestCursor: 'cursor-user-2',
        newestCursor: 'cursor-assistant-2',
        hasOlder: true,
        isPartial: true,
      ),
    );
  }
}

SessionDetail _sessionDetail({
  required List<ChatMessage> messages,
  required TranscriptWindow window,
}) {
  return SessionDetail(
    id: 'session-1',
    title: 'Chat',
    workspacePath: '/workspace',
    workspaceName: 'Workspace',
    agentConfiguration: kDefaultAgentConfiguration,
    createdAt: _timestamp(0),
    updatedAt: _timestamp(3),
    messages: messages,
    transcriptWindow: window,
  );
}

Map<String, dynamic> _sessionJson({
  List<Map<String, dynamic>> messages = const <Map<String, dynamic>>[],
  Map<String, dynamic>? transcriptWindow,
}) {
  return <String, dynamic>{
    'id': 'session-1',
    'title': 'Chat',
    'workspace_path': '/workspace',
    'workspace_name': 'Workspace',
    'agent_configuration': kDefaultAgentConfiguration.toJson(),
    'created_at': _timestamp(0).toIso8601String(),
    'updated_at': _timestamp(1).toIso8601String(),
    'messages': messages,
    'transcript_window': transcriptWindow ?? const <String, dynamic>{},
  };
}

Map<String, dynamic> _messageJson(String id, {bool isUser = false}) {
  return <String, dynamic>{
    'id': id,
    'role': isUser ? 'user' : 'assistant',
    'author_type': isUser ? 'human' : 'assistant',
    'content': '$id text',
    'status': 'completed',
    'created_at': _timestamp(1).toIso8601String(),
    'updated_at': _timestamp(1).toIso8601String(),
  };
}

ChatMessage _message(String id, int minute, {bool isUser = false}) {
  return ChatMessage(
    id: id,
    text: '$id text',
    isUser: isUser,
    authorType:
        isUser ? ChatMessageAuthorType.human : ChatMessageAuthorType.assistant,
    status: ChatMessageStatus.completed,
    createdAt: _timestamp(minute),
    updatedAt: _timestamp(minute),
  );
}

DateTime _timestamp(int minute) => DateTime.utc(2026, 1, 1, 0, minute);
