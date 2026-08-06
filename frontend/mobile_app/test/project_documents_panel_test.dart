import 'dart:typed_data';

import 'package:codex_mobile_frontend/src/models/project_documents.dart';
import 'package:codex_mobile_frontend/src/services/api_client.dart';
import 'package:codex_mobile_frontend/src/widgets/project_documents_panel.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('shows latest charter preview and validation state', (
    WidgetTester tester,
  ) async {
    final apiClient = _ProjectDocumentsPanelApiClient(validationOk: false);
    var requestedPrompt = '';

    await _pumpPanel(
      tester,
      apiClient: apiClient,
      onRequestChange: (prompt) {
        requestedPrompt = prompt;
      },
    );

    expect(find.text('Acta de Proyecto'), findsWidgets);
    expect(_richTextContaining('Draft: v0.1'), findsOneWidget);
    expect(_richTextContaining('Validation: 1 blocking'), findsOneWidget);
    expect(find.text('logo_pending'), findsOneWidget);
    expect(find.textContaining('Choose logo decision'), findsOneWidget);
    expect(find.textContaining('Acta de Proyecto'), findsWidgets);
    expect(find.textContaining('window.bad'), findsNothing);

    final releaseButton = tester.widget<FilledButton>(
      find.widgetWithText(FilledButton, 'Create client version'),
    );
    expect(releaseButton.onPressed, isNull);

    await tester.ensureVisible(find.text('Request charter change'));
    await tester.tap(find.text('Request charter change'));
    await tester.pumpAndSettle();
    expect(requestedPrompt, contains('acta de proyecto'));
    expect(requestedPrompt, contains('version entregable'));
  });

  testWidgets('refreshes render and creates a client release when gates pass', (
    WidgetTester tester,
  ) async {
    final apiClient = _ProjectDocumentsPanelApiClient(staleRender: true);

    await _pumpPanel(tester, apiClient: apiClient);

    expect(_richTextContaining('Render: refresh needed'), findsOneWidget);
    var releaseButton = tester.widget<FilledButton>(
      find.widgetWithText(FilledButton, 'Create client version'),
    );
    expect(releaseButton.onPressed, isNull);

    await tester.ensureVisible(
      find.widgetWithText(OutlinedButton, 'Refresh render'),
    );
    await tester.tap(find.widgetWithText(OutlinedButton, 'Refresh render'));
    await tester.pumpAndSettle();

    expect(apiClient.renderCalls, 1);
    expect(_richTextContaining('Render: fresh'), findsOneWidget);

    releaseButton = tester.widget<FilledButton>(
      find.widgetWithText(FilledButton, 'Create client version'),
    );
    expect(releaseButton.onPressed, isNotNull);

    await tester.ensureVisible(
      find.widgetWithText(FilledButton, 'Create client version'),
    );
    await tester
        .tap(find.widgetWithText(FilledButton, 'Create client version'));
    await tester.pumpAndSettle();

    expect(apiClient.releaseVersions, <String>['v1.0']);
    expect(find.text('v1.0'), findsWidgets);
  });

  testWidgets('lists and opens previous delivered versions', (
    WidgetTester tester,
  ) async {
    final apiClient = _ProjectDocumentsPanelApiClient(
      releases: <ProjectDocumentRelease>[
        _release('v1.0'),
      ],
    );

    await _pumpPanel(tester, apiClient: apiClient);

    await tester.ensureVisible(find.text('Previous Versions'));
    expect(find.text('v1.0'), findsOneWidget);

    await tester.tap(find.widgetWithText(TextButton, 'Open'));
    await tester.pumpAndSettle();

    expect(apiClient.openedReleaseVersions, <String>['v1.0']);
    expect(find.text('Open release v1.0'), findsOneWidget);
    expect(find.textContaining('Proyecto: Clinica Norte'), findsWidgets);
  });

  testWidgets('generates and downloads the client PDF', (
    WidgetTester tester,
  ) async {
    final apiClient = _ProjectDocumentsPanelApiClient(pdfExists: false);
    Uint8List? savedBytes;

    await _pumpPanel(
      tester,
      apiClient: apiClient,
      onSavePdf: (bytes, _) async => savedBytes = bytes,
    );

    await tester.ensureVisible(find.text('Generar PDF'));
    await tester.tap(find.text('Generar PDF'));
    await tester.pumpAndSettle();

    expect(apiClient.generatePdfCalls, 1);
    expect(find.text('Regenerar PDF'), findsOneWidget);
    await tester.tap(find.text('Descargar'));
    await tester.pumpAndSettle();
    expect(savedBytes, isNotNull);
    expect(String.fromCharCodes(savedBytes!.take(5)), '%PDF-');
  });

  testWidgets('keeps PDF actions usable on a narrow phone', (
    WidgetTester tester,
  ) async {
    tester.view.physicalSize = const Size(360, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await _pumpPanel(
      tester,
      apiClient: _ProjectDocumentsPanelApiClient(),
    );
    await tester.ensureVisible(find.text('Entrega al cliente'));
    expect(tester.takeException(), isNull);
    expect(find.text('Regenerar PDF'), findsOneWidget);
    expect(find.text('Descargar'), findsOneWidget);
    expect(find.text('Compartir'), findsOneWidget);
  });
}

Finder _richTextContaining(String value) {
  return find.byWidgetPredicate(
    (widget) => widget is RichText && widget.text.toPlainText().contains(value),
  );
}

Future<void> _pumpPanel(
  WidgetTester tester, {
  required _ProjectDocumentsPanelApiClient apiClient,
  ValueChanged<String>? onRequestChange,
  ProjectDocumentPdfAction? onSavePdf,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      theme: ThemeData.dark(useMaterial3: true),
      home: Scaffold(
        body: SingleChildScrollView(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: ProjectDocumentsPanel(
              apiClient: apiClient,
              workspacePath: '/workspace/a',
              onRequestCharterChange: onRequestChange ?? (_) {},
              onSavePdf: onSavePdf,
            ),
          ),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

class _ProjectDocumentsPanelApiClient extends ApiClient {
  _ProjectDocumentsPanelApiClient({
    this.validationOk = true,
    this.staleRender = false,
    this.pdfExists = true,
    List<ProjectDocumentRelease> releases = const <ProjectDocumentRelease>[],
  })  : _releases = List<ProjectDocumentRelease>.from(releases),
        super(baseUrl: 'http://localhost:8000');

  bool validationOk;
  bool staleRender;
  bool pdfExists;
  final List<ProjectDocumentRelease> _releases;
  final List<String> releaseVersions = <String>[];
  final List<String> openedReleaseVersions = <String>[];
  int renderCalls = 0;
  int generatePdfCalls = 0;

  @override
  Future<ProjectDocuments> listProjectDocuments({
    String? workspacePath,
    String? draftId,
    String? jobId,
  }) async {
    return ProjectDocuments.fromJson(<String, dynamic>{
      'workspace_path': workspacePath ?? '/workspace/a',
      'workspace_name': 'Workspace A',
      'standard': 'project-charter-v1',
      'root': 'docs/project-management',
      'source': 'workspace_path',
      'evidence': <String, dynamic>{'workspacePath': workspacePath},
      'modules': <Map<String, dynamic>>[
        _module('charter', loadByDefault: true, status: 'ready'),
        _module('wbs', status: 'dormant'),
        _module('roles', status: 'dormant'),
        _module('risks', status: 'dormant'),
        _module('alternatives', status: 'dormant'),
      ],
      'charter': <String, dynamic>{
        'path': 'docs/project-management/acta/current/acta.md',
        'status': 'draft',
        'latest_render': 'docs/project-management/acta/current/render.html',
        'latest_release': _releases.isEmpty ? null : _releases.last.version,
        'validation': <String, dynamic>{
          'ok': validationOk,
          'blocking_count': validationOk ? 0 : 1,
        },
        'render': <String, dynamic>{
          'path': 'docs/project-management/acta/current/render.html',
          'exists': true,
          'source_hash': staleRender ? 'old-source-hash' : 'source-hash',
          'render_hash': 'render-hash',
          'status': staleRender ? 'stale' : 'fresh',
        },
      },
    });
  }

  @override
  Future<ProjectDocumentCharterDetail> getProjectDocumentCharter({
    String? workspacePath,
    String? draftId,
    String? jobId,
    bool includeRenderContent = true,
  }) async {
    return ProjectDocumentCharterDetail.fromJson(<String, dynamic>{
      'workspace_path': workspacePath ?? '/workspace/a',
      'workspace_name': 'Workspace A',
      'standard': 'project-charter-v1',
      'source': 'workspace_path',
      'evidence': <String, dynamic>{'workspacePath': workspacePath},
      'metadata': <String, dynamic>{
        'status': 'draft',
        'versions': <String, dynamic>{'draft': 'v0.1', 'delivered': null},
        'timestamps': <String, dynamic>{
          'updated_at': '2026-08-01T12:00:00Z',
        },
      },
      'brand': <String, dynamic>{},
      'source_summary': <String, dynamic>{
        'path': 'docs/project-management/acta/current/acta.md',
        'exists': true,
        'title': 'Acta de Proyecto',
        'size_bytes': 1200,
        'sha256': 'source-hash',
        'section_headings': <String>['Acta de Proyecto', 'Beneficios'],
        'excerpt': '# Acta de Proyecto\n\nProyecto: Clinica Norte',
      },
      'render': <String, dynamic>{
        'path': 'docs/project-management/acta/current/render.html',
        'exists': true,
        'size_bytes': 3200,
        'sha256': 'render-file-hash',
        'content':
            '<!doctype html><html><body><script>window.bad()</script><h1>Acta de Proyecto</h1><p>Proyecto: Clinica Norte</p></body></html>',
        'truncated': false,
      },
      'render_manifest': <String, dynamic>{
        'source_hash': staleRender ? 'old-source-hash' : 'source-hash',
        'render_hash': 'render-hash',
        'status': staleRender ? 'stale' : 'fresh',
      },
      'pdf': <String, dynamic>{
        'path': 'docs/project-management/acta/current/acta.pdf',
        'exists': pdfExists,
        'size_bytes': 48200,
        'sha256': 'pdf-hash',
        'page_count': 3,
      },
      'validation': _validationPayload(),
      'latest_release': _releases.isEmpty ? null : _releases.last.version,
    });
  }

  @override
  Future<ProjectDocumentCharterPdfResponse> generateProjectDocumentCharterPdf({
    String? workspacePath,
    String? draftId,
    String? jobId,
  }) async {
    generatePdfCalls += 1;
    pdfExists = true;
    return ProjectDocumentCharterPdfResponse.fromJson(<String, dynamic>{
      'workspace_path': workspacePath ?? '/workspace/a',
      'ok': true,
      'status': 'generated',
      'message': 'ready',
      'pdf': <String, dynamic>{
        'path': 'docs/project-management/acta/current/acta.pdf',
        'exists': true,
        'size_bytes': 9,
        'sha256': 'pdf-hash',
        'page_count': 1,
      },
      'validation': _validationPayload(),
    });
  }

  @override
  Future<Uint8List> downloadProjectDocumentCharterPdf({
    String? workspacePath,
    String? draftId,
    String? jobId,
    String? releaseVersion,
  }) async =>
      Uint8List.fromList('%PDF-test'.codeUnits);

  @override
  Future<ProjectDocumentCharterValidationResponse>
      validateProjectDocumentCharter({
    String? workspacePath,
    String? draftId,
    String? jobId,
    bool clientExport = true,
  }) async {
    return ProjectDocumentCharterValidationResponse.fromJson(
      <String, dynamic>{
        'workspace_path': workspacePath ?? '/workspace/a',
        'validation': _validationPayload(),
      },
    );
  }

  @override
  Future<ProjectDocumentCharterRenderResponse> renderProjectDocumentCharter({
    String? workspacePath,
    String? draftId,
    String? jobId,
  }) async {
    renderCalls += 1;
    staleRender = false;
    return ProjectDocumentCharterRenderResponse.fromJson(<String, dynamic>{
      'workspace_path': workspacePath ?? '/workspace/a',
      'render': <String, dynamic>{
        'path': 'docs/project-management/acta/current/render.html',
        'exists': true,
        'source_hash': 'source-hash',
        'render_hash': 'render-hash',
        'size_bytes': 3200,
      },
      'render_manifest': <String, dynamic>{
        'source_hash': 'source-hash',
        'render_hash': 'render-hash',
        'status': 'fresh',
      },
    });
  }

  @override
  Future<ProjectDocumentCharterReleaseResponse> releaseProjectDocumentCharter({
    required String version,
    String? workspacePath,
    String? draftId,
    String? jobId,
    List<String> changedFields = const <String>[],
    String? changelogEntry,
    bool clientExport = true,
  }) async {
    releaseVersions.add(version);
    _releases.add(_release(version));
    return ProjectDocumentCharterReleaseResponse.fromJson(<String, dynamic>{
      'workspace_path': workspacePath ?? '/workspace/a',
      'ok': true,
      'release_version': version,
      'release_path': 'docs/project-management/acta/releases/$version',
      'recommended_impact': 'minor',
      'validation': _validationPayload(),
    });
  }

  @override
  Future<ProjectDocumentCharterReleasesResponse>
      listProjectDocumentCharterReleases({
    String? workspacePath,
    String? draftId,
    String? jobId,
  }) async {
    return ProjectDocumentCharterReleasesResponse.fromJson(<String, dynamic>{
      'workspace_path': workspacePath ?? '/workspace/a',
      'releases': _releases.map(_releaseJson).toList(growable: false),
    });
  }

  @override
  Future<ProjectDocumentCharterReleaseResponse>
      getProjectDocumentCharterRelease({
    required String version,
    String? workspacePath,
    String? draftId,
    String? jobId,
    bool includeRenderContent = false,
  }) async {
    openedReleaseVersions.add(version);
    return ProjectDocumentCharterReleaseResponse.fromJson(<String, dynamic>{
      'workspace_path': workspacePath ?? '/workspace/a',
      'release': <String, dynamic>{
        ..._releaseJson(_release(version)),
        'source': <String, dynamic>{
          'path': 'docs/project-management/acta/releases/$version/acta.md',
          'exists': true,
          'size_bytes': 1200,
          'sha256': 'source-hash',
          'content': '# Acta de Proyecto\n\nProyecto: Clinica Norte',
          'truncated': false,
        },
      },
    });
  }

  Map<String, dynamic> _validationPayload() {
    return <String, dynamic>{
      'ok': validationOk,
      'generated_at': '2026-08-01T12:00:01Z',
      'blocking_count': validationOk ? 0 : 1,
      'issues': validationOk
          ? const <Map<String, dynamic>>[]
          : const <Map<String, dynamic>>[
              <String, dynamic>{
                'severity': 'error',
                'code': 'logo_pending',
                'field': 'brand.logo',
                'message': 'Logo pending',
                'next_action': 'Choose logo decision',
                'blocking': true,
                'affected_file':
                    'docs/project-management/acta/current/brand.yaml',
              },
            ],
    };
  }
}

Map<String, dynamic> _module(
  String id, {
  bool loadByDefault = false,
  String status = 'dormant',
}) {
  return <String, dynamic>{
    'id': id,
    'title': id == 'charter' ? 'Project Charter' : id.toUpperCase(),
    'path': 'docs/project-management/$id/README.md',
    'exists': true,
    'status': status,
    'load_by_default': loadByDefault,
    'description': '$id context',
    'validation': id == 'charter'
        ? <String, dynamic>{'ok': true, 'blocking_count': 0}
        : null,
  };
}

ProjectDocumentRelease _release(String version) {
  return ProjectDocumentRelease.fromJson(_releaseJson(
    ProjectDocumentRelease(
      version: version,
      path: 'docs/project-management/acta/releases/$version',
      exists: true,
      manifest: const <String, dynamic>{
        'released_at': '2026-08-01T12:05:00Z',
      },
      metadata: const <String, dynamic>{},
      artifacts: const <String>['acta.md', 'metadata.yaml', 'render.html'],
      source: null,
      render: null,
    ),
  ));
}

Map<String, dynamic> _releaseJson(ProjectDocumentRelease release) {
  return <String, dynamic>{
    'version': release.version,
    'path': release.path,
    'exists': release.exists,
    'manifest': release.manifest,
    'metadata': release.metadata,
    'artifacts': release.artifacts,
  };
}
