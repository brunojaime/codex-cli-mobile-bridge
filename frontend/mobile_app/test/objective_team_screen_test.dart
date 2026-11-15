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
        'objective': 'Crear una app útil',
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
      await tester.tap(find.text('Crear una app útil'));
      await tester.pumpAndSettle();
      expect(find.text('Integrado no significa publicado', findRichText: true),
          findsNothing);
      expect(find.textContaining('Integrado no significa publicado'),
          findsOneWidget);
      expect(find.byIcon(Icons.radio_button_unchecked), findsNWidgets(2));
      await tester.tap(find.text('UX'));
      await tester.pumpAndSettle();
      expect(find.textContaining('Todavía no hay capturas verificadas'),
          findsOneWidget);
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
