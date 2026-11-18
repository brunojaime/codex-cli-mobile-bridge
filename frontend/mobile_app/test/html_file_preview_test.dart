import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:codex_mobile_frontend/src/screens/session_file_screen.dart';
import 'package:codex_mobile_frontend/src/services/api_client.dart';

void main() {
  testWidgets('HTML source toggle, graceful fallback and original download',
      (tester) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.linux;
    addTearDown(() => debugDefaultTargetPlatformOverride = null);
    const source = '<!DOCTYPE html><h1>Documento</h1>';
    var downloaded = '';
    final client = ApiClient(
        baseUrl: 'http://bridge.test',
        client: MockClient((request) async {
          if (request.url.path.endsWith('/content')) {
            return http.Response(source, 200);
          }
          return http.Response(
              jsonEncode({
                'name': 'doc.html',
                'path': 'doc.html',
                'kind': 'text',
                'content_type': 'text/html',
                'text': source
              }),
              200);
        }));
    await tester.pumpWidget(MaterialApp(
        home: SessionFileScreen(
            apiClient: client,
            sessionId: 'test',
            target: 'doc.html',
            onExternalLink: (_) async {},
            onSave: (bytes, file) async {
              downloaded = utf8.decode(bytes);
            })));
    await tester.pumpAndSettle();
    expect(find.text('Reintentar'), findsOneWidget);
    await tester.tap(find.text('Ver código'));
    await tester.pumpAndSettle();
    expect(find.text(source), findsOneWidget);
    await tester.tap(find.byTooltip('Descargar archivo'));
    await tester.pumpAndSettle();
    expect(downloaded, source);
    await tester.tap(find.text('Vista previa'));
    await tester.pumpAndSettle();
    expect(find.text('Reintentar'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
    debugDefaultTargetPlatformOverride = null;
  });
}
