import 'dart:async';
import 'dart:convert';

import 'package:codex_app_updater/codex_app_updater.dart';
import 'package:codex_bridge_workbench/codex_bridge_workbench.dart';
import 'package:codex_mobile_frontend/main.dart';
import 'package:codex_mobile_frontend/src/models/agent_configuration.dart';
import 'package:codex_mobile_frontend/src/models/agent_profile.dart';
import 'package:codex_mobile_frontend/src/models/chat_message.dart';
import 'package:codex_mobile_frontend/src/models/chat_session_summary.dart';
import 'package:codex_mobile_frontend/src/models/codex_tooling.dart';
import 'package:codex_mobile_frontend/src/models/feedback_queue_item.dart';
import 'package:codex_mobile_frontend/src/models/job_status_response.dart';
import 'package:codex_mobile_frontend/src/models/session_detail.dart';
import 'package:codex_mobile_frontend/src/models/workspace.dart';
import 'package:codex_mobile_frontend/src/screens/chat_screen.dart';
import 'package:codex_mobile_frontend/src/services/api_client.dart';
import 'package:codex_mobile_frontend/src/services/audio_note_recorder.dart';
import 'package:codex_mobile_frontend/src/services/chat_notification_service.dart';
import 'package:codex_mobile_frontend/src/services/text_to_speech_player.dart';
import 'package:codex_mobile_frontend/src/state/chat_controller.dart';
import 'package:codex_mobile_frontend/src/utils/chat_timestamp_formatter.dart';
import 'package:codex_mobile_frontend/src/utils/chat_message_visibility.dart';
import 'package:codex_mobile_frontend/src/widgets/chat_bubble.dart';
import 'package:cross_file/cross_file.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  test('Codex app updater defaults on for Android only', () {
    expect(
      shouldEnableCodexAppUpdater(
        isWebOverride: false,
        platformOverride: TargetPlatform.android,
      ),
      isTrue,
    );
    expect(
      shouldEnableCodexAppUpdater(
        isWebOverride: false,
        platformOverride: TargetPlatform.iOS,
      ),
      isFalse,
    );
    expect(
      shouldEnableCodexAppUpdater(
        isWebOverride: true,
        platformOverride: TargetPlatform.android,
      ),
      isFalse,
    );
  });

  test('Codex app updater honors explicit Android enablement define', () {
    expect(
      shouldEnableCodexAppUpdater(
        configuredEnabled: true,
        isWebOverride: false,
        platformOverride: TargetPlatform.android,
      ),
      isTrue,
    );
    expect(
      shouldEnableCodexAppUpdater(
        configuredEnabled: false,
        isWebOverride: false,
        platformOverride: TargetPlatform.android,
      ),
      isFalse,
    );
  });

  test('Codex app updater stays off outside Android even when enabled', () {
    expect(
      shouldEnableCodexAppUpdater(
        configuredEnabled: true,
        isWebOverride: false,
        platformOverride: TargetPlatform.linux,
      ),
      isFalse,
    );
    expect(
      shouldEnableCodexAppUpdater(
        configuredEnabled: false,
        isWebOverride: false,
        platformOverride: TargetPlatform.linux,
      ),
      isFalse,
    );
    expect(
      shouldEnableCodexAppUpdater(
        configuredEnabled: true,
        isWebOverride: true,
        platformOverride: TargetPlatform.android,
      ),
      isFalse,
    );
  });

  test('Codex Bridge dev mode follows its single compile-time flag helper', () {
    expect(isCodexBridgeDevModeEnabled(), isFalse);
    expect(isCodexBridgeDevModeEnabled(configuredEnabled: false), isFalse);
    expect(isCodexBridgeDevModeEnabled(configuredEnabled: true), isTrue);
  });

  testWidgets('Codex Bridge dev wrapper returns child unchanged when disabled',
      (
    tester,
  ) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: CodexBridgeDevModeWrapper(
          enabled: false,
          bridgeUrl: 'http://bridge.test',
          child: Text('normal app'),
        ),
      ),
    );

    expect(find.text('normal app'), findsOneWidget);
    expect(_codexDevBannerFinder(), findsNothing);
  });

  testWidgets('Codex Bridge dev wrapper marks development mode when enabled', (
    tester,
  ) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: CodexBridgeDevModeWrapper(
          enabled: true,
          bridgeUrl: 'http://bridge.test',
          child: Text('normal app'),
        ),
      ),
    );

    expect(find.text('normal app'), findsOneWidget);
    expect(_codexDevBannerFinder(), findsOneWidget);
    expect(find.byTooltip('Open SDD Explorer'), findsOneWidget);
  });

  testWidgets('SDD Explorer shows loading state', (tester) async {
    final pending = Completer<SddProject?>();
    addTearDown(() {
      if (!pending.isCompleted) {
        pending.complete(null);
      }
    });
    await _pumpSddWrapper(
      tester,
      loader: (_) => pending.future,
    );

    await tester.tap(find.byTooltip('Open SDD Explorer'));
    await tester.pump();

    expect(find.text('Loading SDD Explorer'), findsOneWidget);
  });

  testWidgets('SDD Explorer shows error and retry state', (tester) async {
    var attempts = 0;
    await _pumpSddWrapper(
      tester,
      loader: (_) async {
        attempts += 1;
        if (attempts > 1) {
          return null;
        }
        throw Exception('backend unavailable');
      },
    );

    await tester.tap(find.byTooltip('Open SDD Explorer'));
    await tester.pumpAndSettle();

    expect(find.text('Could not load SDD Explorer'), findsOneWidget);
    expect(find.textContaining('backend unavailable'), findsOneWidget);
    await tester.tap(find.widgetWithText(OutlinedButton, 'Retry'));
    await tester.pumpAndSettle();
    expect(attempts, 2);
    expect(find.text('No SDD project found'), findsOneWidget);
  });

  testWidgets('SDD Explorer shows empty state', (tester) async {
    await _pumpSddWrapper(
      tester,
      loader: (_) async => null,
    );

    await tester.tap(find.byTooltip('Open SDD Explorer'));
    await tester.pumpAndSettle();

    expect(find.text('No SDD project found'), findsOneWidget);
    expect(find.textContaining('did not return a project'), findsOneWidget);
  });

  testWidgets('SDD Explorer renders a read-only project view', (tester) async {
    final requestedPaths = <String>[];
    final httpClient = MockClient((request) async {
      requestedPaths.add(request.url.path);
      if (request.url.path == '/sdd/projects') {
        return http.Response(jsonEncode(_sddProjectsIndexJson()), 200);
      }
      if (request.url.path == '/sdd/project') {
        return http.Response(jsonEncode(_sddProjectJson()), 200);
      }
      if (request.url.path == '/sdd/project/diagrams') {
        return http.Response(jsonEncode(_sddProjectDiagramsJson()), 200);
      }
      return http.Response('not found', 404);
    });
    await _pumpSddWrapper(
      tester,
      loader: (bridgeUrl) {
        return SddExplorerClient(
          baseUrl: bridgeUrl,
          client: httpClient,
        ).loadDefaultProject();
      },
      diagramRenderer: _FakeMermaidRenderer.success(),
    );

    await tester.tap(find.byTooltip('Open SDD Explorer'));
    await tester.pumpAndSettle();

    expect(requestedPaths, <String>[
      '/sdd/projects',
      '/sdd/project',
      '/sdd/project/diagrams',
    ]);

    expect(find.text('SDD Workbench'), findsOneWidget);
    expect(find.text('Codex Bridge'), findsWidgets);
    expect(find.text('Overview'), findsWidgets);
    expect(find.text('Specs'), findsWidgets);
    expect(find.text('Diagrams'), findsWidgets);
    expect(find.text('SDD files'), findsNothing);
    expect(find.text('Project identity'), findsOneWidget);
    expect(find.text('1/2'), findsOneWidget);

    await tester.tap(find.text('Specs').first);
    await tester.pumpAndSettle();
    expect(find.text('Bridge Contract'), findsWidgets);
    expect(find.textContaining('# Bridge Contract'), findsOneWidget);
    await tester.tap(find.text('Plan').first);
    await tester.pumpAndSettle();
    expect(find.textContaining('# Plan'), findsOneWidget);
    await tester.tap(find.text('Tasks').first);
    await tester.pumpAndSettle();
    expect(find.text('1/2 tasks complete'), findsOneWidget);
    await tester.tap(find.text('Slice One').first);
    await tester.pumpAndSettle();
    expect(find.textContaining('# Slice One'), findsOneWidget);

    await tester.tap(find.text('Diagrams').first);
    await tester.pumpAndSettle();
    expect(find.text('Architecture diagrams'), findsOneWidget);
    expect(find.text('flowchart diagram'), findsWidgets);
    expect(find.text('rendered architecture/components.mmd'), findsNothing);
    await tester.tap(find.text('flowchart diagram').first);
    await tester.pumpAndSettle();
    expect(
      find.text('rendered architecture/components.mmd'),
      findsOneWidget,
    );
  });

  testWidgets('SDD overview renders local SDD health only', (
    tester,
  ) async {
    await _pumpSddWrapper(
      tester,
      loader: (_) async => SddProject.fromJson(_sddProjectJson()),
      diagramRenderer: _FakeMermaidRenderer.success(),
    );

    await tester.tap(find.byTooltip('Open SDD Explorer'));
    await tester.pumpAndSettle();

    expect(find.text('Project identity'), findsOneWidget);
    expect(find.text('Codex Bridge'), findsWidgets);
    expect(find.text('Manifest'), findsOneWidget);
    expect(find.text('Constitution'), findsOneWidget);
    expect(find.text('Specs'), findsWidgets);
    expect(find.text('Diagrams'), findsWidgets);
    expect(find.text('1/2'), findsOneWidget);
    await tester.drag(find.byType(ListView).first, const Offset(0, -520));
    await tester.pumpAndSettle();
    expect(find.textContaining('No feedback queued'), findsOneWidget);
    expect(find.textContaining('No Codex action submitted'), findsOneWidget);
    expect(find.textContaining('Other Project'), findsNothing);
  });

  testWidgets('SDD overview navigates to Workbench sections', (
    tester,
  ) async {
    await _pumpSddWrapper(
      tester,
      loader: (_) async => SddProject.fromJson(_sddProjectJson()),
      diagramRenderer: _FakeMermaidRenderer.success(),
    );

    await tester.tap(find.byTooltip('Open SDD Explorer'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Diagrams').first);
    await tester.pumpAndSettle();

    expect(find.text('Architecture diagrams'), findsOneWidget);
    expect(find.text('flowchart diagram'), findsWidgets);
  });

  testWidgets('SDD overview launches recommended action composer', (
    tester,
  ) async {
    await _pumpSddWrapper(
      tester,
      loader: (_) async => SddProject.fromJson(_sddProjectJson()),
      diagramRenderer: _FakeMermaidRenderer.success(),
    );

    await tester.tap(find.byTooltip('Open SDD Explorer'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(
      find.widgetWithText(OutlinedButton, 'Refine first spec'),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(OutlinedButton, 'Refine first spec'));
    await tester.pumpAndSettle();

    expect(find.text('Refine spec.md'), findsOneWidget);
    expect(find.textContaining('Action kind: sdd.refine_spec'), findsOneWidget);
    expect(
      find.textContaining(
        'artifact_path: specs/001-codex-bridge-sdd-wrapper/spec.md',
      ),
      findsOneWidget,
    );
  });

  testWidgets('SDD Workbench shows missing artifact status in overview', (
    tester,
  ) async {
    await _pumpSddWrapper(
      tester,
      loader: (_) async => SddProject.fromJson(_sddProjectWithMissingJson()),
    );

    await tester.tap(find.byTooltip('Open SDD Explorer'));
    await tester.pumpAndSettle();
    await tester.drag(find.byType(ListView).first, const Offset(0, -520));
    await tester.pumpAndSettle();

    expect(find.text('Missing required artifacts'), findsOneWidget);
    expect(find.text('- codex-bridge.yaml'), findsOneWidget);
    expect(find.text('Missing'), findsWidgets);
  });

  testWidgets('SDD Workbench switches spec file panes', (tester) async {
    await _pumpSddWrapper(
      tester,
      loader: (_) async => SddProject.fromJson(_sddProjectJson()),
      diagramRenderer: _FakeMermaidRenderer.success(),
    );

    await tester.tap(find.byTooltip('Open SDD Explorer'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Specs').first);
    await tester.pumpAndSettle();

    expect(find.textContaining('# Bridge Contract'), findsOneWidget);
    await tester.tap(find.text('Plan').first);
    await tester.pumpAndSettle();
    expect(find.textContaining('# Plan'), findsOneWidget);
    await tester.tap(find.text('Tasks').first);
    await tester.pumpAndSettle();
    expect(find.textContaining('# Tasks'), findsOneWidget);
    expect(find.text('1/2 tasks complete'), findsOneWidget);
    await tester.tap(find.text('Slice One').first);
    await tester.pumpAndSettle();
    expect(find.textContaining('# Slice One'), findsOneWidget);
  });

  testWidgets('SDD Explorer shows diagram list before opening preview', (
    tester,
  ) async {
    await _pumpSddWrapper(
      tester,
      loader: (_) async => SddProject.fromJson(_sddProjectJson()),
      diagramRenderer: _FakeMermaidRenderer.success(),
    );

    await tester.tap(find.byTooltip('Open SDD Explorer'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Diagrams').first);
    await tester.pumpAndSettle();

    expect(find.text('Architecture diagrams'), findsOneWidget);
    expect(find.text('flowchart diagram'), findsWidgets);
    expect(find.text('rendered architecture/components.mmd'), findsNothing);
    await tester.tap(find.text('flowchart diagram').first);
    await tester.pumpAndSettle();
    expect(
      find.text('rendered architecture/components.mmd'),
      findsOneWidget,
    );
  });

  testWidgets('SDD Explorer toggles a diagram between preview and source', (
    tester,
  ) async {
    await _pumpSddWrapper(
      tester,
      loader: (_) async => SddProject.fromJson(_sddProjectJson()),
      diagramRenderer: _FakeMermaidRenderer.success(),
    );

    await tester.tap(find.byTooltip('Open SDD Explorer'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Diagrams').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('flowchart diagram').first);
    await tester.pumpAndSettle();

    expect(
      find.text('rendered architecture/components.mmd'),
      findsOneWidget,
    );
    expect(find.textContaining('flowchart LR'), findsNothing);

    await tester.tap(find.text('Source').first);
    await tester.pumpAndSettle();

    expect(find.textContaining('flowchart LR'), findsOneWidget);

    await tester.tap(find.text('Preview').first);
    await tester.pumpAndSettle();

    expect(
      find.text('rendered architecture/components.mmd'),
      findsOneWidget,
    );
  });

  testWidgets('SDD Explorer shows empty diagram groups', (tester) async {
    await _pumpSddWrapper(
      tester,
      loader: (_) async =>
          SddProject.fromJson(_sddProjectWithoutDiagramsJson()),
    );

    await tester.tap(find.byTooltip('Open SDD Explorer'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Diagrams').first);
    await tester.pumpAndSettle();

    expect(find.text('Diagrams'), findsWidgets);
    expect(find.text('No diagrams found'), findsWidgets);
  });

  testWidgets('SDD Explorer keeps source available when preview fails', (
    tester,
  ) async {
    final renderer = _FakeMermaidRenderer.failure('invalid Mermaid syntax');
    await _pumpSddWrapper(
      tester,
      loader: (_) async => SddProject.fromJson(_sddProjectJson()),
      diagramRenderer: renderer,
    );

    await tester.tap(find.byTooltip('Open SDD Explorer'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Diagrams').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('flowchart diagram').first);
    await tester.pumpAndSettle();

    expect(find.text('Diagram preview failed'), findsOneWidget);
    expect(find.text('invalid Mermaid syntax'), findsOneWidget);
    expect(find.textContaining('flowchart LR'), findsOneWidget);

    final callsBeforeRetry = renderer.calls;
    final retry = find.widgetWithText(TextButton, 'Retry');
    tester.widget<TextButton>(retry).onPressed!();
    await tester.pumpAndSettle();

    expect(renderer.calls, greaterThan(callsBeforeRetry));
  });

  testWidgets('SDD Workbench queues feedback from a spec artifact', (
    tester,
  ) async {
    final drafts = <SddFeedbackDraft>[];
    await _pumpSddWrapper(
      tester,
      loader: (_) async => SddProject.fromJson(_sddProjectJson()),
      diagramRenderer: _FakeMermaidRenderer.success(),
      feedbackSubmitter: (_, draft) async {
        drafts.add(draft);
        return const SddFeedbackSubmissionResult(
          id: 'sdd-feedback-1',
        );
      },
    );

    await tester.tap(find.byTooltip('Open SDD Explorer'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Specs').first);
    await tester.pumpAndSettle();
    await tester.ensureVisible(
      find.byTooltip(
        'Add SDD feedback for specs/001-codex-bridge-sdd-wrapper/spec.md',
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(
      find.byTooltip(
        'Add SDD feedback for specs/001-codex-bridge-sdd-wrapper/spec.md',
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('SDD feedback'), findsOneWidget);
    expect(find.textContaining('# Bridge Contract'), findsWidgets);
    await tester.enterText(
      find.byType(TextField).last,
      'Clarify acceptance criteria in this spec.',
    );
    await tester.tap(find.widgetWithText(FilledButton, 'Submit feedback'));
    await tester.pumpAndSettle();

    expect(find.text('Feedback queued'), findsOneWidget);
    expect(drafts, hasLength(1));
    final draft = drafts.single;
    expect(draft.comment, 'Clarify acceptance criteria in this spec.');
    expect(draft.target.artifactType, 'spec');
    expect(
      draft.target.artifactPath,
      'specs/001-codex-bridge-sdd-wrapper/spec.md',
    );
    expect(draft.target.specId, '001-codex-bridge-sdd-wrapper');
    expect(
      draft.target.toContextMetadata()['sdd'],
      isA<Map<String, Object?>>()
          .having(
            (value) => value['sourceExcerpt'],
            'source excerpt',
            contains('# Bridge Contract'),
          )
          .having(
            (value) => value['artifactType'],
            'artifact type',
            'spec',
          ),
    );
  });

  testWidgets('SDD Workbench cancels artifact feedback without submitting', (
    tester,
  ) async {
    final drafts = <SddFeedbackDraft>[];
    await _pumpSddWrapper(
      tester,
      loader: (_) async => SddProject.fromJson(_sddProjectJson()),
      diagramRenderer: _FakeMermaidRenderer.success(),
      feedbackSubmitter: (_, draft) async {
        drafts.add(draft);
        return const SddFeedbackSubmissionResult(
          id: 'sdd-feedback-cancel',
        );
      },
    );

    await tester.tap(find.byTooltip('Open SDD Explorer'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Specs').first);
    await tester.pumpAndSettle();
    await tester.ensureVisible(
      find.byTooltip(
        'Add SDD feedback for specs/001-codex-bridge-sdd-wrapper/spec.md',
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(
      find.byTooltip(
        'Add SDD feedback for specs/001-codex-bridge-sdd-wrapper/spec.md',
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('SDD feedback'), findsOneWidget);
    await tester.tap(find.widgetWithText(TextButton, 'Cancel'));
    await tester.pumpAndSettle();

    expect(find.text('SDD feedback'), findsNothing);
    expect(drafts, isEmpty);
  });

  testWidgets('SDD Workbench shows feedback submit errors', (tester) async {
    await _pumpSddWrapper(
      tester,
      loader: (_) async => SddProject.fromJson(_sddProjectJson()),
      diagramRenderer: _FakeMermaidRenderer.success(),
      feedbackSubmitter: (_, __) async {
        throw Exception('queue unavailable');
      },
    );

    await tester.tap(find.byTooltip('Open SDD Explorer'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Specs').first);
    await tester.pumpAndSettle();
    await tester.ensureVisible(
      find.byTooltip(
        'Add SDD feedback for specs/001-codex-bridge-sdd-wrapper/spec.md',
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(
      find.byTooltip(
        'Add SDD feedback for specs/001-codex-bridge-sdd-wrapper/spec.md',
      ),
    );
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, 'This should fail.');
    await tester.tap(find.widgetWithText(FilledButton, 'Submit feedback'));
    await tester.pumpAndSettle();

    expect(find.textContaining('queue unavailable'), findsOneWidget);
    expect(find.text('Feedback queued'), findsNothing);
  });

  testWidgets('SDD Workbench links feedback metadata to a diagram', (
    tester,
  ) async {
    final drafts = <SddFeedbackDraft>[];
    await _pumpSddWrapper(
      tester,
      loader: (_) async => SddProject.fromJson(_sddProjectJson()),
      diagramRenderer: _FakeMermaidRenderer.success(),
      feedbackSubmitter: (_, draft) async {
        drafts.add(draft);
        return const SddFeedbackSubmissionResult(
          id: 'sdd-feedback-diagram',
        );
      },
    );

    await tester.tap(find.byTooltip('Open SDD Explorer'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Diagrams').first);
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Add diagram feedback').first);
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byType(TextField).last,
      'Component boundary should be clearer.',
    );
    await tester.tap(find.widgetWithText(FilledButton, 'Submit feedback'));
    await tester.pumpAndSettle();

    expect(drafts, hasLength(1));
    final target = drafts.single.target;
    expect(target.feedbackKind, 'sdd.diagram');
    expect(target.artifactPath, 'architecture/components.mmd');
    expect(target.diagramType, 'flowchart');
    expect(target.diagramScope, 'architecture');
    expect(
      target.toContextMetadata()['sdd'],
      isA<Map<String, Object?>>()
          .having(
            (value) => value['sourceExcerpt'],
            'source excerpt',
            contains('flowchart LR'),
          )
          .having(
            (value) => value['diagramScope'],
            'diagram scope',
            'architecture',
          ),
    );
  });

  test('api client creates feedback queue items with SDD metadata', () async {
    late Map<String, dynamic> requestPayload;
    final apiClient = ApiClient(
      baseUrl: 'http://bridge.test',
      client: MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/feedback-queue');
        requestPayload = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(
          jsonEncode(<String, dynamic>{
            'id': 'feedback-sdd',
            'source_app': requestPayload['sourceApp'],
            'source_display_name': requestPayload['sourceDisplayName'],
            'comment': requestPayload['comment'],
            'created_at': '2026-07-04T12:00:00Z',
            'status': 'pending',
            'has_screenshot': false,
            'selection_points': <Map<String, dynamic>>[],
            'selection_bounds': requestPayload['selectionBounds'],
            'feedback_kind': requestPayload['feedbackKind'],
            'context_metadata': requestPayload['contextMetadata'],
          }),
          200,
        );
      }),
    );

    final item = await apiClient.createFeedbackQueueItem(
      sourceApp: 'codex-mobile',
      sourceDisplayName: 'Codex Mobile',
      comment: 'Clarify this diagram.',
      feedbackKind: 'sdd.diagram',
      contextMetadata: const <String, Object?>{
        'sdd': <String, Object?>{
          'workspacePath': '/workspace/codex-cli-mobile-bridge',
          'artifactPath': 'architecture/components.mmd',
          'diagramType': 'flowchart',
        },
      },
      selectionBounds: const <String, double>{
        'left': 0,
        'top': 0,
        'width': 1,
        'height': 1,
      },
    );

    expect(requestPayload['sourceApp'], 'codex-mobile');
    expect(requestPayload['feedbackKind'], 'sdd.diagram');
    expect(requestPayload['contextMetadata'], isA<Map<String, dynamic>>());
    expect(requestPayload['selectionBounds'], <String, dynamic>{
      'left': 0,
      'top': 0,
      'width': 1,
      'height': 1,
    });
    expect(item.feedbackKind, 'sdd.diagram');
    expect(item.contextMetadata['sdd'], isA<Map>());
  });

  test('SDD Codex action prompt includes action and linked context', () {
    final prompt = buildSddCodexActionPrompt(
      const SddCodexActionRequest(
        kind: SddCodexActionKind.addressFeedback,
        target: SddFeedbackTarget(
          workspacePath: '/workspace/codex-cli-mobile-bridge',
          artifactType: 'diagram',
          artifactPath: 'architecture/components.mmd',
          artifactTitle: 'Component diagram',
          sourceExcerpt: 'flowchart LR\nA --> B',
          specId: '002-sdd-visual-workbench',
          specTitle: 'Visual Workbench',
          diagramType: 'flowchart',
          diagramScope: 'architecture',
        ),
        linkedFeedbackIds: <String>['feedback-sdd-1'],
      ),
    );

    expect(prompt, contains('Action kind: sdd.address_feedback'));
    expect(
        prompt, contains('workspace_path: /workspace/codex-cli-mobile-bridge'));
    expect(prompt, contains('artifact_path: architecture/components.mmd'));
    expect(prompt, contains('diagram_type: flowchart'));
    expect(prompt, contains('  - feedback-sdd-1'));
    expect(prompt, contains('flowchart LR'));
    expect(
        prompt, contains('Validate any path before reading or editing files.'));
  });

  testWidgets('SDD Workbench shows Codex action menu for a spec artifact', (
    tester,
  ) async {
    await _pumpSddWrapper(
      tester,
      loader: (_) async => SddProject.fromJson(_sddProjectJson()),
      diagramRenderer: _FakeMermaidRenderer.success(),
    );

    await tester.tap(find.byTooltip('Open SDD Explorer'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Specs').first);
    await tester.pumpAndSettle();
    await tester.ensureVisible(
      find.byTooltip(
        'Open Codex actions for specs/001-codex-bridge-sdd-wrapper/spec.md',
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.byTooltip(
        'Open Codex actions for specs/001-codex-bridge-sdd-wrapper/spec.md',
      ),
      findsOneWidget,
    );
    await tester.tap(
      find.byTooltip(
        'Open Codex actions for specs/001-codex-bridge-sdd-wrapper/spec.md',
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Refine spec.md'), findsOneWidget);
  });

  testWidgets('SDD Codex action composer submits an editable prompt', (
    tester,
  ) async {
    final drafts = <SddCodexActionDraft>[];
    await _pumpSddWrapper(
      tester,
      loader: (_) async => SddProject.fromJson(_sddProjectJson()),
      diagramRenderer: _FakeMermaidRenderer.success(),
      actionSubmitter: (_, draft) async {
        drafts.add(draft);
        return _jobResponse(
          jobId: 'job-sdd-action',
          sessionId: 'session-sdd-action',
        );
      },
    );

    await tester.tap(find.byTooltip('Open SDD Explorer'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Specs').first);
    await tester.pumpAndSettle();
    await tester.ensureVisible(
      find.byTooltip(
        'Open Codex actions for specs/001-codex-bridge-sdd-wrapper/spec.md',
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(
      find.byTooltip(
        'Open Codex actions for specs/001-codex-bridge-sdd-wrapper/spec.md',
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Refine spec.md'));
    await tester.pumpAndSettle();

    expect(find.text('Refine spec.md'), findsOneWidget);
    expect(find.textContaining('Action kind: sdd.refine_spec'), findsOneWidget);
    await tester.enterText(
      find.byType(TextField).last,
      'Custom prompt for refining the spec.',
    );
    await tester.tap(find.widgetWithText(FilledButton, 'Submit to Codex'));
    await tester.pumpAndSettle();

    expect(drafts, hasLength(1));
    expect(drafts.single.prompt, 'Custom prompt for refining the spec.');
    expect(drafts.single.request.kind, SddCodexActionKind.refineSpec);
    expect(
      drafts.single.request.target.artifactPath,
      'specs/001-codex-bridge-sdd-wrapper/spec.md',
    );
    expect(
      find.textContaining('session session-sdd-action'),
      findsOneWidget,
    );
  });

  testWidgets('SDD Codex action composer shows submit failure', (tester) async {
    await _pumpSddWrapper(
      tester,
      loader: (_) async => SddProject.fromJson(_sddProjectJson()),
      diagramRenderer: _FakeMermaidRenderer.success(),
      actionSubmitter: (_, __) async {
        throw Exception('Codex rejected action');
      },
    );

    await tester.tap(find.byTooltip('Open SDD Explorer'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Diagrams').first);
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Open diagram Codex actions').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Update .mmd'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Submit to Codex'));
    await tester.pumpAndSettle();

    expect(find.textContaining('Codex rejected action'), findsOneWidget);
    expect(find.textContaining('Codex action submitted'), findsNothing);
  });

  testWidgets('SDD feedback can open a linked Codex action', (tester) async {
    final actionDrafts = <SddCodexActionDraft>[];
    await _pumpSddWrapper(
      tester,
      loader: (_) async => SddProject.fromJson(_sddProjectJson()),
      diagramRenderer: _FakeMermaidRenderer.success(),
      feedbackSubmitter: (_, draft) async {
        return const SddFeedbackSubmissionResult(
          id: 'feedback-linked-1',
        );
      },
      actionSubmitter: (_, draft) async {
        actionDrafts.add(draft);
        return _jobResponse(jobId: 'job-linked', sessionId: 'session-linked');
      },
    );

    await tester.tap(find.byTooltip('Open SDD Explorer'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Diagrams').first);
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Add diagram feedback').first);
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, 'Fix this diagram.');
    await tester.tap(find.widgetWithText(FilledButton, 'Submit feedback'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(
      find.widgetWithText(OutlinedButton, 'Ask Codex to address feedback'),
    );
    await tester.pumpAndSettle();
    await tester.tap(
      find.widgetWithText(OutlinedButton, 'Ask Codex to address feedback'),
    );
    await tester.pumpAndSettle();

    expect(find.text('Address feedback'), findsOneWidget);
    expect(find.textContaining('feedback-linked-1'), findsWidgets);
    await tester.tap(find.widgetWithText(FilledButton, 'Submit to Codex'));
    await tester.pumpAndSettle();

    expect(actionDrafts, hasLength(1));
    expect(
        actionDrafts.single.request.kind, SddCodexActionKind.addressFeedback);
    expect(actionDrafts.single.request.linkedFeedbackIds, <String>[
      'feedback-linked-1',
    ]);
    expect(actionDrafts.single.prompt, contains('linked_feedback_ids'));
  });

  testWidgets('SDD overview opens an audit Codex action', (tester) async {
    final drafts = <SddCodexActionDraft>[];
    await _pumpSddWrapper(
      tester,
      loader: (_) async => SddProject.fromJson(_sddProjectWithMissingJson()),
      actionSubmitter: (_, draft) async {
        drafts.add(draft);
        return _jobResponse(jobId: 'job-audit', sessionId: 'session-audit');
      },
    );

    await tester.tap(find.byTooltip('Open SDD Explorer'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(OutlinedButton, 'Audit SDD').first);
    await tester.pumpAndSettle();

    expect(find.text('Audit SDD'), findsWidgets);
    expect(find.textContaining('Action kind: sdd.audit'), findsOneWidget);
    expect(find.textContaining('missing: codex-bridge.yaml'), findsOneWidget);
    await tester.tap(find.widgetWithText(FilledButton, 'Submit to Codex'));
    await tester.pumpAndSettle();

    expect(drafts, hasLength(1));
    expect(drafts.single.request.kind, SddCodexActionKind.auditSdd);
    expect(drafts.single.request.target.artifactType, 'overview');
  });

  testWidgets('production Mermaid renderer uses a local engine asset', (
    tester,
  ) async {
    final result = await WebViewMermaidDiagramRenderer(
      assetBundle: _FakeMermaidAssetBundle(
        '''
window.mermaid = {
  initialize: function() {},
  render: async function() { return { svg: '<svg></svg>' }; }
};
''',
      ),
    ).render(
      const SddDiagram(
        path: 'architecture/components.mmd',
        sizeBytes: 22,
        diagramType: 'flowchart',
        scope: 'architecture',
        content: 'flowchart LR\nA --> B',
      ),
    );

    expect(result.isSuccess, isTrue);
    expect(result.preview, isA<MermaidWebViewPreview>());
  });

  test('Mermaid preview HTML base64-encodes suspicious diagram source', () {
    const maliciousSource = '''
flowchart LR
  A["</script><script>window.pwned = true</script>"]
  B["<img src=x onerror=alert(1)>"]
  C["quotes ' \\" ` and unicode ñ"]
  A --> B
  click B "https://example.com" "external"
''';

    final html = buildMermaidPreviewHtml(
      mermaidJs: 'window.mermaid = {};',
      source: maliciousSource,
    );

    expect(html, contains(base64Encode(utf8.encode(maliciousSource))));
    expect(html, isNot(contains(maliciousSource)));
    expect(html, isNot(contains('</script><script>window.pwned')));
    expect(html, isNot(contains('<img src=x onerror=alert(1)>')));
    expect(html, isNot(contains('https://example.com')));
  });

  test('Mermaid preview HTML keeps strict security and timeout guards', () {
    final html = buildMermaidPreviewHtml(
      mermaidJs: 'window.mermaid = {};',
      source: 'flowchart LR\nA --> B',
      renderTimeout: const Duration(milliseconds: 1234),
    );

    expect(html, contains("securityLevel: 'strict'"));
    expect(html, contains('htmlLabels: false'));
    expect(html, contains("connect-src 'none'"));
    expect(html, contains("frame-src 'none'"));
    expect(html, contains('setTimeout'));
    expect(html, contains('Mermaid render timed out after 1234 ms.'));
    expect(html, contains('TextDecoder'));
  });

  testWidgets('renders Codex Remote shell', (tester) async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    await tester.pumpWidget(
      const CodexMobileApp(initialApiBaseUrl: 'http://localhost:8000'),
    );

    expect(find.text('Codex Remote'), findsOneWidget);
    expect(find.textContaining('local machine'), findsOneWidget);
    expect(find.byIcon(Icons.mic_rounded), findsOneWidget);
    expect(find.byIcon(Icons.upload_file_outlined), findsNothing);
    expect(find.byIcon(Icons.download_for_offline_outlined), findsNothing);
  });

  testWidgets('uses Bridge-controlled updater for Codex Mobile APKs', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final requestedUris = <Uri>[];
    final controller = CodexAppUpdaterController(
      httpClient: MockClient((request) async {
        requestedUris.add(request.url);
        return http.Response(
          jsonEncode({
            'kind': 'codex.appUpdate',
            'version': 1,
            'sourceApp': 'codex-mobile',
            'displayName': 'Codex Mobile',
            'platform': 'android',
            'currentVersion': '1.2.3',
            'currentBuild': 33,
            'latestVersion': '1.2.4',
            'latestBuild': 34,
            'releaseTag': 'android-v1.2.4-build.34',
            'apkUrl':
                'http://bridge.test/app-updates/codex-mobile/apk/android-v1.2.4-build.34/codex-mobile.apk',
            'apkAssetName': 'codex-mobile.apk',
            'sha256': null,
            'sizeBytes': 123,
            'releaseNotes': 'Nueva APK disponible.',
            'required': false,
            'available': true,
          }),
          200,
        );
      }),
    );
    addTearDown(controller.dispose);

    await tester.pumpWidget(
      CodexMobileApp(
        initialApiBaseUrl: 'http://bridge.test',
        currentVersion: '1.2.3',
        currentBuild: 33,
        appUpdaterEnabled: true,
        appUpdaterController: controller,
      ),
    );
    await tester.pump();

    expect(requestedUris, hasLength(1));
    final uri = requestedUris.single;
    expect(uri.path, '/app-updates/codex-mobile');
    expect(uri.queryParameters['platform'], 'android');
    expect(uri.queryParameters['currentVersion'], '1.2.3');
    expect(uri.queryParameters['currentBuild'], '33');
    expect(uri.queryParameters['channel'], 'stable');
    expect(controller.updateInfo?.apkUrl, startsWith('http://bridge.test/'));
    expect(
        controller.updateInfo?.apkUrl, contains('/app-updates/codex-mobile/'));
    expect(controller.updateInfo?.apkUrl, isNot(contains('github.com')));
    expect(find.byKey(codexAppUpdaterBannerKey), findsOneWidget);
    expect(find.byKey(codexAppUpdaterUpdateButtonKey), findsOneWidget);
  });

  testWidgets('collapses secondary app bar actions on narrow screens', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    tester.view.physicalSize = const Size(320, 780);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      const CodexMobileApp(initialApiBaseUrl: 'http://localhost:8000'),
    );
    await tester.pump();

    expect(find.byIcon(Icons.hub_outlined), findsOneWidget);
    expect(find.byIcon(Icons.more_vert), findsOneWidget);
    expect(find.byIcon(Icons.computer), findsNothing);
    expect(find.byIcon(Icons.add), findsNothing);
    expect(find.byIcon(Icons.upload_file_outlined), findsNothing);
    expect(find.byIcon(Icons.download_for_offline_outlined), findsNothing);
  });

  testWidgets('surfaces pending feedback count in the matching project drawer',
      (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final items = <FeedbackQueueItem>[
      _feedbackItem(
        id: 'feedback-name',
        sourceApp: 'ambientando-calendar',
        sourceDisplayName: 'Ambientando Calendar',
        comment: 'Matches by normalized project name',
      ),
      _feedbackItem(
        id: 'feedback-path',
        sourceApp: 'Ambientando Calendar',
        comment: 'Matches by normalized path/name variant',
      ),
      _feedbackItem(
        id: 'feedback-unrelated',
        sourceApp: 'otra-app',
        comment: 'No debe aparecer en Ambientando',
      ),
      _feedbackItem(
        id: 'feedback-unknown',
        sourceApp: '',
        comment: 'No debe matchear sin source app',
      ),
    ];

    await tester.pumpWidget(
      MaterialApp(
        home: ChatScreen(
          initialApiBaseUrl: 'http://localhost:8000',
          notificationService: const NoopChatNotificationService(),
          enableServerBootstrap: false,
          initialSidebarWorkspaces: const <Workspace>[
            Workspace(
              name: 'Ambientando Calendar',
              path: '/workspace/ambientando-calendar',
            ),
            Workspace(
              name: 'Other Project',
              path: '/workspace/other-project',
            ),
          ],
          feedbackQueueListLoaderOverride: (_, {required includeImages}) async {
            return items;
          },
        ),
      ),
    );
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump();

    expect(find.textContaining('feedback pending'), findsNothing);
    expect(find.byIcon(Icons.feedback_outlined), findsNothing);

    await tester.tap(find.byTooltip('Projects'));
    await tester.pumpAndSettle();

    expect(find.text('2 feedback'), findsOneWidget);
    await tester.tap(find.text('Ambientando Calendar'));
    await tester.pumpAndSettle();
    expect(
      find.widgetWithText(FilledButton, 'Feedback queue (2)'),
      findsOneWidget,
    );
    await tester
        .tap(find.byTooltip('Project actions for Ambientando Calendar'));
    await tester.pumpAndSettle();
    expect(find.text('Feedback queue (2)'), findsWidgets);
    expect(
      find.byTooltip('Project actions for Other Project'),
      findsOneWidget,
    );
    expect(find.text('Feedback queue (1)'), findsNothing);
  });

  testWidgets('feedback source aliases map unrelated source app to workspace', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final items = <FeedbackQueueItem>[
      _feedbackItem(
        id: 'feedback-aliased',
        sourceApp: 'customer-portal',
        sourceDisplayName: 'Customer Portal',
        comment: 'Aliased feedback',
      ),
      _feedbackItem(
        id: 'feedback-unrelated',
        sourceApp: 'another-source',
        comment: 'Wrong workspace',
      ),
    ];

    await tester.pumpWidget(
      MaterialApp(
        home: ChatScreen(
          initialApiBaseUrl: 'http://localhost:8000',
          notificationService: const NoopChatNotificationService(),
          enableServerBootstrap: false,
          initialSidebarWorkspaces: const <Workspace>[
            Workspace(
              name: 'Smart Nienfos',
              path: '/workspace/smart_nienfos',
            ),
          ],
          feedbackSourceWorkspaceAliases: const <String, String>{
            'customer-portal': '/workspace/smart_nienfos',
          },
          feedbackQueueListLoaderOverride: (_, {required includeImages}) async {
            return items;
          },
        ),
      ),
    );
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump();

    await tester.tap(find.byTooltip('Projects'));
    await tester.pumpAndSettle();
    expect(find.text('1 feedback'), findsOneWidget);

    await tester.tap(find.text('Smart Nienfos'));
    await tester.pumpAndSettle();
    expect(
      find.widgetWithText(FilledButton, 'Feedback queue (1)'),
      findsOneWidget,
    );
    await tester.tap(find.widgetWithText(FilledButton, 'Feedback queue (1)'));
    await tester.pumpAndSettle();
    expect(find.text('Aliased feedback'), findsOneWidget);
    expect(find.textContaining('Customer Portal · pending'), findsOneWidget);
    expect(find.text('Wrong workspace'), findsNothing);
  });

  testWidgets('hides project feedback action when no queue items match', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final items = <FeedbackQueueItem>[
      _feedbackItem(
        id: 'feedback-unrelated',
        sourceApp: 'smart-nienfos',
        comment: 'Otro proyecto',
      ),
      _feedbackItem(
        id: 'feedback-missing-source',
        sourceApp: '',
        comment: 'Sin source app',
      ),
    ];

    await tester.pumpWidget(
      MaterialApp(
        home: ChatScreen(
          initialApiBaseUrl: 'http://localhost:8000',
          notificationService: const NoopChatNotificationService(),
          enableServerBootstrap: false,
          initialSidebarWorkspaces: const <Workspace>[
            Workspace(
              name: 'Ambientando Calendar',
              path: '/workspace/ambientando-calendar',
            ),
          ],
          feedbackQueueListLoaderOverride: (_, {required includeImages}) async {
            return items;
          },
        ),
      ),
    );
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump();

    await tester.tap(find.byTooltip('Projects'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Ambientando Calendar'));
    await tester.pumpAndSettle();

    expect(find.textContaining('feedback'), findsNothing);
    expect(
      find.widgetWithText(FilledButton, 'Feedback queue (1)'),
      findsNothing,
    );

    await tester
        .tap(find.byTooltip('Project actions for Ambientando Calendar'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Feedback queue'), findsNothing);
  });

  testWidgets(
    'feedback queue stages only selected project items in the composer',
    (tester) async {
      SharedPreferences.setMockInitialValues(<String, Object>{});
      final fakeApiClient = _FakeApiClient();
      final controller = ChatController(
        apiClient: fakeApiClient,
        notificationService: const NoopChatNotificationService(),
      );
      final selectedItem = _feedbackItem(
        id: 'feedback-selected',
        sourceApp: 'ambientando-calendar',
        comment: 'Cambiar este bloque',
      );
      final uncheckedItem = _feedbackItem(
        id: 'feedback-unchecked',
        sourceApp: 'ambientando-calendar',
        comment: 'No incluir este comentario',
      );
      final unrelatedItem = _feedbackItem(
        id: 'feedback-other',
        sourceApp: 'other-project',
        comment: 'No incluir otro proyecto',
      );

      await tester.pumpWidget(
        MaterialApp(
          home: ChatScreen(
            initialApiBaseUrl: 'http://localhost:8000',
            notificationService: const NoopChatNotificationService(),
            controllerOverride: controller,
            enableServerBootstrap: false,
            initialSidebarWorkspaces: const <Workspace>[
              Workspace(
                name: 'Ambientando Calendar',
                path: '/workspace/ambientando-calendar',
              ),
            ],
            feedbackQueueListLoaderOverride: (_,
                {required includeImages}) async {
              return <FeedbackQueueItem>[
                selectedItem,
                uncheckedItem,
                unrelatedItem,
              ];
            },
          ),
        ),
      );
      await tester.pump(const Duration(milliseconds: 100));
      await tester.pump();

      await tester.tap(find.byTooltip('Projects'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Ambientando Calendar'));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(FilledButton, 'Feedback queue (2)'));
      await tester.pumpAndSettle();

      expect(find.text('Generator only'), findsNothing);
      expect(find.text('Generator + Reviewer'), findsNothing);
      expect(find.text('Select all'), findsOneWidget);
      await tester
          .tap(find.widgetWithText(CheckboxListTile, 'Cambiar este bloque'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Next'));
      await tester.pumpAndSettle();

      expect(controller.currentSession?.workspacePath,
          '/workspace/ambientando-calendar');
      expect(find.textContaining('Feedback queue for Ambientando Calendar'),
          findsOneWidget);
      expect(find.textContaining('Cambiar este bloque'), findsOneWidget);
      expect(
        find.textContaining(
          'The attached screenshot contains the user\'s drawn mark. Treat the marked area as the primary target of this feedback, and use the associated comment to understand the requested change.',
        ),
        findsOneWidget,
      );
      expect(find.textContaining('- source: ambientando-calendar'),
          findsOneWidget);
      expect(find.textContaining('- selection points: 2'), findsOneWidget);
      expect(find.text('feedback-1-feedback-selected.png'), findsOneWidget);
      expect(find.textContaining('No incluir este comentario'), findsNothing);
      expect(find.textContaining('No incluir otro proyecto'), findsNothing);
      expect(find.text('1 selected'), findsOneWidget);

      controller.dispose();
    },
  );

  testWidgets(
    'feedback queue stages selected screenshots in order with marked-area context',
    (tester) async {
      SharedPreferences.setMockInitialValues(<String, Object>{});
      final controller = ChatController(
        apiClient: _FakeApiClient(),
        notificationService: const NoopChatNotificationService(),
      );
      final firstItem = _feedbackItem(
        id: 'feedback-first',
        sourceApp: 'ambientando-calendar',
        comment: 'Primer comentario',
      );
      final secondItem = _feedbackItem(
        id: 'feedback-second',
        sourceApp: 'ambientando-calendar',
        comment: 'Segundo comentario',
      );
      final unrelatedItem = _feedbackItem(
        id: 'feedback-other',
        sourceApp: 'smart-nienfos',
        comment: 'Comentario de otro proyecto',
      );

      await tester.pumpWidget(
        MaterialApp(
          home: ChatScreen(
            initialApiBaseUrl: 'http://localhost:8000',
            notificationService: const NoopChatNotificationService(),
            controllerOverride: controller,
            enableServerBootstrap: false,
            initialSidebarWorkspaces: const <Workspace>[
              Workspace(
                name: 'Ambientando Calendar',
                path: '/workspace/ambientando-calendar',
              ),
            ],
            feedbackQueueListLoaderOverride: (_,
                {required includeImages}) async {
              return <FeedbackQueueItem>[
                firstItem,
                secondItem,
                unrelatedItem,
              ];
            },
          ),
        ),
      );
      await tester.pump(const Duration(milliseconds: 100));
      await tester.pump();

      await tester.tap(find.byTooltip('Projects'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Ambientando Calendar'));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(FilledButton, 'Feedback queue (2)'));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Select all'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Next'));
      await tester.pumpAndSettle();

      final composerText = _composerTextContaining(
        tester,
        'Feedback queue for Ambientando Calendar',
      );
      const markedAreaInstruction =
          'The attached screenshot contains the user\'s drawn mark. Treat the marked area as the primary target of this feedback, and use the associated comment to understand the requested change.';
      expect(_occurrences(composerText, markedAreaInstruction), 2);
      expect(composerText, contains('1. Primer comentario'));
      expect(composerText, contains('2. Segundo comentario'));
      expect(composerText, contains('- source: ambientando-calendar'));
      expect(composerText,
          contains('- image attachment: feedback-1-feedback-first.png'));
      expect(composerText,
          contains('- image attachment: feedback-2-feedback-second.png'));
      expect(composerText, isNot(contains('Comentario de otro proyecto')));
      expect(find.text('feedback-1-feedback-first.png'), findsOneWidget);
      expect(find.text('feedback-2-feedback-second.png'), findsOneWidget);
      expect(find.textContaining('feedback-other'), findsNothing);

      controller.dispose();
    },
  );

  testWidgets('failed attachment send keeps composer text and attachments', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final fakeApiClient = _FakeApiClient(failAttachmentSends: true);
    final controller = ChatController(
      apiClient: fakeApiClient,
      notificationService: const NoopChatNotificationService(),
    );

    await _pumpChatAndStageSingleFeedbackAttachment(
      tester,
      controller: controller,
      feedbackItem: _feedbackItem(
        id: 'feedback-retry',
        sourceApp: 'ambientando-calendar',
        comment: 'Mantener el draft si falla',
      ),
    );

    expect(find.text('1 selected'), findsOneWidget);
    expect(
      _composerTextContaining(
          tester, 'Feedback queue for Ambientando Calendar'),
      contains('Mantener el draft si falla'),
    );

    await tester.showKeyboard(find.byType(TextField).last);
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));

    expect(fakeApiClient.attachmentSends, hasLength(1));
    expect(find.text('1 selected'), findsOneWidget);
    expect(
      _composerTextContaining(
          tester, 'Feedback queue for Ambientando Calendar'),
      contains('Mantener el draft si falla'),
    );
    controller.dispose();
  });

  testWidgets('successful attachment send clears composer draft', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final fakeApiClient = _FakeApiClient();
    final controller = ChatController(
      apiClient: fakeApiClient,
      notificationService: const NoopChatNotificationService(),
    );

    await _pumpChatAndStageSingleFeedbackAttachment(
      tester,
      controller: controller,
      feedbackItem: _feedbackItem(
        id: 'feedback-send',
        sourceApp: 'ambientando-calendar',
        comment: 'Enviar y limpiar',
      ),
    );

    await tester.showKeyboard(find.byType(TextField).last);
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));

    expect(fakeApiClient.attachmentSends, hasLength(1));
    expect(fakeApiClient.attachmentSends.single.message,
        contains('Enviar y limpiar'));
    expect(fakeApiClient.attachmentSends.single.filenames,
        <String>['feedback-1-feedback-send.png']);
    expect(find.text('1 selected'), findsNothing);
    expect(
      () => _composerTextContaining(
        tester,
        'Feedback queue for Ambientando Calendar',
      ),
      throwsStateError,
    );

    controller.dispose();
  });

  testWidgets('recorded voice note sends without flushing staged attachments', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1200, 1600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final textController = TextEditingController();
    addTearDown(textController.dispose);
    final audioSends = <String>[];
    final attachmentSends = <String>[];
    final attachmentPrompts = <String?>[];
    final recorders = <_FakeAudioNoteRecorder>[];

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Align(
            alignment: Alignment.bottomCenter,
            child: buildComposerVoiceRecordingHarnessForTest(
              controller: textController,
              stagedText: 'Keep this attachment staged',
              stageAttachment: true,
              audioRecorderFactory: () {
                final recorder = _FakeAudioNoteRecorder(
                  XFile('voice-note.m4a', name: 'voice-note.m4a'),
                );
                recorders.add(recorder);
                return recorder;
              },
              onSendAudio: (audioFile, {message}) async {
                audioSends.add(audioFile.name);
                expect(message, isNull);
                return true;
              },
              onSendAttachments: (attachments, {prompt}) async {
                attachmentSends.addAll(
                  attachments.map((attachment) => attachment.name),
                );
                attachmentPrompts.add(prompt);
                return true;
              },
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    expect(find.text('1 selected'), findsOneWidget);
    final micButton = find
        .ancestor(
          of: find.byIcon(Icons.mic_rounded),
          matching: find.byType(FilledButton),
        )
        .last;
    await tester.tap(micButton);
    await tester.pump();
    expect(find.text('Recording'), findsOneWidget);

    final voiceSendButton = find
        .ancestor(
          of: find.byIcon(Icons.send_rounded),
          matching: find.byType(FilledButton),
        )
        .last;
    await tester.tap(voiceSendButton);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));

    expect(audioSends, <String>['voice-note.m4a']);
    expect(attachmentSends, isEmpty);
    expect(find.text('1 selected'), findsOneWidget);
    expect(textController.text, contains('Keep this attachment staged'));
    expect(recorders.first.started, isTrue);
    expect(recorders.first.stopped, isTrue);
    expect(recorders.first.cleaned, isTrue);
    expect(recorders.first.disposed, isTrue);
  });

  testWidgets('recorded voice note sends with composer text immediately', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1200, 1600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final textController = TextEditingController();
    addTearDown(textController.dispose);
    final audioSends = <String>[];
    final audioMessages = <String?>[];
    final attachmentSends = <String>[];
    final attachmentPrompts = <String?>[];
    final recorders = <_FakeAudioNoteRecorder>[];

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Align(
            alignment: Alignment.bottomCenter,
            child: buildComposerVoiceRecordingHarnessForTest(
              controller: textController,
              stagedText: 'Explain this voice note',
              audioRecorderFactory: () {
                final recorder = _FakeAudioNoteRecorder(
                  XFile('voice-note.m4a', name: 'voice-note.m4a'),
                );
                recorders.add(recorder);
                return recorder;
              },
              onSendAudio: (audioFile, {message}) async {
                audioSends.add(audioFile.name);
                audioMessages.add(message);
                return true;
              },
              onSendAttachments: (attachments, {prompt}) async {
                attachmentSends.addAll(
                  attachments.map((attachment) => attachment.name),
                );
                attachmentPrompts.add(prompt);
                return true;
              },
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    expect(find.text('Explain this voice note'), findsOneWidget);
    final micButton = find
        .ancestor(
          of: find.byIcon(Icons.mic_rounded),
          matching: find.byType(FilledButton),
        )
        .last;
    await tester.tap(micButton);
    await tester.pump();
    expect(find.text('Recording'), findsOneWidget);

    final voiceSendButton = find
        .ancestor(
          of: find.byIcon(Icons.send_rounded),
          matching: find.byType(FilledButton),
        )
        .last;
    await tester.tap(voiceSendButton);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));

    expect(audioSends, <String>['voice-note.m4a']);
    expect(audioMessages, <String?>['Explain this voice note']);
    expect(attachmentSends, isEmpty);
    expect(attachmentPrompts, isEmpty);
    expect(textController.text, isEmpty);
    expect(recorders.first.cleaned, isTrue);
    expect(recorders.first.disposed, isTrue);
  });

  testWidgets('swiping up on send starts voice recording with composer text', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1200, 1600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final textController = TextEditingController();
    addTearDown(textController.dispose);
    final audioSends = <String>[];
    final audioMessages = <String?>[];
    final recorders = <_FakeAudioNoteRecorder>[];

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Align(
            alignment: Alignment.bottomCenter,
            child: buildComposerVoiceRecordingHarnessForTest(
              controller: textController,
              stagedText: 'Keep this text with the audio',
              audioRecorderFactory: () {
                final recorder = _FakeAudioNoteRecorder(
                  XFile('voice-note.m4a', name: 'voice-note.m4a'),
                );
                recorders.add(recorder);
                return recorder;
              },
              onSendAudio: (audioFile, {message}) async {
                audioSends.add(audioFile.name);
                audioMessages.add(message);
                return true;
              },
              onSendAttachments: (_, {prompt}) async => true,
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    final sendButton = find
        .ancestor(
          of: find.byIcon(Icons.arrow_upward_rounded),
          matching: find.byType(FilledButton),
        )
        .last;
    await tester.drag(sendButton, const Offset(0, -120));
    await tester.pump();

    expect(find.text('Recording'), findsOneWidget);
    expect(recorders.first.started, isTrue);
    expect(textController.text, contains('Keep this text with the audio'));

    final voiceSendButton = find
        .ancestor(
          of: find.byIcon(Icons.send_rounded),
          matching: find.byType(FilledButton),
        )
        .last;
    await tester.tap(voiceSendButton);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));

    expect(audioSends, <String>['voice-note.m4a']);
    expect(audioMessages, <String?>['Keep this text with the audio']);
    expect(textController.text, isEmpty);
  });

  testWidgets('renders assistant options as quick actions', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ChatBubble(
            message: ChatMessage(
              id: 'assistant-1',
              text: '1. Summarize the repo\n2. Show changed files',
              isUser: false,
              authorType: ChatMessageAuthorType.assistant,
              status: ChatMessageStatus.completed,
              createdAt: DateTime.utc(2026, 1, 1),
              updatedAt: DateTime.utc(2026, 1, 1),
              jobStatus: 'completed',
              jobPhase: 'Completed',
            ),
          ),
        ),
      ),
    );

    expect(find.text('Quick options'), findsOneWidget);
    expect(find.text('Summarize the repo'), findsOneWidget);
    expect(find.text('Show changed files'), findsOneWidget);
  });

  testWidgets('renders a readable local timestamp inside the bubble', (
    tester,
  ) async {
    await tester.pumpWidget(
      MediaQuery(
        data: const MediaQueryData(alwaysUse24HourFormat: true),
        child: MaterialApp(
          home: Scaffold(
            body: ChatBubble(
              message: ChatMessage(
                id: 'assistant-timestamp',
                text: 'Reply with a visible timestamp.',
                isUser: false,
                authorType: ChatMessageAuthorType.assistant,
                status: ChatMessageStatus.completed,
                createdAt: DateTime(2026, 1, 1, 15, 42),
                updatedAt: DateTime(2026, 1, 1, 15, 42),
              ),
            ),
          ),
        ),
      ),
    );

    expect(find.text('15:42'), findsOneWidget);
  });

  testWidgets('renders user image attachments as visual metadata', (
    tester,
  ) async {
    await _pumpUserChatBubble(
      tester,
      'Mira esta foto\n\n'
      '[Attached files]\n'
      '- image: scaled_1000215533.jpg',
    );

    expect(find.text('Mira esta foto'), findsOneWidget);
    expect(find.text('Image attached'), findsOneWidget);
    expect(find.textContaining('[Attached files]'), findsNothing);
    expect(find.textContaining('scaled_1000215533.jpg'), findsNothing);
    expect(find.byIcon(Icons.image_rounded), findsOneWidget);
  });

  testWidgets('opens image viewer for structured user image attachments', (
    tester,
  ) async {
    await _pumpUserChatBubble(
      tester,
      'Mira esta foto\n\n'
      '[Attached files]\n'
      '- image: scaled_1000215533.jpg',
      attachmentBaseUrl: 'http://backend.test',
      attachments: const <ChatMessageAttachment>[
        ChatMessageAttachment(
          id: 'job-1:image:0',
          kind: 'image',
          jobId: 'job-1',
          index: 0,
          downloadUrl: '/jobs/job-1/attachments/0',
        ),
      ],
    );

    expect(find.text('Mira esta foto'), findsOneWidget);
    expect(find.text('Image attached'), findsOneWidget);
    expect(find.textContaining('scaled_1000215533.jpg'), findsNothing);
    expect(find.byIcon(Icons.open_in_full_rounded), findsOneWidget);

    await tester.tap(find.text('Image attached'));
    await tester.pump();

    expect(find.text('1 / 1'), findsOneWidget);
    expect(find.byType(Image), findsOneWidget);
  });

  testWidgets('legacy user image metadata stays a non-viewer fallback', (
    tester,
  ) async {
    await _pumpUserChatBubble(
      tester,
      '[Attached files]\n'
      '- image: scaled_1000215533.jpg',
      attachmentBaseUrl: 'http://backend.test',
    );

    expect(find.text('Image attached'), findsOneWidget);
    expect(find.byIcon(Icons.open_in_full_rounded), findsNothing);

    await tester.tap(find.text('Image attached'));
    await tester.pump();

    expect(find.text('1 / 1'), findsNothing);
  });

  testWidgets('renders legacy user audio document attachments visually', (
    tester,
  ) async {
    await _pumpUserChatBubble(
      tester,
      'Summarize this audio\n\n'
      '[Attached audio document: PTT-20260322-WA0001.ogg]',
    );

    expect(find.text('Summarize this audio'), findsOneWidget);
    expect(find.text('Audio attached'), findsOneWidget);
    expect(find.textContaining('[Attached audio document'), findsNothing);
    expect(find.textContaining('PTT-20260322-WA0001.ogg'), findsNothing);
    expect(find.byIcon(Icons.graphic_eq_rounded), findsOneWidget);
  });

  testWidgets('renders voice note transcript instead of audio attachment', (
    tester,
  ) async {
    await _pumpUserChatBubble(
      tester,
      'Explain this voice note\n\n'
      '[Sent via audio]\n\n'
      'The release is ready to send.',
    );

    expect(find.text('Explain this voice note'), findsOneWidget);
    expect(find.text('The release is ready to send.'), findsOneWidget);
    expect(find.text('Sent via audio'), findsOneWidget);
    expect(find.text('Audio attached'), findsNothing);
    expect(find.textContaining('[Sent via audio]'), findsNothing);
  });

  testWidgets('renders legacy user text document attachments visually', (
    tester,
  ) async {
    await _pumpUserChatBubble(
      tester,
      'Extract action items\n\n'
      '[Attached text document: notes.txt]',
    );

    expect(find.text('Extract action items'), findsOneWidget);
    expect(find.text('Document attached'), findsOneWidget);
    expect(find.textContaining('[Attached text document'), findsNothing);
    expect(find.textContaining('notes.txt'), findsNothing);
  });

  testWidgets('renders multiple user attachments without raw filenames', (
    tester,
  ) async {
    await _pumpUserChatBubble(
      tester,
      'Compare everything in this batch\n\n'
      '[Attached files]\n'
      '- image: diagram.png\n'
      '- text: notes.txt\n'
      '- audio: voice.ogg',
    );

    expect(find.text('Compare everything in this batch'), findsOneWidget);
    expect(find.text('3 attachments'), findsOneWidget);
    expect(find.text('1 image · 1 document · 1 audio file'), findsOneWidget);
    expect(find.textContaining('[Attached files]'), findsNothing);
    expect(find.textContaining('diagram.png'), findsNothing);
    expect(find.textContaining('notes.txt'), findsNothing);
    expect(find.textContaining('voice.ogg'), findsNothing);
  });

  testWidgets('renders attachment-only user image metadata as a card', (
    tester,
  ) async {
    await _pumpUserChatBubble(
      tester,
      '[Attached files]\n'
      '- image: scaled_1000215533.jpg',
    );

    expect(find.text('Image attached'), findsOneWidget);
    expect(find.byIcon(Icons.image_rounded), findsOneWidget);
    expect(find.byType(SelectableText), findsNothing);
    expect(find.textContaining('[Attached files]'), findsNothing);
    expect(find.textContaining('scaled_1000215533.jpg'), findsNothing);
  });

  testWidgets('renders reasoning and tool activity as status strips', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Column(
            children: <Widget>[
              ChatBubble(
                message: ChatMessage(
                  id: 'assistant-reasoning',
                  text: '',
                  isUser: false,
                  authorType: ChatMessageAuthorType.assistant,
                  status: ChatMessageStatus.pending,
                  createdAt: DateTime.utc(2026, 1, 1),
                  updatedAt: DateTime.utc(2026, 1, 1),
                  jobStatus: 'running',
                  jobPhase: 'Reasoning',
                  jobLatestActivity: 'Codex is reasoning.',
                ),
              ),
              ChatBubble(
                message: ChatMessage(
                  id: 'assistant-tool',
                  text: '',
                  isUser: false,
                  authorType: ChatMessageAuthorType.assistant,
                  status: ChatMessageStatus.pending,
                  createdAt: DateTime.utc(2026, 1, 1),
                  updatedAt: DateTime.utc(2026, 1, 1),
                  jobStatus: 'running',
                  jobPhase: 'Running tools',
                  jobLatestActivity: 'call-mcp-tool',
                ),
              ),
            ],
          ),
        ),
      ),
    );

    expect(find.text('Reasoning'), findsAtLeastNWidgets(1));
    expect(find.byIcon(Icons.psychology_alt_outlined), findsOneWidget);
    expect(find.text('Codex is reasoning.'), findsOneWidget);
    expect(find.text('Tools'), findsOneWidget);
    expect(find.byIcon(Icons.extension_rounded), findsOneWidget);
    expect(find.text('Calling MCP tool.'), findsOneWidget);
    expect(find.text('call-mcp-tool'), findsNothing);
  });

  testWidgets('day separator formatter supports today and yesterday in Spanish',
      (
    tester,
  ) async {
    late String todayLabel;
    late String yesterdayLabel;

    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) {
            final now = DateTime(2026, 3, 28, 12);
            todayLabel = formatChatDaySeparatorLabel(
              context,
              DateTime(2026, 3, 28, 9, 30),
              now: now,
              locale: const Locale('es'),
            );
            yesterdayLabel = formatChatDaySeparatorLabel(
              context,
              DateTime(2026, 3, 27, 21),
              now: now,
              locale: const Locale('es'),
            );
            return const SizedBox.shrink();
          },
        ),
      ),
    );

    expect(todayLabel, 'Hoy');
    expect(yesterdayLabel, 'Ayer');
  });

  testWidgets(
      'supervisor-only agent studio uses registry selection and hides specialist turn budgets',
      (tester) async {
    tester.view.physicalSize = const Size(1280, 1600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final fakeApiClient = _FakeApiClient();
    final controller = ChatController(
      apiClient: fakeApiClient,
      notificationService: const NoopChatNotificationService(),
    );
    fakeApiClient._sessionConfigurations['session-a'] =
        kDefaultAgentConfiguration.copyWith(
      preset: AgentPreset.supervisor,
      displayMode: AgentDisplayMode.collapseSpecialists,
      turnBudgetMode: TurnBudgetMode.supervisorOnly,
      supervisorMemberIds: const <AgentId>[AgentId.qa, AgentId.seniorEngineer],
      agents: kDefaultAgentDefinitions.map((agent) {
        if (agent.agentId == AgentId.supervisor) {
          return agent.copyWith(enabled: true, maxTurns: 4);
        }
        if (agent.agentId == AgentId.qa ||
            agent.agentId == AgentId.seniorEngineer) {
          return agent.copyWith(enabled: true, maxTurns: 2);
        }
        return agent.copyWith(
          enabled: agent.agentId == AgentId.generator ? false : agent.enabled,
          maxTurns: 0,
        );
      }).toList(growable: false),
    );
    await controller.selectSession('session-a');

    await tester.pumpWidget(
      MaterialApp(
        home: ChatScreen(
          initialApiBaseUrl: 'http://localhost:8000',
          notificationService: const NoopChatNotificationService(),
          controllerOverride: controller,
          enableServerBootstrap: false,
        ),
      ),
    );
    await tester.pump();

    await tester.tap(find.byIcon(Icons.account_tree_outlined));
    await tester.pumpAndSettle();

    expect(find.text('Turn budget mode'), findsOneWidget);
    expect(find.text('Supervisor only'), findsWidgets);
    expect(
      find.textContaining('selected specialists can be called whenever'),
      findsOneWidget,
    );
    expect(
      find.textContaining('Specialist turn budgets are preserved'),
      findsOneWidget,
    );
    expect(
      find.textContaining(
          'Selection is controlled by the supervisor registry above.'),
      findsNWidgets(4),
    );
    expect(find.text('Turn budget'), findsNWidgets(4));
    expect(find.text('Scraper'), findsWidgets);

    controller.dispose();
  });

  testWidgets('renders validation blocks and file reference chips',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ChatBubble(
            message: ChatMessage(
              id: 'assistant-2',
              text:
                  'Updated [docker-compose.yml](/tmp/docker-compose.yml) and [README.md](/tmp/README.md).\n\nValidation:\n- backend tests -> 8 passed\n- flutter analyze -> no issues found',
              isUser: false,
              authorType: ChatMessageAuthorType.assistant,
              status: ChatMessageStatus.completed,
              createdAt: DateTime.utc(2026, 1, 1),
              updatedAt: DateTime.utc(2026, 1, 1),
              jobStatus: 'completed',
              jobPhase: 'Completed',
            ),
          ),
        ),
      ),
    );

    expect(find.text('docker-compose.yml'), findsOneWidget);
    expect(find.text('README.md'), findsOneWidget);
    expect(find.text('Validation'), findsOneWidget);
    expect(find.text('backend tests'), findsOneWidget);
    expect(find.text('8 passed'), findsOneWidget);
    expect(find.text('flutter analyze'), findsOneWidget);
  });

  testWidgets('dispatches inline link taps through the chat bubble callback', (
    tester,
  ) async {
    var tappedTarget = '';

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ChatBubble(
            message: ChatMessage(
              id: 'assistant-3',
              text: 'Open [README.md](/tmp/README.md)',
              isUser: false,
              authorType: ChatMessageAuthorType.assistant,
              status: ChatMessageStatus.completed,
              createdAt: DateTime.utc(2026, 1, 1),
              updatedAt: DateTime.utc(2026, 1, 1),
              jobStatus: 'completed',
              jobPhase: 'Completed',
            ),
            onLinkTap: (target) async {
              tappedTarget = target;
            },
          ),
        ),
      ),
    );

    await tester.tap(find.text('README.md'));
    await tester.pump();

    expect(tappedTarget, '/tmp/README.md');
  });

  testWidgets('renders reviewer codex user bubble with distinct label', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ChatBubble(
            message: ChatMessage(
              id: 'reviewer-1',
              text: 'Ask the generator Codex to add integration coverage.',
              isUser: true,
              authorType: ChatMessageAuthorType.reviewerCodex,
              status: ChatMessageStatus.completed,
              createdAt: DateTime.utc(2026, 1, 1),
              updatedAt: DateTime.utc(2026, 1, 1),
              jobStatus: 'completed',
              jobPhase: 'Prompt ready',
              jobElapsedSeconds: 125,
            ),
          ),
        ),
      ),
    );

    expect(find.text('CODEX REVIEWER'), findsOneWidget);
    expect(find.text('2m 5s'), findsOneWidget);
    expect(
      find.text('Ask the generator Codex to add integration coverage.'),
      findsOneWidget,
    );
  });

  testWidgets('renders summary agent assistant bubble with its own label', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ChatBubble(
            message: ChatMessage(
              id: 'summary-1',
              text: 'Summary response for the user.',
              isUser: false,
              authorType: ChatMessageAuthorType.assistant,
              agentId: AgentId.summary,
              agentType: AgentType.summary,
              status: ChatMessageStatus.completed,
              createdAt: DateTime.utc(2026, 1, 1),
              updatedAt: DateTime.utc(2026, 1, 1),
              jobStatus: 'completed',
              jobPhase: 'Completed',
            ),
          ),
        ),
      ),
    );

    expect(find.text('SUMMARY'), findsOneWidget);
    expect(find.text('Summary response for the user.'), findsOneWidget);
  });

  testWidgets('chat screen can focus on summary updates only', (tester) async {
    tester.view.physicalSize = const Size(1280, 1600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final fakeApiClient = _FakeApiClient();
    final controller = ChatController(
      apiClient: fakeApiClient,
      notificationService: const NoopChatNotificationService(),
    );
    final timestamp = DateTime.utc(2026, 1, 1, 12);
    fakeApiClient.sessionOverrides['session-a'] = SessionDetail(
      id: 'session-a',
      title: 'Chat A',
      workspacePath: '/workspace/a',
      workspaceName: 'A',
      agentConfiguration: kDefaultAgentConfiguration.copyWith(
        preset: AgentPreset.triad,
        agents: kDefaultAgentDefinitions.map((agent) {
          if (agent.agentId == AgentId.summary) {
            return agent.copyWith(enabled: true);
          }
          return agent;
        }).toList(growable: false),
      ),
      createdAt: timestamp,
      updatedAt: timestamp,
      messages: <ChatMessage>[
        ChatMessage(
          id: 'user-1',
          text: 'Do the work',
          isUser: true,
          authorType: ChatMessageAuthorType.human,
          agentId: AgentId.user,
          agentType: AgentType.human,
          status: ChatMessageStatus.completed,
          createdAt: timestamp,
          updatedAt: timestamp,
        ),
        ChatMessage(
          id: 'generator-1',
          text: 'Generator update',
          isUser: false,
          authorType: ChatMessageAuthorType.assistant,
          agentId: AgentId.generator,
          agentType: AgentType.generator,
          status: ChatMessageStatus.completed,
          createdAt: timestamp,
          updatedAt: timestamp,
        ),
        ChatMessage(
          id: 'summary-1',
          text: 'Summary update one',
          isUser: false,
          authorType: ChatMessageAuthorType.assistant,
          agentId: AgentId.summary,
          agentType: AgentType.summary,
          status: ChatMessageStatus.completed,
          createdAt: timestamp,
          updatedAt: timestamp,
          summaryTurnStart: 1,
          summaryTurnEnd: 3,
        ),
        ChatMessage(
          id: 'summary-2',
          text: 'Summary update two',
          isUser: false,
          authorType: ChatMessageAuthorType.assistant,
          agentId: AgentId.summary,
          agentType: AgentType.summary,
          status: ChatMessageStatus.completed,
          createdAt: timestamp,
          updatedAt: timestamp,
        ),
      ],
    );
    await controller.selectSession('session-a');

    await tester.pumpWidget(
      MaterialApp(
        home: ChatScreen(
          initialApiBaseUrl: 'http://localhost:8000',
          notificationService: const NoopChatNotificationService(),
          controllerOverride: controller,
          enableServerBootstrap: false,
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.scrollUntilVisible(
      find.text('Summary update one'),
      120,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();

    expect(find.text('Generator update'), findsOneWidget);
    expect(find.text('Summary update one'), findsOneWidget);

    await tester.tap(find.byTooltip('View summary').first);
    await tester.pumpAndSettle();

    expect(find.textContaining('Showing 2 summary updates'), findsOneWidget);
    expect(find.text('Summary update one'), findsOneWidget);
    expect(find.text('Summary update two'), findsOneWidget);
    expect(find.text('Covers turns 1 to 3'), findsOneWidget);
    expect(find.text('Generator update'), findsNothing);

    controller.dispose();
  });

  testWidgets('renders submission unknown bubble with recovery actions', (
    tester,
  ) async {
    var retried = false;
    var dismissed = false;

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ChatBubble(
            message: ChatMessage(
              id: 'unknown-1',
              text: 'Automatic recovery stopped to avoid duplicate execution.',
              isUser: false,
              authorType: ChatMessageAuthorType.assistant,
              status: ChatMessageStatus.submissionUnknown,
              createdAt: DateTime.utc(2026, 1, 1),
              updatedAt: DateTime.utc(2026, 1, 1),
            ),
            onRecoverUnknownSubmission: () async {
              retried = true;
            },
            onCancelUnknownSubmission: () async {
              dismissed = true;
            },
          ),
        ),
      ),
    );

    expect(find.text('Retry follow-up'), findsOneWidget);
    expect(find.text('Dismiss'), findsOneWidget);

    await tester.tap(find.text('Retry follow-up'));
    await tester.pump();
    expect(retried, isTrue);

    await tester.tap(find.text('Dismiss'));
    await tester.pump();
    expect(dismissed, isTrue);
  });

  testWidgets(
      'renders recovery lineage text for superseded and retried messages',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Column(
            children: <Widget>[
              ChatBubble(
                message: ChatMessage(
                  id: 'old-unknown',
                  text: 'Old uncertain follow-up.',
                  isUser: false,
                  authorType: ChatMessageAuthorType.assistant,
                  status: ChatMessageStatus.cancelled,
                  reasonCode: ChatMessageReasonCode.manualRetryRequested,
                  recoveryAction: MessageRecoveryAction.retry,
                  supersededByMessageId: 'retry-1',
                  createdAt: DateTime.utc(2026, 1, 1),
                  updatedAt: DateTime.utc(2026, 1, 1),
                ),
              ),
              ChatBubble(
                message: ChatMessage(
                  id: 'retry-1',
                  text: 'New attempt.',
                  isUser: false,
                  authorType: ChatMessageAuthorType.assistant,
                  status: ChatMessageStatus.completed,
                  reasonCode: ChatMessageReasonCode.manualRetryRequested,
                  recoveryAction: MessageRecoveryAction.retry,
                  recoveredFromMessageId: 'old-unknown',
                  createdAt: DateTime.utc(2026, 1, 1),
                  updatedAt: DateTime.utc(2026, 1, 1),
                ),
              ),
            ],
          ),
        ),
      ),
    );

    expect(
      find.textContaining('A manual retry was requested for this follow-up.'),
      findsNWidgets(2),
    );
    expect(
      find.textContaining(
        'This uncertain follow-up was superseded by a manual retry.',
      ),
      findsOneWidget,
    );
    expect(
      find.textContaining('Manual retry of an earlier uncertain follow-up.'),
      findsOneWidget,
    );
  });

  test('agent configuration falls back to safe defaults for malformed data',
      () {
    final configuration = AgentConfiguration.fromJson(
      <String, dynamic>{
        'preset': 'invalid',
        'display_mode': 'summary_only',
        'agents': <dynamic>[
          <String, dynamic>{
            'agent_id': 'generator',
            'agent_type': 'generator',
            'enabled': true,
            'label': 'Builder',
            'prompt': 'Build',
            'visibility': 'visible',
            'max_turns': 3,
          },
          'not-a-map',
        ],
      },
    );

    expect(configuration.preset, AgentPreset.solo);
    expect(configuration.displayMode, AgentDisplayMode.summaryOnly);
    expect(configuration.turnBudgetMode, TurnBudgetMode.eachAgent);
    expect(configuration.agents.length, kDefaultAgentDefinitions.length);
    expect(
      configuration.agents.map((agent) => agent.agentId).toList(),
      kDefaultAgentDefinitions.map((agent) => agent.agentId).toList(),
    );
    expect(configuration.byId(AgentId.generator)?.label, 'Builder');
    expect(configuration.byId(AgentId.reviewer)?.enabled, isFalse);
    expect(configuration.byId(AgentId.summary)?.enabled, isFalse);
    expect(
      configuration.byId(AgentId.supervisor)?.enabled,
      kDefaultAgentConfiguration.byId(AgentId.supervisor)?.enabled,
    );
    expect(
      configuration.byId(AgentId.qa)?.label,
      kDefaultAgentConfiguration.byId(AgentId.qa)?.label,
    );
  });

  test(
      'unknown agent ids are ignored instead of overwriting generator defaults',
      () {
    final configuration = AgentConfiguration.fromJson(
      <String, dynamic>{
        'preset': 'triad',
        'display_mode': 'show_all',
        'agents': <dynamic>[
          <String, dynamic>{
            'agent_id': 'rogue',
            'agent_type': 'reviewer',
            'enabled': true,
            'label': 'Rogue',
            'prompt': 'Should be ignored',
            'visibility': 'hidden',
            'max_turns': 9,
          },
        ],
      },
    );

    expect(configuration.byId(AgentId.generator)?.label, 'Generator');
    expect(configuration.byId(AgentId.generator)?.enabled, isTrue);
    expect(configuration.byId(AgentId.reviewer)?.enabled, isFalse);
    expect(configuration.byId(AgentId.summary)?.enabled, isFalse);
  });

  test('supervisor turn budget mode parses and serializes cleanly', () {
    final configuration = AgentConfiguration.fromJson(
      <String, dynamic>{
        'preset': 'supervisor',
        'display_mode': 'collapse_specialists',
        'turn_budget_mode': 'supervisor_only',
        'supervisor_member_ids': const <String>['qa', 'senior_engineer'],
        'agents': kDefaultAgentDefinitions
            .map((agent) => agent.toJson())
            .toList(growable: false),
      },
    );

    expect(configuration.preset, AgentPreset.supervisor);
    expect(configuration.turnBudgetMode, TurnBudgetMode.supervisorOnly);
    expect(
      configuration.supervisorMemberIds,
      <AgentId>[AgentId.qa, AgentId.seniorEngineer],
    );
    expect(configuration.toJson()['turn_budget_mode'], 'supervisor_only');
  });

  test('supervisor configs default summary strategy to the summary window', () {
    final configuration = AgentConfiguration.fromJson(
      <String, dynamic>{
        'preset': 'supervisor',
        'display_mode': 'collapse_specialists',
        'turn_budget_mode': 'supervisor_only',
        'supervisor_member_ids': const <String>['qa'],
        'agents': kDefaultAgentDefinitions
            .map((agent) => agent.toJson())
            .toList(growable: false),
      },
    );

    expect(
      configuration.summaryStrategy.mode,
      SummaryStrategyMode.supervisorWindow,
    );
    expect(configuration.summaryStrategy.supervisorWindowStart, 3);
    expect(configuration.summaryStrategy.supervisorWindowEnd, 6);
  });

  test('legacy session summaries render with default solo agent config', () {
    final summary = ChatSessionSummary.fromJson(
      <String, dynamic>{
        'id': 'session-legacy',
        'title': 'Legacy',
        'workspace_path': '/workspace/legacy',
        'workspace_name': 'Legacy',
        'created_at': DateTime.utc(2026, 1, 1).toIso8601String(),
        'updated_at': DateTime.utc(2026, 1, 1).toIso8601String(),
        'agent_configuration': 'broken',
      },
    );

    expect(summary.agentConfiguration.preset, AgentPreset.solo);
    expect(summary.agentConfiguration.byId(AgentId.generator)?.enabled, isTrue);
    expect(summary.agentConfiguration.byId(AgentId.reviewer)?.enabled, isFalse);
  });

  test('chat message parsing tolerates partial legacy recovery payloads', () {
    final message = ChatMessage.fromJson(
      <String, dynamic>{
        'id': 'legacy-recovery',
        'role': 'assistant',
        'content': 'Legacy',
        'status': 'submission_unknown',
        'reason_code': 'not-a-valid-reason',
        'recovery_action': 'retry',
        'created_at': DateTime.utc(2026, 1, 1).toIso8601String(),
        'updated_at': DateTime.utc(2026, 1, 1).toIso8601String(),
      },
    );

    expect(message.status, ChatMessageStatus.submissionUnknown);
    expect(message.reasonCode, isNull);
    expect(message.recoveryAction, MessageRecoveryAction.retry);
    expect(message.recoveredFromMessageId, isNull);
    expect(message.supersededByMessageId, isNull);
  });

  test('chat message parsing keeps structured image attachments', () {
    final message = ChatMessage.fromJson(
      <String, dynamic>{
        'id': 'with-attachment',
        'role': 'user',
        'content': 'Look',
        'status': 'completed',
        'created_at': DateTime.utc(2026, 1, 1).toIso8601String(),
        'updated_at': DateTime.utc(2026, 1, 1).toIso8601String(),
        'attachments': <Map<String, dynamic>>[
          <String, dynamic>{
            'id': 'job-1:image:0',
            'kind': 'image',
            'job_id': 'job-1',
            'index': 0,
            'download_url': '/jobs/job-1/attachments/0',
          },
        ],
      },
    );

    expect(message.attachments, hasLength(1));
    expect(message.imageAttachments, hasLength(1));
    expect(message.attachments.single.id, 'job-1:image:0');
    expect(message.attachments.single.kind, 'image');
    expect(message.attachments.single.jobId, 'job-1');
    expect(message.attachments.single.index, 0);
    expect(
      message.attachments.single.downloadUrl,
      '/jobs/job-1/attachments/0',
    );
  });

  test('job status parsing keeps agent metadata for notifications', () {
    final snapshot = JobStatusResponse.fromJson(
      <String, dynamic>{
        'job_id': 'job-reviewer',
        'session_id': 'session-a',
        'status': 'completed',
        'elapsed_seconds': 3,
        'agent_id': 'reviewer',
        'agent_type': 'reviewer',
        'response': 'Looks good.',
      },
    );

    expect(snapshot.agentId, AgentId.reviewer);
    expect(snapshot.agentType, AgentType.reviewer);
  });

  test('speech sanitizer strips markdown and code fences safely', () {
    expect(
      sanitizeTextForSpeech(
        'Open [README.md](/tmp/readme)\n\n```dart\nprint("debug");\n```\nUse `flutter test` now.',
      ),
      'Open README.md Use flutter test now.',
    );
  });

  testWidgets('renders reason code text for superseded runs', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ChatBubble(
            message: ChatMessage(
              id: 'superseded-1',
              text: 'Superseded placeholder.',
              isUser: false,
              authorType: ChatMessageAuthorType.assistant,
              status: ChatMessageStatus.cancelled,
              reasonCode: ChatMessageReasonCode.supersededByNewerRun,
              createdAt: DateTime.utc(2026, 1, 1),
              updatedAt: DateTime.utc(2026, 1, 1),
            ),
          ),
        ),
      ),
    );

    expect(
      find.text(
        'Superseded by a newer run before this follow-up could be resumed.',
      ),
      findsOneWidget,
    );
  });

  test('preset helper enables only the expected agents', () {
    expect(agentEnabledForPreset(AgentId.generator, AgentPreset.solo), isTrue);
    expect(agentEnabledForPreset(AgentId.reviewer, AgentPreset.solo), isFalse);
    expect(agentEnabledForPreset(AgentId.reviewer, AgentPreset.review), isTrue);
    expect(agentEnabledForPreset(AgentId.summary, AgentPreset.review), isFalse);
    expect(agentEnabledForPreset(AgentId.summary, AgentPreset.triad), isTrue);
  });

  test('visibility filtering respects display modes and hidden messages', () {
    final messages = <ChatMessage>[
      _message(
        id: 'human',
        isUser: true,
        authorType: ChatMessageAuthorType.human,
        agentId: AgentId.user,
        agentType: AgentType.human,
      ),
      _message(
        id: 'human-generator',
        isUser: true,
        authorType: ChatMessageAuthorType.human,
        agentId: AgentId.generator,
        agentType: AgentType.generator,
      ),
      _message(id: 'generator'),
      _message(
        id: 'reviewer',
        isUser: true,
        authorType: ChatMessageAuthorType.reviewerCodex,
        agentId: AgentId.reviewer,
        agentType: AgentType.reviewer,
        visibility: AgentVisibilityMode.collapsed,
      ),
      _message(
        id: 'summary',
        agentId: AgentId.summary,
        agentType: AgentType.summary,
      ),
      _message(
        id: 'hidden-reviewer',
        isUser: true,
        authorType: ChatMessageAuthorType.reviewerCodex,
        agentId: AgentId.reviewer,
        agentType: AgentType.reviewer,
        visibility: AgentVisibilityMode.hidden,
      ),
    ];

    expect(
      filterVisibleMessages(
        messages,
        displayMode: AgentDisplayMode.showAll,
      ).map((message) => message.id),
      <String>['human', 'human-generator', 'generator', 'reviewer', 'summary'],
    );
    expect(
      filterVisibleMessages(
        messages,
        displayMode: AgentDisplayMode.collapseSpecialists,
      ).map((message) => message.id),
      <String>['human', 'human-generator', 'generator', 'summary'],
    );
    expect(
      filterVisibleMessages(
        messages,
        displayMode: AgentDisplayMode.summaryOnly,
      ).map((message) => message.id),
      <String>['human', 'human-generator', 'summary'],
    );
  });

  test('chat controller sends audio to the captured session override',
      () async {
    final fakeApiClient = _FakeApiClient();
    final controller = ChatController(
      apiClient: fakeApiClient,
      notificationService: const NoopChatNotificationService(),
    );

    await controller.selectSession('session-b');
    final didSend = await controller.sendAudioMessage(
      XFile.fromData(Uint8List.fromList(const <int>[1, 2, 3]),
          name: 'voice-note.m4a'),
      message: 'Explain this voice note',
      sessionIdOverride: 'session-a',
      workspacePathOverride: '/workspace/a',
    );

    expect(didSend, isTrue);
    expect(fakeApiClient.lastAudioSessionId, 'session-a');
    expect(fakeApiClient.lastAudioWorkspacePath, '/workspace/a');
    expect(fakeApiClient.lastAudioMessage, 'Explain this voice note');
    expect(controller.selectedSessionId, 'session-b');

    controller.dispose();
  });

  test('chat controller exposes optimistic audio message while sending',
      () async {
    final fakeApiClient = _FakeApiClient(
      audioSendDelays: <String, Duration>{
        'session-a': const Duration(milliseconds: 40),
      },
    );
    final controller = ChatController(
      apiClient: fakeApiClient,
      notificationService: const NoopChatNotificationService(),
    );

    await controller.selectSession('session-a');
    final sendFuture = controller.sendAudioMessage(
      XFile.fromData(
        Uint8List.fromList(const <int>[1, 2, 3]),
        name: 'voice-note.m4a',
      ),
      sessionIdOverride: 'session-a',
      workspacePathOverride: '/workspace/a',
    );

    final optimisticMessage = controller.messages.single;
    expect(optimisticMessage.text, 'Sending voice...');
    expect(optimisticMessage.isUser, isTrue);
    expect(optimisticMessage.status, ChatMessageStatus.sending);
    expect(
      controller.outgoingUploadSummaryForSession('session-a')?.audioCount,
      1,
    );

    expect(await sendFuture, isTrue);
    expect(controller.messages, isEmpty);
    expect(controller.outgoingUploadSummaryForSession('session-a'), isNull);

    controller.dispose();
  });

  test('chat controller removes optimistic audio message on send failure',
      () async {
    final fakeApiClient = _FakeApiClient(failAudioSends: true);
    final controller = ChatController(
      apiClient: fakeApiClient,
      notificationService: const NoopChatNotificationService(),
    );

    await controller.selectSession('session-a');
    final sendFuture = controller.sendAudioMessage(
      XFile.fromData(
        Uint8List.fromList(const <int>[1, 2, 3]),
        name: 'voice-note.m4a',
      ),
      sessionIdOverride: 'session-a',
      workspacePathOverride: '/workspace/a',
    );

    expect(controller.messages.single.text, 'Sending voice...');
    expect(await sendFuture, isFalse);
    expect(controller.messages, isEmpty);
    expect(controller.errorText, contains('Failed to send audio message.'));

    controller.dispose();
  });

  test('chat controller keeps overlapping audio sends isolated across chats',
      () async {
    final fakeApiClient = _FakeApiClient(
      audioSendDelays: <String, Duration>{
        'session-a': const Duration(milliseconds: 40),
        'session-b': const Duration(milliseconds: 5),
      },
    );
    final controller = ChatController(
      apiClient: fakeApiClient,
      notificationService: const NoopChatNotificationService(),
    );

    await controller.selectSession('session-a');
    final firstSend = controller.sendAudioMessage(
      XFile.fromData(
        Uint8List.fromList(const <int>[1, 2, 3]),
        name: 'voice-a.m4a',
      ),
      sessionIdOverride: 'session-a',
      workspacePathOverride: '/workspace/a',
    );

    await controller.selectSession('session-b');
    final secondSend = controller.sendAudioMessage(
      XFile.fromData(
        Uint8List.fromList(const <int>[4, 5, 6]),
        name: 'voice-b.m4a',
      ),
      sessionIdOverride: 'session-b',
      workspacePathOverride: '/workspace/b',
    );

    final results =
        await Future.wait<bool>(<Future<bool>>[firstSend, secondSend]);

    expect(results, everyElement(isTrue));
    expect(controller.selectedSessionId, 'session-b');
    expect(
      fakeApiClient.audioSends
          .map((send) => '${send.sessionId}:${send.workspacePath}')
          .toList(),
      <String>[
        'session-a:/workspace/a',
        'session-b:/workspace/b',
      ],
    );

    controller.dispose();
  });

  testWidgets('chat screen renders optimistic audio upload in the timeline',
      (tester) async {
    tester.view.physicalSize = const Size(1280, 1600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final fakeApiClient = _FakeApiClient(
      audioSendDelays: <String, Duration>{
        'session-a': const Duration(milliseconds: 40),
      },
    );
    final controller = ChatController(
      apiClient: fakeApiClient,
      notificationService: const NoopChatNotificationService(),
    );

    await controller.selectSession('session-a');

    await tester.pumpWidget(
      MaterialApp(
        home: ChatScreen(
          initialApiBaseUrl: 'http://localhost:8000',
          notificationService: const NoopChatNotificationService(),
          controllerOverride: controller,
          enableServerBootstrap: false,
        ),
      ),
    );
    await tester.pumpAndSettle();

    final sendFuture = controller.sendAudioMessage(
      XFile.fromData(
        Uint8List.fromList(const <int>[1, 2, 3]),
        name: 'voice-note.m4a',
      ),
      sessionIdOverride: 'session-a',
      workspacePathOverride: '/workspace/a',
    );
    await tester.pump();

    expect(find.text('Sending voice...'), findsOneWidget);
    expect(find.byType(ChatBubble), findsOneWidget);
    final bubble = tester.widget<ChatBubble>(find.byType(ChatBubble));
    expect(bubble.message.isUser, isTrue);
    expect(bubble.message.status, ChatMessageStatus.sending);

    await tester.pump(const Duration(milliseconds: 50));
    expect(await sendFuture, isTrue);
    await tester.pump();
    expect(find.text('Sending voice...'), findsNothing);

    await tester.pumpWidget(const SizedBox.shrink());
    controller.dispose();
  });

  test('chat controller updates per-chat agent configuration', () async {
    final fakeApiClient = _FakeApiClient();
    final controller = ChatController(
      apiClient: fakeApiClient,
      notificationService: const NoopChatNotificationService(),
    );

    await controller.selectSession('session-a');
    final didUpdate = await controller.updateAgentConfiguration(
      kDefaultAgentConfiguration.copyWith(
        preset: AgentPreset.review,
        displayMode: AgentDisplayMode.summaryOnly,
        agents: kDefaultAgentDefinitions.map((agent) {
          if (agent.agentId == AgentId.reviewer) {
            return agent.copyWith(enabled: true, model: 'gpt-5.4-mini');
          }
          return agent;
        }).toList(),
      ),
    );

    expect(didUpdate, isTrue);
    expect(fakeApiClient.lastAgentConfiguration?.preset, AgentPreset.review);
    expect(
      fakeApiClient.lastAgentConfiguration?.displayMode,
      AgentDisplayMode.summaryOnly,
    );
    expect(
      controller.currentSession?.agentConfiguration.displayMode,
      AgentDisplayMode.summaryOnly,
    );

    controller.dispose();
  });

  test('chat controller keeps per-chat agent configuration isolated', () async {
    final fakeApiClient = _FakeApiClient();
    final controller = ChatController(
      apiClient: fakeApiClient,
      notificationService: const NoopChatNotificationService(),
    );

    await controller.selectSession('session-a');
    final didUpdate = await controller.updateAgentConfiguration(
      kDefaultAgentConfiguration.copyWith(
        preset: AgentPreset.review,
        displayMode: AgentDisplayMode.summaryOnly,
        agents: kDefaultAgentDefinitions.map((agent) {
          if (agent.agentId == AgentId.reviewer) {
            return agent.copyWith(enabled: true, label: 'A Reviewer');
          }
          return agent;
        }).toList(),
      ),
    );
    expect(didUpdate, isTrue);

    await controller.selectSession('session-b');
    expect(
        controller.currentSession?.agentConfiguration.preset, AgentPreset.solo);
    expect(
      controller.currentSession?.agentConfiguration
          .byId(AgentId.reviewer)
          ?.enabled,
      isFalse,
    );

    await controller.selectSession('session-a');
    expect(
      controller.currentSession?.agentConfiguration.preset,
      AgentPreset.review,
    );
    expect(
      controller.currentSession?.agentConfiguration
          .byId(AgentId.reviewer)
          ?.label,
      'A Reviewer',
    );

    controller.dispose();
  });

  test('chat controller recovers uncertain follow-up state', () async {
    final fakeApiClient = _FakeApiClient();
    final controller = ChatController(
      apiClient: fakeApiClient,
      notificationService: const NoopChatNotificationService(),
    );

    await controller.selectSession('session-a');
    final didRecover = await controller.recoverMessage(
      'message-unknown',
      action: MessageRecoveryAction.retry,
    );

    expect(didRecover, isTrue);
    expect(fakeApiClient.lastRecoveredMessageId, 'message-unknown');
    expect(fakeApiClient.lastRecoveryAction, MessageRecoveryAction.retry);
    expect(controller.currentSession?.messages, isNotEmpty);
    expect(
      controller.currentSession?.messages.first.status,
      ChatMessageStatus.submissionPending,
    );

    controller.dispose();
  });

  test('chat controller saves full agent profile packs', () async {
    final fakeApiClient = _FakeApiClient();
    final controller = ChatController(
      apiClient: fakeApiClient,
      notificationService: const NoopChatNotificationService(),
    );

    final configuration = kDefaultAgentConfiguration.copyWith(
      preset: AgentPreset.triad,
      displayMode: AgentDisplayMode.summaryOnly,
      agents: kDefaultAgentDefinitions.map((agent) {
        if (agent.agentId == AgentId.generator) {
          return agent.copyWith(
            label: 'Agent Creator',
            prompt: 'Design reusable agent packs.',
          );
        }
        if (agent.agentId == AgentId.reviewer) {
          return agent.copyWith(enabled: true, label: 'Pack Reviewer');
        }
        return agent.copyWith(enabled: true, label: 'Pack Summary');
      }).toList(),
    );

    final profile = await controller.createAgentProfile(
      name: 'Agent Creator Pack',
      description: 'Designs and critiques reusable packs.',
      colorHex: '#F28C28',
      configuration: configuration,
    );

    expect(profile, isNotNull);
    expect(fakeApiClient.lastCreatedAgentProfileConfiguration?.preset,
        AgentPreset.triad);
    expect(
      fakeApiClient.lastCreatedAgentProfileConfiguration?.displayMode,
      AgentDisplayMode.summaryOnly,
    );
    expect(
        controller.agentProfiles.any((item) => item.id == profile!.id), isTrue);

    controller.dispose();
  });

  test('chat controller auto-imports agent creator blueprints', () async {
    final fakeApiClient = _FakeApiClient();
    fakeApiClient.sessionOverrides['session-a'] = SessionDetail(
      id: 'session-a',
      title: 'Chat A',
      workspacePath: '/workspace/a',
      workspaceName: 'A',
      agentProfileId: 'agent_creator',
      agentProfileName: 'Agent Creator',
      agentProfileColor: '#F28C28',
      createdAt: _FakeApiClient._timestamp,
      updatedAt: _FakeApiClient._timestamp,
      messages: <ChatMessage>[
        ChatMessage(
          id: 'creator-message',
          text: '''
Built the draft.

```agent-profile
{
  "id": "api_guardian",
  "name": "API Guardian",
  "description": "Reviews API changes for regressions.",
  "color_hex": "#1188AA",
  "prompt": "Review API changes for regressions, compatibility risks, and release blockers."
}
```
''',
          isUser: false,
          authorType: ChatMessageAuthorType.assistant,
          status: ChatMessageStatus.completed,
          createdAt: _FakeApiClient._timestamp,
          updatedAt: _FakeApiClient._timestamp,
        ),
      ],
    );
    final controller = ChatController(
      apiClient: fakeApiClient,
      notificationService: const NoopChatNotificationService(),
    );

    await controller.refreshAgentProfiles();
    await controller.selectSession('session-a');

    expect(fakeApiClient.importedProfiles, hasLength(1));
    expect(fakeApiClient.importedProfiles.single.id, 'api_guardian');
    expect(
      controller.agentProfiles.any((profile) => profile.id == 'api_guardian'),
      isTrue,
    );

    controller.dispose();
  });

  test('chat controller applies full agent profile packs to the session',
      () async {
    final fakeApiClient = _FakeApiClient();
    final controller = ChatController(
      apiClient: fakeApiClient,
      notificationService: const NoopChatNotificationService(),
    );

    await controller.selectSession('session-a');
    final didApply = await controller.applyAgentProfile('agent-pack');

    expect(didApply, isTrue);
    expect(fakeApiClient.lastAppliedAgentProfileId, 'agent-pack');
    expect(controller.currentSession?.agentProfileName, 'Agent Pack');
    expect(controller.currentSession?.agentConfiguration.preset,
        AgentPreset.review);
    expect(
      controller.currentSession?.agentConfiguration.displayMode,
      AgentDisplayMode.collapseSpecialists,
    );
    expect(
      controller.currentSession?.agentConfiguration
          .byId(AgentId.reviewer)
          ?.label,
      'Pack Reviewer',
    );

    controller.dispose();
  });

  test('chat controller exports and imports agent profiles as JSON', () async {
    final fakeApiClient = _FakeApiClient();
    final controller = ChatController(
      apiClient: fakeApiClient,
      notificationService: const NoopChatNotificationService(),
    );

    final exportedJson = await controller.exportAgentProfilesAsJson();
    expect(exportedJson, isNotNull);
    expect(exportedJson, contains('agent-pack'));

    final didImport = await controller.importAgentProfilesFromJson(
      exportedJson!,
    );
    expect(didImport, isTrue);
    expect(fakeApiClient.importedProfiles, isNotEmpty);

    controller.dispose();
  });

  test('api client serializes and deserializes agent configuration round trip',
      () async {
    Map<String, dynamic>? receivedBody;
    final client = ApiClient(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        receivedBody = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(
          jsonEncode(<String, dynamic>{
            'id': 'session-a',
            'title': 'Chat A',
            'workspace_path': '/workspace/a',
            'workspace_name': 'A',
            'created_at': DateTime.utc(2026, 1, 1).toIso8601String(),
            'updated_at': DateTime.utc(2026, 1, 1).toIso8601String(),
            'messages': const <dynamic>[],
            'agent_configuration': receivedBody,
          }),
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );
    final session = await client.updateAgentConfiguration(
      'session-a',
      configuration: kDefaultAgentConfiguration.copyWith(
        preset: AgentPreset.review,
        displayMode: AgentDisplayMode.collapseSpecialists,
        agents: kDefaultAgentDefinitions.map((agent) {
          if (agent.agentId == AgentId.reviewer) {
            return agent.copyWith(enabled: true, model: 'gpt-5.4-mini');
          }
          return agent;
        }).toList(),
      ),
    );

    expect(receivedBody?['preset'], 'review');
    expect(receivedBody?['display_mode'], 'collapse_specialists');
    expect(receivedBody?['turn_budget_mode'], 'each_agent');
    expect(
      (receivedBody?['agents'] as List<dynamic>).length,
      kDefaultAgentDefinitions.length,
    );
    final reviewerPayload = (receivedBody?['agents'] as List<dynamic>)
        .cast<Map<String, dynamic>>()
        .firstWhere((agent) => agent['agent_id'] == 'reviewer');
    expect(reviewerPayload['model'], 'gpt-5.4-mini');
    expect(session.agentConfiguration.preset, AgentPreset.review);
    expect(
      session.agentConfiguration.displayMode,
      AgentDisplayMode.collapseSpecialists,
    );
    expect(
      session.agentConfiguration.agents.length,
      kDefaultAgentDefinitions.length,
    );
    expect(session.agentConfiguration.byId(AgentId.reviewer)?.enabled, isTrue);
    expect(
      session.agentConfiguration.byId(AgentId.reviewer)?.model,
      'gpt-5.4-mini',
    );
    expect(
      session.agentConfiguration.byId(AgentId.supervisor)?.label,
      kDefaultAgentConfiguration.byId(AgentId.supervisor)?.label,
    );
  });

  test('agent definition copyWith can clear a model override', () {
    final original = kDefaultAgentDefinitions
        .firstWhere((agent) => agent.agentId == AgentId.generator)
        .copyWith(model: 'gpt-5.4-mini');

    final cleared = original.copyWith(model: null);

    expect(original.model, 'gpt-5.4-mini');
    expect(cleared.model, isNull);
  });

  test('api client omits cleared model overrides from agent configuration',
      () async {
    Map<String, dynamic>? receivedBody;
    final client = ApiClient(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        receivedBody = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(
          jsonEncode(<String, dynamic>{
            'id': 'session-a',
            'title': 'Chat A',
            'workspace_path': '/workspace/a',
            'workspace_name': 'A',
            'created_at': DateTime.utc(2026, 1, 1).toIso8601String(),
            'updated_at': DateTime.utc(2026, 1, 1).toIso8601String(),
            'messages': const <dynamic>[],
            'agent_configuration': receivedBody,
          }),
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    final generatorWithModel = kDefaultAgentDefinitions
        .firstWhere((agent) => agent.agentId == AgentId.generator)
        .copyWith(model: 'gpt-5.4-mini');
    final generatorWithoutModel = generatorWithModel.copyWith(model: null);

    final configuration = kDefaultAgentConfiguration.copyWith(
      agents: kDefaultAgentDefinitions.map((agent) {
        if (agent.agentId == AgentId.generator) {
          return generatorWithoutModel;
        }
        return agent;
      }).toList(),
    );

    final session = await client.updateAgentConfiguration(
      'session-a',
      configuration: configuration,
    );

    final generatorPayload = (receivedBody?['agents'] as List<dynamic>)
        .cast<Map<String, dynamic>>()
        .firstWhere((agent) => agent['agent_id'] == 'generator');

    expect(generatorPayload.containsKey('model'), isFalse);
    expect(session.agentConfiguration.byId(AgentId.generator)?.model, isNull);
  });

  test('api client serializes and deserializes agent profile packs', () async {
    Map<String, dynamic>? receivedBody;
    final configuration = kDefaultAgentConfiguration.copyWith(
      preset: AgentPreset.review,
      displayMode: AgentDisplayMode.collapseSpecialists,
      agents: kDefaultAgentDefinitions.map((agent) {
        if (agent.agentId == AgentId.generator) {
          return agent.copyWith(
            label: 'Pack Generator',
            prompt: 'Execute the saved pack.',
          );
        }
        if (agent.agentId == AgentId.reviewer) {
          return agent.copyWith(enabled: true, label: 'Pack Reviewer');
        }
        return agent.copyWith(enabled: false);
      }).toList(),
    );
    final client = ApiClient(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        receivedBody = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(
          jsonEncode(<String, dynamic>{
            'id': 'agent-pack',
            'name': 'Agent Pack',
            'description': 'Stored full studio pack.',
            'color_hex': '#1188AA',
            'prompt': 'Execute the saved pack.',
            'is_builtin': false,
            'configuration': receivedBody?['configuration'],
          }),
          201,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    final profile = await client.createAgentProfile(
      name: 'Agent Pack',
      description: 'Stored full studio pack.',
      colorHex: '#1188AA',
      configuration: configuration,
    );

    expect(receivedBody?['configuration']['preset'], 'review');
    expect(
        receivedBody?['configuration']['display_mode'], 'collapse_specialists');
    expect(receivedBody?['configuration']['turn_budget_mode'], 'each_agent');
    expect(profile.configuration.preset, AgentPreset.review);
    expect(
      profile.configuration.byId(AgentId.reviewer)?.label,
      'Pack Reviewer',
    );
  });

  test('chat controller builds reviewer-specific completion notifications',
      () async {
    final controller = ChatController(
      apiClient: _FakeApiClient(),
      notificationService: const NoopChatNotificationService(),
    );

    await controller.selectSession('session-a');
    final notification = controller.buildTerminalNotificationForTesting(
      const JobStatusResponse(
        jobId: 'job-reviewer',
        sessionId: 'session-a',
        status: 'completed',
        elapsedSeconds: 2,
        agentId: AgentId.reviewer,
        agentType: AgentType.reviewer,
        response: 'Add one more test around the retry path.',
      ),
    );

    expect(notification, isNotNull);
    expect(notification.title, 'A');
    expect(notification.channel, ChatNotificationChannel.reviewer);
    expect(notification.body, contains('Reviewer reply ready'));
    expect(notification.summary, 'Reviewer • Chat A');

    controller.dispose();
  });
}

String _composerTextContaining(WidgetTester tester, String needle) {
  for (final editable in tester.widgetList<EditableText>(
    find.byType(EditableText),
  )) {
    final text = editable.controller.text;
    if (text.contains(needle)) {
      return text;
    }
  }
  throw StateError('No composer text contained "$needle".');
}

Future<void> _pumpChatAndStageSingleFeedbackAttachment(
  WidgetTester tester, {
  required ChatController controller,
  required FeedbackQueueItem feedbackItem,
  AudioNoteRecorder Function()? audioRecorderFactory,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      home: ChatScreen(
        initialApiBaseUrl: 'http://localhost:8000',
        notificationService: const NoopChatNotificationService(),
        controllerOverride: controller,
        enableServerBootstrap: false,
        audioRecorderFactoryOverride: audioRecorderFactory,
        initialSidebarWorkspaces: const <Workspace>[
          Workspace(
            name: 'Ambientando Calendar',
            path: '/workspace/ambientando-calendar',
          ),
        ],
        feedbackQueueListLoaderOverride: (_, {required includeImages}) async {
          return <FeedbackQueueItem>[feedbackItem];
        },
      ),
    ),
  );
  await tester.pump(const Duration(milliseconds: 100));
  await tester.pump();

  await tester.tap(find.byTooltip('Projects'));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Ambientando Calendar'));
  await tester.pumpAndSettle();
  await tester.tap(find.widgetWithText(FilledButton, 'Feedback queue (1)'));
  await tester.pumpAndSettle();
  await tester.tap(find.widgetWithText(CheckboxListTile, feedbackItem.comment));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Next'));
  await tester.pumpAndSettle();
}

int _occurrences(String value, String needle) {
  return RegExp(RegExp.escape(needle)).allMatches(value).length;
}

FeedbackQueueItem _feedbackItem({
  required String id,
  required String sourceApp,
  required String comment,
  String? sourceDisplayName,
}) {
  const transparentPng =
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=';
  return FeedbackQueueItem(
    id: id,
    sourceApp: sourceApp,
    sourceDisplayName: sourceDisplayName,
    comment: comment,
    createdAt: DateTime.utc(2026, 6, 8),
    status: 'pending',
    hasScreenshot: true,
    screenshotPngBase64: transparentPng,
    selectionPoints: const <Map<String, double>>[
      <String, double>{'x': 1, 'y': 2},
      <String, double>{'x': 3, 'y': 4},
    ],
    selectionBounds: const <String, double>{
      'left': 1,
      'top': 2,
      'width': 30,
      'height': 40,
    },
  );
}

SddCodexActionSubmissionResult _jobResponse({
  required String jobId,
  required String sessionId,
}) {
  return SddCodexActionSubmissionResult(
    jobId: jobId,
    sessionId: sessionId,
    status: 'pending',
  );
}

Finder _codexDevBannerFinder() {
  return find.byWidgetPredicate(
    (widget) => widget is Banner && widget.message == 'CODEX DEV',
  );
}

Future<void> _pumpSddWrapper(
  WidgetTester tester, {
  required Future<SddProject?> Function(String bridgeUrl) loader,
  MermaidDiagramRenderer? diagramRenderer,
  SddFeedbackSubmitter? feedbackSubmitter,
  SddCodexActionSubmitter? actionSubmitter,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      home: CodexBridgeDevModeWrapper(
        enabled: true,
        bridgeUrl: 'http://bridge.test',
        diagramRenderer: diagramRenderer,
        explorerLoader: loader,
        sddFeedbackSubmitter: feedbackSubmitter,
        sddActionSubmitter: actionSubmitter,
        child: const Text('normal app'),
      ),
    ),
  );
}

Map<String, dynamic> _sddProjectsIndexJson() {
  return <String, dynamic>{
    'kind': 'codex.sddProjects',
    'version': 1,
    'default_workspace_path': '/workspace/codex-cli-mobile-bridge',
    'projects': <Map<String, dynamic>>[
      <String, dynamic>{
        'workspace_name': 'Codex Bridge',
        'workspace_path': '/workspace/codex-cli-mobile-bridge',
        'has_manifest': true,
        'has_constitution': true,
        'spec_count': 2,
        'diagram_count': 2,
        'missing_required': <String>[],
      },
    ],
  };
}

Map<String, dynamic> _sddProjectJson() {
  return <String, dynamic>{
    'kind': 'codex.sddProject',
    'version': 1,
    'workspace_name': 'Codex Bridge',
    'workspace_path': '/workspace/codex-cli-mobile-bridge',
    'required': true,
    'manifest': <String, dynamic>{
      'path': 'codex-bridge.yaml',
      'title': null,
      'size_bytes': 40,
      'content': 'kind: codex.bridge.project\nname: Codex Bridge',
    },
    'constitution': <String, dynamic>{
      'path': '.specify/memory/constitution.md',
      'title': 'Constitution',
      'size_bytes': 120,
      'content': '# Constitution\n\nSDD is mandatory.',
    },
    'architecture_diagrams': <Map<String, dynamic>>[
      <String, dynamic>{
        'path': 'architecture/components.mmd',
        'title': null,
        'size_bytes': 42,
        'content': 'flowchart LR\nA --> B',
        'diagram_type': 'flowchart',
        'scope': 'architecture',
      },
    ],
    'specs': <Map<String, dynamic>>[
      <String, dynamic>{
        'id': '001-codex-bridge-sdd-wrapper',
        'title': 'Bridge Contract',
        'path': 'specs/001-codex-bridge-sdd-wrapper',
        'missing': <String>[],
        'spec': <String, dynamic>{
          'path': 'specs/001-codex-bridge-sdd-wrapper/spec.md',
          'title': 'Bridge Contract',
          'size_bytes': 80,
          'content': '# Bridge Contract',
        },
        'plan': <String, dynamic>{
          'path': 'specs/001-codex-bridge-sdd-wrapper/plan.md',
          'title': 'Plan',
          'size_bytes': 50,
          'content': '# Plan',
        },
        'tasks': <String, dynamic>{
          'path': 'specs/001-codex-bridge-sdd-wrapper/tasks.md',
          'title': 'Tasks',
          'size_bytes': 50,
          'content': '# Tasks\n\n- [x] Done\n- [ ] Pending',
        },
        'slice_docs': <Map<String, dynamic>>[
          <String, dynamic>{
            'path': 'specs/001-codex-bridge-sdd-wrapper/slices/01-slice.md',
            'title': 'Slice One',
            'size_bytes': 70,
            'content': '# Slice One',
          },
        ],
        'diagrams': <Map<String, dynamic>>[],
      },
      <String, dynamic>{
        'id': '002-sdd-visual-workbench',
        'title': 'Visual Workbench',
        'path': 'specs/002-sdd-visual-workbench',
        'missing': <String>[],
        'spec': <String, dynamic>{
          'path': 'specs/002-sdd-visual-workbench/spec.md',
          'title': 'Visual Workbench',
          'size_bytes': 100,
          'content': '# Visual Workbench',
        },
        'plan': <String, dynamic>{
          'path': 'specs/002-sdd-visual-workbench/plan.md',
          'title': 'Plan',
          'size_bytes': 50,
          'content': '# Plan',
        },
        'tasks': <String, dynamic>{
          'path': 'specs/002-sdd-visual-workbench/tasks.md',
          'title': 'Tasks',
          'size_bytes': 50,
          'content': '# Tasks',
        },
        'slice_docs': <Map<String, dynamic>>[],
        'diagrams': <Map<String, dynamic>>[
          <String, dynamic>{
            'path': 'specs/002-sdd-visual-workbench/diagrams/components.mmd',
            'title': null,
            'size_bytes': 64,
            'content': 'flowchart LR\nWorkbench --> API',
            'diagram_type': 'flowchart',
            'scope': '002-sdd-visual-workbench',
          },
        ],
      },
    ],
    'missing_required': <String>[],
  };
}

Map<String, dynamic> _sddProjectWithoutDiagramsJson() {
  final json = _sddProjectJson();
  json['architecture_diagrams'] = <Map<String, dynamic>>[];
  json['specs'] = <Map<String, dynamic>>[];
  return json;
}

Map<String, dynamic> _sddProjectWithMissingJson() {
  final json = _sddProjectJson();
  json['manifest'] = null;
  json['missing_required'] = <String>['codex-bridge.yaml'];
  return json;
}

Map<String, dynamic> _sddProjectDiagramsJson() {
  return <String, dynamic>{
    'kind': 'codex.sddProjectDiagrams',
    'version': 1,
    'workspace_path': '/workspace/codex-cli-mobile-bridge',
    'diagrams': <Map<String, dynamic>>[
      <String, dynamic>{
        'path': 'architecture/components.mmd',
        'title': null,
        'size_bytes': 42,
        'content': 'flowchart LR\nA --> B',
        'diagram_type': 'flowchart',
        'scope': 'architecture',
      },
      <String, dynamic>{
        'path': 'specs/002-sdd-visual-workbench/diagrams/components.mmd',
        'title': null,
        'size_bytes': 64,
        'content': 'flowchart LR\nWorkbench --> API',
        'diagram_type': 'flowchart',
        'scope': '002-sdd-visual-workbench',
      },
    ],
  };
}

class _FakeMermaidRenderer implements MermaidDiagramRenderer {
  _FakeMermaidRenderer(this._render);

  factory _FakeMermaidRenderer.success() {
    return _FakeMermaidRenderer((diagram) async {
      return MermaidRenderResult.success(
        kind: 'fake',
        preview: SizedBox(
          width: 420,
          height: 160,
          child: Text('rendered ${diagram.path}'),
        ),
      );
    });
  }

  factory _FakeMermaidRenderer.failure(String message) {
    return _FakeMermaidRenderer((_) async {
      return MermaidRenderResult.failure(message);
    });
  }

  final Future<MermaidRenderResult> Function(SddDiagram diagram) _render;
  int calls = 0;

  @override
  Future<MermaidRenderResult> render(SddDiagram diagram) {
    calls += 1;
    return _render(diagram);
  }
}

class _FakeMermaidAssetBundle extends CachingAssetBundle {
  _FakeMermaidAssetBundle(this.asset);

  final String asset;

  @override
  Future<ByteData> load(String key) async {
    final bytes = Uint8List.fromList(utf8.encode(asset));
    return ByteData.view(bytes.buffer);
  }

  @override
  Future<String> loadString(String key, {bool cache = true}) async {
    return asset;
  }
}

class _FakeApiClient extends ApiClient {
  _FakeApiClient({
    this.audioSendDelays = const <String, Duration>{},
    this.failAudioSends = false,
    this.failAttachmentSends = false,
  }) : super(baseUrl: 'http://localhost:8000');

  String? lastAudioSessionId;
  String? lastAudioWorkspacePath;
  String? lastAudioMessage;
  AgentConfiguration? lastAgentConfiguration;
  AgentConfiguration? lastCreatedAgentProfileConfiguration;
  String? lastAppliedAgentProfileId;
  List<AgentProfile> importedProfiles = <AgentProfile>[];
  String? lastRecoveredMessageId;
  MessageRecoveryAction? lastRecoveryAction;
  final Map<String, Duration> audioSendDelays;
  final bool failAudioSends;
  final bool failAttachmentSends;
  final List<_RecordedAudioSend> audioSends = <_RecordedAudioSend>[];
  final List<_RecordedAttachmentSend> attachmentSends =
      <_RecordedAttachmentSend>[];
  final Map<String, AgentConfiguration> _sessionConfigurations =
      <String, AgentConfiguration>{};
  final Map<String, SessionDetail> sessionOverrides = <String, SessionDetail>{};
  final List<AgentProfile> _agentProfiles = <AgentProfile>[
    AgentProfile(
      id: 'default',
      name: 'Generator',
      description: 'Default generator.',
      colorHex: '#55D6BE',
      prompt: kDefaultAgentDefinitions.first.prompt,
      configuration: kDefaultAgentConfiguration,
      isBuiltin: true,
    ),
    AgentProfile(
      id: 'agent-pack',
      name: 'Agent Pack',
      description: 'Full stored pack.',
      colorHex: '#1188AA',
      prompt: 'Execute the saved pack.',
      configuration: kDefaultAgentConfiguration.copyWith(
        preset: AgentPreset.review,
        displayMode: AgentDisplayMode.collapseSpecialists,
        agents: kDefaultAgentDefinitions.map((agent) {
          if (agent.agentId == AgentId.generator) {
            return agent.copyWith(
              label: 'Agent Pack',
              prompt: 'Execute the saved pack.',
            );
          }
          if (agent.agentId == AgentId.reviewer) {
            return agent.copyWith(enabled: true, label: 'Pack Reviewer');
          }
          return agent.copyWith(enabled: false);
        }).toList(),
      ),
    ),
  ];

  static final DateTime _timestamp = DateTime.utc(2026, 1, 1);

  @override
  Future<SessionDetail> createSession({
    String? title,
    String? workspacePath,
    String? agentProfileId,
    bool turnSummariesEnabled = false,
  }) async {
    final resolvedWorkspacePath = workspacePath ?? '/workspace/a';
    final session = SessionDetail(
      id: 'created-session',
      title: title ?? 'New chat',
      workspacePath: resolvedWorkspacePath,
      workspaceName: resolvedWorkspacePath.split('/').last,
      agentProfileId: agentProfileId ?? 'default',
      agentProfileName: 'Generator',
      agentProfileColor: '#55D6BE',
      agentConfiguration: kDefaultAgentConfiguration,
      turnSummariesEnabled: turnSummariesEnabled,
      createdAt: _timestamp,
      updatedAt: _timestamp,
      messages: const <ChatMessage>[],
    );
    sessionOverrides[session.id] = session;
    return session;
  }

  @override
  Future<List<ChatSessionSummary>> listSessions() async {
    return <ChatSessionSummary>[
      ChatSessionSummary(
        id: 'session-a',
        title: 'Chat A',
        workspacePath: '/workspace/a',
        workspaceName: 'A',
        agentProfileId: 'default',
        agentProfileName: 'Generator',
        agentProfileColor: '#55D6BE',
        createdAt: _timestamp,
        updatedAt: _timestamp,
      ),
      ChatSessionSummary(
        id: 'session-b',
        title: 'Chat B',
        workspacePath: '/workspace/b',
        workspaceName: 'B',
        agentProfileId: 'default',
        agentProfileName: 'Generator',
        agentProfileColor: '#55D6BE',
        createdAt: _timestamp,
        updatedAt: _timestamp,
      ),
      for (final session in sessionOverrides.values)
        ChatSessionSummary(
          id: session.id,
          title: session.title,
          workspacePath: session.workspacePath,
          workspaceName: session.workspaceName,
          agentProfileId: session.agentProfileId,
          agentProfileName: session.agentProfileName,
          agentProfileColor: session.agentProfileColor,
          createdAt: session.createdAt,
          updatedAt: session.updatedAt,
        ),
    ];
  }

  @override
  Future<List<AgentProfile>> listAgentProfiles() async {
    return List<AgentProfile>.from(_agentProfiles);
  }

  @override
  Future<List<AgentProfile>> exportAgentProfiles() async {
    return List<AgentProfile>.from(
      _agentProfiles.where((profile) => !profile.isBuiltin),
    );
  }

  @override
  Future<SessionDetail> getSession(String sessionId) async {
    final override = sessionOverrides[sessionId];
    if (override != null) {
      return override;
    }
    return SessionDetail(
      id: sessionId,
      title: sessionId == 'session-a' ? 'Chat A' : 'Chat B',
      workspacePath: sessionId == 'session-a' ? '/workspace/a' : '/workspace/b',
      workspaceName: sessionId == 'session-a' ? 'A' : 'B',
      agentProfileId: 'default',
      agentProfileName: 'Generator',
      agentProfileColor: '#55D6BE',
      agentConfiguration:
          _sessionConfigurations[sessionId] ?? kDefaultAgentConfiguration,
      createdAt: _timestamp,
      updatedAt: _timestamp,
      messages: const <ChatMessage>[],
    );
  }

  @override
  Future<JobStatusResponse> sendAudioMessage(
    XFile audioFile, {
    CodexRunOptions? codexRunOptions,
    String? sessionId,
    String? workspacePath,
    String? message,
    String? language,
  }) async {
    lastAudioSessionId = sessionId;
    lastAudioWorkspacePath = workspacePath;
    lastAudioMessage = message;
    audioSends.add(
      _RecordedAudioSend(
        sessionId: sessionId,
        workspacePath: workspacePath,
        message: message,
        filename: audioFile.name,
      ),
    );
    await Future<void>.delayed(audioSendDelays[sessionId] ?? Duration.zero);
    if (failAudioSends) {
      throw Exception('simulated audio failure');
    }
    return JobStatusResponse(
      jobId: 'job-audio-${audioSends.length}',
      sessionId: sessionId ?? 'session-a',
      status: 'pending',
      elapsedSeconds: 0,
    );
  }

  @override
  Future<JobStatusResponse> sendAttachmentsMessage(
    List<XFile> attachments, {
    String? message,
    String? sessionId,
    String? workspacePath,
    String? language,
    CodexRunOptions? codexRunOptions,
  }) async {
    attachmentSends.add(
      _RecordedAttachmentSend(
        sessionId: sessionId,
        workspacePath: workspacePath,
        message: message,
        filenames: attachments.map((attachment) => attachment.name).toList(),
      ),
    );
    if (failAttachmentSends) {
      throw Exception('simulated attachment failure');
    }
    return JobStatusResponse(
      jobId: 'job-attachments-${attachmentSends.length}',
      sessionId: sessionId ?? 'session-a',
      status: 'pending',
      elapsedSeconds: 0,
    );
  }

  @override
  Future<SessionDetail> updateAutoMode(
    String sessionId, {
    required bool enabled,
    required int maxTurns,
    String? reviewerPrompt,
  }) async {
    return SessionDetail(
      id: sessionId,
      title: sessionId == 'session-a' ? 'Chat A' : 'Chat B',
      workspacePath: sessionId == 'session-a' ? '/workspace/a' : '/workspace/b',
      workspaceName: sessionId == 'session-a' ? 'A' : 'B',
      agentProfileId: 'default',
      agentProfileName: 'Generator',
      agentProfileColor: '#55D6BE',
      autoModeEnabled: enabled,
      autoMaxTurns: maxTurns,
      autoReviewerPrompt: reviewerPrompt,
      createdAt: _timestamp,
      updatedAt: _timestamp,
      messages: const <ChatMessage>[],
    );
  }

  @override
  Future<SessionDetail> updateAgentConfiguration(
    String sessionId, {
    required AgentConfiguration configuration,
  }) async {
    lastAgentConfiguration = configuration;
    _sessionConfigurations[sessionId] = configuration;
    return SessionDetail(
      id: sessionId,
      title: sessionId == 'session-a' ? 'Chat A' : 'Chat B',
      workspacePath: sessionId == 'session-a' ? '/workspace/a' : '/workspace/b',
      workspaceName: sessionId == 'session-a' ? 'A' : 'B',
      agentProfileId: 'default',
      agentProfileName: 'Generator',
      agentProfileColor: '#55D6BE',
      agentConfiguration: configuration,
      createdAt: _timestamp,
      updatedAt: _timestamp,
      messages: const <ChatMessage>[],
    );
  }

  @override
  Future<AgentProfile> createAgentProfile({
    required String name,
    required String description,
    required String colorHex,
    required AgentConfiguration configuration,
  }) async {
    lastCreatedAgentProfileConfiguration = configuration;
    final profile = AgentProfile(
      id: 'created-pack',
      name: name,
      description: description,
      colorHex: colorHex,
      prompt: configuration.byId(AgentId.generator)?.prompt ?? '',
      configuration: configuration,
    );
    _agentProfiles.add(profile);
    return profile;
  }

  @override
  Future<SessionDetail> applyAgentProfile(
    String sessionId, {
    required String profileId,
  }) async {
    lastAppliedAgentProfileId = profileId;
    final profile = _agentProfiles.firstWhere((item) => item.id == profileId);
    _sessionConfigurations[sessionId] = profile.configuration;
    return SessionDetail(
      id: sessionId,
      title: sessionId == 'session-a' ? 'Chat A' : 'Chat B',
      workspacePath: sessionId == 'session-a' ? '/workspace/a' : '/workspace/b',
      workspaceName: sessionId == 'session-a' ? 'A' : 'B',
      agentProfileId: profile.id,
      agentProfileName: profile.name,
      agentProfileColor: profile.colorHex,
      agentConfiguration: profile.configuration,
      createdAt: _timestamp,
      updatedAt: _timestamp,
      messages: const <ChatMessage>[],
    );
  }

  @override
  Future<List<AgentProfile>> importAgentProfiles(
    List<AgentProfile> profiles,
  ) async {
    importedProfiles = List<AgentProfile>.from(profiles);
    _agentProfiles.addAll(profiles);
    return profiles;
  }

  @override
  Future<SessionDetail> recoverMessage(
    String sessionId,
    String messageId, {
    required MessageRecoveryAction action,
  }) async {
    lastRecoveredMessageId = messageId;
    lastRecoveryAction = action;
    return SessionDetail(
      id: sessionId,
      title: sessionId == 'session-a' ? 'Chat A' : 'Chat B',
      workspacePath: sessionId == 'session-a' ? '/workspace/a' : '/workspace/b',
      workspaceName: sessionId == 'session-a' ? 'A' : 'B',
      agentProfileId: 'default',
      agentProfileName: 'Generator',
      agentProfileColor: '#55D6BE',
      createdAt: _timestamp,
      updatedAt: _timestamp,
      messages: <ChatMessage>[
        ChatMessage(
          id: 'retry-message',
          text: '',
          isUser: false,
          authorType: ChatMessageAuthorType.assistant,
          status: ChatMessageStatus.submissionPending,
          createdAt: _timestamp,
          updatedAt: _timestamp,
        ),
      ],
    );
  }
}

class _RecordedAudioSend {
  const _RecordedAudioSend({
    required this.sessionId,
    required this.workspacePath,
    required this.message,
    required this.filename,
  });

  final String? sessionId;
  final String? workspacePath;
  final String? message;
  final String filename;
}

class _RecordedAttachmentSend {
  const _RecordedAttachmentSend({
    required this.sessionId,
    required this.workspacePath,
    required this.message,
    required this.filenames,
  });

  final String? sessionId;
  final String? workspacePath;
  final String? message;
  final List<String> filenames;
}

class _FakeAudioNoteRecorder extends AudioNoteRecorder {
  _FakeAudioNoteRecorder(this.audioFile) : super();

  final XFile audioFile;
  bool started = false;
  bool stopped = false;
  bool cleaned = false;
  bool disposed = false;

  @override
  Future<void> start() async {
    started = true;
  }

  @override
  Future<XFile?> stop() async {
    stopped = true;
    return audioFile;
  }

  @override
  Future<void> cleanup(XFile file) async {
    cleaned = true;
  }

  @override
  Future<void> cancel() async {}

  @override
  Future<void> dispose() async {
    disposed = true;
  }
}

Future<void> _pumpUserChatBubble(
  WidgetTester tester,
  String text, {
  List<ChatMessageAttachment> attachments = const <ChatMessageAttachment>[],
  String? attachmentBaseUrl,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: ChatBubble(
          message: ChatMessage(
            id: 'user-message',
            text: text,
            isUser: true,
            authorType: ChatMessageAuthorType.human,
            status: ChatMessageStatus.completed,
            createdAt: DateTime.utc(2026, 1, 1),
            updatedAt: DateTime.utc(2026, 1, 1),
            attachments: attachments,
          ),
          attachmentBaseUrl: attachmentBaseUrl,
        ),
      ),
    ),
  );
}

ChatMessage _message({
  required String id,
  bool isUser = false,
  ChatMessageAuthorType authorType = ChatMessageAuthorType.assistant,
  AgentId agentId = AgentId.generator,
  AgentType agentType = AgentType.generator,
  AgentVisibilityMode visibility = AgentVisibilityMode.visible,
}) {
  return ChatMessage(
    id: id,
    text: id,
    isUser: isUser,
    authorType: authorType,
    agentId: agentId,
    agentType: agentType,
    visibility: visibility,
    status: ChatMessageStatus.completed,
    createdAt: DateTime.utc(2026, 1, 1),
    updatedAt: DateTime.utc(2026, 1, 1),
  );
}
