import 'package:codex_mobile_frontend/src/models/chat_message.dart';
import 'package:codex_mobile_frontend/src/models/chat_session_summary.dart';
import 'package:codex_mobile_frontend/src/models/session_detail.dart';
import 'package:codex_mobile_frontend/src/screens/chat_screen.dart';
import 'package:codex_mobile_frontend/src/services/api_client.dart';
import 'package:codex_mobile_frontend/src/services/chat_notification_service.dart';
import 'package:codex_mobile_frontend/src/state/chat_controller.dart';
import 'package:codex_mobile_frontend/src/utils/internal_chat_link.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const sourceId = '11111111-1111-4111-8111-111111111111';
const targetId = '22222222-2222-4222-8222-222222222222';

void main() {
  test('internal links accept only chat UUIDs and never external targets', () {
    expect(internalChatSessionId('codex-bridge://chat/$targetId'), targetId);
    for (final link in [
      'codex-bridge://evil/$targetId',
      'codex-bridge://chat/not-an-id',
      'codex-bridge://chat/$targetId?url=https://example.com',
      'codex-bridge://chat/$targetId#fragment',
      'codex-bridge://user@chat/$targetId',
      'codex-bridge://chat:8118/$targetId',
      'codex-bridge://chat/$targetId/extra',
      'codex-bridge:broken',
    ]) {
      expect(isInternalChatLink(link), isTrue);
      expect(internalChatSessionId(link), isNull);
    }
    expect(isInternalChatLink('https://example.com'), isFalse);
  });

  for (final broken in [false, true]) {
    testWidgets('chat link navigates only on tap; missing=$broken',
        (tester) async {
      tester.view.physicalSize = const Size(430, 932);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final api = _LinkApi(broken: broken);
      final controller = ChatController(
          apiClient: api,
          notificationService: const NoopChatNotificationService());
      addTearDown(controller.dispose);
      await controller.refreshSessions();
      await controller.selectSession(sourceId);
      await tester.pumpWidget(MaterialApp(
          home: ChatScreen(
        initialApiBaseUrl: 'http://localhost:8000',
        controllerOverride: controller,
        enableServerBootstrap: false,
        notificationService: const NoopChatNotificationService(),
      )));
      await tester.pumpAndSettle();
      expect(controller.selectedSessionId, sourceId);
      expect(api.opened, [sourceId]);
      final link = find.text('Abrir conversación', findRichText: true);
      expect(link, findsOneWidget);
      await tester.tap(link);
      await tester.pumpAndSettle();
      expect(api.opened, [sourceId, targetId]);
      expect(controller.selectedSessionId, broken ? sourceId : targetId);
      if (broken) {
        expect(find.text('No se pudo abrir esa conversación en este servidor.'),
            findsOneWidget);
      }
    });
  }
}

class _LinkApi extends ApiClient {
  _LinkApi({required this.broken}) : super(baseUrl: 'http://localhost:8000');
  final bool broken;
  final opened = <String>[];
  final timestamp = DateTime.utc(2026, 10, 3);
  @override
  Future<List<ChatSessionSummary>> listSessions() async => [
        for (final id in [sourceId, targetId])
          ChatSessionSummary(
            id: id,
            title: id == sourceId ? 'Source' : 'Target',
            workspacePath: '/workspace/project',
            workspaceName: 'Project',
            createdAt: timestamp,
            updatedAt: timestamp,
          ),
      ];
  @override
  Future<SessionDetail> getSession(String sessionId,
      {String? before, int? limit, bool fullTranscript = false}) async {
    opened.add(sessionId);
    if (broken && sessionId == targetId) throw Exception('404');
    return SessionDetail(
      id: sessionId,
      title: sessionId == sourceId ? 'Source' : 'Target',
      workspacePath: '/workspace/project',
      workspaceName: 'Project',
      createdAt: timestamp,
      updatedAt: timestamp,
      messages: [
        ChatMessage(
          id: 'message',
          isUser: false,
          text: sessionId == sourceId
              ? '[Abrir conversación](codex-bridge://chat/$targetId)'
              : 'Target chat',
          authorType: ChatMessageAuthorType.assistant,
          status: ChatMessageStatus.completed,
          createdAt: timestamp,
          updatedAt: timestamp,
        )
      ],
    );
  }
}
