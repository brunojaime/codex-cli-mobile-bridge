import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:codex_mobile_frontend/src/screens/project_work_settings_screen.dart';
import 'package:codex_mobile_frontend/src/services/work_client.dart';

void main() {
  testWidgets('project toggles persist through API and show missing DEV separately', (tester) async {
    bool enabled = false;
    final writes = <Map<String, dynamic>>[];
    final client = WorkClient('https://bridge.example', client: MockClient((request) async {
      if (request.method == 'PUT') {
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        writes.add(body);
        enabled = body['settings']['automatic_execution'] as bool;
        return http.Response(jsonEncode(body), 200);
      }
      return http.Response(jsonEncode({'projects': [
        {'workspace_path':'/rd', 'name':'RD', 'settings':{'automatic_execution':enabled}, 'execution_status':enabled ? 'needs_setup' : 'disabled'},
        {'workspace_path':'/cebando', 'name':'Cebando Tradición', 'settings':{'automatic_execution':false}, 'execution_status':'disabled'},
      ]}), 200);
    }));
    await tester.pumpWidget(MaterialApp(home: ProjectWorkSettingsScreen(client: client)));
    await tester.pumpAndSettle();
    expect(find.text('RD'), findsOneWidget);
    expect(find.text('Cebando Tradición'), findsOneWidget);
    await tester.tap(find.byType(SwitchListTile).first);
    await tester.pumpAndSettle();
    expect(writes.single, {'workspace_path':'/rd', 'settings':{'automatic_execution':true}});
    expect(find.text('Activada · pendiente de preparar la publicación en DEV'), findsOneWidget);
    await tester.enterText(find.byType(TextField), 'RD');
    await tester.pumpAndSettle();
    expect(find.text('Cebando Tradición'), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pumpWidget(MaterialApp(home: ProjectWorkSettingsScreen(client: client)));
    await tester.pumpAndSettle();
    expect(find.widgetWithText(SwitchListTile, 'RD'), findsOneWidget);
    expect(tester.widget<SwitchListTile>(find.byType(SwitchListTile).first).value, isTrue);
    await tester.pumpWidget(const SizedBox.shrink());
    client.close();
  });

  testWidgets('failed write keeps the saved switch value', (tester) async {
    final client = WorkClient('https://bridge.example', client: MockClient((request) async {
      if (request.method == 'PUT') return http.Response('{"detail":"unavailable"}', 503);
      return http.Response('{"projects":[{"workspace_path":"/rd","name":"RD","settings":{"automatic_execution":false},"execution_status":"disabled"}]}', 200);
    }));
    await tester.pumpWidget(MaterialApp(home: ProjectWorkSettingsScreen(client: client)));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(SwitchListTile));
    await tester.pumpAndSettle();
    expect(tester.widget<SwitchListTile>(find.byType(SwitchListTile)).value, isFalse);
    expect(find.text('No se pudo guardar el cambio. Reintentá.'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
    client.close();
  });
}
