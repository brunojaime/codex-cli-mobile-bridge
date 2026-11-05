import 'dart:io';
import 'dart:ui' as ui;
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:codex_mobile_frontend/src/screens/work_screen.dart';
import 'package:codex_mobile_frontend/src/services/work_client.dart';

class FakeWork extends WorkClient {
  FakeWork() : super('https://bridge.example');
  final submissions = <String>[];
  final choices = <int>[];
  String notes = '';
  @override
  Future<Map<String, dynamic>> respond(String id, String action,
      [String text = '']) async {
    notes = text;
    return {};
  }

  @override
  Future<Map<String, dynamic>> overview() async => {
        'updated_at': '08:00 · Argentina',
        'worker': {'recent': true},
        'night': {'completed': 2, 'blocked': 0},
        'projects': [
          {
            'name': 'Laboratorio nocturno',
            'workspace': '/laboratorio',
            'policy': {'enabled': true},
            'active': null,
            'queue': [],
            'completed': [],
            'night_completed': [
              {
                'id': 'done',
                'title': 'Título y descripción actualizados',
                'source': 'chat',
                'status': 'completed',
                'revision': 1,
                'receipt': {'dev_url': 'DEV del laboratorio'},
              }
            ],
          }
        ],
        'questions': [
          {
            'notes': notes,
            'id': 'decision',
            'title': '¿Cómo seguimos con el laboratorio?',
            'options': [
              {'label': 'Mejorar accesibilidad'},
              {'label': 'Revisar pendientes'}
            ]
          }
        ],
        'timeline': [],
      };
  @override
  Future<Map<String, dynamic>> enqueue(String workspace, String text) async {
    submissions.add(text);
    return {'id': 'queued'};
  }

  @override
  Future<Map<String, dynamic>> choose(String id, int option) async {
    choices.add(option);
    return {'id': 'queued'};
  }
}

void main() {
  test('lost response retries the same immutable backlog request', () async {
    SharedPreferences.setMockInitialValues({});
    final payloads = <Map<String, dynamic>>[];
    final client = WorkClient('https://bridge.example',
        client: MockClient((request) async {
      payloads.add(jsonDecode(request.body) as Map<String, dynamic>);
      if (payloads.length == 1) {
        throw const SocketException('lost response');
      }
      return http.Response('{"id":"durable"}', 201);
    }));
    await expectLater(
        client.enqueue('/lab', 'Cambiar título'), throwsException);
    await client.enqueue('/lab', 'Cambiar descripción');
    await client.enqueue('/lab', 'Cambiar título');
    expect(payloads[0], payloads[2]);
    expect(payloads[0]['source_key'], isNot(payloads[1]['source_key']));
    client.close();
  });
  testWidgets('mobile backlog intake and morning choice use the shared queue',
      (tester) async {
    tester.view.physicalSize = const Size(1170, 2532);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final font = File(
        '/home/batata/.local/share/flutter/bin/cache/artifacts/material_fonts/Roboto-Regular.ttf');
    if (font.existsSync()) {
      await tester.runAsync(() => (FontLoader('Roboto')
            ..addFont(
                Future.value(ByteData.sublistView(font.readAsBytesSync()))))
          .load());
    }
    final icons = File(
        '/home/batata/.local/share/flutter/bin/cache/artifacts/material_fonts/MaterialIcons-Regular.otf');
    if (icons.existsSync()) {
      await tester.runAsync(() => (FontLoader('MaterialIcons')
            ..addFont(
                Future.value(ByteData.sublistView(icons.readAsBytesSync()))))
          .load());
    }
    final key = GlobalKey();
    final client = FakeWork();
    await tester.pumpWidget(MaterialApp(
        theme: ThemeData(
            fontFamily: 'Roboto', colorSchemeSeed: const Color(0xff16796b)),
        home: RepaintBoundary(
            key: key,
            child: WorkScreen(
                baseUrl: client.baseUrl,
                workspacePath: '/laboratorio',
                clientOverride: client))));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Agregar tarea'));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byType(TextField), 'Cambiar el título del laboratorio');
    await tester.tap(find.text('Añadir al backlog'));
    await tester.pumpAndSettle();
    expect(client.submissions, ['Cambiar el título del laboratorio']);
    await tester.tap(find.text('Decisiones'));
    await tester.pumpAndSettle();
    ScaffoldMessenger.of(key.currentContext!).clearSnackBars();
    await tester.pumpAndSettle();
    await captureWork(tester, key, 'decisiones.png');
    await tester.tap(find.text('Observaciones'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'Mantener el título');
    await tester.tap(find.text('Guardar observaciones'));
    await tester.pumpAndSettle();
    expect(client.notes, 'Mantener el título');
    await tester.tap(find.text('Mejorar accesibilidad'));
    await tester.pumpAndSettle();
    expect(client.choices, [0]);
    await tester.tap(find.text('Tu noche').first);
    await tester.pumpAndSettle();
    expect(find.text('2 avances en DEV · 0 bloqueos · 1 por decidir'),
        findsOneWidget);
    ScaffoldMessenger.of(key.currentContext!).clearSnackBars();
    await tester.pumpAndSettle();
    await captureWork(tester, key, 'tu-noche.png');
    await tester.pumpWidget(const SizedBox.shrink());
  });
}

Future<void> captureWork(
    WidgetTester tester, GlobalKey key, String name) async {
  if (Platform.environment['CAPTURE_WORK_PILOT'] != '1') return;
  await tester.runAsync(() async {
    final boundary =
        key.currentContext!.findRenderObject()! as RenderRepaintBoundary;
    final image = await boundary.toImage(pixelRatio: 3);
    final bytes = (await image.toByteData(format: ui.ImageByteFormat.png))!
        .buffer
        .asUint8List();
    final file = File('../../reports/work-coordinator-pilot/$name');
    file.parent.createSync(recursive: true);
    file.writeAsBytesSync(bytes);
  });
}
