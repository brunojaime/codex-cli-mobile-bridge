import 'dart:async';
import 'dart:math';
import 'package:cross_file/cross_file.dart';
import 'package:flutter/foundation.dart';
import '../models/outbox_entry.dart';
import 'api_client.dart';
import 'outbox_store.dart';

/// One owner per server survives switching projects and server profiles.
/// Pending records and audio survive process death; background OS execution is
/// intentionally not required. Server-accepted receipts keep running remotely.
class MessageOutbox extends ChangeNotifier {
  MessageOutbox(
      {required this.api,
      required this.store,
      this.pollInterval = const Duration(seconds: 2),
      this.retryInterval = const Duration(seconds: 5)});

  static final Map<String, MessageOutbox> _servers = {};
  static MessageOutbox forServer(ApiClient api) => _servers.putIfAbsent(
      api.baseUrl,
      () => MessageOutbox(api: api, store: createOutboxStore(api.baseUrl)));

  final ApiClient api;
  final OutboxStore store;
  final Duration pollInterval;
  final Duration retryInterval;
  final List<OutboxEntry> _entries = [];
  final Set<String> _activeLanes = {};
  final Set<String> _removing = {};
  Future<void>? _initializing;
  Future<void> _mutations = Future.value();
  final Map<String, Timer> _retryTimers = {};
  bool _closed = false;
  String? storageError;
  int _lastMicros = 0;

  List<OutboxEntry> get entries => List.unmodifiable(_entries);
  Future<T> _serialize<T>(Future<T> Function() operation) {
    final result = _mutations.then((_) => operation());
    _mutations =
        result.then<void>((_) {}, onError: (Object _, StackTrace __) {});
    return result;
  }

  Future<void> initialize() => _initializing ??= _load();
  Future<void> _load() async {
    try {
      _entries.addAll(await store.load());
      for (final entry in _entries) {
        _lastMicros = max(_lastMicros, entry.createdAt.microsecondsSinceEpoch);
      }
      storageError = null;
      if (!_closed) notifyListeners();
      _pump();
    } catch (error) {
      storageError = 'No se pudo recuperar la cola de envíos: $error';
      _initializing = null;
      if (!_closed) notifyListeners();
      rethrow;
    }
  }

  Future<void> enqueue(Map<String, dynamic> payload, {XFile? audio}) =>
      _serialize(() async {
        await initialize();
        if (_entries.where((e) => !e.isAccepted).length >= 100) {
          throw StateError(
              'La cola tiene 100 envíos pendientes. Esperá o revisá los que fallaron.');
        }
        final micros =
            max(DateTime.now().toUtc().microsecondsSinceEpoch, _lastMicros + 1);
        _lastMicros = micros;
        final random = Random.secure();
        final suffix = List.generate(16,
                (_) => random.nextInt(256).toRadixString(16).padLeft(2, '0'))
            .join();
        final entry = OutboxEntry(
            id: '$micros-$suffix',
            payload: Map.of(payload),
            createdAt:
                DateTime.fromMicrosecondsSinceEpoch(micros, isUtc: true));
        // UI gets success only after its record and independent audio copy exist.
        await store.save(entry, audio: audio);
        _entries.add(entry);
        if (!_closed) notifyListeners();
        _pump();
      });

  void _pump() {
    if (_closed) return;
    final heads = <String, OutboxEntry>{};
    for (final entry in _entries) {
      if (!entry.isAccepted) heads.putIfAbsent(entry.sessionId, () => entry);
    }
    for (final entry in heads.values) {
      if (_activeLanes.length >= 2) break;
      if (entry.needsAttention ||
          _activeLanes.contains(entry.sessionId) ||
          _retryTimers.containsKey(entry.sessionId) ||
          _removing.contains(entry.id)) {
        continue;
      }
      _activeLanes.add(entry.sessionId);
      unawaited(_deliver(entry));
    }
  }

  Future<void> _persist(OutboxEntry entry) async {
    await _serialize(() => store.save(entry));
    if (!_closed) notifyListeners();
  }

  Future<void> _deliver(OutboxEntry entry) async {
    var waitForNetwork = false;
    try {
      // Always look up the receipt first: an upload timeout may have hidden a
      // successful acceptance. Repeated POSTs use the same ID and exact payload.
      var receipt = await api.getOutboxReceipt(entry.id);
      if (_closed) return;
      if (receipt == null && entry.receiptKnown) {
        entry.state = 'uncertain';
        entry.error =
            'El servidor perdió un recibo confirmado. Revisá la entrega antes de descartar.';
        await _persist(entry);
        return;
      }
      if (receipt == null) {
        entry.state = 'uploading';
        await _persist(entry);
        receipt = await api.submitOutbox(entry.id, entry.payload,
            audio: entry.isAudio ? await store.audioFile(entry) : null);
      }
      while (!_closed) {
        entry.receiptKnown = true;
        entry.state = receipt!['state'] as String;
        entry.error = receipt['error'] as String?;
        entry.job = receipt['job'] == null
            ? null
            : Map<String, dynamic>.from(receipt['job'] as Map);
        await _persist(entry);
        if (entry.isAccepted || entry.needsAttention) return;
        if (entry.state == 'discarded') {
          await acknowledge(entry.id);
          return;
        }
        await Future<void>.delayed(pollInterval);
        if (_closed) return;
        receipt = await api.getOutboxReceipt(entry.id);
        if (receipt == null) {
          entry.state = 'uncertain';
          entry.error =
              'El servidor perdió el recibo del envío. Revisá la entrega.';
          await _persist(entry);
          return;
        }
      }
    } catch (error) {
      if (_closed) return;
      final permanent = error is OutboxApiException &&
          error.statusCode >= 400 &&
          error.statusCode < 500 &&
          error.statusCode != 408 &&
          error.statusCode != 429;
      entry.state = permanent ? 'failed' : 'waiting_connection';
      entry.error = error.toString();
      waitForNetwork = !permanent;
      try {
        await _persist(entry);
      } catch (storageFailure) {
        storageError = 'No se pudo actualizar la cola: $storageFailure';
        if (!_closed) notifyListeners();
        waitForNetwork = true;
      }
    } finally {
      _activeLanes.remove(entry.sessionId);
      if (!_closed) {
        if (waitForNetwork) {
          // Every pump must honor this lane's wait, including pumps triggered
          // by failures, completions or enqueues in other conversations.
          _retryTimers[entry.sessionId]?.cancel();
          _retryTimers[entry.sessionId] = Timer(retryInterval, () {
            _retryTimers.remove(entry.sessionId);
            _pump();
          });
        }
        // Other projects can progress while this one waits for connectivity.
        _pump();
      }
    }
  }

  Future<void> retry(String id) async {
    final entry = _entries.firstWhere((e) => e.id == id);
    if (!entry.needsAttention && entry.state != 'waiting_connection') return;
    final receipt = await api.getOutboxReceipt(id);
    if (receipt != null) await api.outboxAction(id, 'retry');
    _retryTimers.remove(entry.sessionId)?.cancel();
    entry.error = null;
    entry.state = 'queued';
    await _persist(entry);
    _pump();
  }

  Future<void> discard(String id) async {
    final entry = _entries.firstWhere((e) => e.id == id);
    if (!entry.needsAttention && entry.state != 'waiting_connection') {
      throw StateError(
          'Esperá a que termine de procesarse antes de descartarlo.');
    }
    // A disconnected device cannot safely discard an ambiguous upload.
    final receipt = await api.getOutboxReceipt(id);
    if (receipt != null) await api.outboxAction(id, 'discard');
    await acknowledge(id);
    _pump();
  }

  Future<void> acknowledge(String id) => _serialize(() async {
        if (_removing.contains(id)) return;
        final index = _entries.indexWhere((e) => e.id == id);
        if (index < 0) return;
        _removing.add(id);
        try {
          await store.remove(_entries[index]);
          _entries.removeAt(index);
        } finally {
          _removing.remove(id);
        }
        if (!_closed) notifyListeners();
      });

  Future<void> close() async {
    dispose();
    // Do not reopen the same store until its last durable write has finished.
    await _mutations;
  }

  @override
  void dispose() {
    _closed = true;
    for (final timer in _retryTimers.values) {
      timer.cancel();
    }
    _retryTimers.clear();
    super.dispose();
  }
}
