import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

enum MockProposalDecision { pending, execute, reject }

/// Local UX prototype only. This controller has no agent or network client.
class ProactiveMockController extends ChangeNotifier {
  static const storageKey = 'proactive_proposal_mock_v1';

  bool loading = true;
  bool saving = false;
  bool hasProposal = false;
  bool unread = false;
  String observations = '';
  String? error;
  MockProposalDecision decision = MockProposalDecision.pending;
  bool _disposed = false;

  String get status => switch (decision) {
        MockProposalDecision.execute => 'Ejecución simulada',
        MockProposalDecision.reject => 'Rechazada',
        MockProposalDecision.pending =>
          observations.isEmpty ? 'Pendiente' : 'Con observaciones',
      };

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  Future<void> load() async {
    loading = true;
    error = null;
    _notify();
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(storageKey);
      if (raw != null) {
        final data = jsonDecode(raw) as Map<String, dynamic>;
        hasProposal = data['hasProposal'] as bool;
        unread = data['unread'] as bool;
        observations = data['observations'] as String;
        decision =
            MockProposalDecision.values.byName(data['decision'] as String);
      }
    } catch (_) {
      error = 'No se pudo leer la prueba guardada. Podés reintentar.';
    } finally {
      loading = false;
      _notify();
    }
  }

  Future<bool> _persist({
    required bool nextHasProposal,
    required bool nextUnread,
    required String nextObservations,
    required MockProposalDecision nextDecision,
  }) async {
    if (loading || saving || _disposed) return false;
    saving = true;
    error = null;
    _notify();
    try {
      final prefs = await SharedPreferences.getInstance();
      final saved = await prefs.setString(
          storageKey,
          jsonEncode({
            'hasProposal': nextHasProposal,
            'unread': nextUnread,
            'observations': nextObservations,
            'decision': nextDecision.name,
          }));
      if (!saved) throw StateError('local_write_failed');
      hasProposal = nextHasProposal;
      unread = nextUnread;
      observations = nextObservations;
      decision = nextDecision;
      return true;
    } catch (_) {
      error = 'No se pudo guardar tu respuesta. Volvé a intentarlo.';
      return false;
    } finally {
      saving = false;
      _notify();
    }
  }

  Future<bool> simulateArrival() => _persist(
        nextHasProposal: true,
        nextUnread: true,
        nextObservations: '',
        nextDecision: MockProposalDecision.pending,
      );

  Future<bool> markRead() => _persist(
        nextHasProposal: hasProposal,
        nextUnread: false,
        nextObservations: observations,
        nextDecision: decision,
      );

  Future<bool> respond(MockProposalDecision value) async {
    if (!hasProposal || decision != MockProposalDecision.pending) return false;
    return _persist(
      nextHasProposal: true,
      nextUnread: false,
      nextObservations: observations,
      nextDecision: value,
    );
  }

  Future<bool> saveObservations(String text) async {
    if (!hasProposal ||
        decision != MockProposalDecision.pending ||
        text.trim().isEmpty ||
        text.trim().length > 2000) {
      return false;
    }
    return _persist(
      nextHasProposal: true,
      nextUnread: false,
      nextObservations: text.trim(),
      nextDecision: decision,
    );
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }
}
