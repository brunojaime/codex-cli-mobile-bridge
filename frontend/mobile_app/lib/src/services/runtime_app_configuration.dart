import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

/// Each desktop shortcut keeps its own server while sharing the same web build.
Future<Map<String, String>> loadRuntimeAppConfiguration({
  http.Client? client,
  Uri? configUri,
}) async {
  if (!kIsWeb && configUri == null) return const {};
  final transport = client ?? http.Client();
  try {
    final response = await transport
        .get(configUri ?? Uri.base.resolve('bridge-config.json'))
        .timeout(const Duration(seconds: 3));
    if (response.statusCode != 200) return const {};
    final decoded = jsonDecode(response.body);
    if (decoded is! Map) return const {};
    final result = <String, String>{};
    for (final key in [
      'api_base_url',
      'app_label',
      'source_app',
      'updater_channel'
    ]) {
      final value = decoded[key];
      if (value is String && value.trim().isNotEmpty) {
        result[key] = value.trim();
      }
    }
    final api = Uri.tryParse(result['api_base_url'] ?? '');
    if (api == null ||
        !['http', 'https'].contains(api.scheme) ||
        api.host.isEmpty ||
        api.userInfo.isNotEmpty) {
      result.remove('api_base_url');
    }
    if (result['updater_channel'] != null &&
        !['dev', 'prod'].contains(result['updater_channel'])) {
      result.remove('updater_channel');
    }
    return result;
  } catch (_) {
    // Existing packaged clients and offline startup retain their configured URL.
    return const {};
  } finally {
    if (client == null) transport.close();
  }
}

/// Safe fallback for the installed desktop origins if their config is unavailable.
String? desktopApiBaseUrl(Uri location) {
  if (!['localhost', '127.0.0.1'].contains(location.host)) return null;
  const ports = {5178: 8001, 5179: 8000, 5188: 18201, 5189: 18200, 5180: 8011};
  final port = ports[location.port];
  return port == null ? null : 'http://127.0.0.1:$port';
}
