import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:codex_mobile_frontend/src/screens/objective_team_screen.dart';
import 'package:codex_mobile_frontend/src/services/objective_team_client.dart';

Map<String, dynamic> runState() => {
      'id': 'a' * 24,
      'project': 'Inventario',
      'status': 'executing',
      'total_units': 3,
      'accepted_units': 1,
      'active_agents': [
        {'role': 'ux_review', 'unit': 'account'},
        {'role': 'security', 'unit': 'account'}
      ],
      'jobs': [],
      'units': [
        {'id': 'base', 'state': 'accepted', 'depends_on': []},
        {
          'id': 'account',
          'state': 'reviewing',
          'depends_on': ['base']
        },
        {
          'id': 'polish',
          'state': 'ready',
          'depends_on': ['account']
        }
      ],
      'images': [],
      'issues': [],
      'blocker': {},
      'presentation': {
        'communication': 'current',
        'name': 'Inventario',
        'tasks': [
          {
            'id': 'base',
            'title': 'Base de acceso',
            'purpose': 'Acceder',
            'status': 'verified'
          },
          {
            'id': 'account',
            'title': 'Inicio y cuenta',
            'purpose': 'Organizar tu espacio',
            'owner': 'Revisión',
            'status': 'reviewing'
          },
          {
            'id': 'polish',
            'title': 'Mejorar las cards',
            'purpose': 'Claridad visual',
            'status': 'waiting',
            'dependencies': ['Inicio y cuenta']
          }
        ]
      }
    };
void main() {
  for (final width in [360.0, 1200.0]) {
    testWidgets('execution graph, dependencies and live failure at $width',
        (tester) async {
      tester.view.physicalSize = Size(width, 1200);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final run = runState();
      var offline = false;
      final client =
          ObjectiveTeamClient('http://bridge', client: MockClient((r) async {
        expect(r.method, 'GET');
        if (offline) return http.Response('', 503);
        return http.Response(
            jsonEncode(r.url.path == '/objective-team'
                ? {
                    'runs': [run]
                  }
                : run),
            200);
      }));
      addTearDown(client.close);
      await tester
          .pumpWidget(MaterialApp(home: ObjectiveTeamScreen(client: client)));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(ValueKey('objective-run-${'a' * 24}')));
      await tester.pumpAndSettle();
      expect(find.text('Mapa'), findsOneWidget);
      expect(find.text('2 agentes activos · una tarea'), findsOneWidget);
      await tester.tap(find.text('Inicio y cuenta'));
      await tester.pumpAndSettle();
      expect(find.text('Trabajando ahora'), findsOneWidget);
      expect(find.text('Revisión visual'), findsOneWidget);
      expect(find.text('Seguridad'), findsOneWidget);
      expect(find.text('Base de acceso'), findsOneWidget);
      await tester.tap(find.text('Entendido'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Trabajo pendiente'));
      await tester.pumpAndSettle();
      expect(find.text('Mejorar las cards'), findsOneWidget);
      expect(find.text('Depende de: Inicio y cuenta'), findsOneWidget);
      Navigator.of(tester.element(find.text('Pendientes y dependencias')))
          .pop();
      await tester.pumpAndSettle();
      offline = true;
      await tester.tap(find.byTooltip('Actualizar'));
      await tester.pumpAndSettle();
      expect(
          find.textContaining('pueden estar desactualizados'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox());
    });
    testWidgets(
        'attention decision is explicit, fresh and cancellable at $width',
        (tester) async {
      tester.view.physicalSize = Size(width, 1200);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final run = runState()
        ..['status'] = 'needs_attention'
        ..['active_agents'] = []
        ..['blocker'] = {'reason': 'Recovery budget exhausted'};
      var sent = 0;
      String? message;
      var reads = 0;
      final client =
          ObjectiveTeamClient('http://bridge', client: MockClient((r) async {
        expect(r.method, 'GET');
        if (r.url.path.endsWith('a' * 24)) reads++;
        return http.Response(
            jsonEncode(r.url.path == '/objective-team'
                ? {
                    'runs': [run]
                  }
                : run),
            200);
      }));
      addTearDown(client.close);
      await tester.pumpWidget(MaterialApp(
          home: ObjectiveTeamScreen(
              client: client,
              onRequestAttention: (project, text) async {
                expect(project, 'Inventario');
                sent++;
                message = text;
              })));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(ValueKey('objective-run-${'a' * 24}')));
      await tester.pumpAndSettle();
      expect(find.text('Atender ahora'), findsOneWidget);
      await tester.tap(find.text('Atender ahora'));
      await tester.pumpAndSettle();
      expect(find.textContaining('No es una autorización externa'),
          findsOneWidget);
      await tester.tap(find.text('Resolver con el agente'));
      await tester.pumpAndSettle();
      expect(reads, greaterThanOrEqualTo(2));
      await tester.tap(find.text('Cancelar'));
      await tester.pumpAndSettle();
      expect(sent, 0);
      await tester.tap(find.text('Resolver con el agente'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField),
          'Explicame las opciones antes de cambiar el límite.');
      await tester.tap(find.text('Enviar al agente'));
      await tester.pumpAndSettle();
      expect(sent, 1);
      expect(message, contains('Explicame las opciones'));
      expect(message, contains('No aumentes presupuestos'));
      expect(message, contains('a' * 24));
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox());
    });
  }
}
