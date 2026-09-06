import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/control_status.dart';

class ControlAgentException implements Exception {
  const ControlAgentException(this.message);

  final String message;

  @override
  String toString() => message;
}

class ControlAgentClient {
  ControlAgentClient({
    required String baseUrl,
    required this.token,
    http.Client? client,
  }) : baseUrl = baseUrl.replaceFirst(RegExp(r'/$'), ''),
       _client = client ?? http.Client();

  final String baseUrl;
  final String token;
  final http.Client _client;

  void close() => _client.close();

  Map<String, String> get _headers => <String, String>{
    'Authorization': 'Bearer $token',
    'Content-Type': 'application/json',
  };

  Future<ControlSnapshot> getSnapshot() async {
    final response = await _client.get(
      Uri.parse('$baseUrl/environments'),
      headers: _headers,
    );
    _requireSuccess(response, expectedStatus: 200);
    return ControlSnapshot.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<ControlRestartAction> restart(
    String environment, {
    bool force = false,
  }) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/environments/$environment/restart'),
      headers: _headers,
      body: jsonEncode(<String, String>{'mode': force ? 'force' : 'graceful'}),
    );
    _requireSuccess(response, expectedStatus: 202);
    return ControlRestartAction.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<ControlRestartAction> getAction(String actionId) async {
    final response = await _client.get(
      Uri.parse('$baseUrl/actions/$actionId'),
      headers: _headers,
    );
    _requireSuccess(response, expectedStatus: 200);
    return ControlRestartAction.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  void _requireSuccess(http.Response response, {required int expectedStatus}) {
    if (response.statusCode == expectedStatus) {
      return;
    }
    String detail = response.body;
    try {
      final payload = jsonDecode(response.body) as Map<String, dynamic>;
      final rawDetail = payload['detail'];
      if (rawDetail is Map<String, dynamic>) {
        detail =
            rawDetail['message'] as String? ??
            rawDetail['code'] as String? ??
            response.body;
      } else if (rawDetail is String) {
        detail = rawDetail;
      }
    } catch (_) {
      // Preserve the raw response for diagnostics.
    }
    throw ControlAgentException(
      'Control Agent returned ${response.statusCode}: $detail',
    );
  }
}

String deriveControlAgentUrl(String bridgeUrl) {
  final uri = Uri.parse(bridgeUrl);
  if (!uri.hasPort) {
    final bridgePath = uri.path.replaceFirst(RegExp(r'/$'), '');
    return uri
        .replace(path: '$bridgePath/ops', query: null, fragment: null)
        .toString()
        .replaceFirst(RegExp(r'/$'), '');
  }
  return uri
      .replace(port: 8010, path: '', query: null, fragment: null)
      .toString()
      .replaceFirst(RegExp(r'/$'), '');
}
