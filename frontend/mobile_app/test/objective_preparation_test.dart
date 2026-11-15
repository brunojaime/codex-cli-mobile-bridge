import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:codex_mobile_frontend/src/services/objective_team_client.dart';
import 'package:codex_mobile_frontend/src/screens/objective_team_screen.dart';

void main() {
  for (final width in [360.0, 1200.0]) {
    testWidgets('preparation before registration, failure and handoff $width',
        (tester) async {
      tester.view.physicalSize = Size(width, 1000);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      var active = true;
      var outcome = 'failed';
      var offline = false;
      final requests = <String>[];
      final job = {
        'job_id': 'setup-1',
        'session_id': 'chat-1',
        'status': 'running',
        'message':
            'Creá una app de inventario. Iniciá el equipo por objetivos.',
        'created_at': DateTime.now()
            .subtract(const Duration(minutes: 3))
            .toIso8601String(),
      };
      final client = ObjectiveTeamClient('http://configured-server',
          client: MockClient((r) async {
        requests.add('${r.method} ${r.url.path}');
        expect(r.method, 'GET');
        expect(r.url.host, 'configured-server');
        Object data;
        switch (r.url.path) {
          case '/maintenance/drain':
            if (offline) return http.Response('', 503);
            data = {
              'active_jobs': active
                  ? [
                      job,
                      {
                        ...job,
                        'job_id': 'unrelated',
                        'message': 'Corregí el botón de guardar.'
                      }
                    ]
                  : []
            };
          case '/sessions/chat-1':
            data = {
              'title': 'Inventario nuevo',
              'workspace_name': 'gestion',
              'archived_at': null
            };
          case '/response/setup-1':
            data = {...job, 'status': outcome};
          default:
            data = {'runs': []};
        }
        return http.Response(jsonEncode(data), 200,
            headers: {"content-type": "application/json; charset=utf-8"});
      }));
      addTearDown(client.close);
      await tester
          .pumpWidget(MaterialApp(home: ObjectiveTeamScreen(client: client)));
      await tester.pumpAndSettle();
      expect(find.text('Preparando el proyecto'), findsOneWidget);
      expect(find.text('Inventario nuevo'), findsOneWidget);
      expect(find.text('Todavía no hay ejecuciones'), findsNothing);
      expect(find.textContaining('0 entregas'), findsNothing);
      expect(requests.where((r) => r.contains('/sessions/')).length, 1);
      offline = true;
      await tester.tap(find.byTooltip('Actualizar'));
      await tester.pumpAndSettle();
      expect(find.textContaining('No se pudo actualizar la preparación'),
          findsOneWidget);
      expect(find.text('Inventario nuevo'), findsOneWidget);
      offline = false;
      active = false;
      await tester.tap(find.byTooltip('Actualizar'));
      await tester.pumpAndSettle();
      expect(find.text('Preparación interrumpida'), findsOneWidget);
      outcome = 'completed';
      await tester.tap(find.byTooltip('Actualizar'));
      await tester.pumpAndSettle();
      expect(find.text('Inventario nuevo'), findsNothing);
      expect(find.text('Todavía no hay ejecuciones'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
    });
  }
}
