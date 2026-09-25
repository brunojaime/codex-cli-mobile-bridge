import 'dart:io';
import 'dart:ui' as ui;

import 'package:codex_mobile_frontend/src/widgets/rich_message_content.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

const flow = 'Nienfos Gestión configura RD → publica cuota → administrador RD '
    'la ve → paga → webhook actualiza Gestión → RD consulta el estado actualizado';
const cloudflare = 'https://dash.cloudflare.com/?to=/:account/domains/overview';

Future<void> showMessage(
  WidgetTester tester,
  String text, {
  ValueChanged<String>? onOption,
  Future<void> Function(String)? onLink,
  double scale = 1,
}) async {
  await tester.pumpWidget(MaterialApp(
    theme: ThemeData.dark(),
    home: Scaffold(
      body: MediaQuery(
        data: MediaQueryData(textScaler: TextScaler.linear(scale)),
        child: SingleChildScrollView(
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: RepaintBoundary(
              key: const ValueKey('message-capture'),
              child: Container(
                padding: const EdgeInsets.all(16),
                color: const Color(0xFF264D59),
                child: RichMessageContent(
                  text: text,
                  textColor: Colors.white,
                  onOptionSelected: onOption,
                  onLinkTap: onLink,
                ),
              ),
            ),
          ),
        ),
      ),
    ),
  ));
}

Future<void> tapText(WidgetTester tester, String label) async {
  final finder = find.byType(EditableText).evaluate().firstWhere((element) =>
      (element.widget as EditableText).controller.text.contains(label));
  final editable = finder.widget as EditableText;
  final start = editable.controller.text.indexOf(label);
  final render = (finder as StatefulElement).state as EditableTextState;
  final box = render.renderEditable
      .getBoxesForSelection(
        TextSelection(baseOffset: start, extentOffset: start + label.length),
      )
      .first;
  await tester.tapAt(render.renderEditable.localToGlobal(box.toRect().center));
  await tester.pump();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  var clipboard = '';
  setUp(() {
    clipboard = '';
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, (call) async {
      switch (call.method) {
        case 'Clipboard.setData':
          clipboard = (call.arguments as Map)['text'] as String;
          return null;
        case 'Clipboard.getData':
          return {'text': clipboard};
        case 'Clipboard.hasStrings':
          return {'value': clipboard.isNotEmpty};
        default:
          return null;
      }
    });
  });
  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, null);
  });
  setUpAll(() async {
    if (const bool.fromEnvironment('CAPTURE_MESSAGE_LAYOUTS')) {
      final font = FontLoader('Roboto')
        ..addFont(
          File('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
              .readAsBytes()
              .then((bytes) => ByteData.sublistView(bytes)),
        );
      await font.load();
      final mono = FontLoader('monospace')
        ..addFont(
          File('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf')
              .readAsBytes()
              .then((bytes) => ByteData.sublistView(bytes)),
        );
      await mono.load();
    }
  });
  testWidgets('selection copies inline code as text without an OBJ placeholder',
      (tester) async {
    await showMessage(tester, 'Flujo final: `$flow`');
    final state = tester.state<EditableTextState>(find.byType(EditableText));
    state.selectAll(SelectionChangedCause.toolbar);
    await tester.pump();
    state.copySelection(SelectionChangedCause.toolbar);
    await tester.pump();
    expect(clipboard, 'Flujo final: $flow');
    expect(state.widget.controller.text, isNot(contains('\uFFFC')));
  });

  testWidgets('numbered instructions render formatted, working links',
      (tester) async {
    var opened = '';
    var reply = '';
    await showMessage(
      tester,
      '**Hagamos la opción más directa:**\n\n'
      '1. **[Abrí Cloudflare acá]($cloudflare)** e iniciá sesión.\n\n'
      '2. Entrá en **Domains / Dominios** y tocá agregar.',
      onOption: (text) => reply = text,
      onLink: (target) async => opened = target,
    );
    expect(find.text('Quick options'), findsNothing);
    expect(find.byType(OutlinedButton), findsNothing);
    final visible = tester
        .widgetList<EditableText>(find.byType(EditableText))
        .map((e) => e.controller.text)
        .join('\n');
    expect(visible, contains('1. Abrí Cloudflare acá e iniciá sesión.'));
    expect(visible, isNot(contains('**')));
    await tapText(tester, 'Abrí Cloudflare acá');
    expect(opened, cloudflare);
    expect(reply, isEmpty);
  });

  testWidgets('bare URLs and file links keep their exact targets',
      (tester) async {
    final opened = <String>[];
    await showMessage(
        tester,
        '$cloudflare\n\n[app.py](/home/project/app.py:12)\n\n'
        '[Docs](https://example.com/a_(b)?x=1&y=2)',
        onLink: (target) async => opened.add(target));
    await tapText(tester, cloudflare);
    await tapText(tester, 'app.py');
    await tapText(tester, 'Docs');
    expect(opened, [
      cloudflare,
      '/home/project/app.py:12',
      'https://example.com/a_(b)?x=1&y=2'
    ]);
  });

  testWidgets('explicit options wrap and insert clean text', (tester) async {
    var reply = '';
    await showMessage(
        tester,
        '**Opciones rápidas:**\n\n1. **Revisar** el archivo `main.py`\n'
        '   y mostrar los cambios antes de continuar.\n\n'
        '2. Continuar con el despliegue.',
        onOption: (text) => reply = text);
    expect(find.text('Quick options'), findsOneWidget);
    expect(find.byType(OutlinedButton), findsNWidgets(2));
    await tester.tap(find.byType(OutlinedButton).first);
    expect(reply,
        'Revisar el archivo main.py\ny mostrar los cambios antes de continuar.');
  });

  testWidgets('links within an options section never insert a reply',
      (tester) async {
    var opened = '';
    await showMessage(tester, 'Quick options:\n1. [Abrir]($cloudflare)',
        onOption: (_) => fail('A link must not insert a reply'),
        onLink: (target) async => opened = target);
    expect(find.byType(OutlinedButton), findsNothing);
    await tapText(tester, 'Abrir');
    expect(opened, cloudflare);
  });

  testWidgets('code block copy preserves whitespace and line breaks',
      (tester) async {
    const code = '  first\n    second\n';
    await showMessage(tester, '```text\n$code\n```');
    await tester.tap(find.byTooltip('Copy code'));
    await tester.pump();
    expect(clipboard, code);
  });

  for (final width in [360.0, 430.0, 768.0, 1440.0]) {
    for (final scale in [1.0, 2.0]) {
      testWidgets('readable content at width $width and text scale $scale',
          (tester) async {
        tester.view.physicalSize = Size(width, 1100);
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        const label = 'Revisar la configuración completa del dominio y mostrar '
            'todos los cambios antes de publicar la actualización';
        await showMessage(
            tester,
            'Flujo final:\n\n`$flow`\n\n'
            '1. **[Abrí Cloudflare acá]($cloudflare)** e iniciá sesión.\n\n'
            '2. Entrá en **Domains / Dominios** y agregá el dominio.\n\n'
            'Opciones rápidas:\n\n1. **$label**\n2. Continuar',
            onOption: (_) {},
            onLink: (_) async {},
            scale: scale);
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
        final text = tester.widget<Text>(find.text(label));
        expect(text.maxLines, isNull);
        expect(text.overflow, isNull);
        final render = tester.renderObject<RenderParagraph>(find.text(label));
        expect(render.didExceedMaxLines, isFalse);
        final button = find.byType(OutlinedButton).first;
        expect(tester.getRect(button).width, lessThanOrEqualTo(width - 72));
        expect(tester.getRect(button).height, greaterThanOrEqualTo(48));
        if (const bool.fromEnvironment('CAPTURE_MESSAGE_LAYOUTS')) {
          final boundary = tester.renderObject<RenderRepaintBoundary>(
              find.byKey(const ValueKey('message-capture')));
          await tester.runAsync(() async {
            final image = await boundary.toImage(pixelRatio: 1);
            final bytes =
                await image.toByteData(format: ui.ImageByteFormat.png);
            await File('/tmp/message-$width-$scale.png')
                .writeAsBytes(bytes!.buffer.asUint8List());
            image.dispose();
          });
        }
      });
    }
  }
}
