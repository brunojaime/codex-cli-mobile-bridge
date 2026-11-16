import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:codex_mobile_frontend/src/services/objective_team_client.dart';

void main() {
  for (final scenario in [
    'active',
    'expired',
    'wrong-project',
    'unsafe-url',
    'missing-link',
    'ambiguous'
  ]) {
    test('publication links require evidence: $scenario', () async {
      final project = {
        'name': 'Inventory',
        'workspace_path': '/inventory',
        'environments': [
          {
            'name': 'dev',
            'current': {
              'id': 'preview:p1',
              'status': 'published',
              'deployed_at': '2026-11-15T12:00:00Z'
            }
          }
        ]
      };
      final calls = <String>[];
      final client = ObjectiveTeamClient('http://bridge',
          client: MockClient((request) async {
        expect(request.method, 'GET');
        calls.add(request.url.path);
        if (request.url.path == '/work/deployments') {
          return http.Response(
              jsonEncode({
                'projects': [project, if (scenario == 'ambiguous') project]
              }),
              200);
        }
        if (scenario == 'missing-link') return http.Response('', 503);
        return http.Response(
            jsonEncode({
              'project_path':
                  scenario == 'wrong-project' ? '/other' : '/inventory',
              'status': 'active',
              'expires_at':
                  scenario == 'expired' ? '2020-01-01T00:00:00Z' : null,
              'preview_url': scenario == 'unsafe-url'
                  ? 'javascript:alert(1)'
                  : 'https://inventory.example'
            }),
            200);
      }));
      addTearDown(client.close);
      final result = await client.publications('Inventory');
      final records = result['records'] as List;
      if (scenario == 'ambiguous') {
        expect(records, isEmpty);
        expect(calls, ['/work/deployments']);
      } else {
        expect(records.single['url'],
            scenario == 'active' ? 'https://inventory.example' : isNull);
      }
    });
  }
}
