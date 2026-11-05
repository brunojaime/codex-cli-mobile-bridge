import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/agent_proposal.dart';
import '../services/agent_proposal_client.dart';
import '../services/proposal_notification.dart';

class AgentProposalController extends ChangeNotifier {
  AgentProposalController({required this.client, this.notifications});
  final AgentProposalClient client;
  final ProposalNotificationService? notifications;
  List<AgentProposal> items = [];
  int unreadCount = 0;
  bool loading = false;
  bool busy = false;
  bool hasMore = false;
  String? error;
  String? notificationError;
  void Function(AgentProposal proposal, int count)? onNewProposal;
  Timer? _timer;
  bool _refreshing = false;
  bool _disposed = false;

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  void start() {
    if (_disposed) return;
    _timer ??= Timer.periodic(const Duration(seconds: 30), (_) => refresh());
    unawaited(refresh());
  }

  void pause() {
    _timer?.cancel();
    _timer = null;
  }

  Future<void> refresh({bool more = false}) async {
    if (_disposed || _refreshing) return;
    _refreshing = true;
    loading = items.isEmpty;
    _notify();
    try {
      final result = await client.list(offset: more ? items.length : 0);
      if (_disposed) return;
      final loaded = (result['items'] as List)
          .map((item) => AgentProposal(item as Map<String, dynamic>))
          .toList();
      items = more
          ? {
              for (final p in [...items, ...loaded]) p.id: p
            }.values.toList()
          : loaded;
      unreadCount = result['unread_count'] as int;
      hasMore = result['has_more'] == true;
      error = null;
      _notify();
      await _notifyNew(loaded);
    } catch (e) {
      if (!_disposed) {
        error = e is ProposalApiException
            ? e.message
            : 'No se pudo conectar. Tus propuestas siguen en el servidor.';
      }
    } finally {
      loading = false;
      _refreshing = false;
      _notify();
    }
  }

  Future<void> _notifyNew(List<AgentProposal> loaded) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      if (_disposed) return;
      final key =
          'agent_proposal_notices_v1_${Uri.encodeComponent(client.baseUrl)}';
      final seen = (prefs.getStringList(key) ?? []).toSet();
      final fresh = loaded
          .where((p) =>
              p.unread &&
              p.canRespond &&
              !seen.contains('${p.id}:${p.revision}'))
          .toList();
      if (fresh.isEmpty) return;
      final latest = fresh.first;
      if (notifications != null) {
        try {
          await notifications!.showProposal(ProposalNotificationTarget(
              server: client.baseUrl,
              id: latest.id,
              revision: latest.revision));
        } catch (_) {
          // Inbox and in-app notice still work if native permission/display fails.
          notificationError =
              'No se pudo mostrar el aviso del sistema. La propuesta está en la bandeja.';
        }
      }
      if (_disposed) return;
      onNewProposal?.call(latest, fresh.length);
      seen.addAll(fresh.map((p) => '${p.id}:${p.revision}'));
      final values = seen.toList();
      if (!await prefs.setStringList(
          key,
          values
              .skip(values.length > 1000 ? values.length - 1000 : 0)
              .toList())) {
        notificationError =
            'No se pudo guardar el registro de avisos en este dispositivo.';
      }
    } catch (_) {
      notificationError =
          'No se pudo actualizar el registro de avisos. Podés revisar la bandeja.';
    }
  }

  Future<AgentProposal> open(String id) async {
    final current = await client.get(id);
    final read = await client.read(current);
    _replace(read);
    return read;
  }

  void _replace(AgentProposal updated) {
    if (_disposed) return;
    final old = items.where((p) => p.id == updated.id).firstOrNull;
    if (old?.unread == true && !updated.unread && unreadCount > 0) {
      unreadCount--;
    }
    items = [
      for (final p in items)
        if (p.id == updated.id) updated else p
    ];
    if (old == null) items.insert(0, updated);
    _notify();
  }

  Future<AgentProposal> decide(AgentProposal proposal, String action,
      {String observations = ''}) async {
    if (busy) throw StateError('Hay una respuesta en curso');
    busy = true;
    _notify();
    try {
      final updated =
          await client.decide(proposal, action, observations: observations);
      _replace(updated);
      return updated;
    } finally {
      busy = false;
      _notify();
    }
  }

  @override
  void dispose() {
    _disposed = true;
    pause();
    client.close();
    super.dispose();
  }
}
