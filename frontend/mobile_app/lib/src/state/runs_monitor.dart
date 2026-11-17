import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../models/run_overview.dart';
import '../services/api_client.dart';
import '../services/run_alerts.dart';

typedef WebSocketConnector = WebSocketChannel Function(Uri uri);

/// Live list of every run on the server (`WS /ws/runs`) for the dashboard.
///
/// It also raises alerts when a run starts waiting for the user or finishes,
/// so nobody has to keep the dashboard open to notice.
class RunsMonitor extends ChangeNotifier {
  RunsMonitor({
    required RunAlerts alerts,
    WebSocketConnector? connector,
    this.onOpenSession,
  })  : _alerts = alerts,
        _connector = connector ?? WebSocketChannel.connect;

  final RunAlerts _alerts;
  final WebSocketConnector _connector;

  /// Called when the user clicks a system notification.
  void Function(String sessionId)? onOpenSession;

  ApiClient? _client;
  WebSocketChannel? _channel;
  StreamSubscription<dynamic>? _subscription;
  Timer? _reconnectTimer;
  int _attempt = 0;
  bool _disposed = false;

  RunsOverview _overview = RunsOverview.empty;
  bool _loaded = false;
  bool _connected = false;
  String? _errorText;
  final Set<String> _answering = <String>{};

  // What was already announced, so each alert fires once.
  final Set<String> _announcedRequests = <String>{};
  final Map<String, RunState> _lastStates = <String, RunState>{};
  bool _primed = false;

  RunsOverview get overview => _overview;
  bool get loaded => _loaded;
  bool get connected => _connected;
  String? get errorText => _errorText;
  RunAlerts get alerts => _alerts;
  bool isAnswering(String requestId) => _answering.contains(requestId);

  /// Connects (or reconnects) to [client]'s server.
  void attach(ApiClient client) {
    if (identical(_client, client) ||
        (_client?.baseUrl == client.baseUrl && _channel != null)) {
      _client = client;
      return;
    }
    _client = client;
    _overview = RunsOverview.empty;
    _loaded = false;
    _primed = false;
    _announcedRequests.clear();
    _lastStates.clear();
    _connect(immediate: true);
  }

  void _connect({bool immediate = false}) {
    _reconnectTimer?.cancel();
    _closeChannel();
    final client = _client;
    if (client == null || _disposed) return;
    if (!immediate) {
      final seconds = [1, 2, 4, 8, 15][_attempt.clamp(0, 4)];
      _reconnectTimer = Timer(Duration(seconds: seconds), () => _open(client));
      return;
    }
    _open(client);
  }

  void _open(ApiClient client) {
    if (_disposed || !identical(client, _client)) return;
    final WebSocketChannel channel;
    try {
      channel = _connector(client.runsStreamUri());
    } catch (error) {
      _onDisconnected(error);
      return;
    }
    _channel = channel;
    _subscription = channel.stream.listen(
      (dynamic raw) {
        if (!identical(channel, _channel)) return;
        Map<String, dynamic> data;
        try {
          data = jsonDecode(raw as String) as Map<String, dynamic>;
        } catch (_) {
          return;
        }
        _attempt = 0;
        if (!_connected || _errorText != null) {
          _connected = true;
          _errorText = null;
        }
        try {
          if (data['type'] == 'runs.overview') {
            _apply(RunsOverview.fromJson(data));
          } else {
            notifyListeners();
          }
        } catch (error, stack) {
          // Never leave the dashboard stuck on "loading" silently.
          debugPrint('RunsMonitor: invalid overview: $error\n$stack');
          _errorText = 'El panel recibió datos que no pudo mostrar: $error';
          notifyListeners();
        }
      },
      onError: (Object error) {
        if (identical(channel, _channel)) _onDisconnected(error);
      },
      onDone: () {
        if (identical(channel, _channel)) _onDisconnected(null);
      },
    );
    // A first HTTP load keeps the dashboard useful if sockets are blocked.
    unawaited(_loadOnce(client));
  }

  Future<void> _loadOnce(ApiClient client) async {
    try {
      final overview = await client.getRunsOverview();
      if (_disposed || !identical(client, _client) || _loaded) return;
      _apply(overview);
    } catch (error) {
      if (!_loaded) {
        _errorText = 'No pude cargar el panel: $error';
        notifyListeners();
      }
    }
  }

  void _onDisconnected(Object? error) {
    if (_disposed) return;
    _connected = false;
    _attempt += 1;
    _errorText = _attempt > 2 ? 'Sin conexión con el servidor. Reintentando…' : null;
    notifyListeners();
    _connect();
  }

  @visibleForTesting
  void debugApply(RunsOverview overview) => _apply(overview);

  /// Fetches the overview now (pull to refresh).
  Future<void> refresh() async {
    final client = _client;
    if (client == null) return;
    try {
      _apply(await client.getRunsOverview());
    } catch (error) {
      _errorText = 'No pude actualizar el panel: $error';
      notifyListeners();
    }
  }

  void _apply(RunsOverview overview) {
    _overview = overview;
    _loaded = true;
    _raiseAlerts(overview);
    _alerts.setAttentionCount(overview.count(RunState.needsYou));
    notifyListeners();
  }

  void _raiseAlerts(RunsOverview overview) {
    final firstLoad = !_primed;
    _primed = true;
    for (final run in overview.runs) {
      final previous = _lastStates[run.jobId];
      _lastStates[run.jobId] = run.state;
      for (final pending in run.pending) {
        if (!_announcedRequests.add(pending.requestId) || firstLoad) continue;
        _alert(
          run,
          title: pending.isQuestion
              ? '${run.engineLabel} te pregunta'
              : pending.isPlan
                  ? '${run.engineLabel} propone un plan'
                  : '${run.engineLabel} necesita permiso',
          body: '${run.sessionTitle}: ${pending.title}',
          tag: 'need-${pending.requestId}',
        );
      }
      final wasActive = previous == RunState.working ||
          previous == RunState.needsYou ||
          previous == RunState.queued;
      if (firstLoad || !wasActive) continue;
      if (run.state == RunState.done) {
        _alert(run,
            title: 'Terminó: ${run.sessionTitle}',
            body: run.headline,
            tag: 'end-${run.jobId}');
      } else if (run.state == RunState.failed) {
        _alert(run,
            title: 'Falló: ${run.sessionTitle}',
            body: run.headline,
            tag: 'end-${run.jobId}');
      }
    }
  }

  void _alert(RunCard run,
      {required String title, required String body, required String tag}) {
    if (!_alerts.userAway) return;
    _alerts.notify(
      title: title,
      body: body,
      tag: tag,
      onClick: () => onOpenSession?.call(run.sessionId),
    );
  }

  /// Sends the user's decision; removes the request from view right away.
  Future<bool> respond(
    RunCard run,
    PendingInteraction pending,
    InteractionDecision decision,
  ) async {
    final client = _client;
    if (client == null || !_answering.add(pending.requestId)) return false;
    notifyListeners();
    try {
      final answered = await client.respondInteraction(
          run.jobId, pending.requestId, decision);
      _overview = RunsOverview(
        runs: _overview.runs.map((item) {
          if (item.jobId != run.jobId) return item;
          final rest =
              item.pending.where((p) => p.requestId != pending.requestId).toList();
          return RunCard(
            jobId: item.jobId,
            sessionId: item.sessionId,
            sessionTitle: item.sessionTitle,
            workspaceName: item.workspaceName,
            engine: item.engine,
            state: rest.isEmpty && item.state == RunState.needsYou
                ? RunState.working
                : item.state,
            request: item.request,
            headline: rest.isEmpty ? 'Siguiendo con lo que le indicaste' : item.headline,
            output: item.output,
            pending: rest,
            steps: item.steps,
            failedSteps: item.failedSteps,
            filesChanged: item.filesChanged,
            elapsedSeconds: item.elapsedSeconds,
            receivedAt: item.receivedAt,
            error: item.error,
            createdAt: item.createdAt,
            updatedAt: item.updatedAt,
            completedAt: item.completedAt,
          );
        }).toList(),
      );
      _alerts.setAttentionCount(_overview.count(RunState.needsYou));
      if (!answered) {
        _errorText = 'Ese pedido ya no estaba esperando respuesta.';
      }
      return answered;
    } catch (error) {
      _errorText = 'No pude enviar tu respuesta: $error';
      return false;
    } finally {
      _answering.remove(pending.requestId);
      notifyListeners();
    }
  }

  void clearError() {
    if (_errorText == null) return;
    _errorText = null;
    notifyListeners();
  }

  void _closeChannel() {
    unawaited(_subscription?.cancel());
    _subscription = null;
    try {
      unawaited(_channel?.sink.close());
    } catch (_) {}
    _channel = null;
  }

  @override
  void dispose() {
    _disposed = true;
    _reconnectTimer?.cancel();
    _closeChannel();
    _alerts.setAttentionCount(0);
    super.dispose();
  }
}
