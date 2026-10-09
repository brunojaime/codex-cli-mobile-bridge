import 'dart:async';
import 'dart:convert';

import 'package:codex_mobile_frontend/src/models/agent_configuration.dart';
import 'package:codex_mobile_frontend/src/models/chat_message.dart';
import 'package:codex_mobile_frontend/src/models/codex_tooling.dart';
import 'package:codex_mobile_frontend/src/models/chat_session_summary.dart';
import 'package:codex_mobile_frontend/src/models/job_status_response.dart';
import 'package:codex_mobile_frontend/src/models/session_detail.dart';
import 'package:codex_mobile_frontend/src/services/api_client.dart';
import 'package:codex_mobile_frontend/src/services/chat_notification_service.dart';
import 'package:codex_mobile_frontend/src/screens/chat_screen.dart';
import 'package:codex_mobile_frontend/src/state/chat_controller.dart';
import 'package:codex_mobile_frontend/src/widgets/chat_bubble.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  late _DelayedApi api;
  late ChatController controller;
  var controllerDisposed = false;
  setUp(() {
    controllerDisposed = false;
    api = _DelayedApi();
    controller = ChatController(apiClient: api);
  });
  tearDown(() {
    if (!controllerDisposed) controller.dispose();
  });

  test('switch: cached history is synchronous while network is blocked',
      () async {
    await controller.selectSession('a');
    await controller.selectSession('b');
    final delayed = Completer<SessionDetail>();
    api.read = (_, __) => delayed.future;
    final loading = controller.selectSession('a');
    expect(controller.selectedSessionId, 'a');
    expect(controller.messages.single.text, 'history a');
    expect(controller.isLoading, isFalse);
    delayed.complete(_session('a', text: 'fresh a'));
    await loading;
    expect(controller.messages.single.text, 'fresh a');
  });

  test('switch: out of order success and error cannot replace newer selection',
      () async {
    final a = Completer<SessionDetail>();
    final b = Completer<SessionDetail>();
    api.read = (id, _) => id == 'a' ? a.future : b.future;
    final first = controller.selectSession('a');
    final second = controller.selectSession('b');
    b.complete(_session('b'));
    await second;
    a.complete(_session('a'));
    await first;
    expect(controller.selectedSessionId, 'b');
    expect(controller.currentSession!.id, 'b');
    final failure = Completer<SessionDetail>();
    api.read =
        (id, _) => id == 'a' ? failure.future : Future.value(_session(id));
    final failing = controller.selectSession('a');
    await controller.selectSession('b');
    failure.completeError(Exception('old failure'));
    await failing;
    expect(controller.errorText, isNull);
    expect(controller.currentSession!.id, 'b');
  });

  test('switch: failed refresh keeps cached history and reports the failure',
      () async {
    await controller.selectSession('a');
    await controller.selectSession('b');
    api.read = (_, __) async => throw Exception('offline');
    await controller.selectSession('a');
    expect(controller.messages.single.text, 'history a');
    expect(controller.errorText, contains('offline'));
    expect(controller.isLoading, isFalse);
  });

  test('switch: preserve current on invalid internal navigation', () async {
    await controller.selectSession('a');
    api.read = (_, __) async => throw Exception('404');
    await controller.selectSession('missing', preserveCurrentOnError: true);
    expect(controller.selectedSessionId, 'a');
    expect(controller.messages.single.text, 'history a');
  });

  test('switch: cache evicts older sessions and oversized transcripts',
      () async {
    for (var i = 0; i <= ChatController.sessionCacheLimit; i++) {
      await controller.selectSession('$i');
    }
    final blocked = Completer<SessionDetail>();
    api.read = (_, __) => blocked.future;
    final loading = controller.selectSession('0');
    expect(controller.messages, isEmpty);
    expect(controller.isLoading, isTrue);
    blocked.complete(_session('0',
        text: 'x' * (ChatController.sessionCacheCharacterLimit + 1)));
    await loading;
    api.read = (id, _) async => _session(id);
    await controller.selectSession('b');
    final large = Completer<SessionDetail>();
    api.read = (_, __) => large.future;
    final reloading = controller.selectSession('0');
    expect(controller.messages, isEmpty);
    large.complete(_session('0'));
    await reloading;
  });

  test('switch: paginated history and cursor survive switching and refresh',
      () async {
    api.read = (id, before) async => _session(id).copyWith(
          messages: [
            if (before != null) _message('old', 'older'),
            _message('current', 'current')
          ],
          transcriptWindow: TranscriptWindow(
              oldestCursor: before == null ? 'current' : 'old',
              hasOlder: before == null,
              isPartial: before == null),
        );
    await controller.selectSession('a');
    await controller.loadOlderMessages();
    await controller.selectSession('b');
    await controller.selectSession('a');
    expect(controller.messages.map((m) => m.id), ['old', 'current']);
    expect(controller.hasOlderMessages, isFalse);
    expect(controller.currentSession!.transcriptWindow.oldestCursor, 'old');
  });

  test(
      'send: pending immediately, duplicate tap blocked, accepted before refresh',
      () async {
    await controller.selectSession('a');
    final sending = controller.sendMessage('hello');
    expect(controller.messages.last.text, 'hello');
    expect(controller.messages.last.status, ChatMessageStatus.sending);
    expect(await controller.sendMessage('hello'), isFalse);
    expect(api.sendCount, 1);
    final list = Completer<List<ChatSessionSummary>>();
    final transcript = Completer<SessionDetail>();
    api.list = () => list.future;
    api.read = (_, __) => transcript.future;
    api.accept.complete(_accepted());
    expect(await sending.timeout(const Duration(seconds: 1)), isTrue);
    expect(controller.messages.last.status, ChatMessageStatus.completed);
    expect(list.isCompleted, isFalse);
    expect(transcript.isCompleted, isFalse);
    transcript.complete(_session('a').copyWith(messages: [
      _message('server-user', 'hello', runId: 'run-1'),
    ]));
    await _tick();
    expect(controller.messages.where((m) => m.text == 'hello').length, 1);
    expect(controller.messages.last.id, 'server-user');
    list.complete([]);
    await _tick();
  });

  test('send: refresh failure never reports accepted message as send failure',
      () async {
    await controller.selectSession('a');
    api.list = () async => throw Exception('list failed');
    api.read = (_, __) async => throw Exception('detail failed');
    final sending = controller.sendMessage('hello');
    api.accept.complete(_accepted());
    expect(await sending, isTrue);
    await _tick();
    expect(controller.messages.last.text, 'hello');
    expect(controller.errorText, contains('Message accepted'));
    expect(controller.errorText, isNot(contains('Failed to send')));
  });

  test('send: failure removes optimistic message and permits explicit retry',
      () async {
    await controller.selectSession('a');
    final sending = controller.sendMessage('retry me');
    api.accept.completeError(Exception('rejected'));
    expect(await sending, isFalse);
    expect(controller.messages.any((m) => m.text == 'retry me'), isFalse);
    expect(controller.errorText, contains('Failed to send'));
    api.accept = Completer<JobStatusResponse>();
    final retry = controller.sendMessage('retry me');
    expect(api.sendCount, 2);
    api.accept.complete(_accepted());
    expect(await retry, isTrue);
    await _tick();
  });

  test('send: late acceptance and reload keep newly selected conversation',
      () async {
    await controller.selectSession('a');
    final sending = controller.sendMessage('hello');
    await controller.selectSession('b');
    api.accept.complete(_accepted());
    expect(await sending, isTrue);
    await _tick();
    expect(controller.currentSession!.id, 'b');
    expect(controller.messages.any((m) => m.text == 'hello'), isFalse);
    await controller.selectSession('a');
    final reload = Completer<SessionDetail>();
    api.read =
        (id, _) => id == 'a' ? reload.future : Future.value(_session(id));
    api.accept = Completer<JobStatusResponse>();
    final second = controller.sendMessage('second');
    api.accept.complete(_accepted());
    await second;
    await controller.selectSession('b');
    reload.complete(_session('a'));
    await _tick();
    expect(controller.currentSession!.id, 'b');
    expect(controller.selectedSessionId, 'b');
  });

  test('send: repeated historical text does not hide pending message',
      () async {
    api.read = (id, _) async => _session(id, text: 'hello');
    await controller.selectSession('a');
    final sending = controller.sendMessage('hello');
    expect(controller.messages.where((m) => m.text == 'hello').length, 2);
    api.accept.complete(_accepted());
    await sending;
    await _tick();
    expect(controller.messages.where((m) => m.text == 'hello').length, 2);
  });

  test('send: new conversation displays pending text before session exists',
      () async {
    final sending = controller.sendMessage('new chat');
    expect(controller.messages.single.text, 'new chat');
    api.accept.complete(_accepted());
    expect(await sending, isTrue);
    await _tick();
    expect(controller.selectedSessionId, 'a');
    expect(controller.messages.last.text, 'new chat');
  });

  test('decode: large real schema is parsed with all agent settings intact',
      () async {
    final prompt = 'configuration ' * 10000;
    final client = ApiClient(
        baseUrl: 'http://bridge.test',
        client: MockClient((_) async {
          return http.Response(
              jsonEncode([
                {
                  'id': 'a',
                  'title': 'Chat',
                  'workspace_path': '/work',
                  'workspace_name': 'Work',
                  'created_at': _date.toIso8601String(),
                  'updated_at': _date.toIso8601String(),
                  'auto_reviewer_prompt': prompt,
                  'agent_configuration': kDefaultAgentConfiguration.toJson(),
                }
              ]),
              200,
              headers: {'content-type': 'application/json; charset=utf-8'});
        }));
    final sessions = await client.listSessions();
    expect(sessions.single.autoReviewerPrompt, prompt);
    expect(sessions.single.agentConfiguration.toJson(),
        kDefaultAgentConfiguration.toJson());
  });

  for (final fails in [true, false]) {
    testWidgets(
        'send: composer preserves ${fails ? "failed text" : "new draft while accepting"}',
        (tester) async {
      api.accept = Completer<JobStatusResponse>();
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      await controller.selectSession('a');
      await tester.pumpWidget(MaterialApp(
          home: ChatScreen(
        initialApiBaseUrl: 'http://127.0.0.1:1',
        notificationService: const NoopChatNotificationService(),
        controllerOverride: controller,
        enableServerBootstrap: false,
      )));
      await tester.pumpAndSettle();
      final field = find.byType(TextField).first;
      await tester.enterText(field, 'original draft');
      await tester.pump();
      await tester.tap(find.byIcon(Icons.arrow_upward_rounded).first);
      await tester.pump();
      expect(controller.messages.last.text, 'original draft');
      expect(controller.messages.last.status, ChatMessageStatus.sending);
      if (fails) {
        api.accept.completeError(Exception('rejected'));
      } else {
        await tester.enterText(field, 'next draft');
        api.accept.complete(_accepted());
      }
      await tester.pumpAndSettle();
      expect(tester.widget<TextField>(field).controller!.text,
          fails ? 'original draft' : 'next draft');
      // Unmount listeners before disposing the controller in tearDown.
      await tester.pumpWidget(const SizedBox());
      controller.dispose();
      controllerDisposed = true;
    });
  }

  testWidgets('send: first conversation shows pending bubble before HTTP acceptance', (tester) async {
    api.accept = Completer<JobStatusResponse>();
    await tester.pumpWidget(MaterialApp(home: ChatScreen(
      initialApiBaseUrl: 'http://127.0.0.1:1',
      notificationService: const NoopChatNotificationService(),
      controllerOverride: controller, enableServerBootstrap: false,
    )));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).first, 'first message');
    await tester.pump();
    await tester.tap(find.byIcon(Icons.arrow_upward_rounded).first);
    await tester.pumpAndSettle();
    expect(find.text('Enviando…'), findsOneWidget);
    expect(api.accept.isCompleted, isFalse);
    api.accept.completeError(Exception('test rejection'));
    await tester.pumpAndSettle();
    await tester.pumpWidget(const SizedBox());
    controller.dispose();
    controllerDisposed = true;
  });

  testWidgets('send: real bubble distinguishes pending from accepted',
      (tester) async {
    final pending =
        _message('local', 'hello').copyWith(status: ChatMessageStatus.sending);
    await tester.pumpWidget(
        MaterialApp(home: Scaffold(body: ChatBubble(message: pending))));
    expect(find.text('Enviando…'), findsOneWidget);
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: ChatBubble(
                message:
                    pending.copyWith(status: ChatMessageStatus.completed)))));
    expect(find.text('Enviando…'), findsNothing);
  });
}

Future<void> _tick() => Future<void>.delayed(Duration.zero);
final _date = DateTime.utc(2026, 10, 9);
ChatMessage _message(String id, String text, {String? runId}) => ChatMessage(
      id: id,
      text: text,
      isUser: true,
      authorType: ChatMessageAuthorType.human,
      status: ChatMessageStatus.completed,
      createdAt:
          id == 'old' ? _date.subtract(const Duration(seconds: 1)) : _date,
      updatedAt: _date,
      runId: runId,
    );
SessionDetail _session(String id, {String? text}) => SessionDetail(
      id: id,
      title: id,
      workspacePath: '/work',
      workspaceName: 'Work',
      createdAt: _date,
      updatedAt: _date,
      messages: [_message('history-$id', text ?? 'history $id')],
    );
JobStatusResponse _accepted() => const JobStatusResponse(
      jobId: 'job-1',
      sessionId: 'a',
      status: 'running',
      elapsedSeconds: 0,
      runId: 'run-1',
    );

class _DelayedApi extends ApiClient {
  _DelayedApi() : super(baseUrl: 'http://127.0.0.1:1');
  Future<SessionDetail> Function(String, String?)? read;
  Future<List<ChatSessionSummary>> Function()? list;
  Completer<JobStatusResponse> accept = Completer<JobStatusResponse>();
  int sendCount = 0;
  @override
  Future<SessionDetail> getSession(String id,
          {String? before, int? limit, bool fullTranscript = false}) =>
      read?.call(id, before) ?? Future.value(_session(id));
  @override
  Future<List<ChatSessionSummary>> listSessions() =>
      list?.call() ?? Future.value([]);
  @override
  Future<JobStatusResponse> sendMessage(String message,
      {String? sessionId,
      String? workspacePath,
      CodexRunOptions? codexRunOptions}) {
    sendCount++;
    return accept.future;
  }

  @override
  Future<JobStatusResponse> getJob(String id) async =>
      throw Exception('test polling unavailable');
}
