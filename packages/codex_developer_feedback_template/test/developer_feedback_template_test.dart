import 'dart:convert';
import 'dart:async';
import 'dart:typed_data';

import 'package:codex_developer_feedback_template/developer_feedback_audio_recorder_contract.dart';
import 'package:codex_developer_feedback_template/developer_feedback_template.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('disabled wrapper is absent and does not intercept app taps', (
    tester,
  ) async {
    var taps = 0;
    await tester.pumpWidget(
      _Harness(
        enabled: false,
        child: ElevatedButton(
          onPressed: () => taps += 1,
          child: const Text('App action'),
        ),
      ),
    );
    await tester.tap(find.text('App action'));
    await tester.pump();
    expect(taps, 1);
    expect(find.byKey(developerFeedbackToolbarKey), findsNothing);
    expect(find.byKey(developerFeedbackHistoryKey), findsNothing);
  });

  testWidgets('enabled template starts without pending export UI', (
    tester,
  ) async {
    await tester.pumpWidget(const _Harness(enabled: true));
    expect(find.byKey(developerFeedbackToolbarKey), findsOneWidget);
    expect(find.byKey(developerFeedbackPendingKey), findsNothing);
    expect(find.byKey(developerFeedbackCopyKey), findsNothing);
  });

  testWidgets('template toolbar floats and can be dragged', (tester) async {
    _setViewport(tester, const Size(390, 844));
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(const _Harness(enabled: true));
    await tester.pumpAndSettle();

    final toolbar = find.byKey(developerFeedbackToolbarKey);
    final before = tester.getTopLeft(toolbar);
    expect(_feedbackSwitchValue(tester), isFalse);

    await tester.dragFrom(before + const Offset(12, 12), const Offset(-96, 84));
    await tester.pumpAndSettle();

    final after = tester.getTopLeft(toolbar);
    expect(after.dx, lessThan(before.dx));
    expect(after.dy, greaterThan(before.dy));
    expect(_feedbackSwitchValue(tester), isFalse);

    await tester.tap(find.byKey(developerFeedbackSwitchKey));
    await tester.pump();
    expect(_feedbackSwitchValue(tester), isTrue);
    expect(find.byKey(developerFeedbackOverlayKey), findsOneWidget);
  });

  testWidgets('template toolbar clamps when dragged past viewport edges', (
    tester,
  ) async {
    const viewport = Size(390, 844);
    _setViewport(tester, viewport);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(const _Harness(enabled: true));
    await tester.pumpAndSettle();

    await _dragToolbar(tester, const Offset(-1200, -1200));
    _expectToolbarInsideViewport(tester, viewport);

    await _dragToolbar(tester, const Offset(1200, 1200));
    _expectToolbarInsideViewport(tester, viewport);

    await _dragToolbar(tester, const Offset(-1200, 1200));
    _expectToolbarInsideViewport(tester, viewport);

    await _dragToolbar(tester, const Offset(1200, -1200));
    _expectToolbarInsideViewport(tester, viewport);
    _expectNoFlutterExceptions(tester);
  });

  testWidgets('template toolbar remains visible after viewport resize', (
    tester,
  ) async {
    const portrait = Size(390, 844);
    const compact = Size(320, 480);
    const landscape = Size(844, 390);
    _setViewport(tester, portrait);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(const _Harness(enabled: true));
    await tester.pumpAndSettle();
    await _dragToolbar(tester, const Offset(-80, 560));
    _expectToolbarInsideViewport(tester, portrait);

    _setViewport(tester, compact);
    await tester.pumpAndSettle();
    _expectToolbarInsideViewport(tester, compact);

    _setViewport(tester, landscape);
    await tester.pumpAndSettle();
    _expectToolbarInsideViewport(tester, landscape);
    _expectNoFlutterExceptions(tester);
  });

  testWidgets('moved template toolbar still allows feedback queue flow', (
    tester,
  ) async {
    _setViewport(tester, const Size(390, 844));
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(const _Harness(enabled: true));
    await tester.pumpAndSettle();
    await _dragToolbar(tester, const Offset(-96, 84));
    _expectNoFlutterExceptions(tester);

    await tester.tap(find.byKey(developerFeedbackSwitchKey));
    await tester.pump();
    _expectNoFlutterExceptions(tester);

    await _drawFeedbackSelection(tester);
    await tester.pumpAndSettle();
    _expectNoFlutterExceptions(tester);

    await tester.tap(find.byKey(developerFeedbackCommentActionKey));
    await tester.pumpAndSettle();
    _expectNoFlutterExceptions(tester);

    await tester.enterText(
      find.byKey(developerFeedbackCommentKey),
      'Feedback con toolbar movido',
    );
    await tester.pump();
    _expectNoFlutterExceptions(tester);

    await tester.tap(find.byKey(developerFeedbackSaveKey));
    await tester.pumpAndSettle();
    expect(_feedbackSwitchValue(tester), isTrue);
    expect(find.byKey(developerFeedbackOverlayKey), findsOneWidget);
    _expectToolbarInsideViewport(tester, const Size(390, 844));
    _expectNoFlutterExceptions(tester);

    await tester.tap(find.byKey(developerFeedbackPendingKey));
    await tester.pumpAndSettle();
    expect(find.text('Feedback con toolbar movido'), findsOneWidget);
    _expectNoFlutterExceptions(tester);
  });

  testWidgets('overlay only exists after feedback mode is active', (
    tester,
  ) async {
    await tester.pumpWidget(const _Harness(enabled: true));
    expect(find.byKey(developerFeedbackOverlayKey), findsNothing);
    await tester.tap(find.byKey(developerFeedbackSwitchKey));
    await tester.pump();
    expect(find.byKey(developerFeedbackOverlayKey), findsOneWidget);
  });

  testWidgets('tap, short stroke, or straight line does not open dialog', (
    tester,
  ) async {
    await tester.pumpWidget(const _Harness(enabled: true));
    await tester.tap(find.byKey(developerFeedbackSwitchKey));
    await tester.pump();

    await tester.tap(find.byKey(developerFeedbackOverlayKey));
    await tester.pumpAndSettle();
    expect(find.byKey(developerFeedbackCommentKey), findsNothing);
    expect(find.byKey(developerFeedbackCommentActionKey), findsNothing);
    expect(find.byKey(developerFeedbackOverlayKey), findsOneWidget);

    await _drawFeedbackSelection(tester, shortStroke: true);
    await tester.pumpAndSettle();
    expect(find.byKey(developerFeedbackCommentKey), findsNothing);
    expect(find.byKey(developerFeedbackCommentActionKey), findsNothing);
    expect(find.byKey(developerFeedbackOverlayKey), findsOneWidget);

    await _drawFeedbackSelection(tester, straightStroke: true);
    await tester.pumpAndSettle();
    expect(find.byKey(developerFeedbackCommentKey), findsNothing);
    expect(find.byKey(developerFeedbackCommentActionKey), findsNothing);
    expect(find.byKey(developerFeedbackOverlayKey), findsOneWidget);
  });

  testWidgets('deliberate area selection enables comment action', (
    tester,
  ) async {
    await tester.pumpWidget(const _Harness(enabled: true));
    await tester.tap(find.byKey(developerFeedbackSwitchKey));
    await tester.pump();

    await _drawFeedbackSelection(tester);
    await tester.pumpAndSettle();
    expect(find.byKey(developerFeedbackCommentKey), findsNothing);
    expect(find.byKey(developerFeedbackCommentActionKey), findsOneWidget);

    await tester.tap(find.byKey(developerFeedbackCommentActionKey));
    await tester.pumpAndSettle();
    expect(find.byKey(developerFeedbackCommentKey), findsOneWidget);
  });

  testWidgets('reset clears a ready selection without opening dialog', (
    tester,
  ) async {
    await tester.pumpWidget(const _Harness(enabled: true));
    await tester.tap(find.byKey(developerFeedbackSwitchKey));
    await tester.pump();

    await _drawFeedbackSelection(tester);
    await tester.pumpAndSettle();
    expect(find.byKey(developerFeedbackCommentActionKey), findsOneWidget);

    await tester.tap(find.byKey(developerFeedbackResetSelectionKey));
    await tester.pumpAndSettle();
    expect(find.byKey(developerFeedbackCommentActionKey), findsNothing);
    expect(find.byKey(developerFeedbackResetSelectionKey), findsNothing);
    expect(find.byKey(developerFeedbackCommentKey), findsNothing);
    expect(find.byKey(developerFeedbackOverlayKey), findsOneWidget);
    expect(_feedbackSwitchValue(tester), isTrue);

    await _drawFeedbackSelection(tester);
    await tester.pumpAndSettle();
    expect(find.byKey(developerFeedbackCommentActionKey), findsOneWidget);
    expect(find.byKey(developerFeedbackResetSelectionKey), findsOneWidget);
    expect(_feedbackSwitchValue(tester), isTrue);
  });

  testWidgets('saves queued feedback, copies export, and deletes item', (
    tester,
  ) async {
    var copied = '';
    await tester.pumpWidget(
      _Harness(enabled: true, copyText: (text) async => copied = text),
    );
    await _saveFeedback(tester, 'Cambiar este bloque');

    await tester.tap(find.byKey(developerFeedbackPendingKey));
    await tester.pumpAndSettle();
    expect(find.text('Cambiar este bloque'), findsOneWidget);

    await tester.tap(find.byKey(developerFeedbackCopyKey));
    await tester.pumpAndSettle();
    final decoded = jsonDecode(copied) as Map<String, Object?>;
    final item =
        (decoded['items'] as List<Object?>).single as Map<String, Object?>;
    expect(decoded['kind'], 'codex.developerFeedbackExport');
    expect(item['kind'], 'codex.developerFeedback');
    expect(item['sourceApp'], 'fixture-app');
    expect(item['sourceDisplayName'], 'Fixture App');
    expect(item['queue'], 'codexCli');
    expect(item['status'], 'pending');
    expect(item['comment'], 'Cambiar este bloque');
    expect(item['screenshotMimeType'], 'image/png');
    final selectionPoints = item['selectionPoints'] as List<Object?>;
    final selectionBounds = item['selectionBounds'] as Map<String, Object?>;
    expect(selectionPoints.length, greaterThanOrEqualTo(8));
    expect(selectionBounds['width'], greaterThanOrEqualTo(72));
    expect(selectionBounds['height'], greaterThanOrEqualTo(72));
    expect(item['hasAudio'], isFalse);
    expect(item.containsKey('audioBase64'), isFalse);

    await tester.tap(find.byIcon(Icons.delete_outline));
    await tester.pumpAndSettle();
    expect(find.text('No hay feedback pendiente.'), findsOneWidget);
  });

  testWidgets('queued feedback comment can be edited before sending', (
    tester,
  ) async {
    await tester.pumpWidget(const _Harness(enabled: true));
    await _saveFeedback(tester, 'Texto inicial');

    await tester.tap(find.byKey(developerFeedbackPendingKey));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(developerFeedbackEditCommentKey));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(developerFeedbackCommentKey),
      'Texto corregido y mas claro',
    );
    await tester.tap(find.text('Guardar'));
    await tester.pumpAndSettle();

    expect(find.text('Texto inicial'), findsNothing);
    expect(find.text('Texto corregido y mas claro'), findsOneWidget);
  });

  testWidgets('clears multiple queued items', (tester) async {
    await tester.pumpWidget(const _Harness(enabled: true));
    await _saveFeedback(tester, 'Primero');
    await _saveFeedback(tester, 'Segundo');
    await tester.tap(find.byKey(developerFeedbackPendingKey));
    await tester.pumpAndSettle();
    expect(find.text('Primero'), findsOneWidget);
    expect(find.text('Segundo'), findsOneWidget);
    await tester.tap(find.byKey(developerFeedbackClearKey));
    await tester.pumpAndSettle();
    expect(find.text('No hay feedback pendiente.'), findsOneWidget);
  });

  testWidgets('queues three feedback captures in order', (tester) async {
    var copied = '';
    await tester.pumpWidget(
      _Harness(enabled: true, copyText: (text) async => copied = text),
    );
    await _saveFeedback(tester, 'Primero');
    await _saveFeedback(tester, 'Segundo');
    await _saveFeedback(tester, 'Tercero');

    await tester.tap(find.byKey(developerFeedbackPendingKey));
    await tester.pumpAndSettle();

    expect(
      find.byKey(developerFeedbackPreviewItemKey),
      findsAtLeastNWidgets(1),
    );
    expect(
      find.byKey(developerFeedbackPreviewThumbnailKey),
      findsAtLeastNWidgets(1),
    );
    expect(find.text('Primero'), findsOneWidget);
    expect(find.text('Segundo'), findsOneWidget);

    await tester.tap(find.byKey(developerFeedbackCopyKey));
    await tester.pumpAndSettle();
    final items = jsonDecode(copied)['items'] as List<Object?>;
    expect(
      items
          .cast<Map<String, Object?>>()
          .map((item) => item['comment'])
          .toList(),
      <String>['Primero', 'Segundo', 'Tercero'],
    );
  });

  testWidgets('deleting one queued item preserves the rest', (tester) async {
    await tester.pumpWidget(const _Harness(enabled: true));
    await _saveFeedback(tester, 'Eliminar esta');
    await _saveFeedback(tester, 'Conservar esta');

    await tester.tap(find.byKey(developerFeedbackPendingKey));
    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(Icons.delete_outline).first);
    await tester.pumpAndSettle();

    expect(find.text('Eliminar esta'), findsNothing);
    expect(find.text('Conservar esta'), findsOneWidget);
    expect(find.text('No hay feedback pendiente.'), findsNothing);
    expect(find.byKey(developerFeedbackPreviewItemKey), findsOneWidget);
  });

  testWidgets(
    'preview shows screenshot bounds audio preset and release option',
    (tester) async {
      await tester.pumpWidget(
        _Harness(enabled: true, recorderFactory: () => _SupportedRecorder()),
      );

      await tester.tap(find.byKey(developerFeedbackSwitchKey));
      await tester.pump();
      await _drawFeedbackSelection(tester);
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(developerFeedbackCommentActionKey));
      await tester.pumpAndSettle();
      await tester.enterText(
        find.byKey(developerFeedbackCommentKey),
        'Preview completo',
      );
      await tester.tap(find.byKey(const Key('developer-feedback-audio')));
      await tester.pump();
      await tester.tap(find.byKey(const Key('developer-feedback-audio')));
      await tester.pump();
      await tester.tap(find.byKey(developerFeedbackSaveKey));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(developerFeedbackPendingKey));
      await tester.pumpAndSettle();

      expect(find.byKey(developerFeedbackPreviewThumbnailKey), findsOneWidget);
      expect(find.text('Preview completo'), findsOneWidget);
      expect(find.textContaining('Bounds: x'), findsOneWidget);
      expect(find.text('Audio: 1234 ms, 3 bytes, audio/webm'), findsOneWidget);
      expect(find.byKey(developerFeedbackPresetDropdownKey), findsOneWidget);
      expect(
        tester
            .widget<Checkbox>(
              find.byKey(developerFeedbackReleaseWhenCompleteKey),
            )
            .value,
        isFalse,
      );
    },
  );

  testWidgets('failed custom batch send preserves queued preview', (
    tester,
  ) async {
    var attempts = 0;
    await tester.pumpWidget(
      _Harness(
        enabled: true,
        bridgeSubmitBatch: (_) async {
          attempts += 1;
          throw Exception('bridge unavailable');
        },
      ),
    );

    await _saveFeedback(tester, 'Enviar luego');
    await tester.tap(find.byKey(developerFeedbackPendingKey));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(developerFeedbackSendBatchKey));
    await tester.pumpAndSettle();

    expect(attempts, 1);
    expect(find.text('Enviar luego'), findsOneWidget);
    expect(find.byKey(developerFeedbackPreviewItemKey), findsOneWidget);
    expect(
      tester
          .widget<FilledButton>(find.byKey(developerFeedbackSendBatchKey))
          .onPressed,
      isNotNull,
    );
  });

  testWidgets('copy export fallback is graceful', (tester) async {
    var attempts = 0;
    await tester.pumpWidget(
      _Harness(
        enabled: true,
        copyText: (_) async {
          attempts += 1;
          throw Exception('clipboard unavailable');
        },
      ),
    );
    await _saveFeedback(tester, 'Fallback');
    await tester.tap(find.byKey(developerFeedbackPendingKey));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(developerFeedbackCopyKey));
    await tester.pumpAndSettle();
    expect(attempts, 1);
    expect(find.text('Cola de feedback'), findsOneWidget);
  });

  testWidgets('sends queued feedback batch to configured bridge submitter', (
    tester,
  ) async {
    DeveloperFeedbackBatch? submitted;
    await tester.pumpWidget(
      _Harness(
        enabled: true,
        sourceApp: 'second-app',
        sourceDisplayName: 'Second App',
        bridgeSubmitBatch: (batch) async => submitted = batch,
      ),
    );

    await _saveFeedback(tester, 'Enviar por Tailscale');
    expect(submitted, isNull);
    await tester.tap(find.byKey(developerFeedbackPendingKey));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(developerFeedbackReleaseWhenCompleteKey));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(developerFeedbackSendBatchKey));

    await tester.pumpAndSettle();
    expect(submitted, isNotNull);
    final bridgeJson = submitted!.toBridgeJson();
    expect(bridgeJson['kind'], 'codex.developerFeedbackBatch');
    expect(bridgeJson['version'], 3);
    expect(bridgeJson['batchId'], isA<String>());
    expect(bridgeJson['sourceApp'], 'second-app');
    expect(bridgeJson['sourceDisplayName'], 'Second App');
    expect(bridgeJson['workflowPresetId'], 'generator_only');
    expect(bridgeJson['releaseWhenComplete'], isTrue);
    final items = bridgeJson['items'] as List<Object?>;
    final item = items.single as Map<String, Object?>;
    expect(item['kind'], 'codex.developerFeedback');
    expect(item['version'], 3);
    expect(item['queue'], 'codexCli');
    expect(item['status'], 'pending');
    expect(item['comment'], 'Enviar por Tailscale');
    expect(item['screenshotPngBase64'], isA<String>());
    expect(item['selectionPoints'], isA<List<Object?>>());
    expect(item['selectionBounds'], isA<Map<String, Object?>>());
    expect(item['hasAudio'], isFalse);
  });

  testWidgets('bridge submission posts queued batch to configured bridge URL', (
    tester,
  ) async {
    Map<String, Object?>? postedJson;
    final client = MockClient((request) async {
      if (request.url.path == '/feedback-batches') {
        return http.Response('[]', 200);
      }
      if (request.url.path == '/feedback-workflow-presets') {
        return http.Response(
          jsonEncode(<String, Object?>{
            'default_preset_id': 'generator_reviewer',
            'presets': <Map<String, Object?>>[
              <String, Object?>{
                'id': 'generator_only',
                'name': 'Generator only',
              },
              <String, Object?>{
                'id': 'generator_reviewer',
                'name': 'Generator + Reviewer',
              },
            ],
          }),
          200,
        );
      }
      expect(request.method, 'POST');
      expect(
        request.url.toString(),
        'http://bridge.local/feedback-batches/start-session',
      );
      postedJson = jsonDecode(request.body) as Map<String, Object?>;
      return http.Response('{}', 202);
    });
    await tester.pumpWidget(
      _Harness(
        enabled: true,
        sourceApp: 'fixture-app-two',
        sourceDisplayName: 'Fixture App Two',
        bridgeUrl: 'http://bridge.local/',
        httpClient: client,
      ),
    );

    await _saveFeedback(tester, 'Enviar fixture');
    await tester.tap(find.byKey(developerFeedbackPendingKey));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(developerFeedbackSendBatchKey));
    await tester.pumpAndSettle();

    expect(postedJson, isNotNull);
    expect(postedJson!['kind'], 'codex.developerFeedbackBatch');
    expect(postedJson!['version'], 3);
    expect(postedJson!['batchId'], isA<String>());
    expect(postedJson!['sourceApp'], 'fixture-app-two');
    expect(postedJson!['sourceDisplayName'], 'Fixture App Two');
    expect(postedJson!['workflowPresetId'], 'generator_reviewer');
    expect(postedJson!['releaseWhenComplete'], isFalse);
    final items = postedJson!['items'] as List<Object?>;
    final item = items.single as Map<String, Object?>;
    expect(item['kind'], 'codex.developerFeedback');
    expect(item['version'], 3);
    expect(item['queue'], 'codexCli');
    expect(item['status'], 'pending');
    expect(item['sourceApp'], 'fixture-app-two');
    expect(item['sourceDisplayName'], 'Fixture App Two');
    expect(item['comment'], 'Enviar fixture');
    expect(item['screenshotPngBase64'], isA<String>());
    expect(item['selectionBounds'], isA<Map<String, Object?>>());
    expect(item['hasAudio'], isFalse);
  });

  testWidgets(
    'quick ask posts selection and displays answer without batch send',
    (tester) async {
      final requestedPaths = <String>[];
      Map<String, Object?>? postedJson;
      final client = MockClient((request) async {
        requestedPaths.add('${request.method} ${request.url.path}');
        if (request.url.path == '/feedback-batches') {
          return http.Response('[]', 200);
        }
        if (request.url.path == '/feedback-quick-asks/ask') {
          postedJson = jsonDecode(request.body) as Map<String, Object?>;
          return http.Response(
            jsonEncode(<String, Object?>{
              'quickAskId': 'quick-ask-1',
              'jobId': 'job-quick-ask',
              'sessionId': 'session-quick-ask',
              'status': 'pending',
              'agent_id': 'generator',
              'agent_type': 'generator',
            }),
            202,
          );
        }
        if (request.url.path == '/feedback-quick-asks/quick-ask-1') {
          return http.Response(
            jsonEncode(<String, Object?>{
              'quickAskId': 'quick-ask-1',
              'sourceApp': 'fixture-app',
              'question': 'Why disabled?',
              'status': 'completed',
              'answer': 'The button is likely waiting for a required field.',
              'screenshot_mime_type': 'image/png',
              'has_screenshot': true,
              'selection_points': <Object?>[],
              'selectionBounds': <String, double>{
                'left': 1,
                'top': 2,
                'width': 3,
                'height': 4,
              },
              'jobId': 'job-quick-ask',
              'sessionId': 'session-quick-ask',
              'createdAt': '2026-06-11T00:00:00+00:00',
            }),
            200,
          );
        }
        return http.Response('not found', 404);
      });

      await tester.pumpWidget(
        _Harness(
          enabled: true,
          bridgeUrl: 'http://bridge.local',
          contextMetadataBuilder: (_) => <String, Object?>{
            'screenName': 'order-detail',
            'orderId': 'order-123',
          },
          httpClient: client,
        ),
      );

      await tester.tap(find.byKey(developerFeedbackSwitchKey));
      await tester.pump();
      await _drawFeedbackSelection(tester);
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(developerFeedbackQuickAskActionKey));
      await tester.pumpAndSettle();
      await tester.enterText(
        find.byKey(developerFeedbackQuickAskQuestionKey),
        'Why disabled?',
      );
      await tester.tap(find.byKey(developerFeedbackQuickAskSubmitKey));
      await tester.pumpAndSettle();

      expect(
        find.text('The button is likely waiting for a required field.'),
        findsOneWidget,
      );
      expect(postedJson?['question'], 'Why disabled?');
      expect(postedJson?['screenshotPngBase64'], isA<String>());
      expect(postedJson?['selectionBounds'], isA<Map<String, Object?>>());
      expect(
        postedJson?['contextMetadata'],
        containsPair('screenName', 'order-detail'),
      );
      expect(requestedPaths, contains('POST /feedback-quick-asks/ask'));
      expect(requestedPaths, contains('GET /feedback-quick-asks/quick-ask-1'));
      expect(
        requestedPaths,
        isNot(contains('POST /feedback-batches/start-session')),
      );
      expect(find.byKey(developerFeedbackPendingKey), findsNothing);
    },
  );

  testWidgets('quick ask history shows provenance detail', (tester) async {
    const screenshot =
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=';
    final requestedQueries = <Map<String, String>>[];
    final requestedPaths = <String>[];
    Map<String, Object?>? postedBatch;
    final client = MockClient((request) async {
      requestedPaths.add('${request.method} ${request.url.path}');
      if (request.url.path == '/feedback-batches') {
        return http.Response('[]', 200);
      }
      if (request.url.path == '/feedback-workflow-presets') {
        return http.Response(
          jsonEncode(<String, Object?>{
            'default_preset_id': 'generator_only',
            'presets': <Map<String, Object?>>[
              <String, Object?>{
                'id': 'generator_only',
                'name': 'Generator only',
              },
            ],
          }),
          200,
        );
      }
      if (request.url.path == '/feedback-batches/start-session') {
        postedBatch = jsonDecode(request.body) as Map<String, Object?>;
        return http.Response(
          jsonEncode(<String, Object?>{
            'batchId': 'batch-from-quick-ask',
            'jobId': 'job-from-quick-ask',
            'sessionId': 'session-from-quick-ask',
            'status': 'running',
          }),
          202,
        );
      }
      if (request.url.path == '/feedback-quick-asks') {
        requestedQueries.add(request.url.queryParameters);
        return http.Response(
          jsonEncode(<Map<String, Object?>>[
            <String, Object?>{
              'quickAskId': 'quick-ask-history',
              'sourceApp': 'fixture-app',
              'question': 'Why is the title clipped?',
              'status': 'completed',
              'answer': 'Use the detail view for the full answer.',
              'screenshot_mime_type': 'image/png',
              'has_screenshot': true,
              'selection_points': <Object?>[],
              'selectionBounds': <String, double>{
                'left': 12,
                'top': 20,
                'width': 80,
                'height': 24,
              },
              'jobId': 'job-history',
              'sessionId': 'session-history',
              'createdAt': '2026-06-11T00:00:00+00:00',
            },
          ]),
          200,
        );
      }
      if (request.url.path == '/feedback-quick-asks/quick-ask-history') {
        return http.Response(
          jsonEncode(<String, Object?>{
            'quickAskId': 'quick-ask-history',
            'sourceApp': 'fixture-app',
            'question': 'Why is the title clipped?',
            'status': 'completed',
            'answer': 'The title is clipped because the parent is too narrow.',
            'screenshot_mime_type': 'image/png',
            'has_screenshot': true,
            'screenshotPngBase64': screenshot,
            'selection_points': <Object?>[],
            'selectionBounds': <String, double>{
              'left': 12,
              'top': 20,
              'width': 80,
              'height': 24,
            },
            'jobId': 'job-history',
            'sessionId': 'session-history',
            'createdAt': '2026-06-11T00:00:00+00:00',
          }),
          200,
        );
      }
      return http.Response('not found', 404);
    });

    await tester.pumpWidget(
      _Harness(
        enabled: true,
        sourceApp: 'fixture-app',
        bridgeUrl: 'http://bridge.local',
        httpClient: client,
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(developerFeedbackQuickAskHistoryKey));
    await tester.pumpAndSettle();
    expect(find.byKey(developerFeedbackQuickAskHistoryItemKey), findsOneWidget);
    expect(find.text('Why is the title clipped?'), findsOneWidget);

    await tester.tap(find.byKey(developerFeedbackQuickAskHistoryItemKey));
    await tester.pumpAndSettle();

    expect(find.byKey(developerFeedbackQuickAskPreviewKey), findsOneWidget);
    expect(find.byKey(developerFeedbackQuickAskBoundsKey), findsOneWidget);
    expect(
      find.text('The title is clipped because the parent is too narrow.'),
      findsOneWidget,
    );
    expect(requestedQueries.single['sourceApp'], 'fixture-app');
    expect(
      requestedPaths,
      isNot(contains('POST /feedback-batches/start-session')),
    );

    await tester.tap(find.byKey(developerFeedbackQuickAskActKey));
    await tester.pumpAndSettle();
    expect(find.text('Cola de feedback'), findsOneWidget);
    await tester.tap(find.byKey(developerFeedbackReleaseWhenCompleteKey));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(developerFeedbackSendBatchKey));
    await tester.pumpAndSettle();

    expect(postedBatch?['quickAskId'], 'quick-ask-history');
    expect(postedBatch?['releaseWhenComplete'], isTrue);
    final items = postedBatch?['items'] as List<Object?>;
    final item = items.single as Map<String, Object?>;
    expect(item['comment'], contains('Act from quick ask quick-ask-history.'));
    expect(item['comment'], contains('Question: Why is the title clipped?'));
    expect(
      item['comment'],
      contains('Prior quick ask answer: The title is clipped'),
    );
  });

  testWidgets('bridge batch status is visible and refreshable', (tester) async {
    final requestedPaths = <String>[];
    final client = MockClient((request) async {
      requestedPaths.add(request.url.path);
      if (request.url.path == '/feedback-workflow-presets') {
        return http.Response(
          jsonEncode(<String, Object?>{
            'default_preset_id': 'generator_only',
            'presets': <Map<String, Object?>>[
              <String, Object?>{
                'id': 'generator_only',
                'name': 'Generator only',
              },
            ],
          }),
          200,
        );
      }
      if (request.url.path == '/feedback-batches/start-session') {
        return http.Response(
          jsonEncode(<String, Object?>{
            'batchId': 'batch-123',
            'jobId': 'job-123',
            'sessionId': 'session-123',
            'status': 'running',
          }),
          202,
        );
      }
      if (request.url.path == '/feedback-batches/batch-123') {
        return http.Response(
          jsonEncode(<String, Object?>{
            'batchId': 'batch-123',
            'jobId': 'job-123',
            'sessionId': 'session-123',
            'status': 'completed',
            'workflowStatus': 'completed',
            'status_detail': 'Done',
            'workflowPresetId': 'generator_only',
            'releaseWhenComplete': false,
            'itemCount': 1,
            'item_ids': <String>['feedback-1'],
            'finalSummary': _summaryText(),
            'summary_line_count': 11,
            'created_at': '2026-06-11T00:00:00+00:00',
            'submitted_at': '2026-06-11T00:00:00+00:00',
          }),
          200,
        );
      }
      return http.Response('not found', 404);
    });

    await tester.pumpWidget(
      _Harness(
        enabled: true,
        bridgeUrl: 'http://bridge.local',
        httpClient: client,
      ),
    );

    await _saveFeedback(tester, 'Enviar y seguir');
    await tester.tap(find.byKey(developerFeedbackPendingKey));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(developerFeedbackSendBatchKey));
    await tester.pumpAndSettle();

    expect(find.byKey(developerFeedbackRunsKey), findsOneWidget);
    await tester.tap(find.byKey(developerFeedbackRunsKey));
    await tester.pumpAndSettle();
    expect(find.text('Batch batch-123'), findsOneWidget);
    expect(find.text('Estado: running'), findsOneWidget);

    await tester.tap(find.byKey(developerFeedbackRefreshRunKey));
    await tester.pumpAndSettle();
    expect(find.text('Estado: completed · Done'), findsOneWidget);
    await tester.tap(find.byKey(developerFeedbackSummaryOpenKey));
    await tester.pumpAndSettle();
    expect(find.byKey(developerFeedbackSummaryKey), findsOneWidget);
    expect(find.textContaining('1. Request'), findsOneWidget);
    expect(requestedPaths, contains('/feedback-batches/batch-123'));
  });

  testWidgets('history lists batches for the configured source app', (
    tester,
  ) async {
    Uri? historyUri;
    final client = MockClient((request) async {
      if (request.url.path == '/feedback-batches') {
        historyUri = request.url;
        return http.Response(
          jsonEncode(<Map<String, Object?>>[
            <String, Object?>{
              'batch_id': 'batch-history',
              'job_id': 'job-history',
              'session_id': 'session-history',
              'status': 'completed',
              'status_detail': 'Done',
              'workflow_preset_id': 'generator_only',
              'release_when_complete': false,
              'item_count': 2,
              'item_ids': <String>['one', 'two'],
              'summary': _summaryText(),
              'summary_line_count': 11,
              'created_at': '2026-06-11T00:00:00+00:00',
              'submitted_at': '2026-06-11T00:00:00+00:00',
            },
          ]),
          200,
        );
      }
      return http.Response('not found', 404);
    });

    await tester.pumpWidget(
      _Harness(
        enabled: true,
        sourceApp: 'history-app',
        bridgeUrl: 'http://bridge.local',
        httpClient: client,
      ),
    );

    expect(find.byKey(developerFeedbackHistoryKey), findsOneWidget);
    await tester.tap(find.byKey(developerFeedbackHistoryKey));
    await tester.pumpAndSettle();

    expect(historyUri?.queryParameters['sourceApp'], 'history-app');
    expect(find.byKey(developerFeedbackHistoryItemKey), findsOneWidget);
    expect(find.text('Batch batch-history'), findsOneWidget);
    expect(
      find.text(
        'Estado: completed · Done · job job-history · session session-history · resumen 11 líneas',
      ),
      findsOneWidget,
    );
    await tester.tap(find.byKey(developerFeedbackSummaryOpenKey));
    await tester.pumpAndSettle();
    expect(find.byKey(developerFeedbackSummaryKey), findsOneWidget);
    expect(find.textContaining('11. Validation'), findsOneWidget);
  });

  testWidgets('history shows empty state and supports refresh', (tester) async {
    var calls = 0;
    final client = MockClient((request) async {
      if (request.url.path == '/feedback-batches') {
        calls += 1;
        return http.Response('[]', 200);
      }
      return http.Response('not found', 404);
    });

    await tester.pumpWidget(
      _Harness(
        enabled: true,
        bridgeUrl: 'http://bridge.local',
        httpClient: client,
      ),
    );

    await tester.tap(find.byKey(developerFeedbackHistoryKey));
    await tester.pumpAndSettle();
    expect(find.text('No hay feedback enviado.'), findsOneWidget);

    await tester.tap(find.byKey(developerFeedbackHistoryRefreshKey));
    await tester.pumpAndSettle();
    expect(calls, 3);
    expect(find.text('No hay feedback enviado.'), findsOneWidget);
  });

  testWidgets('history shows unavailable state when bridge fails', (
    tester,
  ) async {
    final client = MockClient((request) async {
      return http.Response('unavailable', 503);
    });

    await tester.pumpWidget(
      _Harness(
        enabled: true,
        bridgeUrl: 'http://bridge.local',
        httpClient: client,
      ),
    );

    await tester.tap(find.byKey(developerFeedbackHistoryKey));
    await tester.pumpAndSettle();
    expect(find.text('No se pudo cargar el historial.'), findsOneWidget);
  });

  testWidgets('notification bell shows without badge at zero unread', (
    tester,
  ) async {
    final client = MockClient((request) async {
      if (request.url.path == '/feedback-batches') {
        return http.Response('[]', 200);
      }
      return http.Response('not found', 404);
    });

    await tester.pumpWidget(
      _Harness(
        enabled: true,
        bridgeUrl: 'http://bridge.local',
        httpClient: client,
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(developerFeedbackNotificationBellKey), findsOneWidget);
    expect(find.byIcon(Icons.notifications_none), findsOneWidget);
    expect(find.text('0'), findsNothing);
  });

  testWidgets('notification bell badge shows unread count', (tester) async {
    final client = MockClient((request) async {
      if (request.url.path == '/feedback-batches') {
        return http.Response(
          jsonEncode(<Map<String, Object?>>[
            _historyBatchJson('batch-1', unread: true),
            _historyBatchJson('batch-2', unread: true),
            _historyBatchJson('batch-3', unread: false),
          ]),
          200,
        );
      }
      return http.Response('not found', 404);
    });

    await tester.pumpWidget(
      _Harness(
        enabled: true,
        bridgeUrl: 'http://bridge.local',
        httpClient: client,
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(developerFeedbackNotificationBellKey), findsOneWidget);
    expect(find.text('2'), findsOneWidget);
  });

  testWidgets('notification bell remains inside compact viewport', (
    tester,
  ) async {
    _setViewport(tester, const Size(320, 480));
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final client = MockClient((request) async {
      if (request.url.path == '/feedback-batches') {
        return http.Response(
          jsonEncode(<Map<String, Object?>>[
            _historyBatchJson('batch-compact', unread: true),
          ]),
          200,
        );
      }
      return http.Response('not found', 404);
    });

    await tester.pumpWidget(
      _Harness(
        enabled: true,
        bridgeUrl: 'http://bridge.local',
        httpClient: client,
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(developerFeedbackNotificationBellKey), findsOneWidget);
    _expectToolbarInsideViewport(tester, const Size(320, 480));
  });

  testWidgets('notification center shows sections and marks read', (
    tester,
  ) async {
    final requestedPaths = <String>[];
    var markedRead = false;
    final client = MockClient((request) async {
      requestedPaths.add('${request.method} ${request.url.path}');
      if (request.url.path == '/feedback-batches') {
        return http.Response(
          jsonEncode(<Map<String, Object?>>[
            _historyBatchJson(
              'batch-complete',
              unread: !markedRead,
              summary: true,
            ),
            _historyBatchJson('batch-active', unread: false, status: 'running'),
            _historyBatchJson('batch-failed', unread: true, status: 'failed'),
          ]),
          200,
        );
      }
      if (request.url.path == '/feedback-batches/batch-complete/notification') {
        markedRead = true;
        return http.Response(
          jsonEncode(
            _historyBatchJson('batch-complete', unread: false, summary: true),
          ),
          200,
        );
      }
      return http.Response('not found', 404);
    });

    await tester.pumpWidget(
      _Harness(
        enabled: true,
        bridgeUrl: 'http://bridge.local',
        httpClient: client,
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('2'), findsOneWidget);

    await tester.tap(find.byKey(developerFeedbackNotificationBellKey));
    await tester.pumpAndSettle();
    expect(find.byKey(developerFeedbackNotificationCenterKey), findsOneWidget);
    expect(find.text('Terminados'), findsOneWidget);
    expect(find.text('Activos'), findsOneWidget);
    expect(find.text('Fallidos'), findsOneWidget);
    expect(find.text('Batch batch-complete'), findsOneWidget);

    await tester.tap(find.byKey(developerFeedbackSummaryOpenKey).first);
    await tester.pumpAndSettle();
    expect(find.byKey(developerFeedbackSummaryKey), findsOneWidget);
    await tester.tap(find.text('Cerrar').last);
    await tester.pumpAndSettle();

    await tester.tap(
      find.byKey(developerFeedbackNotificationMarkReadKey).first,
    );
    await tester.pumpAndSettle();
    expect(markedRead, isTrue);
    expect(
      requestedPaths,
      contains('PATCH /feedback-batches/batch-complete/notification'),
    );
  });

  testWidgets(
    'feedback dialog accepts text while template mode remains enabled',
    (tester) async {
      await tester.pumpWidget(const _Harness(enabled: true));
      await tester.tap(find.byKey(developerFeedbackSwitchKey));
      await tester.pump();
      expect(find.byKey(developerFeedbackOverlayKey), findsOneWidget);

      await _drawFeedbackSelection(tester);
      await tester.pumpAndSettle();
      expect(find.byKey(developerFeedbackCommentActionKey), findsOneWidget);
      expect(find.byKey(developerFeedbackOverlayKey), findsOneWidget);

      await tester.tap(find.byKey(developerFeedbackCommentActionKey));
      await tester.pumpAndSettle();
      expect(find.byKey(developerFeedbackOverlayKey), findsNothing);
      expect(find.text('Generator'), findsNothing);
      expect(find.text('Reviewer'), findsNothing);

      await tester.enterText(
        find.byKey(developerFeedbackCommentKey),
        'Escribir sin apagar plantilla',
      );
      await tester.pump();
      expect(find.text('Escribir sin apagar plantilla'), findsOneWidget);
      await tester.tap(find.byKey(developerFeedbackSaveKey));
      await tester.pumpAndSettle();

      expect(find.byKey(developerFeedbackOverlayKey), findsOneWidget);
      await tester.tap(find.byKey(developerFeedbackPendingKey));
      await tester.pumpAndSettle();
      expect(find.text('Escribir sin apagar plantilla'), findsOneWidget);
    },
  );

  testWidgets(
    'supported recorder stores audio MIME duration and bytes metadata',
    (tester) async {
      var copied = '';
      await tester.pumpWidget(
        _Harness(
          enabled: true,
          recorderFactory: () => _SupportedRecorder(),
          copyText: (text) async => copied = text,
        ),
      );

      await tester.tap(find.byKey(developerFeedbackSwitchKey));
      await tester.pump();
      await _drawFeedbackSelection(tester);
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(developerFeedbackCommentActionKey));
      await tester.pumpAndSettle();
      await tester.enterText(
        find.byKey(developerFeedbackCommentKey),
        'Con audio',
      );
      await tester.tap(find.byKey(const Key('developer-feedback-audio')));
      await tester.pump();
      await tester.tap(find.byKey(const Key('developer-feedback-audio')));
      await tester.pump();
      await tester.tap(find.byKey(developerFeedbackSaveKey));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(developerFeedbackPendingKey));
      await tester.pumpAndSettle();
      expect(find.text('Audio: 1234 ms, 3 bytes, audio/webm'), findsOneWidget);
      await tester.tap(find.byKey(developerFeedbackCopyKey));
      await tester.pumpAndSettle();

      final decoded = jsonDecode(copied) as Map<String, Object?>;
      final item =
          (decoded['items'] as List<Object?>).single as Map<String, Object?>;
      expect(item['hasAudio'], isTrue);
      expect(item['audioMimeType'], 'audio/webm');
      expect(item['audioDurationMs'], 1234);
      expect(item['audioByteLength'], 3);
      expect(item['audioBase64'], base64Encode(<int>[1, 2, 3]));
      expect(jsonEncode(item), isNot(contains('Uint8List')));
      expect(jsonEncode(item), isNot(contains('Instance of')));
    },
  );

  testWidgets('dialog cancel cleans up an active recording', (tester) async {
    final recorder = _TrackedRecorder();
    await tester.pumpWidget(
      _Harness(enabled: true, recorderFactory: () => recorder),
    );

    await _openFeedbackDialog(tester);
    await tester.tap(find.byKey(const Key('developer-feedback-audio')));
    await tester.pump();
    expect(recorder.starts, 1);

    await tester.tap(find.text('Cancelar'));
    await tester.pumpAndSettle();
    expect(recorder.cancels, 1);
    expect(recorder.isRecording, isFalse);
  });

  testWidgets('recorder start failure returns to comment-only save flow', (
    tester,
  ) async {
    final recorder = _FailingStartRecorder();
    await tester.pumpWidget(
      _Harness(enabled: true, recorderFactory: () => recorder),
    );

    await _openFeedbackDialog(tester);
    await tester.tap(find.byKey(const Key('developer-feedback-audio')));
    await tester.pump();
    expect(recorder.cancels, 1);
    expect(find.text('No se pudo grabar audio.'), findsOneWidget);

    await tester.enterText(
      find.byKey(developerFeedbackCommentKey),
      'Solo texto',
    );
    await tester.pump();
    await tester.tap(find.byKey(developerFeedbackSaveKey));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(developerFeedbackPendingKey));
    await tester.pumpAndSettle();
    expect(find.text('Solo texto'), findsOneWidget);
  });

  testWidgets('max recording duration auto-stops and save is stable', (
    tester,
  ) async {
    final recorder = _TrackedRecorder();
    await tester.pumpWidget(
      _Harness(enabled: true, recorderFactory: () => recorder),
    );

    await _openFeedbackDialog(tester);
    await tester.enterText(
      find.byKey(developerFeedbackCommentKey),
      'Con limite',
    );
    await tester.tap(find.byKey(const Key('developer-feedback-audio')));
    await tester.pump();
    expect(find.text('Detener audio (30 s máx.)'), findsOneWidget);
    expect(
      tester
          .widget<FilledButton>(find.byKey(developerFeedbackSaveKey))
          .onPressed,
      isNull,
    );

    await tester.pump(const Duration(seconds: 31));
    await tester.pumpAndSettle();
    expect(recorder.stops, 1);
    expect(find.text('Audio adjunto'), findsOneWidget);
    expect(
      tester
          .widget<FilledButton>(find.byKey(developerFeedbackSaveKey))
          .onPressed,
      isNotNull,
    );
  });

  testWidgets('double stop only calls recorder stop once', (tester) async {
    final recorder = _SlowStopRecorder();
    await tester.pumpWidget(
      _Harness(enabled: true, recorderFactory: () => recorder),
    );

    await _openFeedbackDialog(tester);
    await tester.tap(find.byKey(const Key('developer-feedback-audio')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('developer-feedback-audio')));
    await tester.pump();
    await tester.tap(
      find.byKey(const Key('developer-feedback-audio')),
      warnIfMissed: false,
    );
    await tester.pump();
    expect(recorder.stops, 1);

    recorder.completeStop();
    await tester.pumpAndSettle();
    expect(find.text('Audio adjunto'), findsOneWidget);
  });

  test('export JSON has stable fields and no raw object serialization', () {
    final item = DeveloperFeedbackItem(
      id: 'feedback-1',
      createdAt: DateTime.utc(2026, 6, 7),
      sourceApp: 'fixture-app',
      sourceDisplayName: 'Fixture App',
      comment: 'Mover CTA',
      screenshotPngBase64: 'png',
      selectionPoints: const <Offset>[Offset(1, 2), Offset(5, 8)],
      audio: DeveloperFeedbackAudioClip(
        bytes: Uint8List.fromList(<int>[4, 5, 6]),
        mimeType: 'audio/webm',
        durationMs: 250,
      ),
    );
    final decoded =
        jsonDecode(
              DeveloperFeedbackExport(
                items: <DeveloperFeedbackItem>[item],
              ).toJsonText(),
            )
            as Map<String, Object?>;
    final jsonText = jsonEncode(decoded);
    final exported =
        (decoded['items'] as List<Object?>).single as Map<String, Object?>;
    expect(
      exported.keys,
      containsAll(<String>[
        'kind',
        'version',
        'id',
        'sourceApp',
        'sourceDisplayName',
        'createdAt',
        'queue',
        'status',
        'comment',
        'screenshotMimeType',
        'screenshotPngBase64',
        'selectionPoints',
        'selectionBounds',
        'hasAudio',
        'audioMimeType',
        'audioDurationMs',
        'audioByteLength',
        'audioBase64',
      ]),
    );
    expect(exported['queue'], 'codexCli');
    expect(exported['sourceApp'], 'fixture-app');
    expect(exported['sourceDisplayName'], 'Fixture App');
    expect(exported['status'], 'pending');
    expect(exported['audioMimeType'], 'audio/webm');
    expect(exported['audioDurationMs'], 250);
    expect(exported['audioByteLength'], 3);
    expect(exported['audioBase64'], base64Encode(<int>[4, 5, 6]));
    expect(jsonText, isNot(contains('Offset(')));
    expect(jsonText, isNot(contains('Instance of')));
  });

  test('export omits audioBase64 when clip has no bytes', () {
    final item = DeveloperFeedbackItem(
      id: 'feedback-empty-audio',
      createdAt: DateTime.utc(2026, 6, 7),
      comment: 'Audio vacio',
      screenshotPngBase64: 'png',
      selectionPoints: const <Offset>[Offset(1, 2)],
      audio: DeveloperFeedbackAudioClip(
        bytes: Uint8List(0),
        mimeType: 'audio/webm',
        durationMs: 10,
      ),
    );

    final decoded = item.toJson();
    expect(decoded['hasAudio'], isFalse);
    expect(decoded['audioMimeType'], 'audio/webm');
    expect(decoded['audioDurationMs'], 10);
    expect(decoded['audioByteLength'], 0);
    expect(decoded.containsKey('audioBase64'), isFalse);
  });

  test('bridge JSON keeps generic feedback contract fields', () {
    final item = DeveloperFeedbackItem(
      id: 'feedback-bridge',
      createdAt: DateTime.utc(2026, 6, 7),
      sourceApp: 'fixture-app',
      sourceDisplayName: 'Fixture App',
      comment: 'Enviar a bridge',
      screenshotPngBase64: 'png',
      selectionPoints: const <Offset>[Offset(1, 2), Offset(5, 8)],
      audio: DeveloperFeedbackAudioClip(
        bytes: Uint8List.fromList(<int>[1, 2]),
        mimeType: 'audio/webm',
        durationMs: 300,
      ),
    );

    final bridgeJson = item.toBridgeJson();

    expect(bridgeJson['kind'], 'codex.developerFeedback');
    expect(bridgeJson['version'], 3);
    expect(bridgeJson['queue'], 'codexCli');
    expect(bridgeJson['status'], 'pending');
    expect(bridgeJson['sourceApp'], 'fixture-app');
    expect(bridgeJson['sourceDisplayName'], 'Fixture App');
    expect(bridgeJson['hasAudio'], isTrue);
    expect(bridgeJson['audioBase64'], base64Encode(<int>[1, 2]));
  });

  testWidgets('unsupported audio behavior is graceful', (tester) async {
    await tester.pumpWidget(const _Harness(enabled: true));
    await tester.tap(find.byKey(developerFeedbackSwitchKey));
    await tester.pump();
    await _drawFeedbackSelection(tester);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(developerFeedbackCommentActionKey));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('developer-feedback-audio')));
    await tester.pump();
    expect(find.text('Audio no soportado en este entorno.'), findsOneWidget);
    await tester.enterText(
      find.byKey(developerFeedbackCommentKey),
      'Sin audio',
    );
    await tester.pump();
    await tester.tap(find.byKey(developerFeedbackSaveKey));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(developerFeedbackPendingKey));
    await tester.pumpAndSettle();
    expect(find.text('Sin audio'), findsOneWidget);
  });
}

void _setViewport(WidgetTester tester, Size size) {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
}

Future<void> _dragToolbar(WidgetTester tester, Offset offset) async {
  final toolbar = find.byKey(developerFeedbackToolbarKey);
  final start = tester.getRect(toolbar).topLeft + const Offset(12, 12);
  await tester.dragFrom(start, offset);
  await tester.pumpAndSettle();
}

void _expectToolbarInsideViewport(WidgetTester tester, Size viewport) {
  const margin = 8.0;
  final rect = tester.getRect(find.byKey(developerFeedbackToolbarKey));
  expect(rect.left, greaterThanOrEqualTo(margin));
  expect(rect.top, greaterThanOrEqualTo(margin));
  expect(rect.right, lessThanOrEqualTo(viewport.width - margin));
  expect(rect.bottom, lessThanOrEqualTo(viewport.height - margin));
}

void _expectNoFlutterExceptions(WidgetTester tester) {
  final errors = <String>[];
  Object? error;
  while ((error = tester.takeException()) != null) {
    final current = error!;
    errors.add(
      current is FlutterError
          ? current.diagnostics.map((node) => node.toStringDeep()).join('\n')
          : current.toString(),
    );
  }
  expect(errors, isEmpty);
}

String _summaryText() {
  return List<String>.generate(
    11,
    (index) =>
        '${index + 1}. ${index == 0
            ? 'Request'
            : index == 10
            ? 'Validation'
            : 'Line'}',
  ).join('\n');
}

Map<String, Object?> _historyBatchJson(
  String batchId, {
  required bool unread,
  String status = 'completed',
  bool summary = false,
}) {
  return <String, Object?>{
    'batch_id': batchId,
    'job_id': 'job-$batchId',
    'session_id': 'session-$batchId',
    'status': status,
    'status_detail': 'Done',
    'workflow_preset_id': 'generator_only',
    'release_when_complete': false,
    'item_count': 1,
    'item_ids': <String>['item-$batchId'],
    'notification_unread': unread,
    if (summary) 'summary': _summaryText(),
    if (summary) 'summary_line_count': 11,
    'created_at': '2026-06-11T00:00:00+00:00',
    'submitted_at': '2026-06-11T00:00:00+00:00',
  };
}

Future<void> _saveFeedback(WidgetTester tester, String comment) async {
  if (find.byKey(developerFeedbackOverlayKey).evaluate().isEmpty) {
    await tester.tap(find.byKey(developerFeedbackSwitchKey));
    await tester.pump();
  }
  await _drawFeedbackSelection(tester);
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(developerFeedbackCommentActionKey));
  await tester.pumpAndSettle();
  await tester.enterText(find.byKey(developerFeedbackCommentKey), comment);
  await tester.pump();
  await tester.tap(find.byKey(developerFeedbackSaveKey));
  await tester.pumpAndSettle();
}

Future<void> _openFeedbackDialog(WidgetTester tester) async {
  if (find.byKey(developerFeedbackOverlayKey).evaluate().isEmpty) {
    await tester.tap(find.byKey(developerFeedbackSwitchKey));
    await tester.pump();
  }
  await _drawFeedbackSelection(tester);
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(developerFeedbackCommentActionKey));
  await tester.pumpAndSettle();
}

bool _feedbackSwitchValue(WidgetTester tester) =>
    tester.widget<Switch>(find.byKey(developerFeedbackSwitchKey)).value;

Future<void> _drawFeedbackSelection(
  WidgetTester tester, {
  bool shortStroke = false,
  bool straightStroke = false,
}) async {
  final overlay = find.byKey(developerFeedbackOverlayKey);
  final center = tester.getCenter(overlay);
  final gesture = await tester.startGesture(center + const Offset(-60, 0));
  final offsets = switch ((shortStroke, straightStroke)) {
    (true, _) => const <Offset>[Offset(8, 0), Offset(8, 0)],
    (_, true) => const <Offset>[
      Offset(45, 0),
      Offset(45, 0),
      Offset(45, 0),
      Offset(45, 0),
      Offset(45, 0),
    ],
    _ => const <Offset>[
      Offset(45, -45),
      Offset(65, 0),
      Offset(45, 45),
      Offset(0, 65),
      Offset(-45, 45),
      Offset(-65, 0),
      Offset(-45, -45),
      Offset(0, -65),
    ],
  };
  for (final offset in offsets) {
    await gesture.moveBy(offset);
    await tester.pump(const Duration(milliseconds: 16));
  }
  await gesture.up();
}

class _Harness extends StatelessWidget {
  const _Harness({
    required this.enabled,
    this.sourceApp = 'fixture-app',
    this.sourceDisplayName = 'Fixture App',
    this.bridgeUrl = '',
    this.child,
    this.recorderFactory,
    this.copyText,
    this.bridgeSubmitBatch,
    this.contextMetadataBuilder,
    this.httpClient,
  });

  final bool enabled;
  final String sourceApp;
  final String sourceDisplayName;
  final String bridgeUrl;
  final Widget? child;
  final DeveloperFeedbackRecorderFactory? recorderFactory;
  final DeveloperFeedbackCopyText? copyText;
  final DeveloperFeedbackBridgeSubmitBatch? bridgeSubmitBatch;
  final DeveloperFeedbackContextMetadataBuilder? contextMetadataBuilder;
  final http.Client? httpClient;

  @override
  Widget build(BuildContext context) {
    final navigatorKey = GlobalKey<NavigatorState>();
    final scaffoldMessengerKey = GlobalKey<ScaffoldMessengerState>();
    return MaterialApp(
      navigatorKey: navigatorKey,
      scaffoldMessengerKey: scaffoldMessengerKey,
      home: DeveloperFeedbackTemplate(
        enabled: enabled,
        sourceApp: sourceApp,
        sourceDisplayName: sourceDisplayName,
        bridgeUrl: bridgeUrl,
        navigatorKey: navigatorKey,
        scaffoldMessengerKey: scaffoldMessengerKey,
        recorderFactory:
            recorderFactory ?? (() => const _UnsupportedRecorder()),
        copyText: copyText,
        bridgeSubmitBatch: bridgeSubmitBatch,
        contextMetadataBuilder: contextMetadataBuilder,
        httpClient: httpClient,
        child: Scaffold(body: Center(child: child ?? const Text('App body'))),
      ),
    );
  }
}

class _UnsupportedRecorder implements DeveloperFeedbackAudioRecorder {
  const _UnsupportedRecorder();

  @override
  bool get isRecording => false;

  @override
  Future<bool> get isSupported async => false;

  @override
  Future<void> start() async {
    throw UnsupportedError('unsupported');
  }

  @override
  Future<DeveloperFeedbackAudioClip?> stop() async => null;

  @override
  Future<void> cancel() async {}
}

class _SupportedRecorder implements DeveloperFeedbackAudioRecorder {
  var _recording = false;

  @override
  bool get isRecording => _recording;

  @override
  Future<bool> get isSupported async => true;

  @override
  Future<void> start() async {
    _recording = true;
  }

  @override
  Future<DeveloperFeedbackAudioClip?> stop() async {
    _recording = false;
    return DeveloperFeedbackAudioClip(
      bytes: Uint8List.fromList(<int>[1, 2, 3]),
      mimeType: 'audio/webm',
      durationMs: 1234,
    );
  }

  @override
  Future<void> cancel() async {
    _recording = false;
  }
}

class _TrackedRecorder implements DeveloperFeedbackAudioRecorder {
  var starts = 0;
  var stops = 0;
  var cancels = 0;
  var _recording = false;

  @override
  bool get isRecording => _recording;

  @override
  Future<bool> get isSupported async => true;

  @override
  Future<void> start() async {
    starts += 1;
    _recording = true;
  }

  @override
  Future<DeveloperFeedbackAudioClip?> stop() async {
    stops += 1;
    _recording = false;
    return DeveloperFeedbackAudioClip(
      bytes: Uint8List.fromList(<int>[9]),
      mimeType: 'audio/webm',
      durationMs: 30000,
    );
  }

  @override
  Future<void> cancel() async {
    cancels += 1;
    _recording = false;
  }
}

class _FailingStartRecorder extends _TrackedRecorder {
  @override
  Future<void> start() async {
    starts += 1;
    throw StateError('microphone failed');
  }
}

class _SlowStopRecorder extends _TrackedRecorder {
  Completer<DeveloperFeedbackAudioClip?>? _stopCompleter;

  @override
  Future<DeveloperFeedbackAudioClip?> stop() {
    stops += 1;
    _stopCompleter = Completer<DeveloperFeedbackAudioClip?>();
    return _stopCompleter!.future;
  }

  void completeStop() {
    _recording = false;
    _stopCompleter?.complete(
      DeveloperFeedbackAudioClip(
        bytes: Uint8List.fromList(<int>[7]),
        mimeType: 'audio/webm',
        durationMs: 20,
      ),
    );
  }
}
