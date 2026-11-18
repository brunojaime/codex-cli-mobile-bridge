import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:codex_mobile_frontend/src/models/chat_session_summary.dart';
import 'package:codex_mobile_frontend/src/models/job_status_response.dart';
import 'package:codex_mobile_frontend/src/models/session_detail.dart';
import 'package:codex_mobile_frontend/src/services/api_client.dart';
import 'package:codex_mobile_frontend/src/state/chat_controller.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'rich_message_content_test.dart' show showMessage, tapText;

class _Api extends ApiClient {
  _Api() : super(baseUrl: 'http://localhost:1');
  final reads = <Completer<List<ChatSessionSummary>>>[];
  final detail = Completer<SessionDetail>();
  @override
  Future<SessionDetail> getSession(String id,
          {String? before, int? limit, bool fullTranscript = false}) =>
      detail.future;
  @override
  Future<List<ChatSessionSummary>> listSessions() {
    final result = Completer<List<ChatSessionSummary>>();
    reads.add(result);
    return result.future;
  }
}

ChatSessionSummary summary(String title) => ChatSessionSummary(
    id: 'a',
    title: title,
    workspacePath: '/lab',
    workspaceName: 'Lab',
    createdAt: DateTime.utc(2026),
    updatedAt: DateTime.utc(2026));
void main() {
  test(
      'compact: configuration remains unavailable until complete detail arrives',
      () async {
    final api = _Api();
    final controller = ChatController(apiClient: api);
    addTearDown(controller.dispose);
    final loading = controller.refreshSessions();
    api.reads.single.complete([
      ChatSessionSummary.fromJson({
        'id': 'a',
        'title': 'Chat',
        'workspace_path': '/lab',
        'workspace_name': 'Lab',
        'created_at': '2026-01-01T00:00:00Z',
        'updated_at': '2026-01-01T00:00:00Z',
        'has_full_agent_configuration': false
      })
    ]);
    await loading;
    final selecting = controller.selectSession('a');
    expect(controller.isLoading, isTrue);
    expect(controller.currentSession, isNull);
    api.detail.complete(SessionDetail(
        id: 'a',
        title: 'Chat',
        workspacePath: '/lab',
        workspaceName: 'Lab',
        createdAt: DateTime.utc(2026),
        updatedAt: DateTime.utc(2026),
        messages: const []));
    await selecting;
    expect(controller.currentSession!.id, 'a');
    final current = controller.currentSession;
    controller.applyJobSnapshotForTesting(const JobStatusResponse(
        jobId: 'other-job',
        sessionId: 'other',
        status: 'running',
        elapsedSeconds: 1));
    expect(identical(current, controller.currentSession), isTrue);
  });
  test('compact: large transcript decode keeps Unicode messages and cursors',
      () async {
    final content = 'Información ágil 🧉 ' * 10000;
    final api = ApiClient(
        baseUrl: 'http://localhost:1',
        client: MockClient((request) async {
          expect(request.url.queryParameters['before'], 'older');
          return http.Response.bytes(
              utf8.encode(jsonEncode({
                'id': 'a',
                'title': 'Chat',
                'workspace_path': '/lab',
                'workspace_name': 'Lab',
                'created_at': '2026-01-01T00:00:00Z',
                'updated_at': '2026-01-01T00:00:00Z',
                'messages': [
                  {
                    'id': 'm',
                    'role': 'assistant',
                    'content': content,
                    'status': 'completed',
                    'created_at': '2026-01-01T00:00:00Z',
                    'updated_at': '2026-01-01T00:00:00Z'
                  }
                ],
                'transcript_window': {
                  'oldest_cursor': 'cursor',
                  'has_older': true
                }
              })),
              200);
        }));
    final detail = await api.getSession('a', before: 'older', limit: 5);
    expect(detail.messages.single.text, content);
    expect(detail.transcriptWindow.oldestCursor, 'cursor');
    expect(detail.transcriptWindow.hasOlder, isTrue);
  });
  test('refresh: concurrent burst shares reads and observes trailing mutation',
      () async {
    final api = _Api();
    final controller = ChatController(apiClient: api);
    addTearDown(controller.dispose);
    final requests = List.generate(20, (_) => controller.refreshSessions());
    expect(api.reads.length, 1);
    api.reads.first.complete([summary('before mutation')]);
    await Future<void>.delayed(Duration.zero);
    expect(api.reads.length, 2);
    api.reads.last.complete([summary('after mutation')]);
    await Future.wait(requests);
    expect(controller.sessions.single.title, 'after mutation');
    expect(api.reads.length, 2);
  });
  test('refresh: failed shared read releases state and retry succeeds',
      () async {
    final api = _Api();
    final controller = ChatController(apiClient: api);
    addTearDown(controller.dispose);
    final first = controller.refreshSessions();
    final second = controller.refreshSessions();
    final failures = [
      expectLater(first, throwsException),
      expectLater(second, throwsException)
    ];
    api.reads.first.completeError(Exception('offline'));
    await Future.wait(failures);
    final retry = controller.refreshSessions();
    expect(api.reads.length, 2);
    api.reads.last.complete([summary('restored')]);
    await retry;
    expect(controller.sessions.single.title, 'restored');
  });
  test('refresh: disposing during shared read avoids a trailing request',
      () async {
    final api = _Api();
    final controller = ChatController(apiClient: api);
    final first = controller.refreshSessions();
    final second = controller.refreshSessions();
    controller.dispose();
    api.reads.first.complete([]);
    await Future.wait([first, second]);
    expect(api.reads.length, 1);
  });
  test(
      'refresh: identical job snapshots notify once while progress and terminal notify',
      () {
    final controller = ChatController(apiClient: _Api());
    addTearDown(controller.dispose);
    var notifications = 0;
    controller.addListener(() => notifications++);
    const snapshot = JobStatusResponse(
        jobId: 'job',
        sessionId: 'a',
        status: 'running',
        elapsedSeconds: 1,
        response: 'draft');
    for (var i = 0; i < 100; i++) {
      controller.applyJobSnapshotForTesting(snapshot.copyWith());
    }
    expect(notifications, 1);
    controller
        .applyJobSnapshotForTesting(snapshot.copyWith(response: 'draft plus'));
    controller.applyJobSnapshotForTesting(
        snapshot.copyWith(response: 'finished', status: 'completed'));
    expect(notifications, 3);
  });
  test(
      'compact: client requests compact list and accepts old servers full response',
      () async {
    final api = ApiClient(
        baseUrl: 'http://localhost:1',
        client: MockClient((request) async {
          expect(request.url.queryParameters['compact'], 'true');
          return http.Response(
              jsonEncode([
                {
                  'id': 'a',
                  'title': 'Chat',
                  'workspace_path': '/lab',
                  'workspace_name': 'Lab',
                  'created_at': '2026-01-01T00:00:00Z',
                  'updated_at': '2026-01-01T00:00:00Z',
                  'auto_reviewer_prompt': 'legacy'
                }
              ]),
              200);
        }));
    final result = await api.listSessions();
    expect(result.single.autoReviewerPrompt, 'legacy');
  });
  testWidgets(
      'render: stable paragraphs tables and links reuse spans but update text and callback',
      (tester) async {
    const text =
        'Texto **estable** y [Guía](/guide)\n\n| Nombre | Valor |\n|---|---|\n| Uno | Dos |';
    var oldTaps = 0;
    var newTaps = 0;
    await showMessage(tester, text, onLink: (_) async {
      oldTaps++;
    });
    final initial = tester
        .widgetList<SelectableText>(find.byType(SelectableText))
        .map((w) => w.textSpan)
        .toList();
    var reused = 0;
    final watch = Stopwatch()..start();
    for (var i = 0; i < 30; i++) {
      await showMessage(tester, text, onLink: (_) async {
        newTaps++;
      });
      final next = tester
          .widgetList<SelectableText>(find.byType(SelectableText))
          .map((w) => w.textSpan)
          .toList();
      expect(next.length, initial.length);
      for (var n = 0; n < initial.length; n++) {
        if (identical(initial[n], next[n])) reused++;
      }
    }
    watch.stop();
    expect(reused, 30 * initial.length);
    await tapText(tester, 'Guía');
    expect(newTaps, 1);
    expect(oldTaps, 0);
    await showMessage(
        tester, text.replaceAll('estable', 'nuevo').replaceAll('Dos', 'Tres'));
    final visible = tester
        .widgetList<SelectableText>(find.byType(SelectableText))
        .map((w) => w.textSpan?.toPlainText() ?? w.data ?? '')
        .join('\n');
    expect(visible, contains('nuevo'));
    expect(visible, contains('Tres'));
    expect(tester.takeException(), isNull);
    await tester.runAsync(() async {
      await Directory('../../reports/bridge-performance-20261010')
          .create(recursive: true);
      await File(
              '../../reports/bridge-performance-20261010/render-metrics.json')
          .writeAsString(jsonEncode({
        'stable_rebuilds': 30,
        'inline_spans': initial.length,
        'reused_spans': reused,
        'new_spans_for_stable_text': 30 * initial.length - reused,
        'widget_test_elapsed_ms': watch.elapsedMilliseconds,
        'physical_device': false
      }));
    });
  });
}
