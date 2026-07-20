import 'dart:typed_data';

import 'package:codex_mobile_frontend/src/models/chat_session_summary.dart';
import 'package:codex_mobile_frontend/src/models/codex_tooling.dart';
import 'package:codex_mobile_frontend/src/models/dev_pipeline_handoff.dart';
import 'package:codex_mobile_frontend/src/models/domain_factory.dart';
import 'package:codex_mobile_frontend/src/models/feedback_queue_item.dart';
import 'package:codex_mobile_frontend/src/models/installable_app.dart';
import 'package:codex_mobile_frontend/src/models/project_factory.dart';
import 'package:codex_mobile_frontend/src/models/server_capabilities.dart';
import 'package:codex_mobile_frontend/src/models/server_health.dart';
import 'package:codex_mobile_frontend/src/models/session_detail.dart';
import 'package:codex_mobile_frontend/src/services/api_client.dart';
import 'package:codex_mobile_frontend/src/services/chat_notification_service.dart';
import 'package:codex_mobile_frontend/src/state/chat_controller.dart';
import 'package:cross_file/cross_file.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('installable app model parses install metadata', () {
    final app = InstallableApp.fromJson(const <String, dynamic>{
      'sourceApp': 'satshowroom',
      'displayName': 'SAT Showroom',
      'repo': 'brunojaime/satshowroom',
      'releaseChannel': 'stable',
      'latestVersion': '1.0.0',
      'latestBuild': 12,
      'releaseTag': 'android-v1.0.0-build.12',
      'apkUrl': 'http://bridge.test/app-updates/satshowroom/apk/tag/app.apk',
      'apkAssetName': 'satshowroom.apk',
      'sizeBytes': 12345,
      'sha256': 'abc',
      'available': true,
      'enabled': true,
      'packageId': 'com.example.satshowroom',
      'installStatusHint': 'available',
      'previewUrl': 'https://preview.nienfos.com/satshowroom',
      'runtimeProfile': 'preview',
      'productionReady': false,
      'mockOrDemo': false,
      'releaseMetadata': <String, dynamic>{
        'initialPreviewRelease': true,
      },
    });

    expect(app.sourceApp, 'satshowroom');
    expect(app.title, 'SAT Showroom');
    expect(app.versionLabel, '1.0.0+12');
    expect(app.canInstall, isTrue);
    expect(app.previewUrl, 'https://preview.nienfos.com/satshowroom');
    expect(app.runtimeProfile, 'preview');
    expect(app.isProductionReady, isFalse);
    expect(app.isMockOrDemo, isFalse);
    expect(app.releaseMetadata['initialPreviewRelease'], isTrue);
  });

  test('api client lists and fetches installable apps', () async {
    var step = 0;
    final client = ApiClient(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        step += 1;
        if (step == 1) {
          expect(request.method, 'GET');
          expect(request.url.path, '/installable-apps');
          return http.Response(
            '''
            {
              "kind": "codex.installableApps",
              "version": 1,
              "apps": [
                {
                  "kind": "codex.installableApp",
                  "version": 1,
                  "sourceApp": "satshowroom",
                  "displayName": "SAT Showroom",
                  "repo": "brunojaime/satshowroom",
                  "releaseChannel": "stable",
                  "latestVersion": "1.0.0",
                  "latestBuild": 12,
                  "releaseTag": "android-v1.0.0-build.12",
                  "apkUrl": "http://bridge.test/app-updates/satshowroom/apk/tag/app.apk",
                  "apkAssetName": "satshowroom.apk",
                  "sizeBytes": 12345,
                  "sha256": null,
                  "available": true,
                  "enabled": true,
                  "packageId": "com.example.satshowroom",
                  "installStatusHint": "available",
                  "previewUrl": "https://preview.nienfos.com/satshowroom",
                  "runtimeProfile": "preview",
                  "productionReady": false,
                  "mockOrDemo": false,
                  "releaseMetadata": {"initialPreviewRelease": true}
                }
              ]
            }
            ''',
            200,
            headers: <String, String>{'content-type': 'application/json'},
          );
        }
        expect(request.method, 'GET');
        expect(request.url.path, '/installable-apps/satshowroom');
        return http.Response(
          '''
          {
            "kind": "codex.installableApp",
            "version": 1,
            "sourceApp": "satshowroom",
            "displayName": "SAT Showroom",
            "repo": "brunojaime/satshowroom",
            "releaseChannel": "stable",
            "available": false,
            "enabled": true,
            "installStatusHint": "no_release_available"
          }
          ''',
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    final apps = await client.listInstallableApps();
    expect(apps.single.sourceApp, 'satshowroom');
    expect(apps.single.canInstall, isTrue);

    final detail = await client.getInstallableApp('satshowroom');
    expect(detail.canInstall, isFalse);
    expect(detail.installStatusHint, 'no_release_available');
  });

  test('project factory client creates and generates draft', () async {
    var step = 0;
    final client = ApiClient(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        step += 1;
        if (step == 1) {
          expect(request.method, 'GET');
          expect(request.url.path, '/project-factory/options');
          return http.Response(
            '''
            {
              "kind": "codex.projectFactoryOptions",
              "version": 1,
              "default_platforms": ["ios", "android", "web"],
              "platforms": ["ios", "android", "web"],
              "default_backend": "fastapi",
              "backends": ["fastapi", "go", "none"],
              "defaultFrontendStrategy": "flutter",
              "frontendStrategies": [
                {
                  "id": "flutter",
                  "display_name": "Flutter",
                  "supports_android_preview_apk": true
                },
                {
                  "id": "svelte",
                  "display_name": "Svelte",
                  "supports_android_preview_apk": false
                }
              ],
              "logo_modes": ["generate", "upload", "placeholder"],
              "business_types": ["medical_appointments"],
              "creation_workflow": {
                "runner": "codex_cli",
                "mode": "generator_reviewer_pairs",
                "generator_runs": 20,
                "reviewer_runs": 20
              }
            }
            ''',
            200,
            headers: <String, String>{'content-type': 'application/json'},
          );
        }
        if (step == 2) {
          expect(request.method, 'POST');
          expect(request.url.path, '/project-factory/drafts');
          expect(
              request.body, contains('"businessType":"medical_appointments"'));
          expect(request.body,
              contains('"primaryGoal":"Pacientes reservan turnos"'));
          expect(request.body, contains('"firstReleaseMode":"preview"'));
          expect(request.body, contains('"frontendStrategy":"flutter"'));
          return http.Response(
            '''
            {
              "kind": "codex.projectFactoryDraft",
              "version": 1,
              "draft_id": "pf-draft-1",
              "created_at": "2026-07-07T00:00:00Z",
              "firstReleaseMode": "preview",
              "frontendStrategy": "flutter",
            "manifest_plan": {
              "ok": true,
              "first_release_mode": "preview",
              "target_path": "/projects/clinica-norte"
            },
            "initialPreviewRelease": {
              "sourceApp": "clinica-norte",
              "previewUrl": "https://preview.nienfos.com/clinica-norte",
              "apiBaseUrl": "https://preview.nienfos.com/clinica-norte/api",
              "runtimeProfile": "preview",
              "apiRuntime": "cloudflare_preview",
              "releaseChannel": "prerelease",
              "releaseTagPattern": "android-preview-v*",
              "productionReady": false,
              "mockOrDemo": false,
              "status": "draft",
              "currentPhase": "draft",
              "phaseStatuses": {},
              "manualCommandHints": ["scripts/validate_initial_preview_release.sh"]
            }
            }
            ''',
            200,
            headers: <String, String>{'content-type': 'application/json'},
          );
        }
        expect(request.method, 'POST');
        expect(request.url.path, '/project-factory/drafts/pf-draft-1/generate');
        return http.Response(
          '''
          {
            "kind": "codex.projectFactoryJob",
            "version": 1,
            "job_id": "pf-job-1",
            "draft_id": "pf-draft-1",
            "created_at": "2026-07-07T00:00:00Z",
            "updated_at": "2026-07-07T00:00:00Z",
            "status": "ready",
            "current_step": "ready",
            "message": "Local project foundation generated.",
            "firstReleaseMode": "preview",
            "frontendStrategy": "flutter",
            "manifest_plan": {
              "ok": true,
              "first_release_mode": "preview",
              "target_path": "/projects/clinica-norte"
            },
            "initialPreviewRelease": {
              "sourceApp": "clinica-norte",
              "previewUrl": "https://preview.nienfos.com/clinica-norte",
              "apiBaseUrl": "https://preview.nienfos.com/clinica-norte/api",
              "runtimeProfile": "preview",
              "apiRuntime": "cloudflare_preview",
              "releaseChannel": "prerelease",
              "releaseTagPattern": "android-preview-v*",
              "productionReady": false,
              "mockOrDemo": false,
              "status": "ready",
              "currentPhase": "publish_verification",
              "phaseStatuses": {
                "publish_verification": {
                  "status": "completed",
                  "message": "ok",
                  "command": ["bash", "scripts/validate_initial_preview_release.sh"],
                  "exit_code": 0
                }
              },
              "manualCommandHints": ["scripts/validate_initial_preview_release.sh"]
            },
            "generation_result": {
              "target_path": "/projects/clinica-norte"
            }
          }
          ''',
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    final options = await client.getProjectFactoryOptions();
    expect(options.creationWorkflow['generator_runs'], 20);
    expect(options.creationWorkflow['reviewer_runs'], 20);
    expect(options.defaultFrontendStrategy, 'flutter');
    expect(options.frontendStrategies.map((item) => item['id']),
        containsAll(<String>['flutter', 'svelte']));

    final draft = await client.createProjectFactoryDraft(
      const ProjectFactoryDraftRequest(
        name: 'Clinica Norte',
        businessType: 'medical_appointments',
        primaryGoal: 'Pacientes reservan turnos',
      ),
    );
    expect(draft.draftId, 'pf-draft-1');
    expect(draft.firstReleaseMode, 'preview');
    expect(draft.frontendStrategy, 'flutter');
    expect(
      draft.initialPreviewRelease.previewUrl,
      'https://preview.nienfos.com/clinica-norte',
    );

    final job = await client.generateProjectFactoryDraft(draft.draftId);
    expect(job.isReady, isTrue);
    expect(job.firstReleaseMode, 'preview');
    expect(job.frontendStrategy, 'flutter');
    expect(job.targetPath, '/projects/clinica-norte');
    expect(job.initialPreviewRelease.releaseChannel, 'prerelease');
    expect(
        job.initialPreviewRelease.phaseStatuses['publish_verification']?.status,
        'completed');
  });

  test('project factory guided intake API methods parse state', () async {
    final calls = <String>[];
    final client = ApiClient(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        calls.add('${request.method} ${request.url.path}');
        if (request.url.path.endsWith('/answers')) {
          expect(request.body, contains('"questionId":"initial_admin_emails"'));
          expect(request.body, contains('owner@example.com'));
        }
        return http.Response(
          '''
          {
            "kind": "codex.projectFactoryGuidedIntake",
            "version": 1,
            "enabled": true,
            "status": "ready_for_review",
            "questions": [
              {
                "id": "initial_admin_emails",
                "title": "Initial admin emails",
                "options": []
              }
            ],
            "answers": [
              {
                "questionId": "initial_admin_emails",
                "value": ["owner@example.com"],
                "source": "user",
                "confidence": 1,
                "updatedAt": "2026-07-09T00:00:00Z"
              }
            ],
            "missingFields": [],
            "assumptions": [],
            "blockers": [],
            "contractPreview": {
              "decisions": {"name": "Clinica Norte"}
            },
            "updatedAt": "2026-07-09T00:00:00Z",
            "confirmedAt": null,
            "readyForConfirmation": true,
            "buildAllowed": false
          }
          ''',
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    final state = await client.getProjectFactoryGuidedIntake('pf-draft-1');
    final answered = await client.answerProjectFactoryGuidedIntake(
      draftId: 'pf-draft-1',
      questionId: 'initial_admin_emails',
      value: <String>['owner@example.com'],
    );
    final preview =
        await client.previewProjectFactoryGuidedIntake('pf-draft-1');
    final confirmed =
        await client.confirmProjectFactoryGuidedIntake('pf-draft-1');

    expect(state.questions.single['id'], 'initial_admin_emails');
    expect(answered.answers.single.value, <String>['owner@example.com']);
    expect(preview.contractPreview!['decisions']['name'], 'Clinica Norte');
    expect(confirmed.readyForConfirmation, isTrue);
    expect(calls, <String>[
      'GET /project-factory/drafts/pf-draft-1/intake',
      'POST /project-factory/drafts/pf-draft-1/intake/answers',
      'POST /project-factory/drafts/pf-draft-1/intake/preview',
      'POST /project-factory/drafts/pf-draft-1/intake/confirm',
    ]);
  });

  test('project factory init API starts and fetches deterministic init job',
      () async {
    final calls = <String>[];
    final client = ApiClient(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        calls.add('${request.method} ${request.url.path}');
        if (request.url.path == '/project-factory/drafts/pf-draft-1/init') {
          expect(request.body, contains('"chatSessionId":"chat-1"'));
          expect(request.body, contains('"workspacePath":"/projects"'));
        }
        if (request.url.path == '/project-factory/init-jobs' &&
            request.method == 'GET') {
          expect(request.url.queryParameters['draft_id'], 'pf-draft-1');
          expect(request.url.queryParameters['limit'], '1');
          return http.Response(
            '''
            {
              "kind": "codex.projectFactoryInitJobs",
              "version": 1,
              "jobs": [
                {
                  "kind": "codex.projectFactoryInitJob",
                  "version": 1,
                  "initJobId": "pf-init-1",
                  "draftId": "pf-draft-1",
                  "chatSessionId": "chat-1",
                  "createdAt": "2026-07-11T00:00:00Z",
                  "updatedAt": "2026-07-11T00:00:00Z",
                  "status": "queued",
                  "currentPhase": "init_preflight",
                  "projectPath": null,
                  "workspacePath": "/projects",
                  "generatedWorkspacePath": null,
                  "phases": [],
                  "remoteResources": [],
                  "contextPack": null,
                  "blockers": [],
                  "readyForBusinessLlm": false,
                  "canContinueWithBlockedContext": false,
                  "retryAvailable": true
                }
              ]
            }
            ''',
            200,
            headers: <String, String>{'content-type': 'application/json'},
          );
        }
        return http.Response(
          '''
          {
            "kind": "codex.projectFactoryInitJob",
            "version": 1,
            "initJobId": "pf-init-1",
            "draftId": "pf-draft-1",
            "chatSessionId": "chat-1",
            "createdAt": "2026-07-11T00:00:00Z",
            "updatedAt": "2026-07-11T00:00:00Z",
            "status": "queued",
            "currentPhase": "init_preflight",
            "projectPath": null,
            "workspacePath": "/projects",
            "generatedWorkspacePath": null,
            "phases": [
              {
                "name": "init_preflight",
                "status": "pending",
                "message": "",
                "startedAt": null,
                "completedAt": null,
                "commandEvidence": [],
                "blockers": [],
                "artifacts": []
              }
            ],
            "remoteResources": [],
            "contextPack": null,
            "blockers": [],
            "readyForBusinessLlm": false,
            "canContinueWithBlockedContext": false,
            "retryAvailable": true
          }
          ''',
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    final started = await client.startProjectFactoryInit(
      draftId: 'pf-draft-1',
      chatSessionId: 'chat-1',
      workspacePath: '/projects',
    );
    final loaded = await client.getProjectFactoryInitJob(started.initJobId);
    final listed = await client.listProjectFactoryInitJobs(
      draftId: 'pf-draft-1',
      limit: 1,
    );
    final retried = await client.retryProjectFactoryInitJob(started.initJobId);

    expect(started.initJobId, 'pf-init-1');
    expect(started.currentPhase, 'init_preflight');
    expect(started.phases.single.name, 'init_preflight');
    expect(started.readyForBusinessLlm, isFalse);
    expect(started.retryAvailable, isTrue);
    expect(loaded.initJobId, 'pf-init-1');
    expect(listed.single.retryAvailable, isTrue);
    expect(retried.initJobId, 'pf-init-1');
    expect(calls, <String>[
      'POST /project-factory/drafts/pf-draft-1/init',
      'GET /project-factory/init-jobs/pf-init-1',
      'GET /project-factory/init-jobs',
      'POST /project-factory/init-jobs/pf-init-1/retry',
    ]);
  });

  test('project factory options 404 reports backend update action', () async {
    final client = ApiClient(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        expect(request.method, 'GET');
        expect(request.url.path, '/project-factory/options');
        return http.Response('{"detail":"Not Found"}', 404);
      }),
    );

    expect(
      client.getProjectFactoryOptions,
      throwsA(
        isA<ProjectFactoryUnavailableException>().having(
          (error) => error.message,
          'message',
          contains('Restart or update the bridge backend'),
        ),
      ),
    );
  });

  test('server metadata exposes project factory capability', () {
    final capabilities = ServerCapabilities.fromJson(
      const <String, dynamic>{
        'supports_audio_input': true,
        'supports_speech_output': false,
        'supports_image_input': true,
        'supports_document_input': true,
        'supports_attachment_batch': true,
        'supports_job_cancellation': true,
        'supports_job_retry': true,
        'supports_push_job_stream': true,
        'supports_sdd': true,
        'supports_project_factory': true,
        'supports_domain_factory': true,
        'backend_version': 'bridge-local',
        'backend_commit': 'abc123',
        'features': <String, dynamic>{
          'project_factory': true,
          'domain_factory': true,
        },
        'speech_output_backend': 'disabled',
        'audio_max_upload_bytes': 1,
        'image_max_upload_bytes': 2,
        'document_max_upload_bytes': 3,
        'document_text_char_limit': 4,
      },
    );
    final health = ServerHealth.fromJson(
      const <String, dynamic>{
        'server_name': 'local',
        'backend_mode': 'local',
        'projects_root': '/projects',
        'backend_version': 'bridge-local',
        'backend_commit': 'abc123',
        'features': <String, dynamic>{'project_factory': true},
        'audio_transcription_backend': 'disabled',
        'audio_transcription_resolved_backend': 'disabled',
        'audio_transcription_ready': false,
        'speech_synthesis_backend': 'disabled',
        'speech_synthesis_ready': false,
        'tailscale_installed': true,
        'tailscale_online': true,
        'environment_identity': <String, dynamic>{
          'environment': 'dev',
          'mode': 'stage',
          'stage_id': 'spec-018',
          'spec_id': '018-dev-prod-stage-promotion-pipeline',
          'branch': 'dev/spec-018-dev-prod-stage-promotion-pipeline',
          'worktree_path': '/workspace/spec-018',
          'backend_url': 'http://127.0.0.1:8118',
          'app_channel': 'dev',
          'app_label': 'Codex Mobile Bridge DEV',
          'updater_channel': 'dev',
          'color': '#38BDF8',
          'allowed_capabilities': <String>['stage_backend_lifecycle'],
          'denied_capabilities': <String>['restart_prod_backend'],
        },
      },
    );

    expect(capabilities.supportsProjectFactory, isTrue);
    expect(capabilities.supportsDomainFactory, isTrue);
    expect(capabilities.features['project_factory'], isTrue);
    expect(capabilities.features['domain_factory'], isTrue);
    expect(capabilities.backendCommit, 'abc123');
    expect(health.features['project_factory'], isTrue);
    expect(health.backendVersion, 'bridge-local');
    expect(
      health.environmentIdentity?.displayLabel,
      'DEV - spec-018 - dev/spec-018-dev-prod-stage-promotion-pipeline',
    );
    expect(
      health.environmentIdentity?.allowedCapabilities,
      contains('stage_backend_lifecycle'),
    );
    expect(health.environmentIdentity?.canEnqueueDevHandoff, isFalse);
  });

  test('server health identifies prod dev-handoff availability', () {
    final health = ServerHealth.fromJson(
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
          'backend_url': 'http://prod.example.test',
          'app_channel': 'prod',
          'app_label': 'Codex Mobile Bridge',
          'updater_channel': 'prod',
          'color': '#55D6BE',
          'allowed_capabilities': <String>['enqueue_dev_handoff'],
          'denied_capabilities': <String>['run_shell'],
        },
      },
    );

    expect(health.environmentIdentity?.environment, 'prod');
    expect(health.environmentIdentity?.canEnqueueDevHandoff, isTrue);
  });

  test('api client enqueues dev handoff idempotently', () async {
    var calls = 0;
    final client = ApiClient(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        calls += 1;
        expect(request.method, 'POST');
        expect(request.url.path, '/dev-pipeline/handoffs');
        expect(request.headers['X-Idempotency-Key'], 'mobile-handoff-key');
        expect(request.body, contains('"source_environment":"prod"'));
        expect(request.body, contains('"target_environment":"dev"'));
        expect(request.body, contains('"operation":"enqueue_only"'));
        expect(request.body, contains('"selected_context"'));
        return http.Response(
          '''
          {
            "kind": "codex.devPipelineResponse",
            "version": 1,
            "data": {
              "id": "handoff-1",
              "status": "queued",
              "title": "Fix PROD update",
              "problem": "Update raced active work",
              "idempotency_key": "mobile-handoff-key"
            }
          }
          ''',
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );
    const request = DevPipelineHandoffRequest(
      title: 'Fix PROD update',
      problem: 'Update raced active work',
      context: 'Session context',
      acceptanceCriteria: 'No active work is interrupted.',
      selectedContext: <String, dynamic>{'session_id': 'session-prod'},
      evidence: <Map<String, dynamic>>[
        <String, dynamic>{'kind': 'note', 'text': 'observed in prod'},
      ],
      createdFromSessionId: 'session-prod',
    );

    final first = await client.enqueueDevHandoff(
      request,
      idempotencyKey: 'mobile-handoff-key',
    );
    final second = await client.enqueueDevHandoff(
      request,
      idempotencyKey: 'mobile-handoff-key',
    );

    expect(calls, 2);
    expect(first.id, 'handoff-1');
    expect(second.id, first.id);
    expect(first.status, 'queued');
  });

  test('api client surfaces disabled dev handoff errors', () async {
    final client = ApiClient(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        return http.Response(
          '''
          {
            "detail": {
              "code": "prod_handoff_disabled",
              "message": "PROD handoff is disabled by rollout flag."
            }
          }
          ''',
          409,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    expect(
      client.enqueueDevHandoff(
        const DevPipelineHandoffRequest(
          title: 'Fix PROD update',
          problem: 'Update raced active work',
          context: 'Session context',
          acceptanceCriteria: 'No active work is interrupted.',
        ),
        idempotencyKey: 'mobile-handoff-key',
      ),
      throwsA(
        isA<Exception>().having(
          (error) => error.toString(),
          'message',
          contains('prod_handoff_disabled'),
        ),
      ),
    );
  });

  test('api client drafts dev handoff for review', () async {
    final client = ApiClient(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/dev-pipeline/handoffs/draft');
        expect(request.body, contains('"session_id":"session-prod"'));
        return http.Response(
          '''
          {
            "kind": "codex.devPipelineResponse",
            "version": 1,
            "data": {
              "title": "Generated handoff",
              "problem": "Prod needs DEV work",
              "context": "Recent session context",
              "acceptance_criteria": "DEV validates it",
              "proposed_spec": "019-prod-chat-dev-handoff",
              "proposed_plan": "01-prod-chat",
              "proposed_tasks": ["Implement in DEV"],
              "regression_tests": ["flutter test"],
              "risks": ["grant reuse"],
              "created_from_session_id": "session-prod",
              "created_by_action": "mobile_dev_handoff",
              "draft_token": "draft-token-1"
            }
          }
          ''',
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    final draft = await client.draftDevHandoff(sessionId: 'session-prod');

    expect(draft.title, 'Generated handoff');
    expect(draft.proposedSpec, '019-prod-chat-dev-handoff');
    expect(draft.proposedTasks, <String>['Implement in DEV']);
    expect(draft.draftToken, 'draft-token-1');
  });

  test('api client fetches generated dev handoff draft status', () async {
    final client = ApiClient(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        expect(request.method, 'GET');
        expect(request.url.path, '/dev-pipeline/handoffs/drafts/draft-1');
        return http.Response(
          '''
          {
            "kind": "codex.devPipelineResponse",
            "version": 1,
            "data": {
              "title": "Generated handoff",
              "problem": "Prod needs DEV work",
              "context": "Recent session context",
              "acceptance_criteria": "DEV validates it",
              "proposed_spec": "019-prod-chat-dev-handoff",
              "proposed_plan": "01-prod-chat",
              "proposed_tasks": ["Implement in DEV"],
              "draft_id": "draft-1",
              "draft_status": "ready",
              "draft_token": "draft-token-1"
            }
          }
          ''',
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    final draft = await client.getDevHandoffDraft('draft-1');

    expect(draft.isDraftReady, isTrue);
    expect(draft.draftId, 'draft-1');
    expect(draft.proposedTasks, <String>['Implement in DEV']);
  });

  test('api client starts domain factory on current session', () async {
    final client = ApiClient(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/sessions/session-1/domain-factory/start');
        expect(request.body, contains('/workspace/project'));
        return http.Response(
          '''
          {
            "kind": "codex.domainFactoryStart",
            "version": 1,
            "status": "ready",
            "sessionId": "session-1",
            "firstMessageId": "domain-factory-start-session-1",
            "statePath": ".codex/factory/domain-factory-state.json",
            "specRoot": "specs/019-domain-factory-session-1",
            "context": {
              "kind": "codex.domainFactoryContext",
              "version": 1,
              "status": "ready",
              "sessionId": "session-1",
              "workspacePath": "/workspace/project",
              "workspaceName": "project"
            },
            "session": ${_sessionDetailJson(title: 'Project chat')}
          }
          ''',
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    final result = await client.startDomainFactoryMode(
      'session-1',
      workspacePath: '/workspace/project',
    );

    expect(result.isReady, isTrue);
    expect(result.session.id, 'session-1');
    expect(result.statePath, '.codex/factory/domain-factory-state.json');
    expect(result.specRoot, 'specs/019-domain-factory-session-1');
  });

  test('api client submits domain factory intake and confirms implementation',
      () async {
    var step = 0;
    final client = ApiClient(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        step += 1;
        if (step == 1) {
          expect(request.method, 'POST');
          expect(request.url.path, '/sessions/session-1/domain-factory/intake');
          expect(request.body, contains('Clinic staff and patients'));
          expect(request.body, contains('clinic-home.png'));
          return http.Response(
            '''
            {
              "kind": "codex.domainFactoryIntake",
              "version": 1,
              "status": "implementation_ready",
              "sessionId": "session-1",
              "specRoot": "specs/019-domain-factory-session-1",
              "briefPath": "specs/019-domain-factory-session-1/intake/original-brief.md",
              "mediaReferencesPath": "specs/019-domain-factory-session-1/intake/media-references.json",
              "contractPreviewPath": "specs/019-domain-factory-session-1/contract-preview.json",
              "messageId": "domain-factory-contract-session-1",
              "contractPreview": {
                "status": "ready_for_implementation_confirmation",
                "roles": {"owner": {"allAccess": true}, "admin": {"allAccess": true}},
                "releaseTarget": {"apiUrl": "https://preview.nienfos.com/clinica-norte/api"}
              },
              "session": ${_sessionDetailJson(title: 'Project chat')}
            }
            ''',
            200,
            headers: <String, String>{'content-type': 'application/json'},
          );
        }
        expect(request.method, 'POST');
        expect(
          request.url.path,
          '/sessions/session-1/domain-factory/implementation/confirm',
        );
        return http.Response(
          '''
          {
            "kind": "codex.domainFactoryImplementation",
            "version": 1,
            "status": "implementing",
            "sessionId": "session-1",
            "specRoot": "specs/019-domain-factory-session-1",
            "workflowEvidencePath": "specs/019-domain-factory-session-1/workflow-evidence.json",
            "messageId": "domain-factory-implementing-session-1",
            "session": ${_sessionDetailJson(title: 'Project chat')}
          }
          ''',
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    final intake = await client.submitDomainFactoryIntake(
      'session-1',
      brief: 'Clinic staff and patients need appointments.',
      mediaReferences: const <DomainFactoryMediaReference>[
        DomainFactoryMediaReference(
          id: 'asset-1',
          role: 'visual_reference',
          filename: 'clinic-home.png',
          assetId: 'asset-1',
          mimeType: 'image/png',
        ),
      ],
    );
    final implementation = await client.confirmDomainFactoryImplementation(
      'session-1',
    );

    expect(intake.isImplementationReady, isTrue);
    expect(
      intake.contractPreview['status'],
      'ready_for_implementation_confirmation',
    );
    expect(implementation.isImplementing, isTrue);
    expect(implementation.workflowEvidencePath, contains('workflow-evidence'));
  });

  test('api client persists domain factory release evidence', () async {
    final client = ApiClient(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        expect(request.method, 'POST');
        expect(
          request.url.path,
          '/sessions/session-1/domain-factory/release-evidence',
        );
        expect(request.body, contains('"commit":"def456"'));
        expect(request.body, contains('"initialBuild":1'));
        expect(request.body, contains('"previousBuildSeesNewBuild":true'));
        return http.Response(
          '''
          {
            "kind": "codex.domainFactoryReleaseEvidence",
            "version": 1,
            "status": "ready",
            "ok": true,
            "sessionId": "session-1",
            "sourceApp": "clinica-norte",
            "specRoot": "specs/019-domain-factory-session-1",
            "releaseEvidencePath": "specs/019-domain-factory-session-1/release-evidence.json",
            "statePath": ".codex/factory/domain-factory-state.json",
            "validation": {"ok": true, "build": 2},
            "errors": []
          }
          ''',
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    final result = await client.persistDomainFactoryReleaseEvidence(
      'session-1',
      evidence: const <String, dynamic>{
        'build': 2,
        'commit': 'def456',
        'updaterVerification': <String, dynamic>{
          'previousBuildSeesNewBuild': true,
          'newBuildHasPendingSelfUpdate': false,
        },
      },
    );

    expect(result.isReady, isTrue);
    expect(result.sourceApp, 'clinica-norte');
    expect(result.releaseEvidencePath, contains('release-evidence.json'));
    expect(result.validation['build'], 2);
  });

  test('project factory client manages reference assets', () async {
    var step = 0;
    final client = ApiClient(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        step += 1;
        if (step == 1) {
          expect(request.method, 'POST');
          expect(
            request.url.path,
            '/project-factory/drafts/pf-draft-1/reference-assets',
          );
          expect(
              request.headers['content-type'], contains('multipart/form-data'));
          final body = String.fromCharCodes(request.bodyBytes).toLowerCase();
          expect(body, contains('name="asset"'));
          expect(body, contains('filename="home.png"'));
          expect(body, contains('content-type: image/png'));
          return http.Response(
            _referenceAssetJson(),
            200,
            headers: <String, String>{'content-type': 'application/json'},
          );
        }
        if (step == 2) {
          expect(request.method, 'GET');
          expect(
            request.url.path,
            '/project-factory/drafts/pf-draft-1/reference-assets',
          );
          return http.Response(
            '{"kind":"codex.projectFactoryReferenceAssets","version":1,"draft_id":"pf-draft-1","assets":[${_referenceAssetJson()}]}',
            200,
            headers: <String, String>{'content-type': 'application/json'},
          );
        }
        expect(request.method, 'DELETE');
        expect(
          request.url.path,
          '/project-factory/drafts/pf-draft-1/reference-assets/pf-asset-1',
        );
        return http.Response(
          '{"kind":"codex.projectFactoryReferenceAssetDelete","version":1,"draft_id":"pf-draft-1","asset_id":"pf-asset-1","deleted":true}',
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    final uploaded = await client.uploadProjectFactoryReferenceAsset(
      'pf-draft-1',
      XFile.fromData(
        Uint8List.fromList(<int>[137, 80, 78, 71]),
        name: 'home.png',
        path: 'home.png',
      ),
    );
    expect(uploaded.id, 'pf-asset-1');
    expect(uploaded.originalFilename, 'home.png');

    final listed = await client.listProjectFactoryReferenceAssets('pf-draft-1');
    expect(listed.single.storagePath, 'pf-draft-1/pf-asset-1.png');

    await client.deleteProjectFactoryReferenceAsset(
      draftId: 'pf-draft-1',
      assetId: 'pf-asset-1',
    );
  });

  test('asset depot client uploads and links project draft asset', () async {
    var step = 0;
    final client = ApiClient(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        step += 1;
        if (step == 1) {
          expect(request.method, 'POST');
          expect(request.url.path, '/assets');
          final body = String.fromCharCodes(request.bodyBytes).toLowerCase();
          expect(body, contains('name="asset"'));
          expect(body, contains('filename="logo.png"'));
          expect(body, contains('name="source"'));
          expect(body, contains('chat_upload'));
          return http.Response(
            _assetDepotJson(),
            200,
            headers: <String, String>{'content-type': 'application/json'},
          );
        }
        if (step == 2) {
          expect(request.method, 'POST');
          expect(request.url.path, '/project-factory/drafts/pf-draft-1/assets');
          expect(request.body, contains('"asset_id":"asset-abc123def456"'));
          expect(request.body, contains('"role":"logo"'));
          return http.Response(
            _projectFactoryDraftAssetJson(),
            200,
            headers: <String, String>{'content-type': 'application/json'},
          );
        }
        expect(request.method, 'GET');
        expect(request.url.path, '/project-factory/drafts/pf-draft-1/assets');
        return http.Response(
          '{"kind":"codex.projectFactoryDraftAssets","version":1,"draft_id":"pf-draft-1","assets":[${_projectFactoryDraftAssetJson()}]}',
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    final asset = await client.uploadAssetDepotAsset(
      XFile.fromData(
        Uint8List.fromList(<int>[1, 2, 3, 4]),
        name: 'logo.png',
        mimeType: 'image/png',
        path: 'logo.png',
      ),
      source: 'chat_upload',
    );
    expect(asset.assetId, 'asset-abc123def456');
    expect(asset.sha256, 'sha256-value');

    final linked = await client.linkProjectFactoryDraftAsset(
      draftId: 'pf-draft-1',
      assetId: asset.assetId,
      role: ProjectAssetRole.logo,
      notes: 'Use exact logo',
    );
    expect(linked.role, ProjectAssetRole.logo);
    expect(linked.assetId, asset.assetId);

    final listed = await client.listProjectFactoryDraftAssets('pf-draft-1');
    expect(listed.single.originalFilename, 'logo.png');
  });

  test('project factory client lists drafts and jobs', () async {
    var step = 0;
    final client = ApiClient(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        step += 1;
        if (step == 1) {
          expect(request.method, 'GET');
          expect(request.url.path, '/project-factory/drafts');
          expect(request.url.queryParameters['limit'], '25');
          return http.Response(
            '''
            {
              "kind": "codex.projectFactoryDrafts",
              "version": 1,
              "drafts": [
                {
                  "id": "pf-draft-1",
                  "draft_id": "pf-draft-1",
                  "name": "Clinica Norte",
                  "slug": "clinica-norte",
                  "business_type": "medical",
                  "primary_goal": "Reservar turnos",
                  "status": "valid",
                  "ok": true,
                  "created_at": "2026-07-07T00:00:00Z",
                  "target_path": "/projects/clinica-norte",
                  "error": null,
                  "initialPreviewRelease": {
                    "sourceApp": "clinica-norte",
                    "previewUrl": "https://preview.nienfos.com/clinica-norte",
                    "apiBaseUrl": "https://preview.nienfos.com/clinica-norte/api",
                    "runtimeProfile": "preview",
                    "apiRuntime": "cloudflare_preview",
                    "releaseChannel": "prerelease",
                    "releaseTagPattern": "android-preview-v*",
                    "productionReady": false,
                    "mockOrDemo": false,
                    "status": "draft",
                    "currentPhase": "draft",
                    "phaseStatuses": {},
                    "manualCommandHints": []
                  }
                }
              ]
            }
            ''',
            200,
            headers: <String, String>{'content-type': 'application/json'},
          );
        }
        expect(request.method, 'GET');
        expect(request.url.path, '/project-factory/jobs');
        expect(request.url.queryParameters['status'], 'interrupted');
        expect(request.url.queryParameters['draft_id'], 'pf-draft-1');
        return http.Response(
          '''
          {
            "kind": "codex.projectFactoryJobs",
            "version": 1,
            "jobs": [
              {
                "id": "pf-job-1",
                "job_id": "pf-job-1",
                "draft_id": "pf-draft-1",
                "name": "Clinica Norte",
                "slug": "clinica-norte",
                "status": "interrupted",
                "current_phase": "interrupted",
                "progress": 50,
                "created_at": "2026-07-07T00:00:00Z",
                "started_at": "2026-07-07T00:00:01Z",
                "completed_at": "2026-07-07T00:00:02Z",
                "project_path": null,
                "target_path": "/projects/clinica-norte",
                "error": "Restarted",
                "message": "Restarted",
                "manual_next_step": "Inspect logs",
                "initialPreviewRelease": {
                  "sourceApp": "clinica-norte",
                  "previewUrl": "https://preview.nienfos.com/clinica-norte",
                  "apiBaseUrl": "https://preview.nienfos.com/clinica-norte/api",
                  "runtimeProfile": "preview",
                  "apiRuntime": "cloudflare_preview",
                  "releaseChannel": "prerelease",
                  "releaseTagPattern": "android-preview-v*",
                  "productionReady": false,
                  "mockOrDemo": false,
                  "status": "blocked",
                  "currentPhase": "publish_verification",
                  "blockerText": "Bridge registration missing",
                  "phaseStatuses": {
                    "publish_verification": {
                      "status": "blocked",
                      "message": "Bridge registration missing",
                      "command": ["bash", "scripts/validate_initial_preview_release.sh"]
                    }
                  },
                  "manualCommandHints": ["scripts/register_installable_app.sh"]
                }
              }
            ]
          }
          ''',
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    final drafts = await client.listProjectFactoryDrafts(limit: 25);
    expect(drafts.single.name, 'Clinica Norte');
    expect(drafts.single.targetPath, '/projects/clinica-norte');

    final jobs = await client.listProjectFactoryJobs(
      status: 'interrupted',
      draftId: 'pf-draft-1',
    );
    expect(jobs.single.status, 'interrupted');
    expect(jobs.single.isTerminal, isTrue);
    expect(jobs.single.manualNextStep, 'Inspect logs');
    expect(jobs.single.initialPreviewRelease.isBlocked, isTrue);
    expect(jobs.single.initialPreviewRelease.blockerText,
        'Bridge registration missing');
  });

  test('web preview client parses status and invite operations', () async {
    var step = 0;
    final client = ApiClient(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        step += 1;
        if (step == 1) {
          expect(request.method, 'GET');
          expect(request.url.path, '/web-previews');
          expect(request.url.queryParameters['limit'], '10');
          return http.Response(_webPreviewListJson, 200);
        }
        if (step == 2) {
          expect(request.method, 'GET');
          expect(request.url.path, '/web-previews/wp-clinica-norte');
          return http.Response(_webPreviewJson, 200);
        }
        if (step == 3) {
          expect(request.method, 'POST');
          expect(request.url.path, '/web-previews/plan');
          expect(request.body, contains('"sourceApp":"clinica-norte"'));
          return http.Response(_webPreviewJson, 200);
        }
        if (step == 4) {
          expect(request.method, 'POST');
          expect(request.url.path, '/web-previews/deploy');
          expect(request.body, contains('"confirmApply":false'));
          return http.Response(_webPreviewJson, 200);
        }
        if (step == 5) {
          expect(request.method, 'POST');
          expect(request.url.path, '/web-previews/wp-clinica-norte/invites');
          expect(request.body, contains('"ttlSeconds":300'));
          expect(request.body, contains('"singleUse":true'));
          expect(request.body, contains('"email":"admin@example.com"'));
          expect(request.body, contains('"role":"owner"'));
          return http.Response(_webPreviewInviteJson(withToken: true), 200);
        }
        if (step == 6) {
          expect(request.method, 'GET');
          expect(request.url.path, '/web-previews/wp-clinica-norte/invites');
          return http.Response(
            '{"kind":"codex.webPreviewInvites","version":1,"invites":[${_webPreviewInviteJson()}]}',
            200,
          );
        }
        if (step == 7) {
          expect(request.method, 'DELETE');
          expect(
            request.url.path,
            '/web-previews/wp-clinica-norte/invites/wpi-1',
          );
          return http.Response(_webPreviewInviteJson(revoked: true), 200);
        }
        if (step == 8) {
          expect(request.method, 'POST');
          expect(
            request.url.path,
            '/web-previews/wp-clinica-norte/invites/wpi-1/resend',
          );
          expect(request.body, contains('"ttlSeconds":600'));
          return http.Response(
            _webPreviewInviteJson(withToken: true, resendCount: 1),
            200,
          );
        }
        if (step == 9) {
          expect(request.method, 'POST');
          expect(
            request.url.path,
            '/web-previews/wp-clinica-norte/invites/wpi-1/expire',
          );
          return http.Response(_webPreviewInviteJson(expired: true), 200);
        }
        if (step == 10) {
          expect(request.method, 'POST');
          expect(
            request.url.path,
            '/web-previews/wp-clinica-norte/invites/wpi-1/sync',
          );
          return http.Response(
              _webPreviewInviteJson(syncStatus: 'synced'), 200);
        }
        if (step == 11) {
          expect(request.method, 'POST');
          expect(request.url.path, '/web-previews/wp-clinica-norte/disable');
          expect(request.body, contains('"reason":"operator pause"'));
          return http.Response(
              _webPreviewJson.replaceFirst('"active"', '"disabled"'), 200);
        }
        if (step == 12) {
          expect(request.method, 'POST');
          expect(request.url.path, '/web-previews/wp-clinica-norte/extend');
          expect(request.body, contains('"ttlSeconds":604800'));
          return http.Response(_webPreviewJson, 200);
        }
        expect(request.method, 'POST');
        expect(request.url.path, '/web-previews/wp-clinica-norte/expire');
        return http.Response(
            _webPreviewJson.replaceFirst('"active"', '"expired"'), 200);
      }),
    );

    final previews = await client.listWebPreviews(limit: 10);
    expect(previews.single.status, 'active');
    expect(previews.single.inviteSyncSummary?['synced'], 1);
    expect(previews.single.expiresAt, '2026-08-07T00:00:00Z');
    expect(previews.single.auditEvents.single['event_type'],
        'preview_publish_succeeded');

    final detail = await client.getWebPreview('wp-clinica-norte');
    expect(detail.isActive, isTrue);

    final planned = await client.planWebPreview(sourceApp: 'clinica-norte');
    expect(planned.previewUrl, 'https://preview.nienfos.com/clinica-norte');

    final deployed = await client.deployWebPreview(sourceApp: 'clinica-norte');
    expect(deployed.status, 'active');

    final created = await client.createWebPreviewInvite(
      'wp-clinica-norte',
      ttlSeconds: 300,
      email: 'admin@example.com',
      role: 'owner',
    );
    expect(created.inviteUrl, contains('__preview/access'));
    expect(created.token, 'secret-token');
    expect(created.email, 'admin@example.com');
    expect(created.role, 'owner');
    expect(created.manualDeliveryRequired, isTrue);

    final invites = await client.listWebPreviewInvites('wp-clinica-norte');
    expect(invites.single.syncStatus, 'failed');
    expect(invites.single.canRetrySync, isTrue);

    final revoked = await client.revokeWebPreviewInvite(
      previewId: 'wp-clinica-norte',
      inviteId: 'wpi-1',
    );
    expect(revoked.isRevoked, isTrue);

    final resent = await client.resendWebPreviewInvite(
      previewId: 'wp-clinica-norte',
      inviteId: 'wpi-1',
      ttlSeconds: 600,
    );
    expect(resent.resendCount, 1);

    final expired = await client.expireWebPreviewInvite(
      previewId: 'wp-clinica-norte',
      inviteId: 'wpi-1',
    );
    expect(expired.expiredAt, isNotEmpty);

    final synced = await client.syncWebPreviewInvite(
      previewId: 'wp-clinica-norte',
      inviteId: 'wpi-1',
    );
    expect(synced.syncStatus, 'synced');

    final disabled = await client.disableWebPreview(
      previewId: 'wp-clinica-norte',
      reason: 'operator pause',
    );
    expect(disabled.isDisabled, isTrue);

    final extended = await client.extendWebPreview(
      previewId: 'wp-clinica-norte',
      ttlSeconds: 604800,
    );
    expect(extended.isActive, isTrue);

    final previewExpired = await client.expireWebPreview(
      previewId: 'wp-clinica-norte',
    );
    expect(previewExpired.isExpired, isTrue);
  });

  test('sendMessage includes codex options when requested', () async {
    final client = ApiClient(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/message');
        final body = request.body;
        expect(body, contains('"profile":"safe"'));
        expect(body, contains('"search_enabled":true'));
        expect(body, contains('"skill_ids":["skill-creator"]'));
        expect(body, contains('"mcp_server_ids":["github"]'));
        return http.Response(
          '{"job_id":"job-1","status":"pending"}',
          202,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    await client.sendMessage(
      'Use the real local Codex skill.',
      codexRunOptions: const CodexRunOptions(
        profile: 'safe',
        searchEnabled: true,
        skillIds: <String>['skill-creator'],
        mcpServerIds: <String>['github'],
      ),
    );
  });

  test('startFeedbackQueueSession includes explicit target mode', () async {
    final client = ApiClient(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/feedback-queue/feedback-1/start-session');
        expect(request.body, contains('"target_mode":"generator_reviewer"'));
        return http.Response(
          '{"job_id":"job-1","session_id":"session-1","status":"pending","elapsed_seconds":0}',
          202,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    await client.startFeedbackQueueSession(
      'feedback-1',
      targetMode: FeedbackQueueTargetMode.generatorReviewer,
    );
  });

  test('sendAttachmentsMessage preserves image content type', () async {
    final client = ApiClient(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/message/attachments');
        expect(
            request.headers['content-type'], contains('multipart/form-data'));
        final body = String.fromCharCodes(request.bodyBytes).toLowerCase();
        expect(body, contains('name="attachments"'));
        expect(body, contains('filename="feedback-1.png"'));
        expect(body, contains('content-type: image/png'));
        return http.Response(
          '{"job_id":"job-1","session_id":"session-1","status":"pending","elapsed_seconds":0}',
          202,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    await client.sendAttachmentsMessage(
      <XFile>[
        XFile.fromData(
          Uint8List.fromList(<int>[137, 80, 78, 71]),
          name: 'feedback-1.png',
          mimeType: 'image/png',
          path: 'feedback-1.png',
        ),
      ],
      message: 'Use this screenshot',
    );
  });

  test('sendAttachmentsMessage infers standard document content types',
      () async {
    final client = ApiClient(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/message/attachments');
        final body = String.fromCharCodes(request.bodyBytes).toLowerCase();
        expect(body, contains('filename="market.pdf"'));
        expect(body, contains('content-type: application/pdf'));
        expect(body, contains('filename="estudio de mercado.pptx"'));
        expect(
          body,
          contains(
            'content-type: application/vnd.openxmlformats-officedocument.presentationml.presentation',
          ),
        );
        expect(body, contains('filename="market-data.xlsx"'));
        expect(
          body,
          contains(
            'content-type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          ),
        );
        return http.Response(
          '{"job_id":"job-1","session_id":"session-1","status":"pending","elapsed_seconds":0}',
          202,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    await client.sendAttachmentsMessage(
      <XFile>[
        XFile.fromData(
          Uint8List.fromList(<int>[37, 80, 68, 70]),
          name: 'market.pdf',
          path: 'market.pdf',
        ),
        XFile.fromData(
          Uint8List.fromList(<int>[80, 75, 3, 4]),
          name: 'Estudio de Mercado.pptx',
          path: 'Estudio de Mercado.pptx',
        ),
        XFile.fromData(
          Uint8List.fromList(<int>[80, 75, 3, 4]),
          name: 'market-data.xlsx',
          path: 'market-data.xlsx',
        ),
      ],
      message: 'podes ver este archivo?',
    );
  });

  test('sendAttachmentsMessage sends text, edited PNG image, and audio',
      () async {
    final client = ApiClient(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/message/attachments');
        expect(
            request.headers['content-type'], contains('multipart/form-data'));
        final body = String.fromCharCodes(request.bodyBytes).toLowerCase();
        expect(body, contains('name="message"'));
        expect(body, contains('compare this crop with the voice note'));
        expect(body, contains('name="attachments"'));
        expect(body, contains('filename="screenshot-edited.png"'));
        expect(body, contains('content-type: image/png'));
        expect(body, contains('filename="voice-note.ogg"'));
        expect(body, contains('content-type: audio/ogg'));
        return http.Response(
          '{"job_id":"job-1","session_id":"session-1","status":"pending","elapsed_seconds":0}',
          202,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    await client.sendAttachmentsMessage(
      <XFile>[
        XFile.fromData(
          Uint8List.fromList(<int>[137, 80, 78, 71]),
          name: 'screenshot-edited.png',
          mimeType: 'image/png',
          path: 'screenshot-edited.png',
        ),
        XFile.fromData(
          Uint8List.fromList(<int>[79, 103, 103, 83]),
          name: 'voice-note.ogg',
          mimeType: 'audio/ogg',
          path: 'voice-note.ogg',
        ),
      ],
      message: 'Compare this crop with the voice note',
    );
  });

  test('renameSession updates the session title endpoint', () async {
    final client = ApiClient(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        expect(request.method, 'PUT');
        expect(request.url.path, '/sessions/session-1/title');
        expect(request.body, contains('"title":"Release planning"'));
        return http.Response(
          _sessionDetailJson(title: 'Release planning'),
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    final session = await client.renameSession(
      'session-1',
      title: 'Release planning',
    );

    expect(session.title, 'Release planning');
  });

  test('generateSessionTitle sends text instructions', () async {
    final client = ApiClient(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/sessions/session-1/title/generate');
        expect(request.body, contains('"instructions":"Focus on bugs"'));
        return http.Response(
          _sessionDetailJson(title: 'Bug triage'),
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    final session = await client.generateSessionTitle(
      'session-1',
      instructions: 'Focus on bugs',
    );

    expect(session.title, 'Bug triage');
  });

  test('generateSessionTitleFromAudio uploads voice instructions', () async {
    final client = ApiClient(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/sessions/session-1/title/generate/audio');
        expect(
            request.headers['content-type'], contains('multipart/form-data'));
        final body = String.fromCharCodes(request.bodyBytes).toLowerCase();
        expect(body, contains('name="instructions"'));
        expect(body, contains('keep it short'));
        expect(body, contains('name="audio"'));
        expect(body, contains('filename="title-note.ogg"'));
        expect(body, contains('content-type: audio/ogg'));
        return http.Response(
          _sessionDetailJson(title: 'Short title'),
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    final session = await client.generateSessionTitleFromAudio(
      'session-1',
      XFile.fromData(
        Uint8List.fromList(<int>[79, 103, 103, 83]),
        name: 'title-note.ogg',
        mimeType: 'audio/ogg',
        path: 'title-note.ogg',
      ),
      instructions: 'Keep it short',
    );

    expect(session.title, 'Short title');
  });

  test('updateTurnSummaries explains when the backend route is missing',
      () async {
    final client = ApiClient(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        expect(request.method, 'PUT');
        expect(request.url.path, '/sessions/session-1/turn-summaries');
        return http.Response(
          '{"detail":"Not Found"}',
          404,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    await expectLater(
      () => client.updateTurnSummaries('session-1', enabled: true),
      throwsA(
        predicate<Object>(
          (error) => '$error'.contains(
            'Turn summaries are not available on the connected backend. Pull the latest backend changes and restart it.',
          ),
        ),
      ),
    );
  });

  test('chat controller shows a clean turn summary backend mismatch error',
      () async {
    final controller = ChatController(
      apiClient: _MissingTurnSummaryRouteApiClient(),
      notificationService: const NoopChatNotificationService(),
    );
    addTearDown(controller.dispose);

    await controller.refreshSessions();
    await controller.selectSession('session-1');

    expect(
      await controller.updateTurnSummariesEnabled(true),
      isFalse,
    );
    expect(
      controller.errorText,
      'Failed to update turn summaries.\n'
      'Turn summaries are not available on the connected backend. '
      'Pull the latest backend changes and restart it.',
    );
  });

  test('getCodexTooling parses repo MCP apps including validation errors',
      () async {
    final client = ApiClient(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        expect(request.method, 'GET');
        expect(request.url.path, '/codex/tooling');
        return http.Response(
          '''
          {
            "status": {
              "cli_available": true,
              "command": "codex",
              "status_summary": "ok"
            },
            "profiles": [],
            "skills": [],
            "mcp_server_inventory_complete": false,
            "mcp_servers": [
              {
                "server_id": "github",
                "summary": "github: GitHub connector available",
                "source": "external",
                "backing_app_id": null,
                "status": "disabled",
                "selectable": false,
                "selectable_reason": "This external MCP server is disabled in Codex. Re-enable it before selecting it.",
                "disabled_reason": "Paused by admin",
                "lookup_error": null
              }
            ],
            "mcp_apps": [
              {
                "app_id": "project-catalog",
                "name": "Project Catalog",
                "description": "List local projects",
                "recommended_server_id": "project-catalog",
                "transport": "stdio",
                "command": "uv",
                "args": ["run", "python", "-m", "mcp_apps.project_catalog.server"],
                "env": {"PROJECTS_ROOT": "/projects"},
                "tags": ["projects"],
                "supports_ui_extension": false,
                "ui_entry_uri": null,
                "spec_path": "/repo/mcp_apps/project_catalog/app.json",
                "installed": false,
                "install_state": "drifted",
                "server_present": true,
                "server_presence_known": true,
                "config_matches": false,
                "tools": [
                  {
                    "name": "list_projects",
                    "title": "List Projects",
                    "description": "List projects",
                    "read_only": true,
                    "destructive": false,
                    "idempotent": true,
                    "open_world": false,
                    "input_schema": {"type": "object"}
                  }
                ],
                "resources": [
                  {
                    "name": "Project Catalog JSON",
                    "title": null,
                    "uri": "projects://catalog",
                    "description": "Catalog",
                    "mime_type": "application/json"
                  }
                ],
                "prompts": [],
                "preview": {
                  "tool_name": "list_projects",
                  "arguments": {"limit": 2},
                  "result": {
                    "project_count": 1,
                    "projects": [{"name": "alpha"}]
                  },
                  "is_error": false,
                  "error": null
                },
                "drift_summary": "args differ between the stored Codex config and the repo app spec",
                "disabled_reason": "Authorization: [redacted]",
                "lookup_error": "state unreadable",
                "validation_error": "Broken preview config",
                "protocol_error": "Timed out during initialize."
              }
            ]
          }
          ''',
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    final snapshot = await client.getCodexTooling();
    expect(snapshot.mcpServerInventoryComplete, isFalse);
    expect(snapshot.mcpServers, hasLength(1));
    final server = snapshot.mcpServers.single;
    expect(server.serverId, 'github');
    expect(server.status, 'disabled');
    expect(server.selectable, isFalse);
    expect(server.disabledReason, 'Paused by admin');
    expect(snapshot.mcpApps, hasLength(1));
    final app = snapshot.mcpApps.single;
    expect(app.appId, 'project-catalog');
    expect(app.recommendedServerId, 'project-catalog');
    expect(app.tools.single.name, 'list_projects');
    expect(app.resources.single.uri, 'projects://catalog');
    expect(app.preview?.toolName, 'list_projects');
    expect(app.installState, 'drifted');
    expect(app.serverPresent, isTrue);
    expect(app.serverPresenceKnown, isTrue);
    expect(app.configMatches, isFalse);
    expect(
      app.driftSummary,
      'args differ between the stored Codex config and the repo app spec',
    );
    expect(app.disabledReason, 'Authorization: [redacted]');
    expect(app.lookupError, 'state unreadable');
    expect(app.validationError, 'Broken preview config');
    expect(app.protocolError, 'Timed out during initialize.');
  });

  test('installCodexMcpApp posts to the install endpoint', () async {
    final client = ApiClient(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/codex/mcp-apps/project-catalog/install');
        return http.Response(
          '''
          {
            "app_id": "project-catalog",
            "server_id": "project-catalog",
            "already_installed": true,
            "reconciled": false,
            "command": "uv run python -m mcp_apps.project_catalog.server",
            "summary": "Already installed"
          }
          ''',
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    final result = await client.installCodexMcpApp('project-catalog');
    expect(result.appId, 'project-catalog');
    expect(result.alreadyInstalled, isTrue);
    expect(result.reconciled, isFalse);
    expect(result.summary, 'Already installed');
  });
}

String _sessionDetailJson({required String title}) {
  return '''
  {
    "id": "session-1",
    "title": "$title",
    "workspace_path": "/workspace/project",
    "workspace_name": "Project",
    "agent_profile_id": "default",
    "agent_profile_name": "Generator",
    "agent_profile_color": "#55D6BE",
    "agent_configuration": {
      "version": 1,
      "preset": "solo",
      "agents": []
    },
    "conversation_product": {
      "status_line": "Idle",
      "description": "No updates yet"
    },
    "created_at": "2026-04-01T00:00:00Z",
    "updated_at": "2026-04-01T00:00:00Z",
    "messages": []
  }
  ''';
}

String _referenceAssetJson() {
  return '''
  {
    "id": "pf-asset-1",
    "draft_id": "pf-draft-1",
    "original_filename": "home.png",
    "content_type": "image/png",
    "size_bytes": 4,
    "created_at": "2026-07-07T00:00:00Z",
    "storage_path": "pf-draft-1/pf-asset-1.png"
  }
  ''';
}

String _assetDepotJson() {
  return '''
  {
    "asset_id": "asset-abc123def456",
    "id": "asset-abc123def456",
    "original_filename": "logo.png",
    "content_type": "image/png",
    "size_bytes": 4,
    "sha256": "sha256-value",
    "created_at": "2026-07-07T00:00:00Z",
    "storage_path": "files/asset-abc123def456.png",
    "source": "chat_upload"
  }
  ''';
}

String _projectFactoryDraftAssetJson() {
  return '''
  {
    "draft_id": "pf-draft-1",
    "asset_id": "asset-abc123def456",
    "role": "logo",
    "notes": "Use exact logo",
    "linked_at": "2026-07-07T00:00:00Z",
    "original_filename": "logo.png",
    "content_type": "image/png",
    "size_bytes": 4,
    "sha256": "sha256-value",
    "storage_path": "files/asset-abc123def456.png",
    "source": "chat_upload"
  }
  ''';
}

const String _webPreviewJson = '''
{
  "kind": "codex.webPreview",
  "version": 1,
  "preview_id": "wp-clinica-norte",
  "source_app": "clinica-norte",
  "project_path": "/projects/clinica-norte",
  "manifest_path": "/projects/clinica-norte/deploy/web-preview/web-preview-manifest.yaml",
  "status": "active",
  "preview_url": "https://preview.nienfos.com/clinica-norte",
  "health_url": "https://preview.nienfos.com/clinica-norte/__preview/health",
  "plan_hash": "abc",
  "planned_resources": [{"kind":"worker_script","status":"planned"}],
  "applied_resources": [{"kind":"d1_database","status":"created"}],
  "invite_sync_summary": {"synced": 1, "failed": 0, "pending": 0, "not_deployed": 0},
  "error": null,
  "logs": [],
  "created_at": "2026-07-07T00:00:00Z",
  "updated_at": "2026-07-07T00:01:00Z",
  "expires_at": "2026-08-07T00:00:00Z",
  "disabled_at": null,
  "disabled_reason": null,
  "audit_events": [{"event_type":"preview_publish_succeeded","source_app":"clinica-norte"}],
  "completed_at": "2026-07-07T00:01:00Z"
}
''';

const String _webPreviewListJson = '''
{
  "kind": "codex.webPreviews",
  "version": 1,
  "previews": [$_webPreviewJson]
}
''';

String _webPreviewInviteJson({
  bool withToken = false,
  bool revoked = false,
  bool expired = false,
  int resendCount = 0,
  String syncStatus = 'failed',
}) {
  return '''
  {
    "kind": "codex.webPreviewInvite",
    "version": 1,
    "invite_id": "wpi-1",
    "preview_id": "wp-clinica-norte",
    "source_app": "clinica-norte",
    "app_slug": "clinica-norte",
    "audience": "codex.web-preview",
    "scope": "web_preview:access",
    "created_at": "2026-07-07T00:00:00Z",
    "expires_at": "2026-07-14T00:00:00Z",
    "email": "admin@example.com",
    "role": "owner",
    "single_use": true,
    "used_at": null,
    "revoked_at": ${revoked ? '"2026-07-07T00:05:00Z"' : 'null'},
    "expired_at": ${expired ? '"2026-07-07T00:06:00Z"' : 'null'},
    "resend_count": $resendCount,
    "last_sent_at": ${resendCount > 0 ? '"2026-07-07T00:03:00Z"' : 'null'},
    "email_provider": "manual",
    "email_delivery_status": "manual_link_required",
    "email_delivery_error": null,
    "manual_delivery_required": true,
    "sync_status": "$syncStatus",
    "synced_at": ${syncStatus == 'synced' ? '"2026-07-07T00:02:00Z"' : 'null'},
    "sync_error": ${syncStatus == 'failed' ? '"D1 unavailable"' : 'null'},
    "token_sha256": "abc123",
    "invite_url": ${withToken ? '"https://preview.nienfos.com/clinica-norte/__preview/access?token=secret-token"' : 'null'},
    "token": ${withToken ? '"secret-token"' : 'null'}
  }
  ''';
}

class _MissingTurnSummaryRouteApiClient extends ApiClient {
  _MissingTurnSummaryRouteApiClient() : super(baseUrl: 'http://localhost:8000');

  @override
  Future<List<ChatSessionSummary>> listSessions() async {
    return <ChatSessionSummary>[
      ChatSessionSummary(
        id: 'session-1',
        title: 'Summary route mismatch',
        workspacePath: '/workspace/project',
        workspaceName: 'Project',
        createdAt: DateTime.parse('2026-04-01T00:00:00Z'),
        updatedAt: DateTime.parse('2026-04-01T00:00:00Z'),
      ),
    ];
  }

  @override
  Future<SessionDetail> getSession(
    String sessionId, {
    String? before,
    int? limit,
    bool fullTranscript = false,
  }) async {
    return SessionDetail(
      id: sessionId,
      title: 'Summary route mismatch',
      workspacePath: '/workspace/project',
      workspaceName: 'Project',
      createdAt: DateTime.parse('2026-04-01T00:00:00Z'),
      updatedAt: DateTime.parse('2026-04-01T00:00:00Z'),
      messages: const [],
    );
  }

  @override
  Future<SessionDetail> updateTurnSummaries(
    String sessionId, {
    required bool enabled,
  }) async {
    throw Exception(
      'Failed to update turn summaries: Turn summaries are not available on the connected backend. Pull the latest backend changes and restart it.',
    );
  }
}
