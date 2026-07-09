import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/sdd_project.dart';

class SddExplorerClient {
  SddExplorerClient({required this.baseUrl, http.Client? client})
    : _client = client ?? http.Client();

  final String baseUrl;
  final http.Client _client;

  Future<SddProjectsIndex> listProjects() async {
    final response = await _client.get(Uri.parse('$baseUrl/sdd/projects'));
    if (response.statusCode != 200) {
      throw Exception('Failed to load SDD projects: ${response.body}');
    }
    return SddProjectsIndex.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<SddProject> getProject(String workspacePath) async {
    final uri = Uri.parse('$baseUrl/sdd/project').replace(
      queryParameters: <String, String>{'workspace_path': workspacePath},
    );
    final response = await _client.get(uri);
    if (response.statusCode != 200) {
      throw Exception('Failed to load SDD project: ${response.body}');
    }
    return SddProject.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<SddProject> getProjectSummary(String workspacePath) async {
    final uri = Uri.parse('$baseUrl/sdd/project/summary').replace(
      queryParameters: <String, String>{'workspace_path': workspacePath},
    );
    final response = await _client.get(uri);
    if (response.statusCode != 200) {
      throw Exception('Failed to load SDD project summary: ${response.body}');
    }
    return SddProject.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<SddSpec> getSpec(String workspacePath, String specId) async {
    final uri = Uri.parse('$baseUrl/sdd/project/spec').replace(
      queryParameters: <String, String>{
        'workspace_path': workspacePath,
        'spec_id': specId,
      },
    );
    final response = await _client.get(uri);
    if (response.statusCode != 200) {
      throw Exception('Failed to load SDD spec: ${response.body}');
    }
    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    final spec = payload['spec'];
    if (spec is! Map<String, dynamic>) {
      throw Exception('Failed to load SDD spec: malformed response');
    }
    return SddSpec.fromJson(spec);
  }

  Future<SddProject> loadProject(String workspacePath) async {
    try {
      return await getProjectSummary(workspacePath);
    } catch (_) {
      return getProject(workspacePath);
    }
  }

  Future<List<SddDiagram>> getProjectDiagrams(String workspacePath) async {
    final uri = Uri.parse('$baseUrl/sdd/project/diagrams').replace(
      queryParameters: <String, String>{'workspace_path': workspacePath},
    );
    final response = await _client.get(uri);
    if (response.statusCode != 200) {
      throw Exception('Failed to load SDD diagrams: ${response.body}');
    }
    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    final rawDiagrams = payload['diagrams'];
    if (rawDiagrams is! List) {
      return const <SddDiagram>[];
    }
    return rawDiagrams
        .whereType<Map<String, dynamic>>()
        .map(SddDiagram.fromJson)
        .toList(growable: false);
  }

  Future<SddProject?> loadDefaultProject() async {
    final index = await listProjects();
    if (index.projects.isEmpty) {
      return null;
    }
    final defaultPath = index.defaultWorkspacePath;
    final selected = defaultPath == null
        ? index.projects.first
        : index.projects.firstWhere(
            (project) => project.workspacePath == defaultPath,
            orElse: () => index.projects.first,
          );
    return loadProject(selected.workspacePath);
  }

  Future<SddSpecIntakePlan> dryRunSpecIntake(SddSpecIntakeDraft draft) {
    final path = draft.mode == SddSpecIntakeMode.newSpec
        ? '/sdd/specs/dry-run'
        : '/sdd/specs/edit/dry-run';
    return _postSpecIntakePlan(path, draft);
  }

  Future<SddSpecIntakeApplyResult> applySpecIntake(SddSpecIntakeDraft draft) {
    final path = draft.mode == SddSpecIntakeMode.newSpec
        ? '/sdd/specs/apply'
        : '/sdd/specs/edit/apply';
    return _postSpecIntakeApply(path, draft);
  }

  Future<SddCodexJobStatus> getCodexJob(String jobId) async {
    return _getCodexJob('/sdd/codex-jobs/$jobId');
  }

  Future<SddActivitySnapshot> getCodexJobActivity(String jobId) async {
    final response = await _client.get(
      Uri.parse('$baseUrl/sdd/codex-jobs/$jobId/activity'),
    );
    if (response.statusCode != 200) {
      throw Exception(
        'Failed to load SDD Codex job activity: ${response.body}',
      );
    }
    return SddActivitySnapshot.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<SddCodexJobStatus> runCodexJob(String jobId) async {
    return _postCodexJob('/sdd/codex-jobs/$jobId/run');
  }

  Future<SddCodexJobStatus> cancelCodexJob(String jobId) async {
    return _postCodexJob('/sdd/codex-jobs/$jobId/cancel');
  }

  Future<SddCodexJobRetryResult> retryCodexJob(String jobId) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/sdd/codex-jobs/$jobId/retry'),
    );
    if (response.statusCode != 200) {
      throw Exception('Failed to retry SDD Codex job: ${response.body}');
    }
    return SddCodexJobRetryResult.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<SddCodexJobReview> reviewCodexJob(String jobId) async {
    final response = await _client.get(
      Uri.parse('$baseUrl/sdd/codex-jobs/$jobId/review'),
    );
    if (response.statusCode != 200) {
      throw Exception('Failed to review SDD Codex job: ${response.body}');
    }
    return SddCodexJobReview.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<SddCodexJobApplyResult> applyCodexJob(String jobId) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/sdd/codex-jobs/$jobId/apply'),
    );
    if (response.statusCode != 200) {
      throw Exception('Failed to apply SDD Codex job: ${response.body}');
    }
    return SddCodexJobApplyResult.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<SddStagedMediaAttachment> uploadSpecMedia({
    required String workspacePath,
    required SddMediaAttachmentDraft attachment,
    String kind = 'image',
    String? sourceRef,
    Map<String, Object?>? region,
  }) async {
    final request =
        http.MultipartRequest(
            'POST',
            Uri.parse('$baseUrl/sdd/specs/intake/media'),
          )
          ..fields['workspace_path'] = workspacePath
          ..fields['kind'] = kind
          ..fields['mime_type'] = attachment.mimeType
          ..files.add(
            http.MultipartFile.fromBytes(
              'media',
              attachment.bytes,
              filename: attachment.filename,
            ),
          );
    final sha256 = attachment.sha256;
    if (sha256 != null && sha256.trim().isNotEmpty) {
      request.fields['sha256'] = sha256;
    }
    final durationMs = attachment.durationMs;
    if (durationMs != null) {
      request.fields['duration_ms'] = durationMs.toString();
    }
    if (sourceRef != null && sourceRef.trim().isNotEmpty) {
      request.fields['source_ref'] = sourceRef;
    }
    if (region != null) {
      request.fields['region'] = jsonEncode(region);
    }
    final streamed = await _client.send(request);
    final body = await streamed.stream.bytesToString();
    if (streamed.statusCode != 200) {
      throw Exception('Failed to upload SDD intake media: $body');
    }
    final payload = jsonDecode(body) as Map<String, dynamic>;
    final staged = SddStagedMediaAttachment.fromJson(payload);
    if (staged.status != 'staged') {
      throw Exception(
        <String>[
          'SDD intake media upload blocked',
          ...staged.blocked,
          ...staged.nextActions,
        ].join(': '),
      );
    }
    return staged.copyWith(previewBytes: attachment.bytes);
  }

  Future<SddMediaLifecycleResult> deleteSpecMedia({
    required String workspacePath,
    required String stagedPath,
  }) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/sdd/specs/intake/media/delete'),
      headers: const <String, String>{'content-type': 'application/json'},
      body: jsonEncode(<String, Object?>{
        'workspacePath': workspacePath,
        'stagedPath': stagedPath,
      }),
    );
    if (response.statusCode != 200) {
      throw Exception('Failed to delete SDD intake media: ${response.body}');
    }
    final result = SddMediaLifecycleResult.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
    if (result.status != 'deleted') {
      throw Exception(
        <String>[
          'SDD intake media delete blocked',
          ...result.blocked,
          ...result.nextActions,
        ].join(': '),
      );
    }
    return result;
  }

  Future<SddSpecIntakePlan> _postSpecIntakePlan(
    String path,
    SddSpecIntakeDraft draft,
  ) async {
    final response = await _client.post(
      Uri.parse('$baseUrl$path'),
      headers: const <String, String>{'content-type': 'application/json'},
      body: jsonEncode(draft.toJson()),
    );
    if (response.statusCode != 200) {
      throw Exception('Failed to preview SDD spec intake: ${response.body}');
    }
    return SddSpecIntakePlan.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<SddSpecIntakeApplyResult> _postSpecIntakeApply(
    String path,
    SddSpecIntakeDraft draft,
  ) async {
    final response = await _client.post(
      Uri.parse('$baseUrl$path'),
      headers: const <String, String>{'content-type': 'application/json'},
      body: jsonEncode(draft.toJson()),
    );
    if (response.statusCode != 200) {
      throw Exception('Failed to apply SDD spec intake: ${response.body}');
    }
    return SddSpecIntakeApplyResult.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<SddCodexJobStatus> _getCodexJob(String path) async {
    final response = await _client.get(Uri.parse('$baseUrl$path'));
    if (response.statusCode != 200) {
      throw Exception('Failed to load SDD Codex job: ${response.body}');
    }
    return SddCodexJobStatus.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<SddCodexJobStatus> _postCodexJob(String path) async {
    final response = await _client.post(Uri.parse('$baseUrl$path'));
    if (response.statusCode != 200) {
      throw Exception('Failed to update SDD Codex job: ${response.body}');
    }
    return SddCodexJobStatus.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }
}

enum SddSpecIntakeMode { newSpec, existingSpec }

class SddSpecIntakeDraft {
  const SddSpecIntakeDraft({
    required this.workspacePath,
    required this.mode,
    required this.requestText,
    this.specId,
    this.artifact = 'tasks',
    this.attachments = const <SddStagedMediaAttachment>[],
  });

  final String workspacePath;
  final SddSpecIntakeMode mode;
  final String requestText;
  final String? specId;
  final String artifact;
  final List<SddStagedMediaAttachment> attachments;

  Map<String, Object?> toJson() {
    return <String, Object?>{
      'workspacePath': workspacePath,
      'specTarget': <String, Object?>{
        'mode': mode == SddSpecIntakeMode.newSpec
            ? 'new_spec'
            : 'existing_spec',
        if (specId != null && specId!.trim().isNotEmpty) 'specId': specId,
        'artifact': artifact,
      },
      'intakeItems': <Map<String, Object?>>[
        <String, Object?>{'kind': 'text', 'text': requestText},
        ...attachments.map((attachment) => attachment.intakeItem),
      ],
    };
  }
}

class SddMediaAttachmentDraft {
  const SddMediaAttachmentDraft({
    required this.filename,
    required this.mimeType,
    required this.bytes,
    this.sha256,
    this.durationMs,
  });

  final String filename;
  final String mimeType;
  final List<int> bytes;
  final String? sha256;
  final int? durationMs;
}

class SddStagedMediaAttachment {
  const SddStagedMediaAttachment({
    required this.status,
    required this.intakeItem,
    this.stagedPath,
    this.metadataPath,
    this.previewBytes = const <int>[],
    this.blocked = const <String>[],
    this.cleanup = const <String>[],
    this.nextActions = const <String>[],
  });

  final String status;
  final Map<String, Object?> intakeItem;
  final String? stagedPath;
  final String? metadataPath;
  final List<int> previewBytes;
  final List<String> blocked;
  final List<String> cleanup;
  final List<String> nextActions;

  String get filename => intakeItem['filename']?.toString() ?? 'attachment';
  String get mediaKind => intakeItem['kind']?.toString() ?? 'media';
  String get mimeType => intakeItem['mime_type']?.toString() ?? '';
  bool get isImage =>
      mediaKind == 'image' ||
      mediaKind == 'crop' ||
      mimeType.toLowerCase().startsWith('image/');

  SddStagedMediaAttachment copyWith({
    String? status,
    Map<String, Object?>? intakeItem,
    String? stagedPath,
    String? metadataPath,
    List<int>? previewBytes,
    List<String>? blocked,
    List<String>? cleanup,
    List<String>? nextActions,
  }) {
    return SddStagedMediaAttachment(
      status: status ?? this.status,
      intakeItem: intakeItem ?? this.intakeItem,
      stagedPath: stagedPath ?? this.stagedPath,
      metadataPath: metadataPath ?? this.metadataPath,
      previewBytes: previewBytes ?? this.previewBytes,
      blocked: blocked ?? this.blocked,
      cleanup: cleanup ?? this.cleanup,
      nextActions: nextActions ?? this.nextActions,
    );
  }

  factory SddStagedMediaAttachment.fromJson(Map<String, dynamic> json) {
    final rawItem = json['intake_item'];
    return SddStagedMediaAttachment(
      status: json['status'] as String? ?? 'unknown',
      intakeItem: rawItem is Map<String, dynamic>
          ? rawItem.cast<String, Object?>()
          : const <String, Object?>{},
      stagedPath: json['staged_path'] as String?,
      metadataPath: json['metadata_path'] as String?,
      blocked: _strings(json['blocked']),
      cleanup: _strings(json['cleanup']),
      nextActions: _strings(json['next_actions']),
    );
  }
}

class SddMediaLifecycleResult {
  const SddMediaLifecycleResult({
    required this.status,
    required this.lifecycle,
    this.stagedPath,
    this.deleted = const <String>[],
    this.wouldDelete = const <String>[],
    this.blocked = const <String>[],
    this.cleanup = const <String>[],
    this.nextActions = const <String>[],
  });

  final String status;
  final String lifecycle;
  final String? stagedPath;
  final List<String> deleted;
  final List<String> wouldDelete;
  final List<String> blocked;
  final List<String> cleanup;
  final List<String> nextActions;

  factory SddMediaLifecycleResult.fromJson(Map<String, dynamic> json) {
    return SddMediaLifecycleResult(
      status: json['status'] as String? ?? 'unknown',
      lifecycle: json['lifecycle'] as String? ?? 'unknown',
      stagedPath: json['staged_path'] as String?,
      deleted: _strings(json['deleted']),
      wouldDelete: _strings(json['would_delete']),
      blocked: _strings(json['blocked']),
      cleanup: _strings(json['cleanup']),
      nextActions: _strings(json['next_actions']),
    );
  }
}

class SddSpecIntakePlan {
  const SddSpecIntakePlan({
    required this.status,
    this.specId,
    this.specRoot,
    this.selectedArtifact,
    this.metadataTitle,
    this.metadataDescription,
    this.job,
    this.intakePlan,
    this.dryRun,
    this.changedFiles = const <SddGeneratedChange>[],
    this.plannedFiles = const <String>[],
    this.blocked = const <String>[],
    this.conflicts = const <String>[],
    this.rejectedMedia = const <String>[],
    this.nextActions = const <String>[],
  });

  final String status;
  final String? specId;
  final String? specRoot;
  final String? selectedArtifact;
  final String? metadataTitle;
  final String? metadataDescription;
  final SddCodexJobStatus? job;
  final Map<String, dynamic>? intakePlan;
  final SddSpecIntakePlan? dryRun;
  final List<SddGeneratedChange> changedFiles;
  final List<String> plannedFiles;
  final List<String> blocked;
  final List<String> conflicts;
  final List<String> rejectedMedia;
  final List<String> nextActions;

  factory SddSpecIntakePlan.fromJson(Map<String, dynamic> json) {
    final metadata = json['metadata_proposal'];
    final dryRun = json['dry_run'];
    return SddSpecIntakePlan(
      status: json['status'] as String? ?? 'unknown',
      specId: json['spec_id'] as String?,
      specRoot: json['spec_root'] as String?,
      selectedArtifact: json['selected_artifact'] as String?,
      metadataTitle: metadata is Map<String, dynamic>
          ? metadata['title'] as String?
          : null,
      metadataDescription: metadata is Map<String, dynamic>
          ? metadata['description'] as String?
          : null,
      job: json['job'] is Map<String, dynamic>
          ? SddCodexJobStatus.fromJson(json['job'] as Map<String, dynamic>)
          : null,
      intakePlan: json['intake_plan'] is Map<String, dynamic>
          ? json['intake_plan'] as Map<String, dynamic>
          : null,
      dryRun: dryRun is Map<String, dynamic>
          ? SddSpecIntakePlan.fromJson(dryRun)
          : null,
      changedFiles: _generatedChanges(json['changed_files']),
      plannedFiles: _strings(
        json['target_files'] ??
            json['intended_artifact_updates'] ??
            json['created'],
      ),
      blocked: _strings(json['blocked']),
      conflicts: _strings(json['conflicts']),
      rejectedMedia: _rejectedMedia(json['rejected_media']),
      nextActions: _strings(json['next_actions']),
    );
  }
}

class SddSpecIntakeApplyResult extends SddSpecIntakePlan {
  const SddSpecIntakeApplyResult({
    required super.status,
    super.specId,
    super.specRoot,
    super.selectedArtifact,
    super.metadataTitle,
    super.metadataDescription,
    super.job,
    super.dryRun,
    super.plannedFiles,
    super.blocked,
    super.conflicts,
    super.rejectedMedia,
    super.nextActions,
  });

  factory SddSpecIntakeApplyResult.fromJson(Map<String, dynamic> json) {
    final parsed = SddSpecIntakePlan.fromJson(json);
    return SddSpecIntakeApplyResult(
      status: parsed.status,
      specId: parsed.specId,
      specRoot: parsed.specRoot,
      selectedArtifact: parsed.selectedArtifact,
      metadataTitle: parsed.metadataTitle,
      metadataDescription: parsed.metadataDescription,
      job: parsed.job,
      dryRun: parsed.dryRun,
      plannedFiles: parsed.plannedFiles,
      blocked: parsed.blocked,
      conflicts: parsed.conflicts,
      rejectedMedia: parsed.rejectedMedia,
      nextActions: parsed.nextActions,
    );
  }
}

class SddCodexJobStatus {
  const SddCodexJobStatus({
    required this.id,
    required this.status,
    this.targetArtifact,
    this.sandboxRoot,
    this.activity,
    this.nextActions = const <String>[],
    this.blockedReasons = const <String>[],
  });

  final String id;
  final String status;
  final String? targetArtifact;
  final String? sandboxRoot;
  final SddActivitySnapshot? activity;
  final List<String> nextActions;
  final List<String> blockedReasons;

  factory SddCodexJobStatus.fromJson(Map<String, dynamic> json) {
    return SddCodexJobStatus(
      id: json['job_id'] as String? ?? json['jobId'] as String? ?? '',
      status: json['status'] as String? ?? 'unknown',
      targetArtifact: json['target_artifact'] as String?,
      sandboxRoot: json['sandbox_root'] as String?,
      activity: json['activity'] is Map<String, dynamic>
          ? SddActivitySnapshot.fromJson(
              json['activity'] as Map<String, dynamic>,
            )
          : null,
      nextActions: _strings(json['next_actions']),
      blockedReasons: _strings(json['blocked_reasons']),
    );
  }
}

class SddActivitySnapshot {
  const SddActivitySnapshot({
    required this.state,
    this.jobId,
    this.events = const <SddActivityEvent>[],
    this.nextActions = const <String>[],
  });

  final String state;
  final String? jobId;
  final List<SddActivityEvent> events;
  final List<String> nextActions;

  factory SddActivitySnapshot.fromJson(Map<String, dynamic> json) {
    return SddActivitySnapshot(
      state: json['state'] as String? ?? 'unknown',
      jobId: json['job_id'] as String? ?? json['jobId'] as String?,
      events: _activityEvents(json['events']),
      nextActions: _strings(json['next_actions']),
    );
  }
}

class SddActivityEvent {
  const SddActivityEvent({
    required this.state,
    required this.status,
    required this.label,
    this.detail,
    this.epoch,
  });

  final String state;
  final String status;
  final String label;
  final String? detail;
  final int? epoch;

  factory SddActivityEvent.fromJson(Map<String, dynamic> json) {
    return SddActivityEvent(
      state: json['state'] as String? ?? 'unknown',
      status: json['status'] as String? ?? 'unknown',
      label: json['label'] as String? ?? json['state'] as String? ?? 'Activity',
      detail: json['detail'] as String?,
      epoch: json['epoch'] is int ? json['epoch'] as int : null,
    );
  }
}

class SddCodexJobRetryResult {
  const SddCodexJobRetryResult({
    required this.status,
    required this.originalJobId,
    this.retryJobId,
    this.retryEligible = false,
    this.copiedReferences = const <String>[],
    this.blockedReasons = const <String>[],
    this.job,
    this.activity,
    this.nextActions = const <String>[],
  });

  final String status;
  final String originalJobId;
  final String? retryJobId;
  final bool retryEligible;
  final List<String> copiedReferences;
  final List<String> blockedReasons;
  final SddCodexJobStatus? job;
  final SddActivitySnapshot? activity;
  final List<String> nextActions;

  factory SddCodexJobRetryResult.fromJson(Map<String, dynamic> json) {
    return SddCodexJobRetryResult(
      status: json['status'] as String? ?? 'unknown',
      originalJobId: json['original_job_id'] as String? ?? '',
      retryJobId: json['retry_job_id'] as String?,
      retryEligible: json['retry_eligible'] == true,
      copiedReferences: _strings(json['copied_references']),
      blockedReasons: _strings(json['blocked_reasons']),
      job: json['job'] is Map<String, dynamic>
          ? SddCodexJobStatus.fromJson(json['job'] as Map<String, dynamic>)
          : null,
      activity: json['activity'] is Map<String, dynamic>
          ? SddActivitySnapshot.fromJson(
              json['activity'] as Map<String, dynamic>,
            )
          : null,
      nextActions: _strings(json['next_actions']),
    );
  }
}

class SddCodexJobReview {
  const SddCodexJobReview({
    required this.status,
    required this.validationStatus,
    this.changedFiles = const <SddGeneratedChange>[],
    this.blockedPaths = const <String>[],
    this.conflicts = const <String>[],
    this.protectedBaselineImpacts = const <String>[],
    this.nextActions = const <String>[],
  });

  final String status;
  final String validationStatus;
  final List<SddGeneratedChange> changedFiles;
  final List<String> blockedPaths;
  final List<String> conflicts;
  final List<String> protectedBaselineImpacts;
  final List<String> nextActions;

  bool get canApply => status == 'ready';

  factory SddCodexJobReview.fromJson(Map<String, dynamic> json) {
    return SddCodexJobReview(
      status: json['status'] as String? ?? 'unknown',
      validationStatus: json['validation_status'] as String? ?? 'unknown',
      changedFiles: _generatedChanges(json['changed_files']),
      blockedPaths: _strings(json['blocked_paths']),
      conflicts: _strings(json['conflicts']),
      protectedBaselineImpacts: _strings(json['protected_baseline_impacts']),
      nextActions: _strings(json['next_actions']),
    );
  }
}

class SddCodexJobApplyResult {
  const SddCodexJobApplyResult({
    required this.status,
    this.applied = const <String>[],
    this.blocked = const <String>[],
    this.conflicts = const <String>[],
    this.nextActions = const <String>[],
  });

  final String status;
  final List<String> applied;
  final List<String> blocked;
  final List<String> conflicts;
  final List<String> nextActions;

  factory SddCodexJobApplyResult.fromJson(Map<String, dynamic> json) {
    return SddCodexJobApplyResult(
      status: json['status'] as String? ?? 'unknown',
      applied: _strings(json['applied']),
      blocked: _strings(json['blocked']),
      conflicts: _strings(json['conflicts']),
      nextActions: _strings(json['next_actions']),
    );
  }
}

class SddGeneratedChange {
  const SddGeneratedChange({
    required this.path,
    required this.changeType,
    this.patchPath,
    this.blockedReason,
    this.conflict,
  });

  final String path;
  final String changeType;
  final String? patchPath;
  final String? blockedReason;
  final String? conflict;

  factory SddGeneratedChange.fromJson(Map<String, dynamic> json) {
    return SddGeneratedChange(
      path: json['path'] as String? ?? '',
      changeType: json['change_type'] as String? ?? 'modified',
      patchPath: json['patch_path'] as String?,
      blockedReason: json['blocked_reason'] as String?,
      conflict: json['conflict'] as String?,
    );
  }
}

List<SddGeneratedChange> _generatedChanges(Object? value) {
  if (value is! List) return const <SddGeneratedChange>[];
  return value
      .whereType<Map<String, dynamic>>()
      .map(SddGeneratedChange.fromJson)
      .toList(growable: false);
}

List<SddActivityEvent> _activityEvents(Object? value) {
  if (value is! List) return const <SddActivityEvent>[];
  return value
      .whereType<Map<String, dynamic>>()
      .map(SddActivityEvent.fromJson)
      .toList(growable: false);
}

List<String> _rejectedMedia(Object? value) {
  if (value is! List) return const <String>[];
  return value
      .map((item) {
        if (item is Map<String, dynamic>) {
          return '${item['field'] ?? 'media'}: ${item['message'] ?? item['code'] ?? 'rejected'}';
        }
        return item.toString();
      })
      .where((item) => item.trim().isNotEmpty)
      .toList(growable: false);
}

List<String> _strings(Object? value) {
  if (value is! List) return const <String>[];
  return value
      .map((item) => item?.toString() ?? '')
      .where((item) => item.trim().isNotEmpty)
      .toList(growable: false);
}
