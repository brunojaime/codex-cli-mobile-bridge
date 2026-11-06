import 'dart:async';
import 'package:codex_mobile_frontend/src/models/chat_message.dart';
import 'package:codex_mobile_frontend/src/models/session_detail.dart';
import 'package:codex_mobile_frontend/src/screens/chat_screen.dart';
import 'package:codex_mobile_frontend/src/services/api_client.dart';
import 'package:codex_mobile_frontend/src/services/chat_notification_service.dart';
import 'package:codex_mobile_frontend/src/state/chat_controller.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

const target = ChatNotificationTarget(
    server: 'https://bridge.example.com',
    sessionId: 'session-a',
    jobId: 'job-notified',
    workspacePath: '/projects/a',
    messageId: 'notified');
void main() {
  test('payload round trips and id stays stable across replies', () {
    final parsed = ChatNotificationTarget.parse(target.payload)!;
    expect(parsed.server, target.server);
    expect(parsed.messageId, 'notified');
    expect(parsed.notificationId, target.notificationId);
    const next = ChatNotificationTarget(
        server: 'https://bridge.example.com',
        sessionId: 'session-a',
        jobId: 'new-job',
        workspacePath: '/projects/a');
    expect(next.notificationId, target.notificationId);
    expect(ChatNotificationTarget.parse('{"type":"proposal"}'), isNull);
    expect(ChatNotificationTarget.parse('{"type":"chat_completion"}'), isNull);
    expect(ChatNotificationTarget.parse('invalid'), isNull);
  });
  for (final coldStart in [true, false]) {
    testWidgets(
        '${coldStart ? 'cold launch' : 'live tap'} opens the notified reply and clears project notices',
        (tester) async {
      SharedPreferences.setMockInitialValues({});
      final service = _Notifications()..pending = coldStart ? target : null;
      final controller = ChatController(apiClient: _Api());
      await tester.pumpWidget(MaterialApp(
          home: ChatScreen(
              initialApiBaseUrl: target.server,
              notificationService: service,
              controllerOverride: controller,
              enableServerBootstrap: false)));
      await tester.pumpAndSettle();
      if (!coldStart) {
        service.pending = target;
        service.taps.add(target);
        await tester.pumpAndSettle();
      }
      expect(controller.selectedSessionId, 'session-a');
      expect(find.text('Mensaje de la notificación'), findsOneWidget);
      expect(find.text('Respuesta que originó el aviso'), findsOneWidget);
      expect(find.text('Mensaje anterior'), findsNothing);
      expect(service.projectReads, contains('/projects/a'));
      expect(service.visibleSession, 'session-a');
      await tester.tap(find.text('Ver todo el chat'));
      await tester.pumpAndSettle();
      expect(find.text('Mensaje de la notificación'), findsNothing);
      expect(find.text('Mensaje anterior'), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
      controller.dispose();
      await service.taps.close();
    });
  }
}

class _Notifications
    implements ChatNotificationService, ChatNotificationNavigation {
  final taps = StreamController<ChatNotificationTarget>.broadcast();
  ChatNotificationTarget? pending;
  final projectReads = <String>[];
  String? visibleSession;
  @override
  Stream<ChatNotificationTarget> get chatTaps => taps.stream;
  @override
  ChatNotificationTarget? takePendingChat() {
    final value = pending;
    pending = null;
    return value;
  }

  @override
  Future<void> initialize() async {}
  @override
  Future<void> showChatCompleted(
      ChatCompletedNotification notification) async {}
  @override
  void setVisibleChat(String? server, String? sessionId) {
    visibleSession = sessionId;
  }

  @override
  Future<void> readChat(String server, String sessionId, String workspacePath,
      {bool wholeProject = false}) async {
    if (wholeProject) projectReads.add(workspacePath);
  }
}

class _Api extends ApiClient {
  _Api() : super(baseUrl: target.server);
  @override
  Future<SessionDetail> getSession(String sessionId,
      {String? before, int? limit, bool fullTranscript = false}) async {
    final timestamp = DateTime.utc(2026, 11, 5);
    return SessionDetail(
        id: sessionId,
        title: 'Chat A',
        workspacePath: '/projects/a',
        workspaceName: 'Proyecto A',
        createdAt: timestamp,
        updatedAt: timestamp,
        messages: [
          ChatMessage(
              id: 'previous',
              text: 'Mensaje anterior',
              isUser: true,
              authorType: ChatMessageAuthorType.human,
              status: ChatMessageStatus.completed,
              createdAt: timestamp,
              updatedAt: timestamp),
          ChatMessage(
              id: 'notified',
              text: 'Respuesta que originó el aviso',
              isUser: false,
              authorType: ChatMessageAuthorType.assistant,
              jobId: 'job-notified',
              status: ChatMessageStatus.completed,
              createdAt: timestamp,
              updatedAt: timestamp),
        ]);
  }
}
