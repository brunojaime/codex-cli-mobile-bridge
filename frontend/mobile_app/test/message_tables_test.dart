import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'rich_message_content_test.dart' show showMessage, tapText;

const sampleTable = '''| Por defecto | Qué falta completar por producto |
|---|---|
| Base de acceso **Google** mediante Nienfos Acceso | Registro del consumidor, audiencia y permisos reales |
| Infraestructura de notificaciones: dispositivos, consentimiento, service worker y procesamiento | Eventos, destinatarios, preferencias e integración funcional |
| Ayuda/Tutoriales, campana y cliente editorial | Registro real, contenido y verificación |
| Módulo de correo y soporte para avisos de tutoriales | Remitente, credenciales y autorización de envíos |''';

String visibleText(WidgetTester tester) => tester
    .widgetList<EditableText>(find.byType(EditableText))
    .map((e) => e.controller.text)
    .join('\n');

Future<void> capture(WidgetTester tester, String name) async {
  if (!const bool.fromEnvironment('CAPTURE_TABLE_LAYOUTS')) return;
  await tester.pumpAndSettle();
  final boundary = tester.renderObject<RenderRepaintBoundary>(
      find.byKey(const ValueKey('message-capture')));
  await tester.runAsync(() async {
    final picture = await boundary.toImage(pixelRatio: 1.5);
    final bytes = await picture.toByteData(format: ui.ImageByteFormat.png);
    final file = File('../../reports/mobile-tables-20261008/$name.png');
    await file.writeAsBytes(bytes!.buffer.asUint8List());
    picture.dispose();
  });
}

void main() {
  var clipboard = '';
  setUpAll(() async {
    if (const bool.fromEnvironment('CAPTURE_TABLE_LAYOUTS')) {
      final font = FontLoader('Roboto')
        ..addFont(File('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
            .readAsBytes()
            .then((bytes) => ByteData.sublistView(bytes)));
      await font.load();
      final icons = FontLoader('MaterialIcons')
        ..addFont(rootBundle.load('fonts/MaterialIcons-Regular.otf'));
      await icons.load();
    }
  });
  setUp(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, (call) async {
      if (call.method == 'Clipboard.setData') {
        clipboard = (call.arguments as Map)['text'] as String;
      }
      if (call.method == 'Clipboard.getData') return {'text': clipboard};
      return null;
    });
  });
  tearDown(() => TestDefaultBinaryMessengerBinding
      .instance.defaultBinaryMessenger
      .setMockMethodCallHandler(SystemChannels.platform, null));

  testWidgets(
      'parse: table keeps empty cells, inline styles, escapes and alignment',
      (tester) async {
    await showMessage(tester, r'''Antes
| Nombre | Valor | Más |
| :--- | ---: | :---: |
| **Negrita** | `a\|b` | [Guía](/docs/guide.md:12) |
| Vacío | | Fin |
Después''');
    expect(find.byType(Table), findsOneWidget);
    final table = tester.widget<Table>(find.byType(Table));
    expect(table.children.length, 3);
    expect(visibleText(tester), contains('a|b'));
    expect(visibleText(tester), contains('Antes'));
    expect(visibleText(tester), contains('Después'));
    expect(visibleText(tester), isNot(contains('---')));
    final fields =
        tester.widgetList<SelectableText>(find.byType(SelectableText)).toList();
    expect(fields.any((f) => f.textAlign == TextAlign.right), isTrue);
    expect(fields.any((f) => f.textAlign == TextAlign.center), isTrue);
    final bold =
        fields.firstWhere((f) => f.textSpan?.toPlainText() == 'Negrita');
    expect((bold.textSpan!.children!.single as TextSpan).style!.fontWeight,
        FontWeight.w700);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
      'parse: optional edge pipes, CRLF, short rows and multiple tables',
      (tester) async {
    await showMessage(
        tester,
        'A | B\r\n--- | ---\r\nuno | dos\r\nsolo |\r\n\r\n'
        '| C | D |\n|---|---|\n| tres | cuatro |');
    expect(find.byType(Table), findsNWidgets(2));
    expect(visibleText(tester), contains('solo\n\n'));
    expect(visibleText(tester), contains('cuatro'));
  });

  testWidgets(
      'parse: fenced code, malformed tables and ordinary pipes stay text',
      (tester) async {
    for (final fence in ['```', '~~~~']) {
      await showMessage(tester, '$fence\n$sampleTable\n$fence');
      expect(find.byType(Table), findsNothing);
      expect(find.byTooltip('Copiar tabla'), findsNothing);
      expect(visibleText(tester), contains('|---|---|'));
    }
    for (final text in ['a | b\nNo es tabla', '| a | b |\n|---|\n| c | d |']) {
      await showMessage(tester, text);
      expect(find.byTooltip('Copiar tabla'), findsNothing);
      expect(visibleText(tester), contains(text));
    }
  });

  testWidgets(
      'actions: links navigate and selected code copies clean text in cells',
      (tester) async {
    var opened = '';
    await showMessage(tester,
        '| Archivo | Comando |\n|---|---|\n| [Guía](/docs/guide.md:12) | `a\\|b` |',
        onLink: (target) async => opened = target);
    await tapText(tester, 'Guía');
    expect(opened, '/docs/guide.md:12');
    final cell = find
        .byType(EditableText)
        .evaluate()
        .firstWhere((e) => (e.widget as EditableText).controller.text == 'a|b');
    final state = (cell as StatefulElement).state as EditableTextState;
    state.selectAll(SelectionChangedCause.toolbar);
    await tester.pump();
    state.copySelection(SelectionChangedCause.toolbar);
    await tester.pump();
    expect(clipboard, 'a|b');
  });

  testWidgets(
      'actions: mobile toggles, scrolls columns and copies original Markdown',
      (tester) async {
    tester.view.physicalSize = const Size(360, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await showMessage(
        tester, '| A | B | C |\n|---|---|---|\n| primero | segundo | último |');
    expect(find.byType(Table), findsNothing);
    await tester.tap(find.text('Ver tabla'));
    await tester.pumpAndSettle();
    expect(find.byType(Table), findsOneWidget);
    final scroll = find.byType(SingleChildScrollView).evaluate().firstWhere(
        (e) =>
            (e.widget as SingleChildScrollView).scrollDirection ==
            Axis.horizontal);
    final controller = (scroll.widget as SingleChildScrollView).controller!;
    await tester.drag(find.byWidget(scroll.widget), const Offset(-400, 0));
    await tester.pumpAndSettle();
    expect(controller.offset, greaterThan(0));
    expect(tester.getRect(find.byType(Table)).right, lessThanOrEqualTo(324.1));
    await tester.tap(find.byTooltip('Copiar tabla'));
    await tester.pump();
    expect(clipboard,
        '| A | B | C |\n|---|---|---|\n| primero | segundo | último |');
    await tester.tap(find.text('Ver fichas'));
    await tester.pumpAndSettle();
    expect(find.byType(Table), findsNothing);
    expect(visibleText(tester), contains('último'));
    expect(tester.takeException(), isNull);
  });

  testWidgets(
      'streaming: incomplete table becomes complete and preserves chosen view',
      (tester) async {
    tester.view.physicalSize = const Size(360, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    for (final text in [
      '| A | B |',
      '| A | B |\n|--',
      '| A | B |\n|---|---|'
    ]) {
      await showMessage(tester, text);
      expect(tester.takeException(), isNull);
    }
    expect(find.byTooltip('Copiar tabla'), findsOneWidget);
    await tester.tap(find.text('Ver tabla'));
    await tester.pump();
    await showMessage(tester, '| A | B |\n|---|---|\n| uno |');
    expect(find.byType(Table), findsOneWidget);
    await showMessage(tester, '| A | B |\n|---|---|\n| uno | dos |');
    expect(find.byType(Table), findsOneWidget);
    expect(visibleText(tester), contains('dos'));
    expect(tester.takeException(), isNull);
  });

  for (final width in [360.0, 430.0, 768.0, 1440.0, 1728.0]) {
    for (final scale in [1.0, 2.0]) {
      testWidgets(
          'layout: width $width scale $scale with full text and bounded scroll',
          (tester) async {
        tester.view.physicalSize = Size(width, 1000);
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        await showMessage(tester,
            'Para un **enlatado web nuevo** creado con el bootstrap compartido, hoy viene esto:\n\n$sampleTable',
            scale: scale);
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
        for (final element in find.byType(SelectableText).evaluate()) {
          final rect = tester.getRect(find.byWidget(element.widget));
          expect(rect.left, greaterThanOrEqualTo(20));
          expect(rect.right, lessThanOrEqualTo(width - 20));
          expect((element.widget as SelectableText).maxLines, isNull);
        }
        expect(visibleText(tester),
            contains('Remitente, credenciales y autorización de envíos'));
        expect(visibleText(tester), isNot(contains('|---')));
        await capture(tester, 'tables-${width.toInt()}-${scale.toInt()}x');
        if (width == 360 && scale == 1) {
          await tester.tap(find.text('Ver tabla'));
          await tester.pumpAndSettle();
          await capture(tester, 'tables-360-grid');
        }
      });
    }
  }
}
