import 'package:codex_mobile_frontend/src/services/control_agent_client.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('derives control URL from the selected bridge host', () {
    expect(
      deriveControlAgentUrl('http://device.tailnet.ts.net:8000'),
      'http://device.tailnet.ts.net:8010',
    );
    expect(
      deriveControlAgentUrl('https://device.tailnet.ts.net'),
      'https://device.tailnet.ts.net/ops',
    );
  });

  test('loads environment status with bearer authentication', () async {
    final client = ControlAgentClient(
      baseUrl: 'http://device:8010',
      token: 'secret-token',
      client: MockClient((request) async {
        expect(request.method, 'GET');
        expect(request.url.path, '/environments');
        expect(request.headers['authorization'], 'Bearer secret-token');
        return http.Response(
          '''
          {
            "environments": [{
              "name": "prod",
              "display_name": "Production",
              "service_name": "codex-mobile-bridge-backend.service",
              "backend_url": "http://127.0.0.1:8000",
              "service": {
                "loaded": true,
                "active_state": "active",
                "sub_state": "running",
                "main_pid": 123,
                "restart_count": 0
              },
              "backend_reachable": true,
              "backend_health": {"status": "ok"},
              "active_job_count": 2,
              "active_session_count": 1,
              "in_flight_message_count": 0,
              "drain_requested": false,
              "active_action": null
            }],
            "codex": {
              "available": true,
              "authenticated": true,
              "version": "codex-cli 1.2.3",
              "detail": "Logged in"
            }
          }
          ''',
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    final snapshot = await client.getSnapshot();

    expect(snapshot.environments.single.isHealthy, isTrue);
    expect(snapshot.environments.single.activeJobCount, 2);
    expect(snapshot.environments.single.activeSessionCount, 1);
    expect(snapshot.codex.authenticated, isTrue);
  });

  test('safe restart sends deterministic mode without a command', () async {
    final client = ControlAgentClient(
      baseUrl: 'http://device:8010',
      token: 'secret-token',
      client: MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/environments/dev/restart');
        expect(request.body, '{"mode":"graceful"}');
        return http.Response(
          '{"id":"action-1","environment":"dev","mode":"graceful","status":"queued","stage":"queued","detail":"Restart queued."}',
          202,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    final action = await client.restart('dev');

    expect(action.id, 'action-1');
    expect(action.mode, 'graceful');
  });
}
