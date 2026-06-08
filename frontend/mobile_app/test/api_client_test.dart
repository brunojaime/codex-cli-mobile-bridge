import 'package:codex_mobile_frontend/src/models/chat_session_summary.dart';
import 'package:codex_mobile_frontend/src/models/codex_tooling.dart';
import 'package:codex_mobile_frontend/src/models/feedback_queue_item.dart';
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

  test('startFeedbackQueueSession includes explicit target mode', () async {
    final client = ApiClient(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/feedback-queue/feedback-1/start-session');
        expect(request.body, contains('"target_mode":"generator_reviewer"'));
        return http.Response(
          '{"job_id":"job-1","session_id":"session-1","status":"pending","elapsed_seconds":0}',
          202,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    await client.startFeedbackQueueSession(
      'feedback-1',
      targetMode: FeedbackQueueTargetMode.generatorReviewer,
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

  test('getCodexTooling parses repo MCP apps including validation errors',
      () async {
    final client = ApiClient(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        expect(request.method, 'GET');
        expect(request.url.path, '/codex/tooling');
        return http.Response(
          '''
          {
            "status": {
              "cli_available": true,
              "command": "codex",
              "status_summary": "ok"
            },
            "profiles": [],
            "skills": [],
            "mcp_server_inventory_complete": false,
            "mcp_servers": [
              {
                "server_id": "github",
                "summary": "github: GitHub connector available",
                "source": "external",
                "backing_app_id": null,
                "status": "disabled",
                "selectable": false,
                "selectable_reason": "This external MCP server is disabled in Codex. Re-enable it before selecting it.",
                "disabled_reason": "Paused by admin",
                "lookup_error": null
              }
            ],
            "mcp_apps": [
              {
                "app_id": "project-catalog",
                "name": "Project Catalog",
                "description": "List local projects",
                "recommended_server_id": "project-catalog",
                "transport": "stdio",
                "command": "uv",
                "args": ["run", "python", "-m", "mcp_apps.project_catalog.server"],
                "env": {"PROJECTS_ROOT": "/projects"},
                "tags": ["projects"],
                "supports_ui_extension": false,
                "ui_entry_uri": null,
                "spec_path": "/repo/mcp_apps/project_catalog/app.json",
                "installed": false,
                "install_state": "drifted",
                "server_present": true,
                "server_presence_known": true,
                "config_matches": false,
                "tools": [
                  {
                    "name": "list_projects",
                    "title": "List Projects",
                    "description": "List projects",
                    "read_only": true,
                    "destructive": false,
                    "idempotent": true,
                    "open_world": false,
                    "input_schema": {"type": "object"}
                  }
                ],
                "resources": [
                  {
                    "name": "Project Catalog JSON",
                    "title": null,
                    "uri": "projects://catalog",
                    "description": "Catalog",
                    "mime_type": "application/json"
                  }
                ],
                "prompts": [],
                "preview": {
                  "tool_name": "list_projects",
                  "arguments": {"limit": 2},
                  "result": {
                    "project_count": 1,
                    "projects": [{"name": "alpha"}]
                  },
                  "is_error": false,
                  "error": null
                },
                "drift_summary": "args differ between the stored Codex config and the repo app spec",
                "disabled_reason": "Authorization: [redacted]",
                "lookup_error": "state unreadable",
                "validation_error": "Broken preview config",
                "protocol_error": "Timed out during initialize."
              }
            ]
          }
          ''',
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    final snapshot = await client.getCodexTooling();
    expect(snapshot.mcpServerInventoryComplete, isFalse);
    expect(snapshot.mcpServers, hasLength(1));
    final server = snapshot.mcpServers.single;
    expect(server.serverId, 'github');
    expect(server.status, 'disabled');
    expect(server.selectable, isFalse);
    expect(server.disabledReason, 'Paused by admin');
    expect(snapshot.mcpApps, hasLength(1));
    final app = snapshot.mcpApps.single;
    expect(app.appId, 'project-catalog');
    expect(app.recommendedServerId, 'project-catalog');
    expect(app.tools.single.name, 'list_projects');
    expect(app.resources.single.uri, 'projects://catalog');
    expect(app.preview?.toolName, 'list_projects');
    expect(app.installState, 'drifted');
    expect(app.serverPresent, isTrue);
    expect(app.serverPresenceKnown, isTrue);
    expect(app.configMatches, isFalse);
    expect(
      app.driftSummary,
      'args differ between the stored Codex config and the repo app spec',
    );
    expect(app.disabledReason, 'Authorization: [redacted]');
    expect(app.lookupError, 'state unreadable');
    expect(app.validationError, 'Broken preview config');
    expect(app.protocolError, 'Timed out during initialize.');
  });

  test('installCodexMcpApp posts to the install endpoint', () async {
    final client = ApiClient(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/codex/mcp-apps/project-catalog/install');
        return http.Response(
          '''
          {
            "app_id": "project-catalog",
            "server_id": "project-catalog",
            "already_installed": true,
            "reconciled": false,
            "command": "uv run python -m mcp_apps.project_catalog.server",
            "summary": "Already installed"
          }
          ''',
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    final result = await client.installCodexMcpApp('project-catalog');
    expect(result.appId, 'project-catalog');
    expect(result.alreadyInstalled, isTrue);
    expect(result.reconciled, isFalse);
    expect(result.summary, 'Already installed');
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
