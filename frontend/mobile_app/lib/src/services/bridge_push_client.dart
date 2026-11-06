import 'dart:async';
import 'dart:convert';
import 'dart:math';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'chat_notification_service.dart';
import 'bridge_push_endpoint.dart';

/// Flutter port of the shared native contract: consent, FCM token, secure
/// installation credential, registration/revocation and a single listener.
class BridgePushClient {
  BridgePushClient({required this.display, required this.openPayload});
  final Future<void> Function(ChatCompletedNotification) display;
  final void Function(String) openPayload;
  static const _storage = FlutterSecureStorage();
  static const _key = 'codex_bridge_push_bindings_v1';
  Map<String, dynamic> _bindings = {};
  bool _initialized = false;
  bool _firebaseReady = false;

  Future<void> initialize({BackgroundMessageHandler? backgroundHandler}) async {
    if (_initialized) return;
    _initialized = true;
    try {
      _bindings = jsonDecode(await _storage.read(key: _key) ?? '{}')
          as Map<String, dynamic>;
      await Firebase.initializeApp();
      _firebaseReady = true;
      if (backgroundHandler != null) {
        FirebaseMessaging.onBackgroundMessage(backgroundHandler);
        FirebaseMessaging.onMessage
            .listen((message) => unawaited(receive(message.data)));
        FirebaseMessaging.onMessageOpenedApp
            .listen((message) => unawaited(receive(message.data, open: true)));
        final initial = await FirebaseMessaging.instance.getInitialMessage();
        if (initial != null) unawaited(receive(initial.data, open: true));
        FirebaseMessaging.instance.onTokenRefresh.listen((token) {
          for (final server in _bindings.keys.toList()) {
            if (enabledFor(server)) {
              unawaited(_register(server, token).catchError((_) {}));
            }
          }
        });
        for (final server in _bindings.keys.toList()) {
          if (enabledFor(server)) unawaited(refresh(server).catchError((_) {}));
        }
      }
    } catch (_) {
      // Missing Google services or secure storage must not block the chat.
    }
    _initialized = true;
  }

  bool enabledFor(String server) =>
      _firebaseReady && _bindings[server]?['enabled'] == true;
  bool ownsCompletions(String server) =>
      enabledFor(server) && _bindings[server]?['verified'] == true;
  Future<void> _save() =>
      _storage.write(key: _key, value: jsonEncode(_bindings));
  Future<Map<String, dynamic>> _request(String server, String path,
      {String method = 'GET',
      Map<String, dynamic>? body,
      bool authenticated = true}) async {
    final binding = _bindings[server];
    final client = http.Client();
    try {
      final request =
          http.Request(method, Uri.parse('${bridgePushServiceUrl(server)}/notifications/$path'));
      request.headers['Content-Type'] = 'application/json';
      if (authenticated && binding != null) {
        request.headers['Authorization'] = 'Bearer ${binding['credential']}';
      }
      if (body != null) request.body = jsonEncode(body);
      final response = await http.Response.fromStream(
              await client.send(request).timeout(const Duration(seconds: 10)))
          .timeout(const Duration(seconds: 10));
      if ([401, 403, 410].contains(response.statusCode)) return {'gone': true};
      if (response.statusCode >= 400) {
        throw Exception(
            'No se pudo completar la operación. Revisá la conexión con el bridge.');
      }
      return jsonDecode(response.body) as Map<String, dynamic>;
    } finally {
      client.close();
    }
  }

  Future<Map<String, dynamic>> status(String server) async {
    await initialize();
    final config = await _request(server, 'config', authenticated: false);
    if (!enabledFor(server)) {
      return {
        ...config,
        'enabled': false,
        'verified': false,
        'sdk_available': _firebaseReady
      };
    }
    final device = await _request(server, 'devices/me');
    _bindings[server]['verified'] = device['verified'] == true;
    await _save();
    return {...config, ...device, 'sdk_available': _firebaseReady};
  }

  String _random(int bytes) => base64UrlEncode(
          List<int>.generate(bytes, (_) => Random.secure().nextInt(256)))
      .replaceAll('=', '');
  String _installationId() {
    final bytes = List<int>.generate(16, (_) => Random.secure().nextInt(256));
    bytes[6] = (bytes[6] & 15) | 64;
    bytes[8] = (bytes[8] & 63) | 128;
    final hex = bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
    return '${hex.substring(0, 8)}-${hex.substring(8, 12)}-${hex.substring(12, 16)}-${hex.substring(16, 20)}-${hex.substring(20)}';
  }

  Future<void> enable(String server) async {
    await initialize();
    if (!_firebaseReady) {
      throw Exception(
          'Firebase no está disponible en esta instalación Android.');
    }
    final config = await _request(server, 'config', authenticated: false);
    if (config['configured'] != true ||
        config['firebase_project_id'] != Firebase.app().options.projectId) {
      throw Exception(
          'El servidor y esta app necesitan la misma configuración de notificaciones.');
    }
    final permission = await FirebaseMessaging.instance.requestPermission();
    if (permission.authorizationStatus != AuthorizationStatus.authorized) {
      throw Exception(
          'Habilitá las notificaciones de la app en los ajustes de Android.');
    }
    await FirebaseMessaging.instance.setAutoInitEnabled(true);
    _bindings[server] ??= {
      'installation': _installationId(),
      'credential': _random(32)
    };
    _bindings[server]['bridge_id'] = config['bridge_id'];
    _bindings[server]['enabled'] = false;
    await _save();
    final token = await FirebaseMessaging.instance.getToken();
    if (token == null) {
      throw Exception('No se pudo registrar este teléfono en Firebase.');
    }
    await _register(server, token);
    _bindings[server]['enabled'] = true;
    await _save();
    await test(server);
  }

  Future<void> _register(String server, String token) async {
    final binding = _bindings[server];
    await _request(server, 'devices', method: 'POST', body: {
      'installationId': binding['installation'],
      'token': token,
      'platform': 'android',
    });
  }

  Future<void> refresh(String server) async {
    if (!enabledFor(server)) return;
    final token = await FirebaseMessaging.instance.getToken();
    if (token != null) {
      await _register(server, token);
      await status(server);
    }
  }

  Future<void> disable(String server) async {
    // Revoke remotely before removing the local association. Failed revocation
    // stays visible/retryable instead of silently abandoning an active device.
    await _request(server, 'devices/me', method: 'DELETE');
    _bindings[server]['enabled'] = false;
    await _save();
    if (!_bindings.keys.any(enabledFor)) {
      await FirebaseMessaging.instance.setAutoInitEnabled(false);
      await FirebaseMessaging.instance.deleteToken();
    }
  }

  Future<void> test(String server) async =>
      _request(server, 'devices/me/test', method: 'POST');

  Future<void> read(String server, String session,
      {bool wholeProject = false}) async {
    if (!enabledFor(server)) return;
    try {
      await _request(server, 'read',
          method: 'POST',
          body: {'session_id': session, 'whole_project': wholeProject});
    } catch (_) {
      // A later controller update will synchronize the latest read state.
    }
  }

  Future<void> receive(Map<String, dynamic> data, {bool open = false}) async {
    await initialize();
    final eventId = data['eventId'];
    final bridgeId = data['bridgeId'];
    if (eventId is! String || !RegExp(r'^[a-f0-9]{32}$').hasMatch(eventId)) {
      return;
    }
    // Payloads cannot introduce a URL: resolve only a consented saved binding.
    final servers = _bindings.keys
        .where((s) => enabledFor(s) && _bindings[s]['bridge_id'] == bridgeId);
    if (servers.isEmpty) return;
    final server = servers.first;
    try {
      final event = await _request(server, 'events/$eventId');
      if (event['gone'] == true) return;
      final target = event['test'] == true
          ? null
          : ChatNotificationTarget(
              server: server,
              sessionId: event['session_id'] as String,
              jobId: event['job_id'] as String,
              workspacePath: event['workspace_path'] as String,
              messageId: event['message_id'] as String?);
      if (open && target != null) {
        openPayload(target.payload);
      } else {
        await display(ChatCompletedNotification(
            id: target?.notificationId ??
                stableNotificationId('push-test:$server'),
            title: event['title'] as String,
            body: event['body'] as String,
            summary: event['summary'] as String?,
            channel: ChatNotificationChannel.generic,
            target: target));
      }
      final receipt =
          await _request(server, 'events/$eventId/receipt', method: 'POST');
      if (receipt['device_verified'] == true) {
        _bindings[server]['verified'] = true;
        await _save();
      }
    } catch (_) {
      if (!open) {
        await display(ChatCompletedNotification(
            id: stableNotificationId('$server:pending'),
            title: 'Codex Mobile',
            body:
                'Hay una actualización de tus proyectos. Tocá para abrir la app.',
            channel: ChatNotificationChannel.generic,
            payload: jsonEncode({
              'type': 'bridge_push',
              'eventId': eventId,
              'bridgeId': bridgeId
            })));
      }
    }
  }
}
