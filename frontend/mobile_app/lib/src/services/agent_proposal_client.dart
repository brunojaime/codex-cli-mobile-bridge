import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/agent_proposal.dart';

class AgentProposalClient {
  AgentProposalClient({required this.baseUrl, http.Client? client})
      : _client = client ?? http.Client();
  final String baseUrl;
  final http.Client _client;

  Future<Map<String, dynamic>> _request(String method, String path,
      [Map<String, dynamic>? data]) async {
    final uri = Uri.parse(
        '${baseUrl.replaceAll(RegExp(r'/$'), '')}/agent-proposals$path');
    final request = http.Request(method, uri);
    request.headers['Content-Type'] = 'application/json';
    if (data != null) request.body = jsonEncode(data);
    final response = await http.Response.fromStream(
            await _client.send(request).timeout(const Duration(seconds: 30)))
        .timeout(const Duration(seconds: 30));
    if (response.statusCode < 200 || response.statusCode >= 300) {
      String detail =
          'No se pudo consultar las propuestas (${response.statusCode}).';
      try {
        final body = jsonDecode(response.body) as Map<String, dynamic>;
        if (body['detail'] is String) detail = body['detail'] as String;
      } catch (_) {/* Preserve the HTTP error. */}
      throw ProposalApiException(response.statusCode, detail);
    }
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> list({int offset = 0}) =>
      _request('GET', '?offset=$offset');
  Future<AgentProposal> get(String id) async =>
      AgentProposal(await _request('GET', '/${Uri.encodeComponent(id)}'));
  Future<AgentProposal> read(AgentProposal proposal) async =>
      AgentProposal(await _request(
          'POST',
          '/${Uri.encodeComponent(proposal.id)}/read',
          {'revision': proposal.revision}));
  Future<AgentProposal> decide(AgentProposal proposal, String action,
          {String observations = ''}) async =>
      AgentProposal(await _request(
          'POST', '/${Uri.encodeComponent(proposal.id)}/decisions', {
        'revision': proposal.revision,
        'action': action,
        'observations': observations
      }));
  void close() => _client.close();
}

class ProposalApiException implements Exception {
  ProposalApiException(this.statusCode, this.message);
  final int statusCode;
  final String message;
  @override
  String toString() => message;
}
