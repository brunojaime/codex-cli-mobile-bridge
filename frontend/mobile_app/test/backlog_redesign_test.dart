import 'dart:io';
import 'dart:ui' as ui;
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:codex_mobile_frontend/src/screens/work_screen.dart';
import 'package:codex_mobile_frontend/src/services/work_client.dart';

Map<String, dynamic> task(
        String id, String status, String title, String path) =>
    {
      'id': id,
      'status': status,
      'title': title,
      'instruction':
          '$title\nConservar el comportamiento actual y verificar en celular.',
      'workspace_path': path,
      'source': 'feedback',
      'revision': 1,
      'updated_at': '2026-11-06T19:00:00Z',
    };

class BacklogFixture extends WorkClient {
  BacklogFixture() : super('https://bridge.example');
  bool completed = false;
  final scopes = <String?>[], cursors = <String?>[], controls = <String>[];
  @override
  Future<Map<String, dynamic>> overview() async => {
        'updated_at': '2026-11-06T19:00:00Z',
        'worker': {'recent': true},
        'projects': [
          {
            'name': 'Cebando Tradición',
            'workspace_path': '/cebando',
            'policy': {'enabled': true},
            'active': completed
                ? null
                : task('active', 'running',
                    'Mostrar el stock disponible en cada producto', '/cebando'),
            'queue': [
              task('next', 'queued', 'Simplificar el formulario de entrega',
                  '/cebando'),
              task('stale', 'completed', 'Trabajo ya terminado', '/cebando')
            ],
            'completed': [],
            'night_completed': []
          },
          {
            'name': 'Peluquerías',
            'workspace_path': '/polo',
            'policy': {'enabled': false},
            'active': null,
            'queue': [
              task('polo', 'queued', 'Preparar alertas claras para los turnos',
                  '/polo')
            ],
            'completed': [],
            'night_completed': []
          },
          {
            'name': 'Proyecto sin pendientes',
            'workspace_path': '/empty',
            'policy': null,
            'active': null,
            'queue': [],
            'completed': [],
            'night_completed': []
          },
        ],
        'questions': [
          {
            'id': 'q',
            'workspace': '/polo',
            'title': 'Decisión de Peluquerías',
            'options': []
          }
        ],
        'night': {'completed': 0, 'blocked': 0},
        'timeline': [],
      };
  @override
  Future<Map<String, dynamic>> history(
      {String? workspacePath, String? cursor}) async {
    scopes.add(workspacePath);
    cursors.add(cursor);
    return {
      'tasks': [
        {
          ...task(
              cursor == null ? 'done' : 'older',
              'completed',
              cursor == null
                  ? 'Mejora publicada anteriormente'
                  : 'Mejora más antigua',
              '/cebando'),
          'project_name': 'Cebando Tradición'
        }
      ],
      'next_cursor': cursor == null ? 'page-two' : null
    };
  }

  @override
  Future<Map<String, dynamic>> control(
      Map<String, dynamic> t, String action) async {
    controls.add('${t['id']}:$action');
    return {};
  }
}

Future<GlobalKey> open(WidgetTester tester, BacklogFixture client,
    {String? scope, double width = 390, double scale = 1}) async {
  tester.view.physicalSize = Size(
      width,
      width > 1000
          ? 900
          : width == 768
              ? 1024
              : 844);
  tester.view.devicePixelRatio = 1;
  final key = GlobalKey();
  await tester.pumpWidget(MaterialApp(
      theme: ThemeData(
          useMaterial3: true,
          fontFamily: 'Roboto',
          brightness: Brightness.dark,
          scaffoldBackgroundColor: const Color(0xff0b1020),
          colorScheme: ColorScheme.fromSeed(
              seedColor: const Color(0xff55d6be),
              brightness: Brightness.dark,
              surface: const Color(0xff151d2e)),
          cardTheme: const CardThemeData(
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.all(Radius.circular(12))))),
      builder: (context, child) => MediaQuery(
          data: MediaQuery.of(context)
              .copyWith(textScaler: TextScaler.linear(scale)),
          child: child!),
      home: RepaintBoundary(
          key: key,
          child: WorkScreen(
              baseUrl: client.baseUrl,
              clientOverride: client,
              workspacePath: scope,
              projectName: scope == '/cebando' ? 'Cebando Tradición' : null))));
  await tester.pumpAndSettle();
  return key;
}

Future<void> capture(WidgetTester tester, GlobalKey key, String name) async {
  if (Platform.environment['CAPTURE_BACKLOG'] != '1') return;
  await tester.runAsync(() async {
    final image =
        await (key.currentContext!.findRenderObject()! as RenderRepaintBoundary)
            .toImage(pixelRatio: 2);
    final bytes = (await image.toByteData(format: ui.ImageByteFormat.png))!
        .buffer
        .asUint8List();
    final file = File('../../reports/backlog-redesign/screenshots/$name.png');
    file.parent.createSync(recursive: true);
    file.writeAsBytesSync(bytes);
    image.dispose();
  });
}

void main() {
  setUpAll(() async {
    for (final entry in {
      'Roboto': 'Roboto-Regular.ttf',
      'MaterialIcons': 'MaterialIcons-Regular.otf'
    }.entries) {
      final file = File(
          '/home/batata/.local/share/flutter/bin/cache/artifacts/material_fonts/${entry.value}');
      if (file.existsSync()) {
        await (FontLoader(entry.key)
              ..addFont(
                  Future.value(ByteData.sublistView(file.readAsBytesSync()))))
            .load();
      }
    }
  });
  testWidgets('workspace drilldown scopes pending work, controls and decisions',
      (tester) async {
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final client = BacklogFixture();
    await open(tester, client);
    expect(find.text('3 pedidos pendientes'), findsOneWidget);
    expect(find.text('Proyecto sin pendientes'), findsNothing);
    expect(find.text('Trabajo ya terminado'), findsNothing);
    await tester.tap(find.text('Cebando Tradición'));
    await tester.pumpAndSettle();
    expect(find.text('Preparar alertas claras para los turnos'), findsNothing);
    await tester.tap(find.text('Simplificar el formulario de entrega'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Retirar'));
    await tester.tap(find.text('Retirar'));
    await tester.pumpAndSettle();
    expect(client.controls, ['next:cancel']);
    await tester.ensureVisible(find.text('Decisiones'));
    await tester.tap(find.text('Decisiones'));
    await tester.pumpAndSettle();
    expect(find.text('Decisión de Peluquerías'), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
  });
  testWidgets('project entry stays scoped and paginated history is separate',
      (tester) async {
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final client = BacklogFixture();
    await open(tester, client, scope: '/cebando');
    expect(find.text('Todos los proyectos'), findsNothing);
    expect(find.text('Preparar alertas claras para los turnos'), findsNothing);
    await tester.tap(find.text('Historial'));
    await tester.pumpAndSettle();
    expect(client.scopes, everyElement('/cebando'));
    await tester.tap(find.text('Ver más historial'));
    await tester.pumpAndSettle();
    expect(client.cursors.last, 'page-two');
    expect(find.text('Mejora más antigua'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
  });
  testWidgets(
      'completion removes active task after refresh and history reloads',
      (tester) async {
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final client = BacklogFixture();
    await open(tester, client, scope: '/cebando');
    expect(find.text('Mostrar el stock disponible en cada producto'),
        findsOneWidget);
    client.completed = true;
    await tester.tap(find.byTooltip('Actualizar'));
    await tester.pumpAndSettle();
    expect(find.text('Mostrar el stock disponible en cada producto'),
        findsNothing);
    expect(find.text('Simplificar el formulario de entrega'), findsOneWidget);
    await tester.tap(find.text('Historial'));
    await tester.pumpAndSettle();
    expect(find.text('Mejora publicada anteriormente'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
  });
  for (final width in [360.0, 430.0, 768.0, 1440.0]) {
    testWidgets('responsive backlog and history at $width', (tester) async {
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final client = BacklogFixture();
      final key = await open(tester, client, width: width);
      expect(tester.takeException(), isNull);
      await capture(tester, key, 'workspace-${width.toInt()}');
      await tester.tap(find.text('Cebando Tradición'));
      await tester.pumpAndSettle();
      await capture(tester, key, 'project-${width.toInt()}');
      await tester.tap(find.text('Historial'));
      await tester.pumpAndSettle();
      await capture(tester, key, 'history-${width.toInt()}');
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
    });
  }
  testWidgets('large text remains usable at 360px', (tester) async {
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await open(tester, BacklogFixture(), width: 360, scale: 1.5);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
