import 'package:codex_mobile_frontend/src/screens/notification_settings_screen.dart';
import 'package:codex_mobile_frontend/src/services/chat_notification_service.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('permission and enrollment happen only after an explicit tap',
      (tester) async {
    final service = _Push();
    await tester.pumpWidget(MaterialApp(
        home: NotificationSettingsScreen(
            server: 'https://bridge.example.com', service: service)));
    await tester.pumpAndSettle();
    expect(service.enrollments, 0);
    await tester.tap(find.text('Activar y probar'));
    await tester.pumpAndSettle();
    expect(service.enrollments, 1);
    expect(find.text('Esperando el aviso de prueba'), findsOneWidget);
    await tester.tap(find.text('Desactivar en este teléfono'));
    await tester.pumpAndSettle();
    expect(service.enabled, false);
    await tester.pumpWidget(const SizedBox());
  });
}

class _Push implements ChatNotificationService, ChatPushNotificationSettings {
  bool enabled = false;
  int enrollments = 0;
  @override
  Future<void> initialize() async {}
  @override
  Future<void> showChatCompleted(
      ChatCompletedNotification notification) async {}
  @override
  Future<Map<String, dynamic>> pushStatus(String server) async =>
      {'configured': true, 'enabled': enabled, 'verified': false};
  @override
  Future<void> enablePush(String server) async {
    enrollments++;
    enabled = true;
  }

  @override
  Future<void> disablePush(String server) async {
    enabled = false;
  }

  @override
  Future<void> testPush(String server) async {}
}
