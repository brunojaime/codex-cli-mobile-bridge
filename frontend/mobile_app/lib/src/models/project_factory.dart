class ProjectFactoryOptions {
  const ProjectFactoryOptions({
    required this.defaultPlatforms,
    required this.platforms,
    required this.defaultBackend,
    required this.backends,
    required this.logoModes,
    required this.businessTypes,
    required this.creationWorkflow,
  });

  final List<String> defaultPlatforms;
  final List<String> platforms;
  final String defaultBackend;
  final List<String> backends;
  final List<String> logoModes;
  final List<String> businessTypes;
  final Map<String, dynamic> creationWorkflow;

  factory ProjectFactoryOptions.fromJson(Map<String, dynamic> json) {
    return ProjectFactoryOptions(
      defaultPlatforms: _stringList(json['default_platforms']),
      platforms: _stringList(json['platforms']),
      defaultBackend: json['default_backend'] as String? ?? 'fastapi',
      backends: _stringList(json['backends']),
      logoModes: _stringList(json['logo_modes']),
      businessTypes: _stringList(json['business_types']),
      creationWorkflow: (json['creation_workflow'] as Map<String, dynamic>?) ??
          <String, dynamic>{},
    );
  }
}

enum ProjectAssetRole {
  visualReference('visual_reference', 'Visual reference'),
  exactAsset('exact_asset', 'Copy exact'),
  appIcon('app_icon', 'App icon'),
  logo('logo', 'Logo'),
  documentContext('document_context', 'Document');

  const ProjectAssetRole(this.apiValue, this.label);

  final String apiValue;
  final String label;

  static ProjectAssetRole fromApiValue(String value) {
    return ProjectAssetRole.values.firstWhere(
      (role) => role.apiValue == value,
      orElse: () => ProjectAssetRole.visualReference,
    );
  }
}

class AssetDepotAsset {
  const AssetDepotAsset({
    required this.assetId,
    required this.originalFilename,
    required this.contentType,
    required this.sizeBytes,
    required this.sha256,
    required this.createdAt,
    required this.storagePath,
    required this.source,
  });

  final String assetId;
  final String originalFilename;
  final String contentType;
  final int sizeBytes;
  final String sha256;
  final String createdAt;
  final String storagePath;
  final String source;

  factory AssetDepotAsset.fromJson(Map<String, dynamic> json) {
    return AssetDepotAsset(
      assetId: json['asset_id'] as String? ?? json['id'] as String? ?? '',
      originalFilename: json['original_filename'] as String? ?? '',
      contentType: json['content_type'] as String? ?? '',
      sizeBytes: json['size_bytes'] as int? ?? 0,
      sha256: json['sha256'] as String? ?? '',
      createdAt: json['created_at'] as String? ?? '',
      storagePath: json['storage_path'] as String? ?? '',
      source: json['source'] as String? ?? '',
    );
  }
}

class ProjectFactoryDraftAsset {
  const ProjectFactoryDraftAsset({
    required this.draftId,
    required this.assetId,
    required this.role,
    required this.notes,
    required this.linkedAt,
    required this.originalFilename,
    required this.contentType,
    required this.sizeBytes,
    required this.sha256,
    required this.storagePath,
    required this.source,
  });

  final String draftId;
  final String assetId;
  final ProjectAssetRole role;
  final String notes;
  final String linkedAt;
  final String originalFilename;
  final String contentType;
  final int sizeBytes;
  final String sha256;
  final String storagePath;
  final String source;

  factory ProjectFactoryDraftAsset.fromJson(Map<String, dynamic> json) {
    return ProjectFactoryDraftAsset(
      draftId: json['draft_id'] as String? ?? '',
      assetId: json['asset_id'] as String? ?? '',
      role: ProjectAssetRole.fromApiValue(json['role'] as String? ?? ''),
      notes: json['notes'] as String? ?? '',
      linkedAt: json['linked_at'] as String? ?? '',
      originalFilename: json['original_filename'] as String? ?? '',
      contentType: json['content_type'] as String? ?? '',
      sizeBytes: json['size_bytes'] as int? ?? 0,
      sha256: json['sha256'] as String? ?? '',
      storagePath: json['storage_path'] as String? ?? '',
      source: json['source'] as String? ?? '',
    );
  }
}

class ProjectFactoryDraftRequest {
  const ProjectFactoryDraftRequest({
    required this.name,
    required this.businessType,
    required this.primaryGoal,
    this.slug,
    this.platforms = const <String>['ios', 'android', 'web'],
    this.backend = 'fastapi',
    this.logoMode = 'generate',
    this.firstReleaseMode = 'preview',
    this.visualReferencePaths = const <String>[],
  });

  final String name;
  final String businessType;
  final String primaryGoal;
  final String? slug;
  final List<String> platforms;
  final String backend;
  final String logoMode;
  final String firstReleaseMode;
  final List<String> visualReferencePaths;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'name': name,
      'businessType': businessType,
      'primaryGoal': primaryGoal,
      if (slug != null && slug!.trim().isNotEmpty) 'slug': slug,
      'platforms': platforms,
      'backend': backend,
      'logoMode': logoMode,
      'firstReleaseMode': firstReleaseMode,
      'visualReferencePaths': visualReferencePaths,
    };
  }
}

class ProjectFactoryDraft {
  const ProjectFactoryDraft({
    required this.draftId,
    required this.createdAt,
    required this.manifestPlan,
    this.firstReleaseMode = 'preview',
    this.initialPreviewRelease = InitialPreviewRelease.empty,
  });

  final String draftId;
  final String createdAt;
  final Map<String, dynamic> manifestPlan;
  final String firstReleaseMode;
  final InitialPreviewRelease initialPreviewRelease;

  factory ProjectFactoryDraft.fromJson(Map<String, dynamic> json) {
    return ProjectFactoryDraft(
      draftId: json['draft_id'] as String,
      createdAt: json['created_at'] as String,
      manifestPlan: (json['manifest_plan'] as Map<String, dynamic>?) ??
          <String, dynamic>{},
      firstReleaseMode: json['firstReleaseMode'] as String? ??
          json['first_release_mode'] as String? ??
          'preview',
      initialPreviewRelease: InitialPreviewRelease.fromJson(
        _mapFromJson(
            json['initialPreviewRelease'] ?? json['initial_preview_release']),
      ),
    );
  }
}

class ProjectFactoryDraftSummary {
  const ProjectFactoryDraftSummary({
    required this.id,
    required this.draftId,
    required this.name,
    required this.businessType,
    required this.primaryGoal,
    required this.status,
    required this.ok,
    required this.createdAt,
    this.slug,
    this.targetPath,
    this.error,
    this.firstReleaseMode = 'preview',
    this.initialPreviewRelease = InitialPreviewRelease.empty,
  });

  final String id;
  final String draftId;
  final String name;
  final String? slug;
  final String businessType;
  final String primaryGoal;
  final String status;
  final bool ok;
  final String createdAt;
  final String? targetPath;
  final String? error;
  final String firstReleaseMode;
  final InitialPreviewRelease initialPreviewRelease;

  factory ProjectFactoryDraftSummary.fromJson(Map<String, dynamic> json) {
    return ProjectFactoryDraftSummary(
      id: json['id'] as String? ?? json['draft_id'] as String,
      draftId: json['draft_id'] as String? ?? json['id'] as String,
      name: json['name'] as String? ?? '',
      slug: json['slug'] as String?,
      businessType: json['business_type'] as String? ?? '',
      primaryGoal: json['primary_goal'] as String? ?? '',
      status: json['status'] as String? ?? 'unknown',
      ok: json['ok'] as bool? ?? false,
      createdAt: json['created_at'] as String? ?? '',
      targetPath: json['target_path'] as String?,
      error: json['error'] as String?,
      firstReleaseMode: json['firstReleaseMode'] as String? ??
          json['first_release_mode'] as String? ??
          'preview',
      initialPreviewRelease: InitialPreviewRelease.fromJson(
        _mapFromJson(
            json['initialPreviewRelease'] ?? json['initial_preview_release']),
      ),
    );
  }
}

class InitialPreviewReleasePhaseStatus {
  const InitialPreviewReleasePhaseStatus({
    required this.status,
    required this.message,
    required this.command,
    this.exitCode,
  });

  final String status;
  final String message;
  final List<String> command;
  final int? exitCode;

  factory InitialPreviewReleasePhaseStatus.fromJson(
    Map<String, dynamic> json,
  ) {
    return InitialPreviewReleasePhaseStatus(
      status: json['status'] as String? ?? 'pending',
      message: json['message'] as String? ?? '',
      command: _stringList(json['command']),
      exitCode: _intOrNull(json['exit_code'] ?? json['exitCode']),
    );
  }

  String get commandText => command.join(' ');
}

class InitialPreviewRelease {
  const InitialPreviewRelease({
    required this.sourceApp,
    required this.previewUrl,
    required this.apiBaseUrl,
    required this.runtimeProfile,
    required this.apiRuntime,
    required this.releaseChannel,
    required this.releaseTagPattern,
    required this.productionReady,
    required this.mockOrDemo,
    required this.status,
    required this.currentPhase,
    required this.phaseStatuses,
    required this.manualCommandHints,
    this.blockerText,
  });

  static const empty = InitialPreviewRelease(
    sourceApp: '',
    previewUrl: null,
    apiBaseUrl: null,
    runtimeProfile: 'preview',
    apiRuntime: 'cloudflare_preview',
    releaseChannel: 'prerelease',
    releaseTagPattern: 'android-preview-v*',
    productionReady: false,
    mockOrDemo: false,
    status: 'draft',
    currentPhase: 'draft',
    phaseStatuses: <String, InitialPreviewReleasePhaseStatus>{},
    manualCommandHints: <String>[],
  );

  final String sourceApp;
  final String? previewUrl;
  final String? apiBaseUrl;
  final String runtimeProfile;
  final String apiRuntime;
  final String releaseChannel;
  final String releaseTagPattern;
  final bool productionReady;
  final bool mockOrDemo;
  final String status;
  final String currentPhase;
  final Map<String, InitialPreviewReleasePhaseStatus> phaseStatuses;
  final String? blockerText;
  final List<String> manualCommandHints;

  factory InitialPreviewRelease.fromJson(Map<String, dynamic> json) {
    final rawPhases =
        _mapFromJson(json['phaseStatuses'] ?? json['phase_statuses']);
    return InitialPreviewRelease(
      sourceApp:
          json['sourceApp'] as String? ?? json['source_app'] as String? ?? '',
      previewUrl:
          json['previewUrl'] as String? ?? json['preview_url'] as String?,
      apiBaseUrl:
          json['apiBaseUrl'] as String? ?? json['api_base_url'] as String?,
      runtimeProfile: json['runtimeProfile'] as String? ??
          json['runtime_profile'] as String? ??
          'preview',
      apiRuntime: json['apiRuntime'] as String? ??
          json['api_runtime'] as String? ??
          'cloudflare_preview',
      releaseChannel: json['releaseChannel'] as String? ??
          json['release_channel'] as String? ??
          'prerelease',
      releaseTagPattern: json['releaseTagPattern'] as String? ??
          json['release_tag_pattern'] as String? ??
          'android-preview-v*',
      productionReady: json['productionReady'] as bool? ??
          json['production_ready'] as bool? ??
          false,
      mockOrDemo:
          json['mockOrDemo'] as bool? ?? json['mock_or_demo'] as bool? ?? false,
      status: json['status'] as String? ?? 'draft',
      currentPhase: json['currentPhase'] as String? ??
          json['current_phase'] as String? ??
          'draft',
      phaseStatuses: rawPhases.map(
        (key, value) => MapEntry(
          key,
          InitialPreviewReleasePhaseStatus.fromJson(_mapFromJson(value)),
        ),
      ),
      blockerText:
          json['blockerText'] as String? ?? json['blocker_text'] as String?,
      manualCommandHints: _stringList(
        json['manualCommandHints'] ?? json['manual_command_hints'],
      ),
    );
  }

  bool get hasPreviewUrl => previewUrl != null && previewUrl!.trim().isNotEmpty;
  bool get isReady => status == 'ready' || status == 'completed';
  bool get isBlocked => status == 'blocked';
  String get productionReadinessLabel =>
      productionReady ? 'Production ready' : 'Production pending';
  String get mockDemoLabel => mockOrDemo ? 'Mock/demo' : 'Real preview data';
}

class ProjectFactoryJob {
  const ProjectFactoryJob({
    required this.jobId,
    required this.draftId,
    required this.status,
    required this.currentStep,
    required this.currentPhase,
    required this.progress,
    required this.message,
    required this.manifestPlan,
    required this.stepLogs,
    this.firstReleaseMode = 'preview',
    this.initialPreviewRelease = InitialPreviewRelease.empty,
    this.startedAt,
    this.completedAt,
    this.error,
    this.projectPath,
    this.generationResult,
  });

  final String jobId;
  final String draftId;
  final String status;
  final String currentStep;
  final String currentPhase;
  final int progress;
  final String message;
  final Map<String, dynamic> manifestPlan;
  final List<Map<String, dynamic>> stepLogs;
  final String firstReleaseMode;
  final InitialPreviewRelease initialPreviewRelease;
  final String? startedAt;
  final String? completedAt;
  final String? error;
  final String? projectPath;
  final Map<String, dynamic>? generationResult;

  bool get isReady => status == 'ready';
  bool get isTerminal =>
      status == 'ready' ||
      status == 'completed' ||
      status == 'failed' ||
      status == 'blocked' ||
      status == 'interrupted';

  String? get targetPath {
    if (projectPath != null && projectPath!.isNotEmpty) {
      return projectPath;
    }
    final resultPath = generationResult?['target_path'];
    if (resultPath is String && resultPath.isNotEmpty) {
      return resultPath;
    }
    final plannedPath = manifestPlan['target_path'];
    return plannedPath is String && plannedPath.isNotEmpty ? plannedPath : null;
  }

  factory ProjectFactoryJob.fromJson(Map<String, dynamic> json) {
    return ProjectFactoryJob(
      jobId: json['job_id'] as String,
      draftId: json['draft_id'] as String,
      status: json['status'] as String,
      currentStep: json['current_step'] as String,
      currentPhase: json['current_phase'] as String? ??
          json['current_step'] as String? ??
          'queued',
      progress:
          json['progress'] as int? ?? (json['status'] == 'ready' ? 100 : 0),
      message: json['message'] as String? ?? '',
      manifestPlan: (json['manifest_plan'] as Map<String, dynamic>?) ??
          <String, dynamic>{},
      stepLogs: ((json['step_logs'] as List<dynamic>?) ?? <dynamic>[])
          .whereType<Map<String, dynamic>>()
          .toList(growable: false),
      firstReleaseMode: json['firstReleaseMode'] as String? ??
          json['first_release_mode'] as String? ??
          'preview',
      initialPreviewRelease: InitialPreviewRelease.fromJson(
        _mapFromJson(
            json['initialPreviewRelease'] ?? json['initial_preview_release']),
      ),
      startedAt: json['started_at'] as String?,
      completedAt: json['completed_at'] as String?,
      error: json['error'] as String?,
      projectPath: json['project_path'] as String?,
      generationResult: json['generation_result'] as Map<String, dynamic>?,
    );
  }
}

class ProjectFactoryJobSummary {
  const ProjectFactoryJobSummary({
    required this.id,
    required this.jobId,
    required this.draftId,
    required this.status,
    required this.currentPhase,
    required this.progress,
    required this.createdAt,
    this.name,
    this.slug,
    this.startedAt,
    this.completedAt,
    this.projectPath,
    this.targetPath,
    this.error,
    this.message,
    this.manualNextStep,
    this.firstReleaseMode = 'preview',
    this.initialPreviewRelease = InitialPreviewRelease.empty,
  });

  final String id;
  final String jobId;
  final String draftId;
  final String? name;
  final String? slug;
  final String status;
  final String currentPhase;
  final int progress;
  final String createdAt;
  final String? startedAt;
  final String? completedAt;
  final String? projectPath;
  final String? targetPath;
  final String? error;
  final String? message;
  final String? manualNextStep;
  final String firstReleaseMode;
  final InitialPreviewRelease initialPreviewRelease;

  bool get isReady => status == 'ready' || status == 'completed';
  bool get isTerminal =>
      isReady ||
      status == 'failed' ||
      status == 'blocked' ||
      status == 'interrupted';

  factory ProjectFactoryJobSummary.fromJson(Map<String, dynamic> json) {
    return ProjectFactoryJobSummary(
      id: json['id'] as String? ?? json['job_id'] as String,
      jobId: json['job_id'] as String? ?? json['id'] as String,
      draftId: json['draft_id'] as String,
      name: json['name'] as String?,
      slug: json['slug'] as String?,
      status: json['status'] as String? ?? 'unknown',
      currentPhase: json['current_phase'] as String? ?? '',
      progress: json['progress'] as int? ?? 0,
      createdAt: json['created_at'] as String? ?? '',
      startedAt: json['started_at'] as String?,
      completedAt: json['completed_at'] as String?,
      projectPath: json['project_path'] as String?,
      targetPath: json['target_path'] as String?,
      error: json['error'] as String?,
      message: json['message'] as String?,
      manualNextStep: json['manual_next_step'] as String?,
      firstReleaseMode: json['firstReleaseMode'] as String? ??
          json['first_release_mode'] as String? ??
          'preview',
      initialPreviewRelease: InitialPreviewRelease.fromJson(
        _mapFromJson(
            json['initialPreviewRelease'] ?? json['initial_preview_release']),
      ),
    );
  }
}

class ProjectFactoryReferenceAsset {
  const ProjectFactoryReferenceAsset({
    required this.id,
    required this.draftId,
    required this.originalFilename,
    required this.contentType,
    required this.sizeBytes,
    required this.createdAt,
    required this.storagePath,
  });

  final String id;
  final String draftId;
  final String originalFilename;
  final String contentType;
  final int sizeBytes;
  final String createdAt;
  final String storagePath;

  factory ProjectFactoryReferenceAsset.fromJson(Map<String, dynamic> json) {
    return ProjectFactoryReferenceAsset(
      id: json['id'] as String,
      draftId: json['draft_id'] as String,
      originalFilename: json['original_filename'] as String,
      contentType: json['content_type'] as String,
      sizeBytes: json['size_bytes'] as int,
      createdAt: json['created_at'] as String,
      storagePath: json['storage_path'] as String,
    );
  }
}

class WebPreview {
  const WebPreview({
    required this.previewId,
    required this.sourceApp,
    required this.status,
    required this.previewUrl,
    required this.plannedResources,
    required this.appliedResources,
    required this.logs,
    required this.createdAt,
    this.healthUrl,
    this.error,
    this.completedAt,
    this.inviteSyncSummary,
    this.planHash,
    this.projectPath,
    this.manifestPath,
  });

  final String previewId;
  final String sourceApp;
  final String status;
  final String previewUrl;
  final String? healthUrl;
  final String? error;
  final String? completedAt;
  final String? planHash;
  final String? projectPath;
  final String? manifestPath;
  final Map<String, dynamic>? inviteSyncSummary;
  final List<Map<String, dynamic>> plannedResources;
  final List<Map<String, dynamic>> appliedResources;
  final List<Map<String, dynamic>> logs;
  final String createdAt;

  bool get isActive => status == 'active';
  bool get isFailed => status == 'failed';
  bool get isApplyDisabled => status == 'apply_disabled';

  factory WebPreview.fromJson(Map<String, dynamic> json) {
    return WebPreview(
      previewId: json['preview_id'] as String? ?? '',
      sourceApp: json['source_app'] as String? ?? '',
      status: json['status'] as String? ?? 'unknown',
      previewUrl: json['preview_url'] as String? ?? '',
      healthUrl: json['health_url'] as String?,
      error: json['error'] as String?,
      completedAt: json['completed_at'] as String?,
      planHash: json['plan_hash'] as String?,
      projectPath: json['project_path'] as String?,
      manifestPath: json['manifest_path'] as String?,
      inviteSyncSummary: json['invite_sync_summary'] as Map<String, dynamic>?,
      plannedResources: _mapList(json['planned_resources']),
      appliedResources: _mapList(json['applied_resources']),
      logs: _mapList(json['logs']),
      createdAt: json['created_at'] as String? ?? '',
    );
  }
}

class WebPreviewInvite {
  const WebPreviewInvite({
    required this.inviteId,
    required this.previewId,
    required this.sourceApp,
    required this.appSlug,
    required this.createdAt,
    required this.expiresAt,
    required this.singleUse,
    required this.syncStatus,
    required this.tokenSha256,
    this.usedAt,
    this.revokedAt,
    this.syncedAt,
    this.syncError,
    this.inviteUrl,
    this.token,
  });

  final String inviteId;
  final String previewId;
  final String sourceApp;
  final String appSlug;
  final String createdAt;
  final String expiresAt;
  final bool singleUse;
  final String? usedAt;
  final String? revokedAt;
  final String syncStatus;
  final String? syncedAt;
  final String? syncError;
  final String tokenSha256;
  final String? inviteUrl;
  final String? token;

  bool get isRevoked => revokedAt != null && revokedAt!.isNotEmpty;
  bool get canRetrySync => syncStatus == 'failed' || syncStatus == 'pending';

  factory WebPreviewInvite.fromJson(Map<String, dynamic> json) {
    return WebPreviewInvite(
      inviteId: json['invite_id'] as String? ?? '',
      previewId: json['preview_id'] as String? ?? '',
      sourceApp: json['source_app'] as String? ?? '',
      appSlug: json['app_slug'] as String? ?? '',
      createdAt: json['created_at'] as String? ?? '',
      expiresAt: json['expires_at'] as String? ?? '',
      singleUse: json['single_use'] as bool? ?? true,
      usedAt: json['used_at'] as String?,
      revokedAt: json['revoked_at'] as String?,
      syncStatus: json['sync_status'] as String? ?? 'not_deployed',
      syncedAt: json['synced_at'] as String?,
      syncError: json['sync_error'] as String?,
      tokenSha256: json['token_sha256'] as String? ?? '',
      inviteUrl: json['invite_url'] as String?,
      token: json['token'] as String?,
    );
  }
}

List<String> _stringList(Object? value) {
  if (value is! List) {
    return <String>[];
  }
  return value.whereType<String>().toList(growable: false);
}

List<Map<String, dynamic>> _mapList(Object? value) {
  if (value is! List) {
    return <Map<String, dynamic>>[];
  }
  return value.whereType<Map<String, dynamic>>().toList(growable: false);
}

Map<String, dynamic> _mapFromJson(Object? value) {
  if (value is Map<String, dynamic>) {
    return value;
  }
  if (value is Map) {
    return value.map((key, item) => MapEntry(key.toString(), item));
  }
  return <String, dynamic>{};
}

int? _intOrNull(Object? value) {
  if (value is int) return value;
  if (value is String) return int.tryParse(value);
  return null;
}
