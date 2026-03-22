import 'package:codex_mobile_frontend/main.dart';
import 'package:codex_mobile_frontend/src/models/chat_message.dart';
import 'package:codex_mobile_frontend/src/widgets/chat_bubble.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  testWidgets('renders Codex Remote shell', (tester) async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    await tester.pumpWidget(
      const CodexMobileApp(initialApiBaseUrl: 'http://localhost:8000'),
    );

    expect(find.text('Codex Remote'), findsOneWidget);
    expect(find.textContaining('local machine'), findsOneWidget);
  });

  testWidgets('renders assistant options as quick actions', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ChatBubble(
            message: ChatMessage(
              id: 'assistant-1',
              text: '1. Summarize the repo\n2. Show changed files',
              isUser: false,
              status: ChatMessageStatus.completed,
              createdAt: DateTime.utc(2026, 1, 1),
              updatedAt: DateTime.utc(2026, 1, 1),
              jobStatus: 'completed',
              jobPhase: 'Completed',
            ),
          ),
        ),
      ),
    );

    expect(find.text('Quick options'), findsOneWidget);
    expect(find.text('Summarize the repo'), findsOneWidget);
    expect(find.text('Show changed files'), findsOneWidget);
  });
}
