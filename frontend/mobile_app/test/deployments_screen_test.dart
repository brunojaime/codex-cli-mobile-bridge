import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:codex_mobile_frontend/src/screens/deployments_screen.dart';
import 'package:codex_mobile_frontend/src/services/work_client.dart';

Map<String, dynamic> record(String env,
        {String status = 'published', String version = 'v2.4.0'}) =>
    {
      'id': '$env-$status',
      'status': status,
      'release': version,
      'commit': 'a' * 40,
      'deployed_at': '2026-11-06T15:30:00Z',
      'source': 'manifest',
    };
Map<String, dynamic> project(String name,
        {bool empty = false, bool errors = false}) =>
    {
      'name': name,
      'workspace_path': '/projects/$name',
      'comparison': empty ? 'insufficient' : 'different',
      'errors': errors
          ? ['No se pudo leer el registro de deploys del proyecto.']
          : [],
      'environments': [
        for (final env in ['dev', 'qa', 'prod'])
          {
            'name': env,
            'current': empty || env == 'qa'
                ? null
                : record(env, version: env == 'dev' ? 'v2.4.0' : 'v2.3.1'),
            'latest': empty || env == 'qa'
                ? null
                : record(env, status: env == 'dev' ? 'failed' : 'published'),
            'history': empty || env == 'qa'
                ? []
                : [
                    if (env == 'dev') record(env, status: 'failed'),
                    record(env)
                  ],
          }
      ],
    };

Future<void> pump(WidgetTester tester, WorkClient client,
    {String? path, String? name}) async {
  await tester.pumpWidget(MaterialApp(
      theme: ThemeData(
        useMaterial3: true,
        brightness: Brightness.dark,
        colorScheme: ColorScheme.fromSeed(
            seedColor: const Color(0xFF55D6BE),
            brightness: Brightness.dark,
            surface: const Color(0xFF141C33)),
        scaffoldBackgroundColor: const Color(0xFF0B1020),
        textTheme: ThemeData.dark().textTheme.apply(
            fontFamily: 'CaptureFont',
            bodyColor: Colors.white,
            displayColor: Colors.white),
        inputDecorationTheme: InputDecorationTheme(
            filled: true,
            fillColor: const Color(0xFF141C33),
            hintStyle: const TextStyle(color: Color(0xFF8B97B5)),
            border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(18),
                borderSide: BorderSide.none)),
        appBarTheme: const AppBarTheme(
            backgroundColor: Color(0xFF0B1020),
            foregroundColor: Colors.white,
            elevation: 0),
      ),
      home: RepaintBoundary(
          key: const ValueKey('capture'),
          child: DeploymentsScreen(
              client: client, workspacePath: path, projectName: name))));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets(
      'global searches projects, scoped request sends exact project path',
      (tester) async {
    final requests = <Uri>[];
    final client = WorkClient('https://bridge.example/api/v1',
        client: MockClient((request) async {
      requests.add(request.url);
      return http.Response(
          jsonEncode({
            'projects': [project('Casa'), project('Calendar', empty: true)]
          }),
          200);
    }));
    await pump(tester, client);
    expect(find.text('Deploys · Workspace'), findsOneWidget);
    expect(find.text('Dev'), findsNWidgets(2));
    expect(find.text('QA'), findsNWidgets(2));
    expect(find.text('Pro'), findsNWidgets(2));
    await tester.enterText(find.byType(TextField), 'Casa');
    await tester.pumpAndSettle();
    expect(find.text('Calendar'), findsNothing);
    expect(find.text('Releases diferentes'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
    await pump(tester, client, path: '/projects/A & B', name: 'A & B');
    expect(requests.last.queryParameters['workspace_path'], '/projects/A & B');
    expect(requests.last.path, '/api/v1/work/deployments');
    expect(find.byType(TextField), findsNothing);
    await tester.pumpWidget(const SizedBox());
    client.close();
  });

  testWidgets('retry restores results and failed refresh labels stale data',
      (tester) async {
    bool fail = true;
    final client = WorkClient('https://bridge.example',
        client: MockClient((_) async => fail
            ? http.Response('{"detail":"down"}', 503)
            : http.Response(
                jsonEncode({
                  'projects': [project('Casa', empty: true)]
                }),
                200)));
    await pump(tester, client);
    expect(find.text('Reintentar'), findsOneWidget);
    expect(find.text('— Sin deploy registrado'), findsNothing);
    fail = false;
    await tester.tap(find.text('Reintentar'));
    await tester.pumpAndSettle();
    expect(find.text('— Sin deploy registrado'), findsNWidgets(3));
    fail = true;
    await tester.tap(find.byTooltip('Actualizar'));
    await tester.pumpAndSettle();
    expect(find.text('Los datos visibles son de la consulta anterior.'),
        findsOneWidget);
    await tester.pumpWidget(const SizedBox());
    client.close();
  });

  for (final size in [
    const Size(390, 844),
    const Size(430, 932),
    const Size(768, 1024),
    const Size(1440, 900)
  ]) {
    testWidgets('environments and long names fit ${size.width}',
        (tester) async {
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final capture = Platform.environment['CAPTURE_DEPLOYS'] == '1';
      if (capture) {
        await tester.runAsync(() async {
          final font = File('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf');
          final loader = FontLoader('CaptureFont')
            ..addFont(
                Future.value(ByteData.sublistView(await font.readAsBytes())));
          await loader.load();
          final icons = FontLoader('MaterialIcons')
            ..addFont(rootBundle.load('fonts/MaterialIcons-Regular.otf'));
          await icons.load();
        });
      }
      final client = WorkClient('https://bridge.example',
          client: MockClient((_) async => http.Response(
              jsonEncode({
                'projects': [
                  project('Casa Digital · Vivienda principal con nombre largo'),
                  project('Calendar', empty: true)
                ]
              }),
              200)));
      await pump(tester, client);
      expect(tester.takeException(), isNull);
      expect(find.text('QA'), findsNWidgets(2));
      if (capture) {
        await tester.runAsync(() async {
          final boundary = tester.renderObject<RenderRepaintBoundary>(
              find.byKey(const ValueKey('capture')));
          final image = await boundary.toImage(pixelRatio: 1);
          final data = await image.toByteData(format: ui.ImageByteFormat.png);
          final file = File(
              '../../reports/project-deployments/screenshots/deploys-${size.width.toInt()}.png');
          await file.parent.create(recursive: true);
          await file.writeAsBytes(data!.buffer.asUint8List());
          image.dispose();
        });
      }
      await tester.tap(find.text('Dev').first);
      await tester.pumpAndSettle();
      expect(find.textContaining('Registro del proyecto'), findsWidgets);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox());
      client.close();
    });
  }
}
