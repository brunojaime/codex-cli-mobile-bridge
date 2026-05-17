import 'package:codex_mobile_frontend/src/models/chat_session_summary.dart';
import 'package:codex_mobile_frontend/src/models/codex_tooling.dart';
import 'package:codex_mobile_frontend/src/models/session_detail.dart';
import 'package:codex_mobile_frontend/src/services/api_client.dart';
import 'package:codex_mobile_frontend/src/services/chat_notification_service.dart';
import 'package:codex_mobile_frontend/src/state/chat_controller.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('sendMessage includes codex options when requested', () async {
    final client = ApiClient(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/message');
        final body = request.body;
        expect(body, contains('"profile":"safe"'));
        expect(body, contains('"search_enabled":true'));
        expect(body, contains('"skill_ids":["skill-creator"]'));
        expect(body, contains('"mcp_server_ids":["github"]'));
        return http.Response(
          '{"job_id":"job-1","status":"pending"}',
          202,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    await client.sendMessage(
      'Use the real local Codex skill.',
      codexRunOptions: const CodexRunOptions(
        profile: 'safe',
        searchEnabled: true,
        skillIds: <String>['skill-creator'],
        mcpServerIds: <String>['github'],
      ),
    );
  });

  test('updateTurnSummaries explains when the backend route is missing',
      () async {
    final client = ApiClient(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        expect(request.method, 'PUT');
        expect(request.url.path, '/sessions/session-1/turn-summaries');
        return http.Response(
          '{"detail":"Not Found"}',
          404,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    await expectLater(
      () => client.updateTurnSummaries('session-1', enabled: true),
      throwsA(
        predicate<Object>(
          (error) => '$error'.contains(
            'Turn summaries are not available on the connected backend. Pull the latest backend changes and restart it.',
          ),
        ),
      ),
    );
  });

  test('chat controller shows a clean turn summary backend mismatch error',
      () async {
    final controller = ChatController(
      apiClient: _MissingTurnSummaryRouteApiClient(),
      notificationService: const NoopChatNotificationService(),
    );
    addTearDown(controller.dispose);

    await controller.refreshSessions();
    await controller.selectSession('session-1');

    expect(
      await controller.updateTurnSummariesEnabled(true),
      isFalse,
    );
    expect(
      controller.errorText,
      'Failed to update turn summaries.\n'
      'Turn summaries are not available on the connected backend. '
      'Pull the latest backend changes and restart it.',
    );
  });
}

class _MissingTurnSummaryRouteApiClient extends ApiClient {
  _MissingTurnSummaryRouteApiClient() : super(baseUrl: 'http://localhost:8000');

  @override
  Future<List<ChatSessionSummary>> listSessions() async {
    return <ChatSessionSummary>[
      ChatSessionSummary(
        id: 'session-1',
        title: 'Summary route mismatch',
        workspacePath: '/workspace/project',
        workspaceName: 'Project',
        createdAt: DateTime.parse('2026-04-01T00:00:00Z'),
        updatedAt: DateTime.parse('2026-04-01T00:00:00Z'),
      ),
    ];
  }

  @override
  Future<SessionDetail> getSession(String sessionId) async {
    return SessionDetail(
      id: sessionId,
      title: 'Summary route mismatch',
      workspacePath: '/workspace/project',
      workspaceName: 'Project',
      createdAt: DateTime.parse('2026-04-01T00:00:00Z'),
      updatedAt: DateTime.parse('2026-04-01T00:00:00Z'),
      messages: const [],
    );
  }

  @override
  Future<SessionDetail> updateTurnSummaries(
    String sessionId, {
    required bool enabled,
  }) async {
    throw Exception(
      'Failed to update turn summaries: Turn summaries are not available on the connected backend. Pull the latest backend changes and restart it.',
    );
  }
}
