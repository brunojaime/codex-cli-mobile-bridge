import 'package:codex_mobile_frontend/src/screens/chat_screen.dart';
import 'package:codex_mobile_frontend/src/services/audio_note_recorder.dart';
import 'package:cross_file/cross_file.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('typing slash opens and filters command palette', (tester) async {
    final controller = TextEditingController();
    await tester.pumpWidget(_harness(controller: controller));

    await tester.enterText(find.byType(TextField), '/sta');
    await tester.pump();

    expect(find.textContaining('/status'), findsOneWidget);
    expect(find.textContaining('/new-project'), findsNothing);
  });

  testWidgets('disabled commands show reason and do not execute',
      (tester) async {
    final controller = TextEditingController();
    final executed = <String>[];
    await tester.pumpWidget(_harness(
      controller: controller,
      onSlashCommand: (commandId, payload) async {
        executed.add(commandId);
        return true;
      },
    ));

    await tester.enterText(find.byType(TextField), '/plan');
    await tester.pump();
    await tester.tap(find.text('/plan  Plan'));
    await tester.pump();

    expect(
        find.text('Planning mode is unavailable in this build.'), findsWidgets);
    expect(executed, isEmpty);
  });

  testWidgets('new project command dispatches callback', (tester) async {
    final controller = TextEditingController();
    final executed = <String>[];
    await tester.pumpWidget(_harness(
      controller: controller,
      onSlashCommand: (commandId, payload) async {
        executed.add(commandId);
        return true;
      },
    ));

    await tester.enterText(find.byType(TextField), '/new');
    await tester.pump();
    await tester.tap(find.text('/new-project  New Project'));
    await tester.pump();

    expect(executed, <String>['new-project']);
    expect(controller.text, isEmpty);
  });
}

Widget _harness({
  required TextEditingController controller,
  Future<bool> Function(String commandId, String payload)? onSlashCommand,
}) {
  return MaterialApp(
    home: Scaffold(
      body: Align(
        alignment: Alignment.bottomCenter,
        child: buildComposerVoiceRecordingHarnessForTest(
          controller: controller,
          audioRecorderFactory: _UnavailableAudioRecorder.new,
          onSendAudio: (_, {message}) async => false,
          onSendAttachments: (_, {prompt}) async => false,
          onSlashCommand: onSlashCommand,
        ),
      ),
    ),
  );
}

class _UnavailableAudioRecorder extends AudioNoteRecorder {
  @override
  Future<void> cancel() async {}

  @override
  Future<void> cleanup(XFile file) async {}

  @override
  Future<void> dispose() async {}

  @override
  Future<XFile?> stop() async {
    throw UnimplementedError();
  }

  @override
  Future<void> start() async {}
}
