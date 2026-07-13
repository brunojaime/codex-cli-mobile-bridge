import 'package:codex_mobile_frontend/src/models/dev_pipeline_handoff.dart';
import 'package:codex_mobile_frontend/src/models/server_health.dart';
import 'package:codex_mobile_frontend/src/screens/chat_screen.dart';
import 'package:codex_mobile_frontend/src/services/api_client.dart';
import 'package:codex_mobile_frontend/src/services/chat_notification_service.dart';
import 'package:codex_mobile_frontend/src/state/chat_controller.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  testWidgets('dev handoff dialog enqueues successfully', (tester) async {
    final handoffClient = _DevHandoffDialogApiClient();
    await _pumpHandoffScreen(tester, handoffClient: handoffClient);

    await _openHandoffDialog(tester);
    await _fillHandoffDialog(tester);
    await tester.tap(find.widgetWithText(FilledButton, 'Queue'));
    await tester.pumpAndSettle();

    expect(handoffClient.requests, hasLength(1));
    expect(handoffClient.idempotencyKeys.single, startsWith('mobile-'));
    expect(handoffClient.requests.single.title, 'Fix PROD issue');
    expect(
        handoffClient.requests.single.problem, 'A production issue happened.');
    expect(
      handoffClient.requests.single.acceptanceCriteria,
      'The DEV stage reproduces and fixes it.',
    );
    expect(find.text('DEV handoff queued: handoff-1'), findsOneWidget);
  });

  testWidgets('dev handoff dialog shows enqueue errors', (tester) async {
    final handoffClient = _DevHandoffDialogApiClient(shouldFail: true);
    await _pumpHandoffScreen(tester, handoffClient: handoffClient);

    await _openHandoffDialog(tester);
    await _fillHandoffDialog(tester);
    await tester.tap(find.widgetWithText(FilledButton, 'Queue'));
    await tester.pumpAndSettle();

    expect(handoffClient.requests, hasLength(1));
    expect(find.textContaining('DEV handoff failed.'), findsOneWidget);
    expect(find.textContaining('prod_handoff_disabled'), findsOneWidget);
  });
}

Future<void> _pumpHandoffScreen(
  WidgetTester tester, {
  required _DevHandoffDialogApiClient handoffClient,
}) async {
  SharedPreferences.setMockInitialValues(<String, Object>{});
  final controller = ChatController(
    apiClient: ApiClient(baseUrl: 'http://localhost:8000'),
    notificationService: const NoopChatNotificationService(),
  );
  addTearDown(controller.dispose);
  await tester.pumpWidget(
    MaterialApp(
      home: ChatScreen(
        initialApiBaseUrl: 'http://localhost:8000',
        notificationService: const NoopChatNotificationService(),
        controllerOverride: controller,
        enableServerBootstrap: false,
        initialServerHealthOverride: _prodHandoffHealth(),
        devHandoffClientOverride: handoffClient,
      ),
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> _openHandoffDialog(WidgetTester tester) async {
  await tester.enterText(find.byType(TextField).last, '/dev');
  await tester.pump();
  await tester.tap(find.text('/dev-handoff  DEV Handoff'));
  await tester.pumpAndSettle();
  expect(find.text('DEV Handoff'), findsOneWidget);
}

Future<void> _fillHandoffDialog(WidgetTester tester) async {
  final fields = find.byType(TextFormField);
  await tester.enterText(fields.at(0), 'Fix PROD issue');
  await tester.enterText(fields.at(1), 'A production issue happened.');
  await tester.enterText(fields.at(2), 'Observed in the active session.');
  await tester.enterText(
      fields.at(3), 'The DEV stage reproduces and fixes it.');
  await tester.enterText(fields.at(4), 'Screenshot and transcript available.');
  await tester.pump();
}

ServerHealth _prodHandoffHealth() {
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
        'backend_url': 'http://localhost:8000',
        'app_channel': 'prod',
        'app_label': 'Codex Mobile Bridge',
        'updater_channel': 'prod',
        'color': '#55D6BE',
        'allowed_capabilities': <String>['enqueue_dev_handoff'],
        'denied_capabilities': <String>['run_shell'],
      },
    },
  );
}

class _DevHandoffDialogApiClient extends ApiClient {
  _DevHandoffDialogApiClient({this.shouldFail = false})
      : super(baseUrl: 'http://localhost:8000');

  final bool shouldFail;
  final List<DevPipelineHandoffRequest> requests =
      <DevPipelineHandoffRequest>[];
  final List<String> idempotencyKeys = <String>[];

  @override
  Future<DevPipelineHandoff> enqueueDevHandoff(
    DevPipelineHandoffRequest request, {
    required String idempotencyKey,
  }) async {
    requests.add(request);
    idempotencyKeys.add(idempotencyKey);
    if (shouldFail) {
      throw Exception('prod_handoff_disabled');
    }
    return const DevPipelineHandoff(
      id: 'handoff-1',
      status: 'queued',
      title: 'Fix PROD issue',
      problem: 'A production issue happened.',
      idempotencyKey: 'mobile-key',
    );
  }
}
