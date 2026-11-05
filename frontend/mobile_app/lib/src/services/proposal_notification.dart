import 'dart:convert';

/// Optional capability; chat-completion implementations remain compatible.
abstract class ProposalNotificationService {
  Stream<ProposalNotificationTarget> get proposalTaps;
  ProposalNotificationTarget? takePendingProposal(String server);
  Future<void> showProposal(ProposalNotificationTarget target);
}

class ProposalNotificationTarget {
  const ProposalNotificationTarget(
      {required this.server, required this.id, required this.revision});
  final String server;
  final String id;
  final int revision;
  String get payload => jsonEncode({
        'kind': 'agent_proposal',
        'server': server,
        'id': id,
        'revision': revision
      });

  static ProposalNotificationTarget? parse(String? payload) {
    try {
      final data = jsonDecode(payload!) as Map<String, dynamic>;
      final uri = Uri.parse(data['server'] as String);
      if (data['kind'] != 'agent_proposal' ||
          !const {'https', 'http'}.contains(uri.scheme) ||
          uri.host.isEmpty ||
          !RegExp(r'^[a-f0-9-]{36}$').hasMatch(data['id'] as String) ||
          data['revision'] is! int ||
          (data['revision'] as int) < 1) {
        return null;
      }
      return ProposalNotificationTarget(
          server: data['server'] as String,
          id: data['id'] as String,
          revision: data['revision'] as int);
    } catch (_) {
      return null;
    }
  }
}
