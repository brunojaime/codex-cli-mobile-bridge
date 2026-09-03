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

  test('video attachment detection accepts video MIME types and MP4 files', () {
    expect(
      isVideoAttachmentDraftInput(
        fileName: 'upload.bin',
        mimeType: 'video/mp4',
      ),
      isTrue,
    );
    expect(
      isVideoAttachmentDraftInput(fileName: 'screen-recording.mp4'),
      isTrue,
    );
    expect(
      isAudioAttachmentDraftInput(fileName: 'screen-recording.mp4'),
      isFalse,
    );
    expect(
      isAudioAttachmentDraftInput(
        fileName: 'upload.mp4',
        mimeType: 'audio/mp4',
      ),
      isTrue,
    );
  });

  test('CAD attachment detection accepts DXF and DWG names and MIME types', () {
    expect(isCadAttachmentDraftInput(fileName: 'planta-baja.dxf'), isTrue);
    expect(isCadAttachmentDraftInput(fileName: 'MODELO.DWG'), isTrue);
    expect(
      isCadAttachmentDraftInput(
        fileName: 'upload.bin',
        mimeType: 'image/vnd.dwg',
      ),
      isTrue,
    );
    expect(
      isCadAttachmentDraftInput(
        fileName: 'croquis.pdf',
        mimeType: 'application/pdf',
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
