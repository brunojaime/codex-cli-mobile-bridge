import 'dart:convert';
import 'dart:math';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

class WorkClient {
  WorkClient(this.baseUrl, {http.Client? client})
      : _client = client ?? http.Client();
  final String baseUrl;
  final http.Client _client;
  Future<Map<String, dynamic>> request(String method, String path,
      [Map<String, dynamic>? data]) async {
    final request = http.Request(method,
        Uri.parse('${baseUrl.replaceAll(RegExp(r'/$'), '')}/work$path'));
    request.headers['Content-Type'] = 'application/json';
    if (data != null) request.body = jsonEncode(data);
    final response = await http.Response.fromStream(
            await _client.send(request).timeout(const Duration(seconds: 30)))
        .timeout(const Duration(seconds: 30));
    final body = jsonDecode(response.body) as Map<String, dynamic>;
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception(body['detail'] is String
          ? body['detail']
          : 'No se pudo completar la operación.');
    }
    return body;
  }

  Future<Map<String, dynamic>> projectSettings() => request('GET', '/settings');
  Future<Map<String, dynamic>> updateProjectSettings(
          String workspace, Map<String, dynamic> settings) =>
      request('PUT', '/settings',
          {'workspace_path': workspace, 'settings': settings});

  Future<Map<String, dynamic>> overview() => request('GET', '');
  Future<Map<String, dynamic>> enqueue(
      String workspace, String instruction) async {
    final prefs = await SharedPreferences.getInstance();
    final key =
        'work-pending:${Uri.encodeComponent(baseUrl)}:${Uri.encodeComponent(workspace)}:${Uri.encodeComponent(instruction)}';
    Map<String, dynamic>? pending;
    final stored = prefs.getString(key);
    if (stored != null) pending = jsonDecode(stored) as Map<String, dynamic>;
    if (pending == null || pending['instruction'] != instruction) {
      pending = {
        'workspace_path': workspace,
        'source': 'chat',
        'instruction': instruction,
        'source_key':
            'mobile-${DateTime.now().microsecondsSinceEpoch}-${Random.secure().nextInt(1 << 30)}'
      };
      if (!await prefs.setString(key, jsonEncode(pending))) {
        throw Exception('No se pudo guardar el envío pendiente.');
      }
    }
    final result = await request('POST', '/backlog', pending);
    await prefs.remove(key);
    return result;
  }

  Future<Map<String, dynamic>> choose(String id, int option) =>
      request('POST', '/questions/$id/choose', {'option': option});
  Future<Map<String, dynamic>> control(
          Map<String, dynamic> task, String action) =>
      request('POST', '/backlog/${task['id']}/control',
          {'revision': task['revision'], 'action': action});
  Future<Map<String, dynamic>> policy(Map<String, dynamic> policy) =>
      request('PUT', '/policy', policy);
  Future<Map<String, dynamic>> respond(String id, String action,
          [String text = '']) =>
      request(
          'POST', '/questions/$id/respond', {'action': action, 'text': text});
  void close() => _client.close();
}
