import 'dart:convert';
import 'dart:typed_data';

import 'package:codex_mobile_frontend/src/screens/chat_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('audio attachment detection prefers MIME type over filename extension',
      () {
    expect(
      isAudioAttachmentDraftInput(
        fileName: 'upload.bin',
        mimeType: 'audio/ogg; codecs=opus',
      ),
      isTrue,
    );
    expect(
      isAudioAttachmentDraftInput(fileName: 'voice-note.m4a'),
      isTrue,
    );
    expect(
      isAudioAttachmentDraftInput(
        fileName: 'notes.txt',
        mimeType: 'text/plain',
      ),
      isFalse,
    );
  });

  testWidgets('image editor can be cancelled without returning an edit', (
    tester,
  ) async {
    Object? editorResult = Object();
    final imageBytes = base64Decode(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/lwM3TAAAAABJRU5ErkJggg==',
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) {
            return Scaffold(
              body: Center(
                child: FilledButton(
                  onPressed: () async {
                    editorResult = await Navigator.of(context).push<Object?>(
                      MaterialPageRoute<Object?>(
                        builder: (context) {
                          return buildImageEditorForTest(
                            imageBytes: Uint8List.fromList(imageBytes),
                            fileName: 'screenshot.png',
                          );
                        },
                      ),
                    );
                  },
                  child: const Text('Open editor'),
                ),
              ),
            );
          },
        ),
      ),
    );

    await tester.tap(find.text('Open editor'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    await tester.pump(const Duration(seconds: 1));

    expect(find.text('screenshot.png'), findsOneWidget);
    expect(find.text('Original'), findsOneWidget);
    expect(find.text('Done'), findsOneWidget);

    await tester.tap(find.byTooltip('Back'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(editorResult, isNull);
  });
}
