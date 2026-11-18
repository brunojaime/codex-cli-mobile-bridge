// ignore_for_file: depend_on_referenced_packages
import 'dart:convert';
import 'dart:io';

import 'package:firebase_core_platform_interface/test.dart';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:codex_mobile_frontend/src/services/bridge_push_client.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('first activation persists flags and registers before sending a test',
      () async {
    final previousHttpOverrides = HttpOverrides.current;
    HttpOverrides.global = null;
    addTearDown(() => HttpOverrides.global = previousHttpOverrides);
    setupFirebaseCoreMocks();
    FlutterSecureStorage.setMockInitialValues({});
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(
        const MethodChannel('plugins.flutter.io/firebase_messaging'),
        (call) async {
      switch (call.method) {
        case 'Messaging#requestPermission':
          return {'authorizationStatus': 1};
        case 'Messaging#setAutoInitEnabled':
          return {'isAutoInitEnabled': true};
        case 'Messaging#getToken':
          return {'token': 'synthetic-test-token'};
        default:
          return <String, dynamic>{};
      }
    });
    addTearDown(() => messenger.setMockMethodCallHandler(
        const MethodChannel('plugins.flutter.io/firebase_messaging'), null));
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    addTearDown(() => server.close(force: true));
    final requests = <String>[];
    server.listen((request) async {
      requests.add('${request.method} ${request.uri.path}');
      final body = await utf8.decoder.bind(request).join();
      var response = <String, dynamic>{'ok': true};
      if (request.uri.path.endsWith('/config')) {
        response = {
          'configured': true,
          'firebase_project_id': '123',
          'bridge_id': 'test-bridge'
        };
      } else {
        expect(request.headers.value('authorization'), startsWith('Bearer '));
        if (request.uri.path.endsWith('/devices')) {
          final device = jsonDecode(body) as Map<String, dynamic>;
          expect(device['token'], 'synthetic-test-token');
          expect(device['platform'], 'android');
        }
      }
      request.response.headers.contentType = ContentType.json;
      request.response.write(jsonEncode(response));
      await request.response.close();
    });
    final address = 'http://127.0.0.1:${server.port}';
    final client = BridgePushClient(display: (_) async {}, openPayload: (_) {});
    await client.enable(address);
    expect(client.enabledFor(address), isTrue);
    expect(client.ownsCompletions(address), isFalse);
    final saved = jsonDecode((await const FlutterSecureStorage()
        .read(key: 'codex_bridge_push_bindings_v1'))!);
    expect(saved[address]['enabled'], isTrue);
    expect(saved[address]['bridge_id'], 'test-bridge');
    expect(requests, [
      'GET /notifications/config',
      'POST /notifications/devices',
      'POST /notifications/devices/me/test',
    ]);
  });
}
