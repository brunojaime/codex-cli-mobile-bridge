import 'package:codex_mobile_frontend/src/models/server_health.dart';
import 'package:codex_mobile_frontend/src/screens/chat_screen.dart';
import 'package:codex_mobile_frontend/src/services/chat_notification_service.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  testWidgets('renders PROD environment identity from health', (tester) async {
    await _pumpChatScreen(tester, health: _health(environment: 'prod'));

    expect(find.byKey(const ValueKey<String>('environment-identity-badge')),
        findsOneWidget);
    expect(find.text('PROD'), findsOneWidget);
    expect(find.textContaining('prod  |  https://bridge.example.invalid'),
        findsOneWidget);
    expect(find.text('CODEX DEV'), findsNothing);

    final container = tester.widget<Container>(
      find.byKey(const ValueKey<String>('environment-identity-badge')),
    );
    final decoration = container.decoration as BoxDecoration;
    expect(decoration.border, isNotNull);
  });

  testWidgets('renders DEV stage identity with stage branch and backend', (
    tester,
  ) async {
    await _pumpChatScreen(
      tester,
      health: _health(
        environment: 'dev',
        stageId: 'spec-018',
        branch: 'dev/spec-018-dev-prod-stage-promotion-pipeline',
        backendUrl: 'http://127.0.0.1:8118',
        appChannel: 'dev',
        appLabel: 'Codex Mobile Bridge DEV',
        updaterChannel: 'dev',
        color: '#F59E0B',
        stageRuntime: <String, dynamic>{
          'url': 'http://127.0.0.1:8118',
          'port': 8118,
          'health': 'healthy',
          'last_restart_at': '2026-07-13T10:00:00Z',
          'last_healthcheck_at': '2026-07-13T10:01:00Z',
        },
      ),
    );

    expect(find.text('DEV'), findsOneWidget);
    expect(find.textContaining('spec-018'), findsOneWidget);
    expect(
      find.textContaining('dev/spec-018-dev-prod-stage-promotion-pipeline'),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: find.byKey(const ValueKey<String>('environment-identity-badge')),
        matching: find.textContaining('http://127.0.0.1:8118'),
      ),
      findsWidgets,
    );
    expect(find.byKey(const ValueKey<String>('stage-runtime-status')),
        findsOneWidget);
    expect(find.textContaining('health healthy'), findsOneWidget);
    expect(find.textContaining('port 8118'), findsOneWidget);
    expect(find.textContaining('checked 2026-07-13T10:01:00Z'), findsOneWidget);
    expect(find.text('CODEX DEV'), findsNothing);
  });

  testWidgets('renders stage runtime in compact width', (tester) async {
    tester.view.physicalSize = const Size(420, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await _pumpChatScreen(
      tester,
      health: _health(
        environment: 'dev',
        stageId: 'spec-018',
        branch: 'dev/spec-018-dev-prod-stage-promotion-pipeline',
        backendUrl: 'http://127.0.0.1:8118',
        appChannel: 'dev',
        appLabel: 'Codex Mobile Bridge DEV',
        updaterChannel: 'dev',
        color: '#F59E0B',
        stageRuntime: <String, dynamic>{
          'url': 'http://127.0.0.1:8118',
          'port': 8118,
          'health': 'unhealthy',
          'last_healthcheck_at': '2026-07-13T10:02:00Z',
        },
      ),
    );

    expect(find.byKey(const ValueKey<String>('stage-runtime-status')),
        findsOneWidget);
    expect(find.textContaining('health unhealthy'), findsOneWidget);
    expect(find.textContaining('source http://127.0.0.1:8118'), findsOneWidget);
  });
}

Future<void> _pumpChatScreen(
  WidgetTester tester, {
  required ServerHealth health,
}) async {
  SharedPreferences.setMockInitialValues(<String, Object>{});
  await tester.pumpWidget(
    MaterialApp(
      home: ChatScreen(
        initialApiBaseUrl: health.environmentIdentity?.backendUrl ??
            'https://bridge.example.invalid',
        notificationService: const NoopChatNotificationService(),
        enableServerBootstrap: false,
        initialServerHealthOverride: health,
      ),
    ),
  );
  await tester.pumpAndSettle();
}

ServerHealth _health({
  required String environment,
  String? stageId,
  String? branch,
  String backendUrl = 'https://bridge.example.invalid',
  String appChannel = 'prod',
  String appLabel = 'Codex Mobile Bridge',
  String updaterChannel = 'prod',
  String color = '#2563EB',
  Map<String, dynamic>? stageRuntime,
}) {
  return ServerHealth.fromJson(
    <String, dynamic>{
      'server_name': environment,
      'backend_mode': 'local',
      'projects_root': '/projects',
      'audio_transcription_backend': 'disabled',
      'audio_transcription_resolved_backend': 'disabled',
      'audio_transcription_ready': false,
      'speech_synthesis_backend': 'disabled',
      'speech_synthesis_ready': false,
      'tailscale_installed': false,
      'tailscale_online': false,
      'environment_identity': <String, dynamic>{
        'environment': environment,
        'mode': stageId == null ? 'normal' : 'stage',
        'stage_id': stageId,
        'branch': branch,
        'backend_url': backendUrl,
        'app_channel': appChannel,
        'app_label': appLabel,
        'updater_channel': updaterChannel,
        'color': color,
        'allowed_capabilities': <String>[],
        'denied_capabilities': <String>[],
        if (stageRuntime != null) 'stage_runtime': stageRuntime,
      },
    },
  );
}
