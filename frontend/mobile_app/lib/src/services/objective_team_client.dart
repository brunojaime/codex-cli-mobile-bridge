import 'dart:convert';
import 'package:http/http.dart' as http;

class ObjectiveTeamClient {
  ObjectiveTeamClient(this.baseUrl, {http.Client? client})
      : _client = client ?? http.Client();
  final String baseUrl;
  final http.Client _client;
  String url(String path) {
    const gateway = String.fromEnvironment('CODEX_OBJECTIVE_TEAM_GATEWAY');
    final target = Uri.parse(baseUrl);
    final bridge = Uri.tryParse(gateway);
    // Only the configured Bridge host uses the shared, read-only monitor.
    // Switching to another server must not expose Batata's executions there.
    if (bridge != null &&
        bridge.hasAuthority &&
        target.host == bridge.host &&
        {80, 443, 8118, 8443}.contains(target.port)) {
      final channel = {8118, 8443}.contains(target.port) ? '/dev' : '';
      return '${gateway.replaceAll(RegExp(r'/$'), '')}$channel/objective-team$path';
    }
    return '${baseUrl.replaceAll(RegExp(r'/$'), '')}/objective-team$path';
  }

  Future<Map<String, dynamic>> get([String path = '']) async {
    final response = await _client
        .get(Uri.parse(url(path)))
        .timeout(const Duration(seconds: 20));
    if (response.statusCode != 200) {
      throw Exception('No se pudo consultar el equipo');
    }
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  void close() => _client.close();
}
