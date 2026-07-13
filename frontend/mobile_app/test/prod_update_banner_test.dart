import 'package:codex_mobile_frontend/src/models/prod_update_status.dart';
import 'package:codex_mobile_frontend/src/models/server_health.dart';
import 'package:codex_mobile_frontend/src/screens/chat_screen.dart';
import 'package:codex_mobile_frontend/src/services/api_client.dart';
import 'package:codex_mobile_frontend/src/services/chat_notification_service.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  testWidgets('prod update banner renders waiting and failed states', (
    tester,
  ) async {
    await _pump(
      tester,
      status: const ProdUpdateStatus(
        state: 'waiting_for_idle',
        preparedUpdateId: 'update-1',
        blockers: <String>['active_jobs', 'pending_follow_ups'],
        notification: true,
      ),
    );

    expect(find.byKey(const ValueKey<String>('prod-update-status-banner')),
        findsOneWidget);
    expect(find.textContaining('PROD update waiting for idle'), findsOneWidget);
    expect(find.textContaining('active_jobs, pending_follow_ups'), findsOneWidget);
    expect(find.widgetWithText(TextButton, 'Force'), findsOneWidget);

    await _pump(
      tester,
      status: const ProdUpdateStatus(
        state: 'failed',
        preparedUpdateId: 'update-2',
        blockers: <String>['executor_failed'],
        notification: true,
      ),
    );
    expect(find.textContaining('PROD update failed'), findsOneWidget);
  });

  testWidgets('prod update banner acknowledge and force actions', (
    tester,
  ) async {
    final client = _ProdUpdateApiClient();
    await _pump(
      tester,
      client: client,
      status: const ProdUpdateStatus(
        state: 'updated_pending_ack',
        preparedUpdateId: 'update-ack',
        notification: true,
      ),
    );

    await tester.tap(find.widgetWithText(TextButton, 'Acknowledge'));
    await tester.pumpAndSettle();
    expect(client.acknowledged, isTrue);
    expect(find.byKey(const ValueKey<String>('prod-update-status-banner')),
        findsNothing);

    await _pump(
      tester,
      client: client,
      status: const ProdUpdateStatus(
        state: 'waiting_for_idle',
        preparedUpdateId: 'update-force',
        notification: true,
      ),
    );
    await tester.tap(find.widgetWithText(TextButton, 'Force'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byType(TextField).last,
      'FORCE PROD UPDATE update-force',
    );
    await tester.pump();
    await tester.tap(find.widgetWithText(FilledButton, 'Force'));
    await tester.pumpAndSettle();

    expect(client.forceConfirmation, 'FORCE PROD UPDATE update-force');
    expect(find.byKey(const ValueKey<String>('prod-update-status-banner')),
        findsNothing);
  });
}

Future<void> _pump(
  WidgetTester tester, {
  required ProdUpdateStatus status,
  _ProdUpdateApiClient? client,
}) async {
  SharedPreferences.setMockInitialValues(<String, Object>{});
  await tester.pumpWidget(
    MaterialApp(
      home: ChatScreen(
        key: UniqueKey(),
        initialApiBaseUrl: 'https://bridge.example.invalid',
        notificationService: const NoopChatNotificationService(),
        enableServerBootstrap: false,
        initialServerHealthOverride: _health(),
        initialProdUpdateStatusOverride: status,
        prodUpdateClientOverride: client,
      ),
    ),
  );
  await tester.pumpAndSettle();
}

ServerHealth _health() {
  return ServerHealth.fromJson(
    const <String, dynamic>{
      'server_name': 'prod',
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
        'environment': 'prod',
        'mode': 'normal',
        'backend_url': 'https://bridge.example.invalid',
        'app_channel': 'prod',
        'app_label': 'Codex Mobile Bridge',
        'updater_channel': 'prod',
        'color': '#2563EB',
      },
    },
  );
}

class _ProdUpdateApiClient extends ApiClient {
  _ProdUpdateApiClient() : super(baseUrl: 'https://bridge.example.invalid');

  bool acknowledged = false;
  String? forceConfirmation;

  @override
  Future<ProdUpdateStatus> acknowledgeProdUpdate({
    required String acknowledgedBy,
  }) async {
    acknowledged = true;
    return const ProdUpdateStatus(state: 'acknowledged');
  }

  @override
  Future<ProdUpdateStatus> forceProdUpdate({
    required String requestedBy,
    required String strongConfirmation,
  }) async {
    forceConfirmation = strongConfirmation;
    return const ProdUpdateStatus(
      state: 'force_requested',
      preparedUpdateId: 'update-force',
      notification: true,
    );
  }
}
