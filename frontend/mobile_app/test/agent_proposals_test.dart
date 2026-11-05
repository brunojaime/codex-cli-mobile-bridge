import 'dart:io';
import 'dart:ui' as ui;
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'dart:async';
import 'dart:convert';
import 'package:codex_mobile_frontend/src/models/agent_proposal.dart';
import 'package:codex_mobile_frontend/src/services/agent_proposal_client.dart';
import 'package:codex_mobile_frontend/src/services/proposal_notification.dart';
import 'package:codex_mobile_frontend/src/services/chat_notification_service.dart';
import 'package:codex_mobile_frontend/src/state/agent_proposal_controller.dart';
import 'package:codex_mobile_frontend/src/widgets/agent_proposals.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

Map<String, dynamic> proposal(
        {bool unread = true, String status = 'pending', int revision = 1}) =>
    {
      'id': '11111111-1111-4111-8111-111111111111',
      'revision': revision,
      'title': 'Conservar el borrador al reconectar',
      'summary': 'Recuperar el mensaje si se interrumpe la conexión.',
      'rationale': 'Reducir el trabajo perdido.',
      'workspace_name': 'Proyecto de pruebas',
      'workspace_path': '/project',
      'status': status,
      'unread': unread,
      'observations':
          status == 'needs_revision' ? 'Primero el formulario principal.' : '',
      'session_id':
          status == 'started' ? '22222222-2222-4222-8222-222222222222' : null,
      'job_id': null,
      'problem': null,
      'evidence': ['docs/reconnect.md'],
      'generator_turns': 3,
      'reviewer_turns': 2,
      'kickoff': 'Revisar, implementar y validar la recuperación.',
    };

class Notifications
    implements ProposalNotificationService, ChatNotificationService {
  final sent = <ProposalNotificationTarget>[];
  final taps = StreamController<ProposalNotificationTarget>.broadcast();
  ProposalNotificationTarget? pending;
  @override
  Future<void> initialize() async {}
  @override
  Future<void> showChatCompleted(
      ChatCompletedNotification notification) async {}
  @override
  Stream<ProposalNotificationTarget> get proposalTaps => taps.stream;
  @override
  ProposalNotificationTarget? takePendingProposal(String server) {
    if (pending?.server != server) return null;
    final result = pending;
    pending = null;
    return result;
  }

  @override
  Future<void> showProposal(ProposalNotificationTarget target) async =>
      sent.add(target);
}

Future<void> showApp(WidgetTester tester, MaterialApp app) async {
  await tester.pumpWidget(
      RepaintBoundary(key: const ValueKey('proposal-capture'), child: app));
}

Future<void> capture(WidgetTester tester, String name) async {
  if (!const bool.fromEnvironment('CAPTURE_AGENT_PROPOSALS')) return;
  await tester.pumpAndSettle();
  final boundary = tester.renderObject<RenderRepaintBoundary>(
      find.byKey(const ValueKey('proposal-capture')));
  await tester.runAsync(() async {
    final image = await boundary.toImage(pixelRatio: 1);
    final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
    final file = File(
        '../../reports/agent-proposals-implementation/screenshots/$name.png');
    await file.parent.create(recursive: true);
    await file.writeAsBytes(bytes!.buffer.asUint8List());
    image.dispose();
  });
}

void main() {
  setUpAll(() async {
    if (!const bool.fromEnvironment('CAPTURE_AGENT_PROPOSALS')) return;
    final fonts = FontLoader('Roboto')
      ..addFont(File('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
          .readAsBytes()
          .then(ByteData.sublistView));
    await fonts.load();
    final icons = FontLoader('MaterialIcons')
      ..addFont(rootBundle.load('fonts/MaterialIcons-Regular.otf'));
    await icons.load();
  });
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test(
      'notice is silent on empty inbox and deduplicated by server and revision',
      () async {
    var data = <Map<String, dynamic>>[];
    final notifications = Notifications();
    final controller = AgentProposalController(
        notifications: notifications,
        client: AgentProposalClient(
            baseUrl: 'https://bridge.test',
            client: MockClient((request) async => http.Response(
                jsonEncode({
                  'items': data,
                  'unread_count': data.length,
                  'has_more': false
                }),
                200))));
    await controller.refresh();
    expect(notifications.sent, isEmpty);
    data = [proposal()];
    await controller.refresh();
    await controller.refresh();
    expect(notifications.sent, hasLength(1));
    data = [proposal(revision: 2)];
    await controller.refresh();
    expect(notifications.sent, hasLength(2));
    controller.dispose();
    final reloaded = AgentProposalController(
        notifications: notifications,
        client: AgentProposalClient(
            baseUrl: 'https://bridge.test',
            client: MockClient((request) async => http.Response(
                jsonEncode(
                    {'items': data, 'unread_count': 1, 'has_more': false}),
                200))));
    await reloaded.refresh();
    expect(notifications.sent, hasLength(2));
    reloaded.dispose();
  });

  test('API errors preserve existing proposals and show an error', () async {
    var fail = false;
    final controller = AgentProposalController(
        client: AgentProposalClient(
            baseUrl: 'https://bridge.test',
            client: MockClient((request) async => fail
                ? http.Response('offline', 503)
                : http.Response(
                    jsonEncode({
                      'items': [proposal()],
                      'unread_count': 1,
                      'has_more': false
                    }),
                    200))));
    await controller.refresh();
    fail = true;
    await controller.refresh();
    expect(controller.items, hasLength(1));
    expect(controller.error, isNotNull);
    controller.dispose();
  });

  test('notification payload validates navigation data', () {
    const target = ProposalNotificationTarget(
        server: 'https://bridge.test',
        id: '11111111-1111-4111-8111-111111111111',
        revision: 1);
    expect(ProposalNotificationTarget.parse(target.payload)?.id, target.id);
    expect(ProposalNotificationTarget.parse('{}'), isNull);
    expect(ProposalNotificationTarget.parse('invalid'), isNull);
    expect(
        ProposalNotificationTarget.parse(
            target.payload.replaceFirst('https:', 'javascript:')),
        isNull);
  });

  for (final mode in ['warm', 'cold', 'other-server']) {
    testWidgets('notification click routes correctly: $mode', (tester) async {
      final notifications = Notifications();
      final target = ProposalNotificationTarget(
          server: mode == 'other-server'
              ? 'https://other.test'
              : 'https://bridge.test',
          id: '11111111-1111-4111-8111-111111111111',
          revision: 1);
      if (mode == 'cold') notifications.pending = target;
      var reads = 0;
      final client = AgentProposalClient(
          baseUrl: 'https://bridge.test',
          client: MockClient((request) async {
            if (request.url.path.endsWith('/read')) reads++;
            if (request.url.path == '/agent-proposals') {
              return http.Response(
                  jsonEncode(
                      {'items': [], 'unread_count': 0, 'has_more': false}),
                  200);
            }
            return http.Response(jsonEncode(proposal(unread: false)), 200);
          }));
      await showApp(
          tester,
          MaterialApp(
              debugShowCheckedModeBanner: false,
              theme: ThemeData(
                  useMaterial3: true,
                  brightness: Brightness.dark,
                  scaffoldBackgroundColor: const Color(0xFF0B1020),
                  colorScheme: ColorScheme.fromSeed(
                      seedColor: const Color(0xFF55D6BE),
                      brightness: Brightness.dark,
                      surface: const Color(0xFF141C33))),
              home: Scaffold(
                  appBar: AppBar(actions: [
                AgentProposalsButton(
                  baseUrl: 'https://bridge.test',
                  clientOverride: client,
                  notificationService: notifications,
                  autoStart: mode == 'cold',
                  onOpenChat: (_) async {},
                )
              ]))));
      await tester.pumpAndSettle();
      if (mode != 'cold') notifications.taps.add(target);
      await tester.pumpAndSettle();
      expect(reads, mode == 'other-server' ? 0 : 1);
      expect(find.text('Ejecutar'),
          mode == 'other-server' ? findsNothing : findsOneWidget);
      await tester.pumpWidget(const SizedBox());
      await notifications.taps.close();
    });
  }

  for (final action in ['execute', 'reject', 'observations']) {
    testWidgets('real API decision: $action', (tester) async {
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final calls = <Map<String, dynamic>>[];
      final controller = AgentProposalController(
          client: AgentProposalClient(
              baseUrl: 'https://bridge.test',
              client: MockClient((request) async {
                if (request.url.path.endsWith('/decisions')) {
                  final body = jsonDecode(request.body) as Map<String, dynamic>;
                  calls.add(body);
                  return http.Response(
                      jsonEncode(proposal(
                          unread: false,
                          status: body['action'] == 'execute'
                              ? 'started'
                              : body['action'] == 'reject'
                                  ? 'rejected'
                                  : 'needs_revision')),
                      200);
                }
                return http.Response(jsonEncode(proposal(unread: false)), 200);
              })));
      await showApp(
          tester,
          MaterialApp(
              debugShowCheckedModeBanner: false,
              theme: ThemeData(
                  useMaterial3: true,
                  brightness: Brightness.dark,
                  scaffoldBackgroundColor: const Color(0xFF0B1020),
                  colorScheme: ColorScheme.fromSeed(
                      seedColor: const Color(0xFF55D6BE),
                      brightness: Brightness.dark,
                      surface: const Color(0xFF141C33))),
              home: AgentProposalDetail(
                  controller: controller,
                  initial: AgentProposal(proposal()),
                  onOpenChat: (_) async {})));
      if (action == 'observations') {
        await tester.tap(find.text('Observaciones'));
        await tester.pumpAndSettle();
        await tester.tap(find.text('Enviar observaciones'));
        await tester.pumpAndSettle();
        expect(find.text('Escribí una observación.'), findsOneWidget);
        await tester.enterText(
            find.byType(TextField), 'Primero el formulario principal.');
        await capture(tester, 'observations-390');
        await tester.tap(find.text('Enviar observaciones'));
      } else {
        await tester
            .tap(find.text(action == 'execute' ? 'Ejecutar' : 'Rechazar'));
      }
      await tester.pumpAndSettle();
      await capture(tester, 'result-$action-390');
      expect(calls, hasLength(1));
      expect(calls.single['action'], action);
      expect(calls.single['revision'], 1);
      expect(find.text('Ejecutar'), findsNothing);
      if (action == 'execute') {
        expect(find.text('Abrir trabajo'), findsOneWidget);
      }
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox());
      controller.dispose();
    });
  }

  for (final size in [
    const Size(360, 800),
    const Size(430, 932),
    const Size(768, 1024),
    const Size(1440, 900),
    const Size(640, 360)
  ]) {
    testWidgets('real proposal layout $size', (tester) async {
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final controller = AgentProposalController(
          client: AgentProposalClient(baseUrl: 'https://bridge.test'));
      await showApp(
          tester,
          MaterialApp(
              debugShowCheckedModeBanner: false,
              theme: ThemeData(
                  useMaterial3: true,
                  brightness: Brightness.dark,
                  scaffoldBackgroundColor: const Color(0xFF0B1020),
                  colorScheme: ColorScheme.fromSeed(
                      seedColor: const Color(0xFF55D6BE),
                      brightness: Brightness.dark,
                      surface: const Color(0xFF141C33))),
              builder: (context, child) => MediaQuery(
                  data: MediaQuery.of(context)
                      .copyWith(textScaler: const TextScaler.linear(1.3)),
                  child: child!),
              home: AgentProposalDetail(
                  controller: controller,
                  initial: AgentProposal(proposal()),
                  onOpenChat: (_) async {})));
      expect(tester.takeException(), isNull);
      await capture(tester, 'proposal-${size.width.toInt()}');
      await tester.tap(find.text('Observaciones'));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      await tester.tap(find.text('Cancelar'));
      await tester.pumpAndSettle();
      await tester.pumpWidget(const SizedBox());
      controller.dispose();
    });
  }
}
