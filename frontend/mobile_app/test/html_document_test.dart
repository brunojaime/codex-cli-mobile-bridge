import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter_test/flutter_test.dart';
import 'package:html/parser.dart';
import 'package:codex_mobile_frontend/src/services/html_document.dart';
import 'package:codex_mobile_frontend/src/models/session_file.dart';

void main() {
  test('HTML extension and MIME select renderer, other previews preserved', () {
    for (final ext in ['HTML', 'htm']) {
      expect(
          SessionFile(
                  name: 'report.$ext',
                  path: 'report.$ext',
                  kind: 'text',
                  contentType: 'text/plain')
              .previewKind,
          'html');
    }
    expect(
        const SessionFile(
                name: 'report',
                path: 'report',
                kind: 'text',
                contentType: 'text/html; charset=utf-8')
            .previewKind,
        'html');
    for (final ext in ['pdf', 'svg', 'mp4', 'md']) {
      expect(
          SessionFile(
                  name: 'a.$ext',
                  path: 'a.$ext',
                  kind: 'text',
                  contentType: 'text/plain')
              .previewKind,
          {'mp4': 'video', 'md': 'text'}[ext] ?? ext);
    }
  });
  test('renders styles, embeds relative CSS and images, resolves nested assets',
      () async {
    final paths = <String>[];
    final assets = {
      'reports/styles/main.css':
          '@import "nested.css"; body { background: url(../photo.png); color: green; }',
      'reports/styles/nested.css': 'h1 { font-size: 30px; }',
      'reports/photo.png': 'image-bytes',
    };
    final result = await HtmlDocumentBuilder((path) async {
      paths.add(path);
      return Uint8List.fromList(utf8.encode(assets[path]!));
    }).build(
        '<!DOCTYPE html><link rel="stylesheet" href="styles/main.css"><h1>Hola</h1><img src="photo.png"><a href="next.html">Más</a>',
        'reports/index.html');
    final doc = parse(result.html);
    expect(doc.querySelector('h1')!.text, 'Hola');
    expect(doc.querySelector('img')!.attributes['src'],
        startsWith('data:image/png;base64,'));
    final css = utf8.decode(base64Decode(
        doc.querySelector('link')!.attributes['href']!.split(',').last));
    expect(css, contains('data:text/css;base64,'));
    expect(css, contains('data:image/png;base64,'));
    expect(paths, [
      'reports/styles/main.css',
      'reports/styles/nested.css',
      'reports/photo.png'
    ]);
    expect(result.unavailableAssets, 0);
    expect(doc.querySelector('a')!.attributes['href'], 'next.html');
    expect(doc.querySelector('meta[name="viewport"]'), isNotNull);
  });
  test('blocks active content and network requests without reading credentials',
      () async {
    final paths = <String>[];
    final result = await HtmlDocumentBuilder((path) async {
      paths.add(path);
      throw Exception('denied');
    }).build(
        '''<base href="https://evil.test/"><meta http-equiv="refresh" content="0;url=https://evil.test">
<script>alert(1)</script><iframe src="file:///etc/passwd"></iframe><img src="file:///etc/passwd" onerror="alert(1)">
<img src="https://evil.test/pixel"><img src="../.env"><form action="https://evil.test"><input></form>
<a href="javascript:alert(1)" ping="https://evil.test">unsafe</a><a href="mailto:test@example.com">Mail</a>''',
        'reports/index.html');
    final doc = parse(result.html);
    expect(paths, isEmpty);
    expect(doc.querySelectorAll('script,iframe,base,[onerror],[ping],[action]'),
        isEmpty);
    expect(doc.querySelector('a')!.attributes.containsKey('href'), isFalse);
    expect(doc.querySelector('meta[http-equiv]')!.attributes['content'],
        contains("default-src 'none'"));
    expect(result.unavailableAssets, 3);
  });
  test('missing asset is visible, cycles and size are bounded', () async {
    var requests = 0;
    final result = await HtmlDocumentBuilder((path) async {
      requests++;
      if (path.endsWith('css')) {
        return Uint8List.fromList(utf8.encode('@import "a.css";'));
      }
      throw Exception('missing');
    }).build('<link rel="stylesheet" href="a.css"><img src="missing.png">',
        'r.html');
    expect(requests, 2);
    expect(result.unavailableAssets, 1);
    await expectLater(
        HtmlDocumentBuilder((_) async => Uint8List(0))
            .build('a' * (maxHtmlBytes + 1), 'a.html'),
        throwsStateError);
  });
  test('spaces and accents in workspace file paths survive URI conversion', () {
    final uri = htmlDocumentUri('reports/mi página.html');
    expect(
        Uri.decodeComponent(uri.resolve('imagen%20uno.png').path.substring(1)),
        'reports/imagen uno.png');
  });
}
