import 'dart:io';
import 'dart:typed_data';
import 'package:flutter/services.dart';
import 'package:codex_mobile_frontend/src/models/agent_activity.dart';
import 'package:codex_mobile_frontend/src/models/chat_message.dart';
import 'package:codex_mobile_frontend/src/models/job_status_response.dart';
import 'package:codex_mobile_frontend/src/widgets/agent_activity_timeline.dart';
import 'package:codex_mobile_frontend/src/widgets/chat_bubble.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const items = [
  AgentActivity(
      id: 'progress',
      kind: 'commentary',
      title:
          'Encontré dónde se pierde la actividad. Voy a conservar cada paso y conectarlo con el chat.',
      status: 'completed'),
  AgentActivity(
      id: 'read',
      kind: 'tool',
      title: 'Read',
      detail: 'frontend/mobile_app/lib/src/screens/chat_screen.dart',
      status: 'completed'),
  AgentActivity(
      id: 'edit',
      kind: 'tool',
      title: 'Cambios en archivos',
      detail: 'lib/src/widgets/agent_activity_timeline.dart',
      status: 'completed'),
  AgentActivity(
      id: 'test',
      kind: 'tool',
      title: 'Comando',
      detail:
          'flutter test test/agent_activity_timeline_test.dart\n\nAll tests passed!',
      status: 'running'),
];

Widget app({List<AgentActivity> activities = items, bool running = true}) =>
    MaterialApp(
      theme: ThemeData.dark(useMaterial3: true),
      home: Scaffold(
          body: SingleChildScrollView(
              child: Padding(
        padding: const EdgeInsets.all(16),
        child:
            AgentActivityTimeline(activities: activities, isRunning: running),
      ))),
    );

void main() {
  if (const bool.fromEnvironment('CAPTURE_ACTIVITY')) {
    setUpAll(() async {
      final directory = Platform.environment['ACTIVITY_FONT_DIR']!;
      for (final name in ['Roboto', 'MaterialIcons', 'monospace']) {
        final path = name != 'MaterialIcons'
            ? 'Roboto-Regular.ttf'
            : 'MaterialIcons-Regular.otf';
        final loader = FontLoader(name)
          ..addFont(Future.value(ByteData.sublistView(
              File('$directory/$path').readAsBytesSync())));
        await loader.load();
      }
    });
  }

  testWidgets('live steps update in place and expanded output survives updates',
      (tester) async {
    await tester.pumpWidget(app());
    expect(find.text('4 pasos · 1 en curso'), findsOneWidget);
    await tester.tap(find.text('Comando'));
    await tester.pump();
    expect(find.text(items.last.detail), findsOneWidget);
    await tester.pumpWidget(app(running: false, activities: [
      ...items.take(3),
      AgentActivity(
          id: 'test',
          kind: 'tool',
          title: 'Comando',
          detail: items.last.detail,
          status: 'completed'),
    ]));
    await tester.pumpAndSettle();
    expect(find.text('En curso'), findsNothing);
    expect(find.text(items.last.detail), findsOneWidget);
    expect(find.text('Completado'), findsNWidgets(3));
  });

  testWidgets('history can be opened and closed with the keyboard',
      (tester) async {
    await tester.pumpWidget(app(running: false));
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(find.text('Comando'), findsOneWidget);
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(find.text('Comando'), findsNothing);
  });

  testWidgets('finished history can be reopened and old steps remain reachable',
      (tester) async {
    final history = List.generate(
        12,
        (i) => AgentActivity(
            id: '$i', kind: 'tool', title: 'Paso $i', status: 'completed'));
    await tester.pumpWidget(app(activities: history, running: false));
    expect(find.text('Paso 11'), findsNothing);
    await tester.tap(find.text('Actividad'));
    await tester.pumpAndSettle();
    expect(find.text('Paso 11'), findsOneWidget);
    expect(find.text('Paso 0'), findsNothing);
    await tester.tap(find.text('Ver 6 pasos anteriores'));
    await tester.pumpAndSettle();
    expect(find.text('Paso 0'), findsOneWidget);
  });

  testWidgets(
      'failure and uncertain outcomes are explicit and final text is not repeated',
      (tester) async {
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: AgentActivityTimeline(
      isRunning: true,
      responseText: 'Respuesta final',
      activities: const [
        AgentActivity(
            id: 'failed', kind: 'tool', title: 'Prueba', status: 'failed'),
        AgentActivity(
            id: 'unknown',
            kind: 'tool',
            title: 'Interrumpido',
            status: 'unknown'),
        AgentActivity(
            id: 'final',
            kind: 'commentary',
            title: 'Respuesta final',
            status: 'completed'),
      ],
    ))));
    expect(find.text('Error'), findsOneWidget);
    expect(find.text('Sin resultado confirmado'), findsOneWidget);
    expect(find.text('Respuesta final'), findsNothing);
  });

  for (final width in [320.0, 390.0, 1280.0]) {
    testWidgets('chat activity fits width $width with enlarged text',
        (tester) async {
      tester.view.physicalSize = Size(width, 1100);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      await tester.pumpWidget(MaterialApp(
        theme: ThemeData.dark(useMaterial3: true),
        home: MediaQuery(
          data: MediaQueryData(
              size: Size(width, 1100),
              textScaler: const TextScaler.linear(1.25),
              disableAnimations: true),
          child: Scaffold(
              backgroundColor: const Color(0xFF09111F),
              body: SingleChildScrollView(
                  child: Padding(
                padding: const EdgeInsets.all(12),
                child: ChatBubble(
                    message: ChatMessage(
                  id: 'fixture',
                  text: 'Estoy verificando la nueva vista de actividad.',
                  isUser: false,
                  authorType: ChatMessageAuthorType.assistant,
                  status: ChatMessageStatus.pending,
                  jobStatus: 'running',
                  jobPhase: 'Running tools',
                  jobLatestActivity: 'Verificando la vista de actividad.',
                  createdAt: DateTime(2026, 11, 16, 15),
                  updatedAt: DateTime(2026, 11, 16, 15),
                  activities: items,
                )),
              ))),
        ),
      ));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      if (const bool.fromEnvironment('CAPTURE_ACTIVITY')) {
        await expectLater(
            find.byType(Scaffold),
            matchesGoldenFile(
                'activity_preview/activity-${width.toInt()}.png'));
      }
    });
  }

  test('job snapshot equality detects activity changes and round trips history',
      () {
    final first = JobStatusResponse.fromJson({
      'job_id': 'job',
      'agent_id': 'generator',
      'agent_type': 'generator',
      'session_id': 'chat',
      'status': 'running',
      'activities': items.map((item) => item.toJson()).toList(),
    });
    final second = first.copyWith(activities: items.take(3).toList());
    expect(first.sameUpdateAs(second), isFalse);
    expect(
        first.sameUpdateAs(JobStatusResponse.fromJson(first.toJson())), isTrue);
    final message = ChatMessage.fromJson({
      'id': 'message',
      'role': 'assistant',
      'created_at': '2026-11-16T15:00:00Z',
      'updated_at': '2026-11-16T15:00:00Z',
      'job_activities': first.toJson()['activities'],
    });
    expect(message.activities, items);
  });
}
