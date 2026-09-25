import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;
import 'package:codex_mobile_frontend/src/models/session_file.dart';
import 'package:codex_mobile_frontend/src/screens/session_file_screen.dart';
import 'package:codex_mobile_frontend/src/services/api_client.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const report = '# Informe y capturas\n\n'
    '**Publicado:** portal de pagos con los cambios verificados.\n\n'
    '[Abrir pagos](https://chrem-staging.nienfos.com/admin/servicios)\n\n'
    '## Capturas\n\n'
    '| Estado | Móvil | Escritorio |\n|---|---|---|\n'
    '| Portal publicado | [390](captura.png) | [1440](desktop.png) |\n\n'
    '[Detalles](details.json)';

http.Response metadata(
        {String kind = 'text',
        String path = 'reports/INFORME.md',
        String? text = report}) =>
    http.Response(
        jsonEncode({
          'name': path.split('/').last,
          'path': path,
          'kind': kind,
          'content_type': kind == 'image' ? 'image/png' : 'text/markdown',
          'text': text,
          'truncated': false,
          'entries': [],
        }),
        200,
        headers: {'content-type': 'application/json; charset=utf-8'});

Future<void> showFile(
  WidgetTester tester,
  ApiClient client, {
  Future<void> Function(String)? onExternalLink,
  SaveSessionFile? onSave,
}) async {
  await tester.pumpWidget(MaterialApp(
    theme: ThemeData.dark(),
    home: RepaintBoundary(
        key: const ValueKey('file-capture'),
        child: SessionFileScreen(
          apiClient: client,
          sessionId: 'chat-1',
          target: '/project/reports/INFORME.md',
          onExternalLink: onExternalLink ?? (_) async {},
          onSave: onSave,
        )),
  ));
  await tester.pumpAndSettle();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(() async {
    if (const bool.fromEnvironment('CAPTURE_FILE_VIEWER')) {
      final font = FontLoader('Roboto')
        ..addFont(
          File('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
              .readAsBytes()
              .then(ByteData.sublistView),
        );
      await font.load();
    }
  });
  test('classifies local files separately from real web URLs', () {
    for (final target in [
      '/project/INFORME.md',
      'file:///project/INFORME.md',
      'AGENTS.md:38',
      'captura.png',
      '../capturas/mobile.png'
    ]) {
      expect(isServerFileLink(target), isTrue);
    }
    expect(isServerFileLink('https://chrem-staging.nienfos.com'), isFalse);
    expect(isServerFileLink('mailto:team@example.com'), isFalse);
    expect(isServerFileLink(''), isFalse);
  });
  testWidgets('report resolves screenshot relative to its own directory',
      (tester) async {
    final requests = <Uri>[];
    final client = ApiClient(
        baseUrl: 'http://bridge:8118',
        client: MockClient((request) async {
          requests.add(request.url);
          return request.url.queryParameters['path'] == 'captura.png'
              ? metadata(kind: 'image', path: 'reports/captura.png', text: null)
              : metadata();
        }));
    await showFile(tester, client);
    await tester.tap(find.text('390', findRichText: true).first);
    await tester.pumpAndSettle();
    expect(requests.last.queryParameters['relative_to'], 'reports/INFORME.md');
    expect(requests.last.path, '/sessions/chat-1/files');
    expect(find.byType(InteractiveViewer), findsOneWidget);
    final image = tester.widget<Image>(find.byType(Image));
    final uri = Uri.parse((image.image as NetworkImage).url);
    expect(uri.host, 'bridge');
    expect(uri.port, 8118);
    expect(uri.queryParameters['path'], 'reports/captura.png');
    expect(uri.path, '/sessions/chat-1/files/content');
  });
  testWidgets('web links keep their original destination', (tester) async {
    var opened = '';
    await showFile(
        tester,
        ApiClient(
            baseUrl: 'http://bridge',
            client: MockClient((_) async => metadata())),
        onExternalLink: (target) async => opened = target);
    await tester.tap(find.text('Abrir pagos', findRichText: true).first);
    await tester.pump();
    expect(opened, 'https://chrem-staging.nienfos.com/admin/servicios');
    expect(find.byType(SessionFileScreen), findsOneWidget);
  });
  testWidgets('download saves bytes instead of the server path',
      (tester) async {
    String? saved;
    final client = ApiClient(
        baseUrl: 'http://bridge',
        client: MockClient((request) async =>
            request.url.path.endsWith('/content')
                ? http.Response.bytes(utf8.encode(report), 200)
                : metadata()));
    await showFile(tester, client, onSave: (bytes, file) async {
      expect(file.name, 'INFORME.md');
      saved = utf8.decode(bytes);
    });
    await tester.tap(find.byTooltip('Descargar archivo'));
    await tester.pumpAndSettle();
    expect(saved, report);
    expect(find.text('Archivo guardado.'), findsOneWidget);
  });
  testWidgets('missing files explain the error and allow retry',
      (tester) async {
    var failed = true;
    final client = ApiClient(
        baseUrl: 'http://bridge',
        client: MockClient((_) async => failed
            ? http.Response(
                jsonEncode({
                  'detail': 'El archivo ya no está disponible en el servidor.'
                }),
                404)
            : metadata()));
    await showFile(tester, client);
    expect(find.text('El archivo ya no está disponible en el servidor.'),
        findsOneWidget);
    failed = false;
    await tester.tap(find.text('Reintentar'));
    await tester.pumpAndSettle();
    expect(find.text('INFORME.md'), findsOneWidget);
  });
  for (final width in [360.0, 430.0, 768.0, 1440.0]) {
    testWidgets('report table fits at $width', (tester) async {
      tester.view.physicalSize = Size(width, 950);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      await showFile(
          tester,
          ApiClient(
              baseUrl: 'http://bridge',
              client: MockClient((_) async => metadata())));
      expect(tester.takeException(), isNull);
      expect(find.byType(Table), findsOneWidget);
      expect(
          tester.getSize(find.byType(Table)).width, lessThanOrEqualTo(width));
      if (const bool.fromEnvironment('CAPTURE_FILE_VIEWER')) {
        final boundary = tester.renderObject<RenderRepaintBoundary>(
            find.byKey(const ValueKey('file-capture')));
        await tester.runAsync(() async {
          final image = await boundary.toImage(pixelRatio: 1);
          final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
          await File('/tmp/file-viewer-$width.png')
              .writeAsBytes(bytes!.buffer.asUint8List());
          image.dispose();
        });
      }
    });
  }
}
