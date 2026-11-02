import 'dart:async';
import 'dart:typed_data';
import 'package:codex_mobile_frontend/src/screens/chat_screen.dart';
import 'package:codex_mobile_frontend/src/services/audio_note_recorder.dart';
import 'package:codex_mobile_frontend/src/services/message_outbox.dart';
import 'package:codex_mobile_frontend/src/widgets/outbox_panel.dart';
import 'package:codex_mobile_frontend/src/models/outbox_entry.dart';
import 'package:cross_file/cross_file.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'message_outbox_test.dart' show MemoryStore, QueueApi, payload;

class Recorder extends AudioNoteRecorder {
  bool cleaned = false;
  @override
  Future<void> start() async {}
  @override
  Future<XFile?> stop() async =>
      XFile.fromData(Uint8List.fromList([1, 2, 3]), name: 'voice.m4a');
  @override
  Future<void> cleanup(XFile file) async {
    cleaned = true;
  }

  @override
  Future<void> cancel() async {}
  @override
  Future<void> dispose() async {}
}

Finder button(IconData icon) => find
    .ancestor(of: find.byIcon(icon), matching: find.byType(FilledButton))
    .last;

void main() {
  testWidgets(
      'audio enqueues while transcription waits and microphone is immediately reusable',
      (tester) async {
    final controller = TextEditingController();
    addTearDown(controller.dispose);
    final api = QueueApi();
    final queue = MessageOutbox(api: api, store: MemoryStore());
    final recorders = <Recorder>[];
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: Align(
                alignment: Alignment.bottomCenter,
                child: buildComposerVoiceRecordingHarnessForTest(
                    controller: controller,
                    audioRecorderFactory: () {
                      final r = Recorder();
                      recorders.add(r);
                      return r;
                    },
                    onSendAudio: (file, {message}) async {
                      await queue.enqueue(payload('a', 0, audio: true),
                          audio: file);
                      return true;
                    },
                    onSendAttachments: (_, {prompt}) async => false)))));
    await tester.tap(button(Icons.mic_rounded));
    await tester.pump();
    expect(find.text('Recording'), findsOneWidget);
    await tester.tap(button(Icons.send_rounded));
    await tester.pump();
    expect(queue.entries.single.state, 'transcribing');
    expect(recorders.first.cleaned, isTrue);
    expect(controller.text, isEmpty);
    await tester.tap(button(Icons.mic_rounded));
    await tester.pump();
    expect(find.text('Recording'), findsOneWidget);
    expect(api.submissions.length, 1);
    queue.dispose();
    await tester.pump(const Duration(seconds: 2));
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets(
      'changing project releases composer and late audio completion preserves new draft',
      (tester) async {
    final controller = TextEditingController();
    addTearDown(controller.dispose);
    final saving = Completer<bool>();
    Widget screen(String session, String draft) => MaterialApp(
        home: Scaffold(
            body: Align(
                alignment: Alignment.bottomCenter,
                child: buildComposerVoiceRecordingHarnessForTest(
                    sessionId: session,
                    controller: controller,
                    stagedText: draft,
                    audioRecorderFactory: Recorder.new,
                    onSendAudio: (_, {message}) => saving.future,
                    onSendAttachments: (_, {prompt}) async => false))));
    await tester.pumpWidget(screen('a', 'old draft'));
    await tester.tap(button(Icons.mic_rounded));
    await tester.pump();
    await tester.tap(button(Icons.send_rounded));
    await tester.pump();
    expect(
        tester.widget<TextField>(find.byType(TextField).last).enabled, isFalse);
    await tester.pumpWidget(screen('b', 'new project draft'));
    expect(
        tester.widget<TextField>(find.byType(TextField).last).enabled, isTrue);
    saving.complete(true);
    await tester.pump();
    expect(controller.text, 'new project draft');
  });

  testWidgets('save failure keeps recorded audio as an attachment for retry',
      (tester) async {
    final controller = TextEditingController();
    addTearDown(controller.dispose);
    final recorders = <Recorder>[];
    final retried = <XFile>[];
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: Align(
                alignment: Alignment.bottomCenter,
                child: buildComposerVoiceRecordingHarnessForTest(
                    controller: controller,
                    audioRecorderFactory: () {
                      final r = Recorder();
                      recorders.add(r);
                      return r;
                    },
                    onSendAudio: (_, {message}) async => false,
                    onSendAttachments: (files, {prompt}) async {
                      retried.addAll(files);
                      return false;
                    })))));
    await tester.tap(button(Icons.mic_rounded));
    await tester.pump();
    await tester.tap(button(Icons.send_rounded));
    await tester.pump();
    expect(recorders.first.cleaned, isFalse);
    expect(find.text('1 selected'), findsOneWidget);
    await tester.showKeyboard(find.byType(TextField).last);
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pump();
    expect(retried, hasLength(1));
    expect(await retried.single.readAsBytes(), [1, 2, 3]);
  });

  testWidgets(
      'queue controls fit narrow screen with failed send and long project name',
      (tester) async {
    tester.view.physicalSize = const Size(320, 640);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final entry = OutboxEntry(
        id: 'failed',
        payload: payload('a', 0),
        createdAt: DateTime.now(),
        state: 'failed',
        error: 'No se pudo transcribir el audio');
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: OutboxPanel(
                entries: [entry],
                sessionTitle: (_) =>
                    'Un nombre de proyecto muy largo para un teléfono',
                onRetry: (_) async {},
                onDiscard: (_) async {}))));
    await tester.tap(find.byType(ExpansionTile));
    await tester.pumpAndSettle();
    expect(find.byTooltip('Reintentar envío'), findsOneWidget);
    expect(find.byTooltip('Descartar envío'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
