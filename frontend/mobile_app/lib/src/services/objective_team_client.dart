import 'dart:convert';
import 'package:http/http.dart' as http;

class ObjectiveTeamClient {
  ObjectiveTeamClient(this.baseUrl, {http.Client? client})
      : _client = client ?? http.Client();
  final String baseUrl;
  final http.Client _client;
  final Map<String, Map<String, dynamic>> _preparations = {};

  Future<Map<String, dynamic>> _bridgeGet(String path) async {
    final response = await _client
        .get(Uri.parse('${baseUrl.replaceAll(RegExp(r'/$'), '')}$path'))
        .timeout(const Duration(seconds: 20));
    if (response.statusCode != 200) throw Exception('Preparation unavailable');
    return jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
  }

  // These are operator chats, not coordinator runs. Never infer a run link from
  // a project name or claim that a particular setup step already succeeded.
  Future<List<Map<String, dynamic>>> preparations() async {
    final activity = await _bridgeGet('/maintenance/drain');
    final active = (activity['active_jobs'] as List? ?? [])
        .whereType<Map<String, dynamic>>()
        .where((job) {
      final text = '${job['message'] ?? ''}'.toLowerCase();
      return RegExp(r'equipo\s+por\s+objetivos|objective[ -]team')
              .hasMatch(text) &&
          RegExp(r'inici[aá]|cre[aá]|arranc|lanz|start|launch|create')
              .hasMatch(text) &&
          job['session_id'] is String &&
          job['job_id'] is String;
    }).toList();
    final activeIds = active.map((j) => j['job_id']).toSet();
    final next = <String, Map<String, dynamic>>{};
    for (final job in active) {
      final id = job['job_id'] as String;
      var previous = _preparations[id];
      if (previous == null) {
        final session = await _bridgeGet(
            '/sessions/${Uri.encodeComponent(job['session_id'] as String)}?transcript=window&limit=1');
        if (session['archived_at'] != null ||
            '${session['workspace_name']}'.startsWith('nienfos-team-')) {
          continue;
        }
        previous = {'title': session['title'] ?? 'Nuevo proyecto'};
      }
      next[id] = {...previous, ...job};
    }
    for (final entry in _preparations.entries) {
      if (activeIds.contains(entry.key)) continue;
      final job =
          await _bridgeGet('/response/${Uri.encodeComponent(entry.key)}');
      // A completed operator chat hands off to the registered team. A failed
      // or cancelled request remains visible while this panel is open.
      if (job['status'] != 'completed') {
        next[entry.key] = {...entry.value, ...job};
      }
    }
    _preparations
      ..clear()
      ..addAll(next);
    return next.values.toList();
  }

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
