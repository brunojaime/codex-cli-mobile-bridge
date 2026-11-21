import 'package:codex_mobile_frontend/src/services/runtime_app_configuration.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('missing desktop config cannot select another environment', () {
    for (final pair in {
      5178: 8001,
      5179: 8000,
      5188: 18201,
      5189: 18200,
      5180: 8011
    }.entries) {
      expect(desktopApiBaseUrl(Uri.parse('http://127.0.0.1:${pair.key}')),
          'http://127.0.0.1:${pair.value}');
    }
    expect(desktopApiBaseUrl(Uri.parse('https://example.com')), isNull);
  });

  test('each desktop front retains its real endpoint and environment identity',
      () async {
    for (final port in [8000, 8001, 18200, 18201, 8011]) {
      final config = await loadRuntimeAppConfiguration(
          configUri: Uri.parse('http://desktop.test/bridge-config.json'),
          client: MockClient((_) async => http.Response(
              '{"api_base_url":"http://127.0.0.1:$port","app_label":"Bridge $port","updater_channel":"dev"}',
              200)));
      expect(config['api_base_url'], 'http://127.0.0.1:$port');
      expect(config['app_label'], 'Bridge $port');
    }
  });
  test('older deployments and malformed config keep packaged defaults',
      () async {
    for (final body in ['', 'broken', '[]', '{}']) {
      final config = await loadRuntimeAppConfiguration(
          configUri: Uri.parse('http://desktop.test/bridge-config.json'),
          client: MockClient((_) async => http.Response(body, 200)));
      expect(config, isEmpty);
    }
    final config = await loadRuntimeAppConfiguration(
        configUri: Uri.parse('http://desktop.test/bridge-config.json'),
        client: MockClient((_) async => http.Response(
            '{"api_base_url":"javascript:alert(1)","updater_channel":"other"}',
            200)));
    expect(config, isEmpty);
  });
}
