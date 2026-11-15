import 'dart:ui' as ui;
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:codex_mobile_frontend/src/screens/objective_team_screen.dart';
import 'package:codex_mobile_frontend/src/services/objective_team_client.dart';

void main() {
  for (final width in [360.0, 1200.0]) {
    testWidgets('real navigation, evidence empty and honest delivery at $width',
        (tester) async {
      tester.view.physicalSize = Size(width, 1000);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final run = {
        'id': 'a' * 24,
        'project': 'Proyecto',
        'objective': 'Crear scripts/objective-tests.mjs',
        'presentation': {
          'name': 'Proyecto', 'purpose': 'Organizar las reservas del negocio.',
          'communication': 'current', 'verified': 0, 'active': 1, 'issues': 0,
          'tasks': [{'id':'u1', 'title':'Comprobar las reservas',
            'purpose':'Evitar que dos personas ocupen el mismo lugar.',
            'outcome':'Poder reservar con disponibilidad confiable.',
            'status':'reviewing', 'owner':'Verificación', 'dependencies':[]}],
          'capabilities':[{'title':'Agenda del negocio','purpose':'Organizar la disponibilidad.',
            'status':'reviewing','verified':0,'total':1}]
        },
        'status': 'final_review',
        'total_units': 2,
        'accepted_units': 1,
        'active_agents': [],
        'delivery': {'implemented': true, 'verified': false, 'applied': false},
        'calls': 8,
        'max_calls': 32,
        'units': [],
        'stories': [],
        'images': [],
        'issues': [],
        'jobs': [],
        'blocker': {},
        'updated_at': '2026-11-15T12:00:00Z'
      };
      var fail = false;
      final client = ObjectiveTeamClient('http://bridge',
          client: MockClient((request) async {
        if (fail) return http.Response('unavailable', 503);
        return http.Response(
            jsonEncode(request.url.path == '/objective-team'
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
      final semantics = tester.ensureSemantics();
      final node = tester
          .getSemantics(find.byKey(ValueKey('objective-run-${'a' * 24}')));
      expect(node.flagsCollection.isButton, isTrue);
      expect(node.getSemanticsData().hasAction(ui.SemanticsAction.tap), isTrue);
      semantics.dispose();
      await tester.tap(find.byKey(ValueKey('objective-run-${'a' * 24}')));
      await tester.pumpAndSettle();
      expect(find.text('En marcha'), findsOneWidget);
      expect(find.textContaining('scripts/'), findsNothing);
      expect(find.text('Comprobar las reservas'), findsOneWidget);
      expect(find.text('En revisión'), findsOneWidget);
      await tester.ensureVisible(find.text('Producto'));
      await tester.tap(find.text('Producto'));
      await tester.pumpAndSettle();
      expect(find.text('Agenda del negocio'), findsOneWidget);
      await tester.ensureVisible(find.text('Resultados'));
      await tester.tap(find.text('Resultados'));
      await tester.pumpAndSettle();
      expect(find.text('Todavía no hay entregas verificadas'), findsOneWidget);
      expect(find.text('Comprobar las reservas'), findsNothing);
      await tester.ensureVisible(find.text('Diseño'));
      await tester.tap(find.text('Diseño'));
      await tester.pumpAndSettle();
      expect(find.textContaining('Todavía no hay capturas verificadas'), findsOneWidget);
      fail = true;
      await tester.tap(find.byTooltip('Actualizar'));
      await tester.pumpAndSettle();
      expect(
          find.textContaining(
              'Los datos anteriores pueden estar desactualizados'),
          findsOneWidget);
      expect(find.text('Proyecto'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox());
    });
  }
}
