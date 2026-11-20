import 'dart:convert';

import 'package:codex_mobile_frontend/src/screens/relevo_screen.dart';
import 'package:codex_mobile_frontend/src/services/api_client.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  testWidgets('Pasar a Batata pide confirmación, inicia el relevo y muestra el resultado', (tester) async {
    var latest = <String, dynamic>{'status': 'none'};
    final posts = <Map<String, dynamic>>[];
    final client = MockClient((request) async {
      final path = request.url.path;
      if (path.endsWith('/relevo/destinations')) {
        return _json({
              'destinations': [
                {'name': 'batata', 'enabled': true},
                {'name': 'mac', 'enabled': false, 'note': 'Falta su Bridge'},
              ]
            }, 200);
      }
      if (path.endsWith('/relevo/runs') && request.method == 'POST') {
        posts.add(jsonDecode(request.body) as Map<String, dynamic>);
        latest = {
          'id': 'r1',
          'status': 'running',
          'destination': 'batata',
          'progress': ['Cerrando 2 chat(s) activos por steering (hasta 180s)…'],
          'already_running': false,
        };
        return _json(latest, 202);
      }
      if (path.endsWith('/relevo/runs/latest')) {
        return _json(latest, 200);
      }
      return http.Response('not found', 404);
    });
    await tester.pumpWidget(MaterialApp(
      home: RelevoScreen(
        client: ApiClient(baseUrl: 'http://bridge', client: client),
        pollInterval: const Duration(milliseconds: 50),
      ),
    ));
    await tester.pumpAndSettle();
    expect(find.text('Pasar a Batata'), findsOneWidget);
    expect(find.text('Falta su Bridge'), findsOneWidget);

    // Cancelar no inicia nada.
    await tester.tap(find.byKey(const Key('relevo-start')));
    await tester.pumpAndSettle();
    expect(find.textContaining('incluido este'), findsOneWidget);
    await tester.tap(find.text('Cancelar'));
    await tester.pumpAndSettle();
    expect(posts, isEmpty);

    await tester.tap(find.byKey(const Key('relevo-start')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('relevo-confirm')));
    for (var i = 0; i < 6; i++) {
      await tester.pump(const Duration(milliseconds: 5));
    }
    expect(posts, [
      {'destination': 'batata'}
    ]);
    expect(find.text('Relevo en curso'), findsOneWidget);
    expect(find.textContaining('Cerrando 2 chat'), findsOneWidget);
    expect(find.text('Relevo en curso…'), findsOneWidget);

    latest = {
      'id': 'r1',
      'status': 'finished',
      'destination': 'batata',
      'projects': [
        {
          'proyecto': '/home/x/patsa',
          'estado': 'en batata: código verificado (abc) y chat de continuación abierto',
          'chat_destino': '0123456789abcdef',
          'chats': ['a1b2c3d4: cerró por steering']
        }
      ],
    };
    await tester.pump(const Duration(milliseconds: 120));
    await tester.pumpAndSettle();
    expect(find.text('Relevo terminado'), findsOneWidget);
    expect(find.text('patsa'), findsOneWidget);
    expect(find.textContaining('cerró por steering'), findsOneWidget);
    expect(find.text('Chat en batata: 01234567'), findsOneWidget);
  });
}

http.Response _json(Object body, int status) => http.Response.bytes(
      utf8.encode(jsonEncode(body)),
      status,
      headers: const {'content-type': 'application/json; charset=utf-8'},
    );
