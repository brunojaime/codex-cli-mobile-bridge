import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:codex_mobile_frontend/src/models/chat_message.dart';
import 'package:codex_mobile_frontend/src/widgets/chat_bubble.dart';

void main() {
  testWidgets('video opens its download only after an explicit tap',
      (tester) async {
    final opened = <String>[];
    final now = DateTime(2026, 10, 5);
    final message = ChatMessage(
      id: 'message',
      text: 'Revisar\n\n[Attached files]\n- video: video-original.mp4',
      isUser: true,
      authorType: ChatMessageAuthorType.human,
      status: ChatMessageStatus.completed,
      createdAt: now,
      updatedAt: now,
      attachments: [
        ChatMessageAttachment.fromJson({
          'id': 'job:video:0',
          'kind': 'video',
          'job_id': 'job',
          'index': 0,
          'download_url': '/jobs/job/attachments/0',
        })
      ],
    );
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: ChatBubble(
      message: message,
      attachmentBaseUrl: 'https://bridge.example',
      onLinkTap: (url) async {
        opened.add(url);
      },
    ))));
    expect(opened, isEmpty);
    expect(find.text('Abrir video 1'), findsOneWidget);
    await tester.tap(find.text('Abrir video 1'));
    expect(opened, ['https://bridge.example/jobs/job/attachments/0']);
    expect(tester.takeException(), isNull);
  });
}
