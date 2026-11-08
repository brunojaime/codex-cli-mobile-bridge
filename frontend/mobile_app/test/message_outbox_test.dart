import 'dart:convert';
import 'dart:io';
import 'package:codex_mobile_frontend/src/models/outbox_entry.dart';
import 'package:codex_mobile_frontend/src/services/api_client.dart';
import 'package:codex_mobile_frontend/src/services/message_outbox.dart';
import 'package:codex_mobile_frontend/src/services/outbox_store_io.dart';
import 'package:cross_file/cross_file.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

Future<void> until(bool Function() condition) async {
  final deadline = DateTime.now().add(const Duration(seconds: 3));
  while (!condition()) {
    if (DateTime.now().isAfter(deadline)) fail('Timed out waiting for queue');
    await Future<void>.delayed(const Duration(milliseconds: 2));
  }
}

Map<String, dynamic> payload(String session, int index, {bool audio = false}) =>
    {
      'kind': audio ? 'audio' : 'text',
      'message': '$index',
      'session_id': session,
      'conversation_key': session,
      'workspace_path': '/workspace/$session',
      if (audio) 'filename': 'voice-note.m4a',
    };

class MemoryStore implements OutboxStore {
  final Map<String, String> records = {};
  bool failSave = false;
  @override
  Future<List<OutboxEntry>> load() async => records.values
      .map((v) => OutboxEntry.fromJson(jsonDecode(v) as Map<String, dynamic>))
      .toList();
  @override
  Future<void> save(OutboxEntry e, {XFile? audio}) async {
    if (failSave) throw StateError('disk full');
    if (audio != null) e.audioData = base64Encode(await audio.readAsBytes());
    records[e.id] = jsonEncode(e.toJson());
  }

  @override
  Future<void> remove(OutboxEntry e) async {
    records.remove(e.id);
  }

  @override
  Future<XFile> audioFile(OutboxEntry e) async =>
      XFile.fromData(base64Decode(e.audioData!), name: 'voice-note.m4a');
}

class QueueApi extends ApiClient {
  QueueApi() : super(baseUrl: 'http://queue.test');
  final Map<String, Map<String, dynamic>> receipts = {};
  final List<Map<String, dynamic>> submissions = [];
  final List<List<int>> uploadedBytes = [];
  final List<String> receiptRequests = [];
  bool completeImmediately = false;
  bool loseNextResponse = false;
  bool offline = false;
  int transientReceiptFailures = 0;
  @override
  Future<Map<String, dynamic>?> getOutboxReceipt(String id) async {
    receiptRequests.add(id);
    if (transientReceiptFailures > 0) {
      transientReceiptFailures--;
      throw const SocketException('transient offline');
    }
    if (offline) throw const SocketException('offline');
    return receipts[id];
  }

  @override
  Future<Map<String, dynamic>> submitOutbox(
      String id, Map<String, dynamic> payload,
      {XFile? audio}) async {
    submissions.add({'id': id, ...payload});
    if (audio != null) uploadedBytes.add(await audio.readAsBytes());
    receipts[id] = {
      'id': id,
      'state': 'transcribing',
      'job': null,
      'error': null
    };
    if (completeImmediately) complete(id);
    if (loseNextResponse) {
      loseNextResponse = false;
      throw const SocketException('lost acceptance');
    }
    return receipts[id]!;
  }

  void complete(String id) {
    final submission = submissions.firstWhere((s) => s['id'] == id);
    receipts[id] = {
      'id': id,
      'state': 'accepted',
      'error': null,
      'job': {
        'job_id': 'job-$id',
        'session_id': submission['session_id'],
        'status': 'pending',
        'run_id': 'run-$id',
        'user_text': submission['message']
      }
    };
  }
}

void main() {
  test('a confirmed receipt that disappears never triggers another upload',
      () async {
    final store = MemoryStore();
    final entry = OutboxEntry(
        id: 'previously-confirmed-receipt',
        payload: payload('a', 0),
        createdAt: DateTime.now(),
        state: 'transcribing',
        receiptKnown: true);
    await store.save(entry);
    final api = QueueApi();
    final queue = MessageOutbox(api: api, store: store);
    addTearDown(queue.dispose);
    await queue.initialize();
    await until(() => queue.entries.single.state == 'uncertain');
    expect(api.submissions, isEmpty);
  });

  test('on-disk queues are isolated by server profile', () async {
    final directory = await Directory.systemTemp.createTemp('outbox-servers-');
    addTearDown(() => directory.delete(recursive: true));
    final first =
        FileOutboxStore('http://first.test', rootDirectory: directory.path);
    final second =
        FileOutboxStore('http://second.test', rootDirectory: directory.path);
    await first.save(OutboxEntry(
        id: 'one', payload: payload('a', 0), createdAt: DateTime.now()));
    expect((await first.load()).single.id, 'one');
    expect(await second.load(), isEmpty);
  });

  test('20 mixed sends save locally, preserve order and free other projects',
      () async {
    final api = QueueApi();
    final store = MemoryStore();
    final queue = MessageOutbox(
        api: api, store: store, pollInterval: const Duration(milliseconds: 5));
    addTearDown(queue.dispose);
    for (var i = 0; i < 20; i++) {
      await queue.enqueue(payload('a', i, audio: i.isEven),
          audio: i.isEven
              ? XFile.fromData(utf8.encode('audio-$i'), name: 'note.m4a')
              : null);
    }
    expect(store.records.length, 20);
    await until(() => api.submissions.isNotEmpty);
    expect(api.submissions.length, 1);
    await queue.enqueue(payload('b', 100));
    await until(() => api.submissions.length == 2);
    expect(api.submissions.last['session_id'], 'b');
    api.complete(api.submissions.last['id'] as String);
    await until(
        () => queue.entries.any((e) => e.sessionId == 'b' && e.isAccepted));
    api.completeImmediately = true;
    api.complete(api.submissions.first['id'] as String);
    await until(() => queue.entries.every((e) => e.isAccepted));
    expect(
        api.submissions
            .where((s) => s['session_id'] == 'a')
            .map((s) => s['message']),
        List.generate(20, (i) => '$i'));
    expect(api.uploadedBytes.length, 10);
    expect(api.uploadedBytes.first, utf8.encode('audio-0'));
  });
  test('lost acceptance recovers by receipt with no second upload', () async {
    final api = QueueApi()
      ..loseNextResponse = true
      ..completeImmediately = true;
    final queue = MessageOutbox(
        api: api,
        store: MemoryStore(),
        retryInterval: const Duration(milliseconds: 5));
    addTearDown(queue.dispose);
    await queue.enqueue(payload('a', 1));
    await until(() => queue.entries.single.isAccepted);
    expect(api.submissions.length, 1);
  });
  testWidgets('disconnected conversations each wait their full retry interval',
      (tester) async {
    // Bound failures so a retry storm fails assertions instead of hanging.
    final api = QueueApi()
      ..transientReceiptFailures = 4
      ..completeImmediately = true;
    final queue = MessageOutbox(
        api: api,
        store: MemoryStore(),
        retryInterval: const Duration(seconds: 5));
    addTearDown(queue.dispose);

    await queue.enqueue(payload('a', 0));
    await tester.pump();
    final a = queue.entries.single.id;
    expect(queue.entries.single.state, 'waiting_connection');
    expect(api.receiptRequests, [a]);

    await tester.pump(const Duration(seconds: 2));
    await queue.enqueue(payload('b', 0));
    await tester.pump();
    final b = queue.entries.last.id;
    expect(queue.entries.last.state, 'waiting_connection');
    expect(api.receiptRequests, [a, b]);

    // Enqueue pumps and queued followers must respect both lane cooldowns.
    await queue.enqueue(payload('a', 1));
    await queue.enqueue(payload('b', 1));
    await tester.pump();
    expect(api.receiptRequests, [a, b]);
    await tester.pump(const Duration(seconds: 2));
    api.transientReceiptFailures = 0;
    await queue.enqueue(payload('c', 0));
    await tester.pump();
    expect(api.submissions.single['session_id'], 'c');
    expect(api.receiptRequests.where((id) => id == a).length, 1);
    expect(api.receiptRequests.where((id) => id == b).length, 1);

    await tester.pump(const Duration(milliseconds: 999));
    expect(api.submissions.length, 1);
    await tester.pump(const Duration(milliseconds: 1));
    expect(api.receiptRequests.where((id) => id == a).length, 2);
    expect(api.receiptRequests.where((id) => id == b).length, 1);
    expect(
        api.submissions
            .where((s) => s['session_id'] == 'a')
            .map((s) => s['message']),
        ['0', '1']);

    await tester.pump(const Duration(milliseconds: 1999));
    expect(api.receiptRequests.where((id) => id == b).length, 1);
    await tester.pump(const Duration(milliseconds: 1));
    expect(api.receiptRequests.where((id) => id == b).length, 2);
    expect(
        api.submissions
            .where((s) => s['session_id'] == 'b')
            .map((s) => s['message']),
        ['0', '1']);
    expect(queue.entries.every((e) => e.isAccepted), isTrue);
    expect(api.submissions.length, 5);
    expect(api.submissions.map((s) => s['id']).toSet().length, 5);
  });
  test('failed save rejects enqueue and preserves original audio', () async {
    final api = QueueApi();
    final store = MemoryStore()..failSave = true;
    final queue = MessageOutbox(api: api, store: store);
    addTearDown(queue.dispose);
    final audio =
        XFile.fromData(utf8.encode('original audio'), name: 'note.m4a');
    await expectLater(queue.enqueue(payload('a', 0, audio: true), audio: audio),
        throwsStateError);
    expect(queue.entries, isEmpty);
    expect(api.submissions, isEmpty);
    expect(await audio.readAsString(), 'original audio');
  });
  test('disk outbox restores audio after original recording is deleted',
      () async {
    final directory = await Directory.systemTemp.createTemp('outbox-test-');
    addTearDown(() => directory.delete(recursive: true));
    final source = File('${directory.path}/recording.m4a');
    await source.writeAsString('durable audio');
    final api = QueueApi()..offline = true;
    final store = FileOutboxStore(api.baseUrl, rootDirectory: directory.path);
    final original = MessageOutbox(
        api: api, store: store, retryInterval: const Duration(milliseconds: 5));
    await original.enqueue(payload('a', 0, audio: true),
        audio: XFile(source.path, name: 'recording.m4a'));
    await until(() => original.entries.single.state == 'waiting_connection');
    await original.close();
    await source.delete();
    api.offline = false;
    api.completeImmediately = true;
    final restored = MessageOutbox(
        api: api,
        store: FileOutboxStore(api.baseUrl, rootDirectory: directory.path));
    addTearDown(restored.dispose);
    await restored.initialize();
    await until(() => restored.entries.single.isAccepted);
    expect(api.uploadedBytes.single, utf8.encode('durable audio'));
    final entry = restored.entries.single;
    await restored.acknowledge(entry.id);
    expect(await store.load(), isEmpty);
    expect(await File(entry.audioPath!).exists(), isFalse);
  });
  test('failed turn holds its lane while another project continues', () async {
    final api = QueueApi();
    final queue = MessageOutbox(
        api: api,
        store: MemoryStore(),
        pollInterval: const Duration(milliseconds: 5));
    addTearDown(queue.dispose);
    await queue.enqueue(payload('a', 0));
    await until(() => api.submissions.isNotEmpty);
    final id = api.submissions.first['id'] as String;
    api.receipts[id] = {
      'id': id,
      'state': 'failed',
      'error': 'bad audio',
      'job': null
    };
    await until(() => queue.entries.first.needsAttention);
    await queue.enqueue(payload('a', 1));
    await queue.enqueue(payload('b', 2));
    await until(() => api.submissions.length == 2);
    expect(api.submissions.last['session_id'], 'b');
    expect(queue.entries.where((e) => e.sessionId == 'a').last.state, 'queued');
  });
  test('API uses durable endpoint, stable ID and exact audio bytes', () async {
    final seen = <http.Request>[];
    final api = ApiClient(
        baseUrl: 'http://queue.test/api/v1',
        client: MockClient((request) async {
          seen.add(request);
          if (request.method == 'GET') return http.Response('{}', 404);
          expect(request.bodyBytes,
              containsAllInOrder(utf8.encode('exact-audio')));
          expect(request.body, contains('"session_id":"a"'));
          return http.Response(
              jsonEncode({'id': 'stable-submission-123', 'state': 'queued'}),
              202);
        }));
    expect(await api.getOutboxReceipt('stable-submission-123'), isNull);
    await api.submitOutbox(
        'stable-submission-123', payload('a', 0, audio: true),
        audio: XFile.fromData(utf8.encode('exact-audio'), name: 'note.m4a'));
    expect(seen.map((r) => r.url.path),
        everyElement('/api/v1/message-outbox/stable-submission-123'));
  });
}
