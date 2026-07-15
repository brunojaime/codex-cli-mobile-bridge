import 'dart:convert';

import 'package:cross_file/cross_file.dart';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';

import '../models/job_status_response.dart';
import '../models/agent_configuration.dart';
import '../models/agent_profile.dart';
import '../models/chat_message.dart';
import '../models/codex_tooling.dart';
import '../models/dev_pipeline_handoff.dart';
import '../models/domain_factory.dart';
import '../models/feedback_queue_item.dart';
import '../models/installable_app.dart';
import '../models/project_factory.dart';
import '../models/prod_update_status.dart';
import '../models/server_capabilities.dart';
import '../models/session_detail.dart';
import '../models/chat_session_summary.dart';
import '../models/server_health.dart';
import '../models/workspace.dart';

class SynthesizedSpeechClip {
  const SynthesizedSpeechClip({
    required this.audioBytes,
    required this.contentType,
    required this.responseFormat,
  });

  final List<int> audioBytes;
  final String contentType;
  final String responseFormat;
}

class ProjectFactoryUnavailableException implements Exception {
  const ProjectFactoryUnavailableException(this.message);

  final String message;

  @override
  String toString() => message;
}

class ApiClient {
  ApiClient({required this.baseUrl, http.Client? client})
      : _client = client ?? http.Client();

  final String baseUrl;
  final http.Client _client;

  Uri jobStreamUri(String jobId) {
    final httpUri = Uri.parse(baseUrl);
    final scheme = httpUri.scheme == 'https' ? 'wss' : 'ws';
    return httpUri.replace(
      scheme: scheme,
      path: '${httpUri.path.replaceAll(RegExp(r'/$'), '')}/ws/jobs/$jobId',
    );
  }

  Future<List<ChatSessionSummary>> listSessions() async {
    final response = await _client.get(Uri.parse('$baseUrl/sessions'));

    if (response.statusCode != 200) {
      throw Exception('Failed to list sessions: ${response.body}');
    }

    final payload = jsonDecode(response.body) as List<dynamic>;
    return payload
        .map(
          (item) => ChatSessionSummary.fromJson(item as Map<String, dynamic>),
        )
        .toList();
  }

  Future<ServerHealth> getHealth() async {
    final response = await _client.get(Uri.parse('$baseUrl/health'));

    if (response.statusCode != 200) {
      throw Exception('Failed to fetch health: ${response.body}');
    }

    return ServerHealth.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<DevPipelineHandoff> enqueueDevHandoff(
    DevPipelineHandoffRequest request, {
    required String idempotencyKey,
  }) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/dev-pipeline/handoffs'),
      headers: <String, String>{
        'Content-Type': 'application/json',
        'X-Idempotency-Key': idempotencyKey,
      },
      body: jsonEncode(request.toJson()),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to enqueue DEV handoff: ${response.body}');
    }

    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    return DevPipelineHandoff.fromJson(
      payload['data'] as Map<String, dynamic>,
    );
  }

  Future<DevPipelineHandoffRequest> draftDevHandoff({
    String? sessionId,
  }) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/dev-pipeline/handoffs/draft'),
      headers: <String, String>{'Content-Type': 'application/json'},
      body: jsonEncode(<String, dynamic>{
        if (sessionId != null) 'session_id': sessionId,
      }),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to draft DEV handoff: ${response.body}');
    }

    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    return DevPipelineHandoffRequest.fromJson(
      payload['data'] as Map<String, dynamic>,
    );
  }

  Future<ProdUpdateStatus> getProdUpdateStatus() async {
    final response = await _client.get(
      Uri.parse('$baseUrl/dev-pipeline/prod-update/status'),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to fetch PROD update status: ${response.body}');
    }

    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    return ProdUpdateStatus.fromJson(payload['data'] as Map<String, dynamic>);
  }

  Future<ProdUpdateStatus> acknowledgeProdUpdate({
    required String acknowledgedBy,
  }) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/dev-pipeline/prod-update/acknowledge'),
      headers: <String, String>{'Content-Type': 'application/json'},
      body: jsonEncode(<String, dynamic>{'acknowledged_by': acknowledgedBy}),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to acknowledge PROD update: ${response.body}');
    }

    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    return ProdUpdateStatus.fromJson(payload['data'] as Map<String, dynamic>);
  }

  Future<ProdUpdateStatus> forceProdUpdate({
    required String requestedBy,
    required String strongConfirmation,
  }) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/dev-pipeline/prod-update/force'),
      headers: <String, String>{'Content-Type': 'application/json'},
      body: jsonEncode(<String, dynamic>{
        'requested_by': requestedBy,
        'strong_confirmation': strongConfirmation,
      }),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to force PROD update: ${response.body}');
    }

    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    return ProdUpdateStatus.fromJson(payload['data'] as Map<String, dynamic>);
  }

  Future<SynthesizedSpeechClip> synthesizeSpeech(String text) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/audio/speech'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(<String, dynamic>{'text': text}),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to synthesize speech: ${response.body}');
    }

    return SynthesizedSpeechClip(
      audioBytes: response.bodyBytes,
      contentType: response.headers['content-type'] ?? 'audio/mpeg',
      responseFormat: response.headers['x-response-format'] ?? 'mp3',
    );
  }

  Future<ServerCapabilities> getCapabilities() async {
    final response = await _client.get(Uri.parse('$baseUrl/capabilities'));

    if (response.statusCode != 200) {
      throw Exception('Failed to fetch capabilities: ${response.body}');
    }

    return ServerCapabilities.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<List<InstallableApp>> listInstallableApps() async {
    final response = await _client.get(Uri.parse('$baseUrl/installable-apps'));

    if (response.statusCode != 200) {
      throw Exception('Failed to list installable apps: ${response.body}');
    }

    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    return ((payload['apps'] as List<dynamic>?) ?? <dynamic>[])
        .whereType<Map<String, dynamic>>()
        .map(InstallableApp.fromJson)
        .toList(growable: false);
  }

  Future<InstallableApp> getInstallableApp(String sourceApp) async {
    final response = await _client.get(
      Uri.parse('$baseUrl/installable-apps/$sourceApp'),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to fetch installable app: ${response.body}');
    }

    return InstallableApp.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<ProjectFactoryOptions> getProjectFactoryOptions() async {
    final response = await _client.get(
      Uri.parse('$baseUrl/project-factory/options'),
    );

    if (response.statusCode == 404) {
      throw const ProjectFactoryUnavailableException(
        'This backend does not expose Project Factory yet. Restart or update the bridge backend, then try again.',
      );
    }

    if (response.statusCode != 200) {
      throw Exception(
        'Failed to fetch project factory options: ${response.body}',
      );
    }

    return ProjectFactoryOptions.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<ProjectFactoryDraft> createProjectFactoryDraft(
    ProjectFactoryDraftRequest request,
  ) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/project-factory/drafts'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(request.toJson()),
    );

    if (response.statusCode != 200) {
      throw Exception(
        'Failed to create project factory draft: ${response.body}',
      );
    }

    return ProjectFactoryDraft.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<List<ProjectFactoryDraftSummary>> listProjectFactoryDrafts({
    int limit = 50,
  }) async {
    final uri = Uri.parse(
      '$baseUrl/project-factory/drafts',
    ).replace(queryParameters: <String, String>{'limit': '$limit'});
    final response = await _client.get(uri);

    if (response.statusCode != 200) {
      throw Exception(
        'Failed to list project factory drafts: ${response.body}',
      );
    }

    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    return ((payload['drafts'] as List<dynamic>?) ?? <dynamic>[])
        .whereType<Map<String, dynamic>>()
        .map(ProjectFactoryDraftSummary.fromJson)
        .toList(growable: false);
  }

  Future<ProjectFactoryDraft> getProjectFactoryDraft(String draftId) async {
    final response = await _client.get(
      Uri.parse('$baseUrl/project-factory/drafts/$draftId'),
    );

    if (response.statusCode != 200) {
      throw Exception(
        'Failed to fetch project factory draft: ${response.body}',
      );
    }

    return ProjectFactoryDraft.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<ProjectFactoryGuidedIntake> getProjectFactoryGuidedIntake(
    String draftId,
  ) async {
    final response = await _client.get(
      Uri.parse('$baseUrl/project-factory/drafts/$draftId/intake'),
    );

    if (response.statusCode != 200) {
      throw Exception(
        'Failed to fetch project intake: ${response.body}',
      );
    }

    return ProjectFactoryGuidedIntake.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<ProjectFactoryGuidedIntake> answerProjectFactoryGuidedIntake({
    required String draftId,
    required String questionId,
    required Object? value,
    String source = 'user',
    double confidence = 1,
  }) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/project-factory/drafts/$draftId/intake/answers'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(<String, Object?>{
        'questionId': questionId,
        'value': value,
        'source': source,
        'confidence': confidence,
      }),
    );

    if (response.statusCode != 200) {
      throw Exception(
        'Failed to answer project intake: ${response.body}',
      );
    }

    return ProjectFactoryGuidedIntake.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<ProjectFactoryGuidedIntake> previewProjectFactoryGuidedIntake(
    String draftId,
  ) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/project-factory/drafts/$draftId/intake/preview'),
    );

    if (response.statusCode != 200) {
      throw Exception(
        'Failed to preview project intake: ${response.body}',
      );
    }

    return ProjectFactoryGuidedIntake.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<ProjectFactoryGuidedIntake> confirmProjectFactoryGuidedIntake(
    String draftId,
  ) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/project-factory/drafts/$draftId/intake/confirm'),
    );

    if (response.statusCode != 200) {
      throw Exception(
        'Failed to confirm project intake: ${response.body}',
      );
    }

    return ProjectFactoryGuidedIntake.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<ProjectFactoryJob> generateProjectFactoryDraft(String draftId) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/project-factory/drafts/$draftId/generate'),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to generate project: ${response.body}');
    }

    return ProjectFactoryJob.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<ProjectFactoryInitJob> startProjectFactoryInit({
    required String draftId,
    String? chatSessionId,
    String? workspacePath,
  }) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/project-factory/drafts/$draftId/init'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(<String, dynamic>{
        if (chatSessionId != null) 'chatSessionId': chatSessionId,
        if (workspacePath != null) 'workspacePath': workspacePath,
      }),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to start project init: ${response.body}');
    }

    return ProjectFactoryInitJob.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<ProjectFactoryInitJob> getProjectFactoryInitJob(
      String initJobId) async {
    final response = await _client.get(
      Uri.parse('$baseUrl/project-factory/init-jobs/$initJobId'),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to fetch project init: ${response.body}');
    }

    return ProjectFactoryInitJob.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<List<ProjectFactoryJobSummary>> listProjectFactoryJobs({
    String? status,
    String? draftId,
    int limit = 50,
  }) async {
    final query = <String, String>{'limit': '$limit'};
    if (status != null && status.trim().isNotEmpty) {
      query['status'] = status.trim();
    }
    if (draftId != null && draftId.trim().isNotEmpty) {
      query['draft_id'] = draftId.trim();
    }
    final uri = Uri.parse(
      '$baseUrl/project-factory/jobs',
    ).replace(queryParameters: query);
    final response = await _client.get(uri);

    if (response.statusCode != 200) {
      throw Exception('Failed to list project factory jobs: ${response.body}');
    }

    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    return ((payload['jobs'] as List<dynamic>?) ?? <dynamic>[])
        .whereType<Map<String, dynamic>>()
        .map(ProjectFactoryJobSummary.fromJson)
        .toList(growable: false);
  }

  Future<ProjectFactoryJob> getProjectFactoryJob(String jobId) async {
    final response = await _client.get(
      Uri.parse('$baseUrl/project-factory/jobs/$jobId'),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to fetch project factory job: ${response.body}');
    }

    return ProjectFactoryJob.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<List<WebPreview>> listWebPreviews({int limit = 50}) async {
    final uri = Uri.parse(
      '$baseUrl/web-previews',
    ).replace(queryParameters: <String, String>{'limit': '$limit'});
    final response = await _client.get(uri);

    if (response.statusCode != 200) {
      throw Exception('Failed to list web previews: ${response.body}');
    }

    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    return ((payload['previews'] as List<dynamic>?) ?? <dynamic>[])
        .whereType<Map<String, dynamic>>()
        .map(WebPreview.fromJson)
        .toList(growable: false);
  }

  Future<WebPreview> getWebPreview(String previewId) async {
    final response = await _client.get(
      Uri.parse('$baseUrl/web-previews/$previewId'),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to fetch web preview: ${response.body}');
    }

    return WebPreview.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<WebPreview> planWebPreview({
    String? projectPath,
    String? manifestPath,
    String? sourceApp,
  }) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/web-previews/plan'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(<String, dynamic>{
        if (projectPath != null) 'projectPath': projectPath,
        if (manifestPath != null) 'manifestPath': manifestPath,
        if (sourceApp != null) 'sourceApp': sourceApp,
      }),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to plan web preview: ${response.body}');
    }

    return WebPreview.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<WebPreview> deployWebPreview({
    String? projectPath,
    String? manifestPath,
    String? sourceApp,
    bool confirmApply = false,
    String? expectedPlanHash,
  }) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/web-previews/deploy'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(<String, dynamic>{
        if (projectPath != null) 'projectPath': projectPath,
        if (manifestPath != null) 'manifestPath': manifestPath,
        if (sourceApp != null) 'sourceApp': sourceApp,
        'confirmApply': confirmApply,
        if (expectedPlanHash != null) 'expectedPlanHash': expectedPlanHash,
      }),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to deploy web preview: ${response.body}');
    }

    return WebPreview.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<WebPreview> disableWebPreview({
    required String previewId,
    String? reason,
  }) {
    return _mutateWebPreviewLifecycle(
      previewId: previewId,
      action: 'disable',
      reason: reason,
    );
  }

  Future<WebPreview> expireWebPreview({
    required String previewId,
    String? reason,
  }) {
    return _mutateWebPreviewLifecycle(
      previewId: previewId,
      action: 'expire',
      reason: reason,
    );
  }

  Future<WebPreview> extendWebPreview({
    required String previewId,
    int? ttlSeconds,
    String? reason,
  }) {
    return _mutateWebPreviewLifecycle(
      previewId: previewId,
      action: 'extend',
      ttlSeconds: ttlSeconds,
      reason: reason,
    );
  }

  Future<WebPreview> _mutateWebPreviewLifecycle({
    required String previewId,
    required String action,
    int? ttlSeconds,
    String? reason,
  }) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/web-previews/$previewId/$action'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(<String, dynamic>{
        if (ttlSeconds != null) 'ttlSeconds': ttlSeconds,
        if (reason != null && reason.trim().isNotEmpty) 'reason': reason.trim(),
      }),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to $action web preview: ${response.body}');
    }

    return WebPreview.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<List<WebPreviewInvite>> listWebPreviewInvites(String previewId) async {
    final response = await _client.get(
      Uri.parse('$baseUrl/web-previews/$previewId/invites'),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to list web preview invites: ${response.body}');
    }

    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    return ((payload['invites'] as List<dynamic>?) ?? <dynamic>[])
        .whereType<Map<String, dynamic>>()
        .map(WebPreviewInvite.fromJson)
        .toList(growable: false);
  }

  Future<WebPreviewInvite> createWebPreviewInvite(
    String previewId, {
    int? ttlSeconds,
    bool singleUse = true,
    String? email,
    String role = 'admin',
  }) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/web-previews/$previewId/invites'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(<String, dynamic>{
        if (ttlSeconds != null) 'ttlSeconds': ttlSeconds,
        'singleUse': singleUse,
        if (email != null && email.trim().isNotEmpty) 'email': email.trim(),
        'role': role,
      }),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to create web preview invite: ${response.body}');
    }

    return WebPreviewInvite.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<WebPreviewInvite> resendWebPreviewInvite({
    required String previewId,
    required String inviteId,
    int? ttlSeconds,
  }) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/web-previews/$previewId/invites/$inviteId/resend'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(<String, dynamic>{
        if (ttlSeconds != null) 'ttlSeconds': ttlSeconds,
      }),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to resend web preview invite: ${response.body}');
    }

    return WebPreviewInvite.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<WebPreviewInvite> expireWebPreviewInvite({
    required String previewId,
    required String inviteId,
  }) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/web-previews/$previewId/invites/$inviteId/expire'),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to expire web preview invite: ${response.body}');
    }

    return WebPreviewInvite.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<WebPreviewInvite> revokeWebPreviewInvite({
    required String previewId,
    required String inviteId,
  }) async {
    final response = await _client.delete(
      Uri.parse('$baseUrl/web-previews/$previewId/invites/$inviteId'),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to revoke web preview invite: ${response.body}');
    }

    return WebPreviewInvite.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<WebPreviewInvite> syncWebPreviewInvite({
    required String previewId,
    required String inviteId,
  }) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/web-previews/$previewId/invites/$inviteId/sync'),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to sync web preview invite: ${response.body}');
    }

    return WebPreviewInvite.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<List<ProjectFactoryReferenceAsset>> listProjectFactoryReferenceAssets(
    String draftId,
  ) async {
    final response = await _client.get(
      Uri.parse('$baseUrl/project-factory/drafts/$draftId/reference-assets'),
    );

    if (response.statusCode != 200) {
      throw Exception(
        'Failed to list project reference assets: ${response.body}',
      );
    }

    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    final assets = payload['assets'] as List<dynamic>? ?? <dynamic>[];
    return assets
        .map(
          (item) => ProjectFactoryReferenceAsset.fromJson(
            item as Map<String, dynamic>,
          ),
        )
        .toList(growable: false);
  }

  Future<ProjectFactoryReferenceAsset> uploadProjectFactoryReferenceAsset(
    String draftId,
    XFile image,
  ) async {
    final request = http.MultipartRequest(
      'POST',
      Uri.parse('$baseUrl/project-factory/drafts/$draftId/reference-assets'),
    );
    request.files.add(await _multipartFileFromXFile('asset', image));

    final streamedResponse = await _client.send(request);
    final response = await http.Response.fromStream(streamedResponse);
    if (response.statusCode != 200) {
      throw Exception('Failed to upload reference asset: ${response.body}');
    }

    return ProjectFactoryReferenceAsset.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<AssetDepotAsset> uploadAssetDepotAsset(
    XFile file, {
    String source = 'manual_upload',
  }) async {
    final request = http.MultipartRequest('POST', Uri.parse('$baseUrl/assets'));
    request.fields['source'] = source;
    request.files.add(await _multipartFileFromXFile('asset', file));

    final streamedResponse = await _client.send(request);
    final response = await http.Response.fromStream(streamedResponse);
    if (response.statusCode != 200) {
      throw Exception('Failed to upload asset: ${response.body}');
    }

    return AssetDepotAsset.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<AssetDepotAsset> createAssetFromJobAttachment({
    required String jobId,
    required int attachmentIndex,
    String source = 'chat_upload',
  }) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/assets/from-job-attachment'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(<String, dynamic>{
        'job_id': jobId,
        'attachment_index': attachmentIndex,
        'source': source,
      }),
    );

    if (response.statusCode != 200) {
      throw Exception(
        'Failed to create asset from chat attachment: ${response.body}',
      );
    }

    return AssetDepotAsset.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<ProjectFactoryDraftAsset> linkProjectFactoryDraftAsset({
    required String draftId,
    required String assetId,
    required ProjectAssetRole role,
    String notes = '',
  }) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/project-factory/drafts/$draftId/assets'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(<String, dynamic>{
        'asset_id': assetId,
        'role': role.apiValue,
        'notes': notes,
      }),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to link project asset: ${response.body}');
    }

    return ProjectFactoryDraftAsset.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<List<ProjectFactoryDraftAsset>> listProjectFactoryDraftAssets(
    String draftId,
  ) async {
    final response = await _client.get(
      Uri.parse('$baseUrl/project-factory/drafts/$draftId/assets'),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to list project assets: ${response.body}');
    }

    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    final assets = payload['assets'] as List<dynamic>? ?? <dynamic>[];
    return assets
        .map(
          (item) =>
              ProjectFactoryDraftAsset.fromJson(item as Map<String, dynamic>),
        )
        .toList(growable: false);
  }

  Future<void> deleteProjectFactoryReferenceAsset({
    required String draftId,
    required String assetId,
  }) async {
    final response = await _client.delete(
      Uri.parse(
        '$baseUrl/project-factory/drafts/$draftId/reference-assets/$assetId',
      ),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to delete reference asset: ${response.body}');
    }
  }

  Future<CodexToolingSnapshot> getCodexTooling({String? workspacePath}) async {
    final uri = Uri.parse('$baseUrl/codex/tooling').replace(
      queryParameters: <String, String>{
        if (workspacePath != null && workspacePath.trim().isNotEmpty)
          'workspace_path': workspacePath,
      },
    );
    final response = await _client.get(uri);

    if (response.statusCode != 200) {
      throw Exception('Failed to fetch Codex tooling: ${response.body}');
    }

    return CodexToolingSnapshot.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<CodexMcpAppInstallResult> installCodexMcpApp(String appId) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/codex/mcp-apps/$appId/install'),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to install MCP app: ${response.body}');
    }

    return CodexMcpAppInstallResult.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<List<Workspace>> listWorkspaces() async {
    final response = await _client.get(Uri.parse('$baseUrl/workspaces'));

    if (response.statusCode != 200) {
      throw Exception('Failed to list workspaces: ${response.body}');
    }

    final payload = jsonDecode(response.body) as List<dynamic>;
    return payload
        .map((item) => Workspace.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<List<AgentProfile>> listAgentProfiles() async {
    final response = await _client.get(Uri.parse('$baseUrl/agent-profiles'));

    if (response.statusCode != 200) {
      throw Exception('Failed to list agent profiles: ${response.body}');
    }

    final payload = jsonDecode(response.body) as List<dynamic>;
    return payload
        .map((item) => AgentProfile.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<List<AgentProfile>> exportAgentProfiles() async {
    final response = await _client.get(
      Uri.parse('$baseUrl/agent-profiles/export'),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to export agent profiles: ${response.body}');
    }

    final payload = jsonDecode(response.body) as List<dynamic>;
    return payload
        .map((item) => AgentProfile.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<SessionDetail> createSession({
    String? title,
    String? workspacePath,
    String? agentProfileId,
    bool turnSummariesEnabled = false,
  }) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/sessions'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'title': title,
        if (workspacePath != null) 'workspace_path': workspacePath,
        if (agentProfileId != null) 'agent_profile_id': agentProfileId,
        'turn_summaries_enabled': turnSummariesEnabled,
      }),
    );

    if (response.statusCode != 201) {
      throw Exception('Failed to create session: ${response.body}');
    }

    return SessionDetail.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<AgentProfile> createAgentProfile({
    required String name,
    required String description,
    required String colorHex,
    required AgentConfiguration configuration,
  }) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/agent-profiles'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(<String, dynamic>{
        'name': name,
        'description': description,
        'color_hex': colorHex,
        'configuration': configuration.toJson(),
      }),
    );

    if (response.statusCode != 201) {
      throw Exception('Failed to create agent profile: ${response.body}');
    }

    return AgentProfile.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<List<AgentProfile>> importAgentProfiles(
    List<AgentProfile> profiles,
  ) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/agent-profiles/import'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(<String, dynamic>{
        'profiles': profiles.map((profile) => profile.toJson()).toList(),
      }),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to import agent profiles: ${response.body}');
    }

    final payload = jsonDecode(response.body) as List<dynamic>;
    return payload
        .map((item) => AgentProfile.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<SessionDetail> getSession(
    String sessionId, {
    String? before,
    int? limit,
    bool fullTranscript = false,
  }) async {
    final query = <String, String>{
      if (before != null) 'before': before,
      if (limit != null) 'limit': '$limit',
      'transcript': fullTranscript ? 'full' : 'window',
    };
    final uri = Uri.parse(
      '$baseUrl/sessions/$sessionId',
    ).replace(queryParameters: query.isEmpty ? null : query);
    final response = await _client.get(uri);

    if (response.statusCode != 200) {
      throw Exception('Failed to fetch session: ${response.body}');
    }

    return SessionDetail.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<SessionDetail> updateAutoMode(
    String sessionId, {
    required bool enabled,
    required int maxTurns,
    String? reviewerPrompt,
  }) async {
    final response = await _client.put(
      Uri.parse('$baseUrl/sessions/$sessionId/auto-mode'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'enabled': enabled,
        'max_turns': maxTurns,
        'reviewer_prompt': reviewerPrompt,
      }),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to update auto mode: ${response.body}');
    }

    return SessionDetail.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<SessionDetail> updateAgentConfiguration(
    String sessionId, {
    required AgentConfiguration configuration,
  }) async {
    final response = await _client.put(
      Uri.parse('$baseUrl/sessions/$sessionId/agents'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(configuration.toJson()),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to update agent configuration: ${response.body}');
    }

    return SessionDetail.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<DomainFactoryStart> startDomainFactoryMode(
    String sessionId, {
    String? workspacePath,
  }) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/sessions/$sessionId/domain-factory/start'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(<String, dynamic>{
        if (workspacePath != null) 'workspace_path': workspacePath,
      }),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to start Domain Factory: ${response.body}');
    }

    return DomainFactoryStart.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<DomainFactoryIntake> submitDomainFactoryIntake(
    String sessionId, {
    required String brief,
    List<DomainFactoryMediaReference> mediaReferences =
        const <DomainFactoryMediaReference>[],
  }) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/sessions/$sessionId/domain-factory/intake'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(<String, dynamic>{
        'brief': brief,
        'mediaReferences': mediaReferences
            .map((reference) => reference.toJson())
            .toList(growable: false),
      }),
    );

    if (response.statusCode != 200) {
      throw Exception(
          'Failed to submit Domain Factory intake: ${response.body}');
    }

    return DomainFactoryIntake.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<DomainFactoryImplementation> confirmDomainFactoryImplementation(
    String sessionId,
  ) async {
    final response = await _client.post(
      Uri.parse(
        '$baseUrl/sessions/$sessionId/domain-factory/implementation/confirm',
      ),
      headers: {'Content-Type': 'application/json'},
    );

    if (response.statusCode != 200) {
      throw Exception(
        'Failed to confirm Domain Factory implementation: ${response.body}',
      );
    }

    return DomainFactoryImplementation.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<SessionDetail> updateTurnSummaries(
    String sessionId, {
    required bool enabled,
  }) async {
    final response = await _client.put(
      Uri.parse('$baseUrl/sessions/$sessionId/turn-summaries'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(<String, dynamic>{'enabled': enabled}),
    );

    if (response.statusCode != 200) {
      throw Exception(
        'Failed to update turn summaries: ${_turnSummaryErrorDetail(response)}',
      );
    }

    return SessionDetail.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  String _turnSummaryErrorDetail(http.Response response) {
    final detail = _responseErrorDetail(response);
    if (response.statusCode == 404 && detail.toLowerCase() == 'not found') {
      return 'Turn summaries are not available on the connected backend. Pull the latest backend changes and restart it.';
    }
    return detail;
  }

  String _responseErrorDetail(http.Response response) {
    final body = response.body.trim();
    if (body.isEmpty) {
      return 'HTTP ${response.statusCode}';
    }
    try {
      final decoded = jsonDecode(body);
      if (decoded is Map<String, dynamic>) {
        final detail = decoded['detail'];
        if (detail is String && detail.trim().isNotEmpty) {
          return detail.trim();
        }
      }
    } catch (_) {
      // Fall back to the raw body for non-JSON responses.
    }
    return body;
  }

  Future<SessionDetail> setSessionArchived(
    String sessionId, {
    required bool archived,
  }) async {
    final response = await _client.put(
      Uri.parse('$baseUrl/sessions/$sessionId/archive'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(<String, dynamic>{'archived': archived}),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to update archive state: ${response.body}');
    }

    return SessionDetail.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<SessionDetail> renameSession(
    String sessionId, {
    required String title,
  }) async {
    final response = await _client.put(
      Uri.parse('$baseUrl/sessions/$sessionId/title'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(<String, dynamic>{'title': title}),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to rename chat: ${response.body}');
    }

    return SessionDetail.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<SessionDetail> generateSessionTitle(
    String sessionId, {
    String? instructions,
  }) async {
    final trimmedInstructions = instructions?.trim();
    final response = await _client.post(
      Uri.parse('$baseUrl/sessions/$sessionId/title/generate'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(<String, dynamic>{
        if (trimmedInstructions != null && trimmedInstructions.isNotEmpty)
          'instructions': trimmedInstructions,
      }),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to generate chat title: ${response.body}');
    }

    return SessionDetail.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<SessionDetail> generateSessionTitleFromAudio(
    String sessionId,
    XFile audioFile, {
    String? instructions,
    String? language,
  }) async {
    final request = http.MultipartRequest(
      'POST',
      Uri.parse('$baseUrl/sessions/$sessionId/title/generate/audio'),
    );
    final trimmedInstructions = instructions?.trim();
    if (trimmedInstructions != null && trimmedInstructions.isNotEmpty) {
      request.fields['instructions'] = trimmedInstructions;
    }
    if (language != null) {
      request.fields['language'] = language;
    }
    request.files.add(await _multipartFileFromXFile('audio', audioFile));

    final streamedResponse = await _client.send(request);
    final response = await http.Response.fromStream(streamedResponse);
    if (response.statusCode != 200) {
      throw Exception(
        'Failed to generate chat title from audio: ${response.body}',
      );
    }

    return SessionDetail.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<SessionDetail> applyAgentProfile(
    String sessionId, {
    required String profileId,
  }) async {
    final response = await _client.put(
      Uri.parse('$baseUrl/sessions/$sessionId/agent-profile'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(<String, dynamic>{'profile_id': profileId}),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to apply agent profile: ${response.body}');
    }

    return SessionDetail.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<JobStatusResponse> sendMessage(
    String message, {
    String? sessionId,
    String? workspacePath,
    CodexRunOptions? codexRunOptions,
  }) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/message'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'message': message,
        if (sessionId != null) 'session_id': sessionId,
        if (workspacePath != null) 'workspace_path': workspacePath,
        if (codexRunOptions != null && !codexRunOptions.isEmpty)
          'codex_options': codexRunOptions.toJson(),
      }),
    );

    if (response.statusCode != 202) {
      throw Exception('Failed to create job: ${response.body}');
    }

    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    return JobStatusResponse.fromJson(payload);
  }

  Future<JobStatusResponse> sendAudioMessage(
    XFile audioFile, {
    String? sessionId,
    String? workspacePath,
    String? message,
    String? language,
    CodexRunOptions? codexRunOptions,
  }) async {
    final request = http.MultipartRequest(
      'POST',
      Uri.parse('$baseUrl/message/audio'),
    );
    if (sessionId != null) {
      request.fields['session_id'] = sessionId;
    }
    if (workspacePath != null) {
      request.fields['workspace_path'] = workspacePath;
    }
    final trimmedMessage = message?.trim();
    if (trimmedMessage != null && trimmedMessage.isNotEmpty) {
      request.fields['message'] = trimmedMessage;
    }
    if (language != null) {
      request.fields['language'] = language;
    }
    if (codexRunOptions != null && !codexRunOptions.isEmpty) {
      request.fields['codex_options_json'] = jsonEncode(
        codexRunOptions.toJson(),
      );
    }

    request.files.add(await _multipartFileFromXFile('audio', audioFile));

    final streamedResponse = await _client.send(request);
    final response = await http.Response.fromStream(streamedResponse);
    if (response.statusCode != 202) {
      throw Exception('Failed to upload audio message: ${response.body}');
    }

    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    return JobStatusResponse.fromJson(payload);
  }

  Future<JobStatusResponse> sendImageMessage(
    XFile imageFile, {
    String? message,
    String? sessionId,
    String? workspacePath,
    CodexRunOptions? codexRunOptions,
  }) async {
    final request = http.MultipartRequest(
      'POST',
      Uri.parse('$baseUrl/message/image'),
    );
    if (message != null && message.trim().isNotEmpty) {
      request.fields['message'] = message.trim();
    }
    if (sessionId != null) {
      request.fields['session_id'] = sessionId;
    }
    if (workspacePath != null) {
      request.fields['workspace_path'] = workspacePath;
    }
    if (codexRunOptions != null && !codexRunOptions.isEmpty) {
      request.fields['codex_options_json'] = jsonEncode(
        codexRunOptions.toJson(),
      );
    }

    request.files.add(await _multipartFileFromXFile('image', imageFile));

    final streamedResponse = await _client.send(request);
    final response = await http.Response.fromStream(streamedResponse);
    if (response.statusCode != 202) {
      throw Exception('Failed to upload image message: ${response.body}');
    }

    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    return JobStatusResponse.fromJson(payload);
  }

  Future<List<FeedbackQueueItem>> listFeedbackQueue({
    bool includeImages = false,
  }) async {
    final uri = Uri.parse('$baseUrl/feedback-queue').replace(
      queryParameters: <String, String>{
        if (includeImages) 'include_images': 'true',
      },
    );
    final response = await _client.get(uri);

    if (response.statusCode != 200) {
      throw Exception('Failed to list feedback queue: ${response.body}');
    }

    final payload = jsonDecode(response.body) as List<dynamic>;
    return payload
        .map((item) => FeedbackQueueItem.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<FeedbackQueueItem> createFeedbackQueueItem({
    required String sourceApp,
    required String comment,
    String? sourceDisplayName,
    String? feedbackKind,
    Map<String, Object?> contextMetadata = const <String, Object?>{},
    Map<String, double> selectionBounds = const <String, double>{},
  }) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/feedback-queue'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(<String, Object?>{
        'sourceApp': sourceApp,
        if (sourceDisplayName != null && sourceDisplayName.trim().isNotEmpty)
          'sourceDisplayName': sourceDisplayName.trim(),
        'comment': comment.trim(),
        if (feedbackKind != null && feedbackKind.trim().isNotEmpty)
          'feedbackKind': feedbackKind.trim(),
        if (contextMetadata.isNotEmpty) 'contextMetadata': contextMetadata,
        if (selectionBounds.isNotEmpty) 'selectionBounds': selectionBounds,
      }),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to create feedback item: ${response.body}');
    }

    return FeedbackQueueItem.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<void> deleteFeedbackQueueItem(String id) async {
    final response = await _client.delete(
      Uri.parse('$baseUrl/feedback-queue/$id'),
    );
    if (response.statusCode != 204) {
      throw Exception('Failed to delete feedback item: ${response.body}');
    }
  }

  Future<void> clearFeedbackQueue() async {
    final response = await _client.delete(Uri.parse('$baseUrl/feedback-queue'));
    if (response.statusCode != 204) {
      throw Exception('Failed to clear feedback queue: ${response.body}');
    }
  }

  Future<JobStatusResponse> startFeedbackQueueSession(
    String id, {
    String? message,
    String? sessionId,
    String? workspacePath,
    FeedbackQueueTargetMode targetMode = FeedbackQueueTargetMode.generatorOnly,
    CodexRunOptions? codexRunOptions,
  }) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/feedback-queue/$id/start-session'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(<String, dynamic>{
        if (message != null && message.trim().isNotEmpty)
          'message': message.trim(),
        if (sessionId != null) 'session_id': sessionId,
        if (workspacePath != null) 'workspace_path': workspacePath,
        'target_mode': targetMode.apiValue,
        if (codexRunOptions != null && !codexRunOptions.isEmpty)
          'codex_options': codexRunOptions.toJson(),
      }),
    );

    if (response.statusCode != 202) {
      throw Exception('Failed to start feedback session: ${response.body}');
    }

    return JobStatusResponse.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<JobStatusResponse> sendDocumentMessage(
    XFile documentFile, {
    String? message,
    String? sessionId,
    String? workspacePath,
    String? language,
    CodexRunOptions? codexRunOptions,
  }) async {
    final request = http.MultipartRequest(
      'POST',
      Uri.parse('$baseUrl/message/document'),
    );
    if (message != null && message.trim().isNotEmpty) {
      request.fields['message'] = message.trim();
    }
    if (sessionId != null) {
      request.fields['session_id'] = sessionId;
    }
    if (workspacePath != null) {
      request.fields['workspace_path'] = workspacePath;
    }
    if (language != null) {
      request.fields['language'] = language;
    }
    if (codexRunOptions != null && !codexRunOptions.isEmpty) {
      request.fields['codex_options_json'] = jsonEncode(
        codexRunOptions.toJson(),
      );
    }

    request.files.add(await _multipartFileFromXFile('document', documentFile));

    final streamedResponse = await _client.send(request);
    final response = await http.Response.fromStream(streamedResponse);
    if (response.statusCode != 202) {
      throw Exception('Failed to upload document message: ${response.body}');
    }

    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    return JobStatusResponse.fromJson(payload);
  }

  Future<JobStatusResponse> sendAttachmentsMessage(
    List<XFile> attachments, {
    String? message,
    String? sessionId,
    String? workspacePath,
    String? language,
    CodexRunOptions? codexRunOptions,
  }) async {
    if (attachments.isEmpty) {
      throw Exception('No attachments were provided.');
    }

    final request = http.MultipartRequest(
      'POST',
      Uri.parse('$baseUrl/message/attachments'),
    );
    if (message != null && message.trim().isNotEmpty) {
      request.fields['message'] = message.trim();
    }
    if (sessionId != null) {
      request.fields['session_id'] = sessionId;
    }
    if (workspacePath != null) {
      request.fields['workspace_path'] = workspacePath;
    }
    if (language != null) {
      request.fields['language'] = language;
    }
    if (codexRunOptions != null && !codexRunOptions.isEmpty) {
      request.fields['codex_options_json'] = jsonEncode(
        codexRunOptions.toJson(),
      );
    }

    for (final attachment in attachments) {
      request.files.add(
        await _multipartFileFromXFile('attachments', attachment),
      );
    }

    final streamedResponse = await _client.send(request);
    final response = await http.Response.fromStream(streamedResponse);
    if (response.statusCode != 202) {
      throw Exception('Failed to upload attachments: ${response.body}');
    }

    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    return JobStatusResponse.fromJson(payload);
  }

  Future<JobStatusResponse> getJob(String jobId) async {
    final response = await _client.get(Uri.parse('$baseUrl/response/$jobId'));

    if (response.statusCode != 200) {
      throw Exception('Failed to fetch job: ${response.body}');
    }

    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    return JobStatusResponse.fromJson(payload);
  }

  Future<JobStatusResponse> cancelJob(String jobId) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/jobs/$jobId/cancel'),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to cancel job: ${response.body}');
    }

    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    return JobStatusResponse.fromJson(payload);
  }

  Future<JobStatusResponse> retryJob(String jobId) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/jobs/$jobId/retry'),
    );

    if (response.statusCode != 202) {
      throw Exception('Failed to retry job: ${response.body}');
    }

    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    return JobStatusResponse.fromJson(payload);
  }

  Future<SessionDetail> recoverMessage(
    String sessionId,
    String messageId, {
    required MessageRecoveryAction action,
  }) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/sessions/$sessionId/messages/$messageId/recovery'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(<String, dynamic>{
        'action': action == MessageRecoveryAction.cancel ? 'cancel' : 'retry',
      }),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to recover message: ${response.body}');
    }

    return SessionDetail.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<http.MultipartFile> _multipartFileFromXFile(
    String field,
    XFile file,
  ) async {
    final mimeType = file.mimeType?.trim();
    final filename = _filenameFromXFile(file);
    final resolvedMimeType = mimeType == null || mimeType.isEmpty
        ? _mimeTypeFromFilename(filename)
        : mimeType;
    return http.MultipartFile.fromBytes(
      field,
      await file.readAsBytes(),
      filename: filename,
      contentType: resolvedMimeType == null || resolvedMimeType.isEmpty
          ? null
          : MediaType.parse(resolvedMimeType),
    );
  }

  String? _filenameFromXFile(XFile file) {
    final name = file.name.trim();
    if (name.isNotEmpty) {
      return name;
    }
    final path = file.path.trim();
    if (path.isEmpty) {
      return null;
    }
    final normalized = path.replaceAll('\\', '/');
    final segments = normalized
        .split('/')
        .where((segment) => segment.trim().isNotEmpty)
        .toList();
    return segments.isEmpty ? null : segments.last;
  }

  String? _mimeTypeFromFilename(String? filename) {
    final suffix = filename?.trim().toLowerCase().split('.').last;
    return switch (suffix) {
      'png' => 'image/png',
      'jpg' || 'jpeg' => 'image/jpeg',
      'webp' => 'image/webp',
      'gif' => 'image/gif',
      'm4a' || 'mp4' => 'audio/mp4',
      'mp3' => 'audio/mpeg',
      'wav' => 'audio/wav',
      'webm' => 'audio/webm',
      _ => null,
    };
  }
}
