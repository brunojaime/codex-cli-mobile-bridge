import 'package:codex_mobile_frontend/src/screens/chat_screen.dart';
import 'package:codex_mobile_frontend/src/models/slash_command.dart';
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

  testWidgets('apps and workbench commands dispatch panel callbacks',
      (tester) async {
    final controller = TextEditingController();
    final executed = <String>[];
    await tester.pumpWidget(_harness(
      controller: controller,
      onSlashCommand: (commandId, payload) async {
        executed.add('$commandId:$payload');
        return true;
      },
    ));

    await tester.enterText(find.byType(TextField), '/apps');
    await tester.pump();
    await tester.tap(find.text('/apps  Apps'));
    await tester.pump();

    await tester.enterText(find.byType(TextField), '/workbench');
    await tester.pump();
    await tester.tap(find.text('/workbench  Workbench'));
    await tester.pump();

    expect(executed, <String>['apps:apps', 'workbench:workbench']);
  });

  testWidgets('dev handoff command dispatches only when enabled',
      (tester) async {
    final controller = TextEditingController();
    final executed = <String>[];
    await tester.pumpWidget(_harness(
      controller: controller,
      slashCommandContext: const SlashCommandContext(
        bridgeEnvironment: 'prod',
        devHandoffAvailable: true,
      ),
      onSlashCommand: (commandId, payload) async {
        executed.add(commandId);
        return true;
      },
    ));

    await tester.enterText(find.byType(TextField), '/dev');
    await tester.pump();
    await tester.tap(find.text('/dev-handoff  DEV Handoff'));
    await tester.pump();

    expect(executed, <String>['dev-handoff']);
  });

  testWidgets('dev handoff is blocked only for explicit dev environment',
      (tester) async {
    final controller = TextEditingController();
    final executed = <String>[];
    await tester.pumpWidget(_harness(
      controller: controller,
      slashCommandContext: const SlashCommandContext(
        bridgeEnvironment: 'dev',
        devHandoffAvailable: false,
      ),
      onSlashCommand: (commandId, payload) async {
        executed.add(commandId);
        return true;
      },
    ));

    await tester.enterText(find.byType(TextField), '/dev');
    await tester.pump();
    await tester.tap(find.text('/dev-handoff  DEV Handoff'));
    await tester.pump();

    expect(find.text('DEV handoff is only available from PROD.'), findsWidgets);
    expect(executed, isEmpty);
  });

  testWidgets('dev handoff underscore alias dispatches same command',
      (tester) async {
    final controller = TextEditingController();
    final executed = <String>[];
    await tester.pumpWidget(_harness(
      controller: controller,
      slashCommandContext: const SlashCommandContext(
        bridgeEnvironment: 'prod',
        devHandoffAvailable: true,
      ),
      onSlashCommand: (commandId, payload) async {
        executed.add(commandId);
        return true;
      },
    ));

    await tester.enterText(find.byType(TextField), '/dev_handoff');
    await tester.pump();
    await tester.tap(find.text('/dev-handoff  DEV Handoff'));
    await tester.pump();

    expect(executed, <String>['dev-handoff']);
  });

  testWidgets('backend guarded panel commands show unavailable state',
      (tester) async {
    final controller = TextEditingController();
    final executed = <String>[];
    await tester.pumpWidget(_harness(
      controller: controller,
      slashCommandContext: const SlashCommandContext(
        hasActiveBackend: false,
        workbenchAvailable: false,
        appsAvailable: false,
      ),
      onSlashCommand: (commandId, payload) async {
        executed.add(commandId);
        return true;
      },
    ));

    await tester.enterText(find.byType(TextField), '/apps');
    await tester.pump();
    await tester.tap(find.text('/apps  Apps'));
    await tester.pump();

    expect(find.text('No active bridge server.'), findsWidgets);
    expect(executed, isEmpty);
  });

  testWidgets('ordinary slash-containing messages send from button',
      (tester) async {
    final controller = TextEditingController();
    var sent = 0;
    await tester.pumpWidget(_harness(
      controller: controller,
      onSend: () async {
        sent += 1;
        return true;
      },
      onSlashCommand: (_, __) async {
        fail('ordinary slash-containing text must not dispatch a command');
      },
    ));

    await tester.enterText(find.byType(TextField), 'please inspect /tmp/logs');
    await tester.pump();
    await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
    await tester.pump();

    expect(sent, 1);
  });

  testWidgets('keyboard enter inserts newline instead of sending',
      (tester) async {
    final controller = TextEditingController();
    var sent = 0;
    await tester.pumpWidget(_harness(
      controller: controller,
      onSend: () async {
        sent += 1;
        return true;
      },
    ));

    await tester.enterText(find.byType(TextField), 'line one');
    await tester.testTextInput.receiveAction(TextInputAction.newline);
    await tester.enterText(find.byType(TextField), 'line one\nline two');
    await tester.pump();

    expect(controller.text, 'line one\nline two');
    expect(sent, 0);
  });
}

Widget _harness({
  required TextEditingController controller,
  Future<bool> Function()? onSend,
  Future<bool> Function(String commandId, String payload)? onSlashCommand,
  SlashCommandContext slashCommandContext = const SlashCommandContext(),
}) {
  return MaterialApp(
    home: Scaffold(
      body: Align(
        alignment: Alignment.bottomCenter,
        child: buildComposerVoiceRecordingHarnessForTest(
          controller: controller,
          audioRecorderFactory: _UnavailableAudioRecorder.new,
          onSend: onSend,
          onSendAudio: (_, {message}) async => false,
          onSendAttachments: (_, {prompt}) async => false,
          onSlashCommand: onSlashCommand,
          slashCommandContext: slashCommandContext,
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
