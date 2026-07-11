class ProjectFactoryOptions {
  const ProjectFactoryOptions({
    required this.defaultPlatforms,
    required this.platforms,
    required this.defaultBackend,
    required this.backends,
    this.defaultFrontendStrategy = 'flutter',
    this.frontendStrategies = const <Map<String, dynamic>>[],
    required this.logoModes,
    required this.businessTypes,
    required this.creationWorkflow,
  });

  final List<String> defaultPlatforms;
  final List<String> platforms;
  final String defaultBackend;
  final List<String> backends;
  final String defaultFrontendStrategy;
  final List<Map<String, dynamic>> frontendStrategies;
  final List<String> logoModes;
  final List<String> businessTypes;
  final Map<String, dynamic> creationWorkflow;

  factory ProjectFactoryOptions.fromJson(Map<String, dynamic> json) {
    return ProjectFactoryOptions(
      defaultPlatforms: _stringList(json['default_platforms']),
      platforms: _stringList(json['platforms']),
      defaultBackend: json['default_backend'] as String? ?? 'fastapi',
      backends: _stringList(json['backends']),
      defaultFrontendStrategy: json['defaultFrontendStrategy'] as String? ??
          json['default_frontend_strategy'] as String? ??
          'flutter',
      frontendStrategies: ((json['frontendStrategies'] ??
                  json['frontend_strategies']) as List<dynamic>?)
              ?.whereType<Map<String, dynamic>>()
              .toList(growable: false) ??
          const <Map<String, dynamic>>[],
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

class ProjectFactoryGuidedIntakeAnswer {
  const ProjectFactoryGuidedIntakeAnswer({
    required this.questionId,
    required this.value,
    required this.source,
    required this.confidence,
    required this.updatedAt,
  });

  final String questionId;
  final Object? value;
  final String source;
  final double confidence;
  final String updatedAt;

  factory ProjectFactoryGuidedIntakeAnswer.fromJson(Map<String, dynamic> json) {
    return ProjectFactoryGuidedIntakeAnswer(
      questionId:
          json['questionId'] as String? ?? json['question_id'] as String? ?? '',
      value: json['value'],
      source: json['source'] as String? ?? 'user',
      confidence: (json['confidence'] as num?)?.toDouble() ?? 1,
      updatedAt:
          json['updatedAt'] as String? ?? json['updated_at'] as String? ?? '',
    );
  }
}

class ProjectFactoryGuidedIntake {
  const ProjectFactoryGuidedIntake({
    required this.enabled,
    required this.status,
    required this.questions,
    required this.answers,
    required this.missingFields,
    required this.assumptions,
    required this.blockers,
    required this.readyForConfirmation,
    required this.buildAllowed,
    this.contractPreview,
    this.updatedAt = '',
    this.confirmedAt,
  });

  static const empty = ProjectFactoryGuidedIntake(
    enabled: false,
    status: 'confirmed',
    questions: <Map<String, dynamic>>[],
    answers: <ProjectFactoryGuidedIntakeAnswer>[],
    missingFields: <Map<String, dynamic>>[],
    assumptions: <Map<String, dynamic>>[],
    blockers: <Map<String, dynamic>>[],
    readyForConfirmation: false,
    buildAllowed: true,
  );

  final bool enabled;
  final String status;
  final List<Map<String, dynamic>> questions;
  final List<ProjectFactoryGuidedIntakeAnswer> answers;
  final List<Map<String, dynamic>> missingFields;
  final List<Map<String, dynamic>> assumptions;
  final List<Map<String, dynamic>> blockers;
  final Map<String, dynamic>? contractPreview;
  final String updatedAt;
  final String? confirmedAt;
  final bool readyForConfirmation;
  final bool buildAllowed;

  bool get isCollecting => status == 'collecting';
  bool get isBlocked => status == 'blocked';
  bool get isConfirmed => status == 'confirmed' || status == 'build_started';

  factory ProjectFactoryGuidedIntake.fromJson(Map<String, dynamic> json) {
    return ProjectFactoryGuidedIntake(
      enabled: json['enabled'] as bool? ?? false,
      status: json['status'] as String? ?? 'confirmed',
      questions: _mapList(json['questions']),
      answers: _mapList(json['answers'])
          .map(ProjectFactoryGuidedIntakeAnswer.fromJson)
          .toList(growable: false),
      missingFields: _mapList(json['missingFields'] ?? json['missing_fields']),
      assumptions: _mapList(json['assumptions']),
      blockers: _mapList(json['blockers']),
      contractPreview: _nullableMapFromJson(
        json['contractPreview'] ?? json['contract_preview'],
      ),
      updatedAt:
          json['updatedAt'] as String? ?? json['updated_at'] as String? ?? '',
      confirmedAt:
          json['confirmedAt'] as String? ?? json['confirmed_at'] as String?,
      readyForConfirmation: json['readyForConfirmation'] as bool? ??
          json['ready_for_confirmation'] as bool? ??
          false,
      buildAllowed: json['buildAllowed'] as bool? ??
          json['build_allowed'] as bool? ??
          false,
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
    this.frontendStrategy = 'flutter',
    this.logoMode = 'generate',
    this.firstReleaseMode = 'preview',
    this.guidedIntakeEnabled = false,
    this.initialAdminEmails = const <String>[],
    this.visualReferencePaths = const <String>[],
  });

  final String name;
  final String businessType;
  final String primaryGoal;
  final String? slug;
  final List<String> platforms;
  final String backend;
  final String frontendStrategy;
  final String logoMode;
  final String firstReleaseMode;
  final bool guidedIntakeEnabled;
  final List<String> initialAdminEmails;
  final List<String> visualReferencePaths;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'name': name,
      'businessType': businessType,
      'primaryGoal': primaryGoal,
      if (slug != null && slug!.trim().isNotEmpty) 'slug': slug,
      'platforms': platforms,
      'backend': backend,
      'frontendStrategy': frontendStrategy,
      'logoMode': logoMode,
      'firstReleaseMode': firstReleaseMode,
      'guidedIntakeEnabled': guidedIntakeEnabled,
      'initialAdminEmails': initialAdminEmails,
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
    this.frontendStrategy = 'flutter',
    this.initialPreviewRelease = InitialPreviewRelease.empty,
    this.guidedIntake = ProjectFactoryGuidedIntake.empty,
  });

  final String draftId;
  final String createdAt;
  final Map<String, dynamic> manifestPlan;
  final String firstReleaseMode;
  final String frontendStrategy;
  final InitialPreviewRelease initialPreviewRelease;
  final ProjectFactoryGuidedIntake guidedIntake;

  factory ProjectFactoryDraft.fromJson(Map<String, dynamic> json) {
    return ProjectFactoryDraft(
      draftId: json['draft_id'] as String,
      createdAt: json['created_at'] as String,
      manifestPlan: (json['manifest_plan'] as Map<String, dynamic>?) ??
          <String, dynamic>{},
      firstReleaseMode: json['firstReleaseMode'] as String? ??
          json['first_release_mode'] as String? ??
          'preview',
      frontendStrategy: json['frontendStrategy'] as String? ??
          json['frontend_strategy'] as String? ??
          'flutter',
      initialPreviewRelease: InitialPreviewRelease.fromJson(
        _mapFromJson(
            json['initialPreviewRelease'] ?? json['initial_preview_release']),
      ),
      guidedIntake: ProjectFactoryGuidedIntake.fromJson(
        _mapFromJson(json['guidedIntake'] ?? json['guided_intake']),
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
    this.frontendStrategy = 'flutter',
    this.initialPreviewRelease = InitialPreviewRelease.empty,
    this.guidedIntake = ProjectFactoryGuidedIntake.empty,
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
  final String frontendStrategy;
  final InitialPreviewRelease initialPreviewRelease;
  final ProjectFactoryGuidedIntake guidedIntake;

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
      frontendStrategy: json['frontendStrategy'] as String? ??
          json['frontend_strategy'] as String? ??
          'flutter',
      initialPreviewRelease: InitialPreviewRelease.fromJson(
        _mapFromJson(
            json['initialPreviewRelease'] ?? json['initial_preview_release']),
      ),
      guidedIntake: ProjectFactoryGuidedIntake.fromJson(
        _mapFromJson(json['guidedIntake'] ?? json['guided_intake']),
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
    this.frontendStrategy = 'flutter',
    this.installableAndroid = true,
    this.bridgeRegistrationRequired = true,
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
    frontendStrategy: 'flutter',
    installableAndroid: true,
    bridgeRegistrationRequired: true,
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
  final String frontendStrategy;
  final bool installableAndroid;
  final bool bridgeRegistrationRequired;
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
      releaseTagPattern: (json.containsKey('releaseTagPattern') ||
              json.containsKey('release_tag_pattern'))
          ? (json['releaseTagPattern'] as String? ??
              json['release_tag_pattern'] as String? ??
              '')
          : 'android-preview-v*',
      frontendStrategy: json['frontendStrategy'] as String? ??
          json['frontend_strategy'] as String? ??
          'flutter',
      installableAndroid: json['installableAndroid'] as bool? ??
          json['installable_android'] as bool? ??
          true,
      bridgeRegistrationRequired: json['bridgeRegistrationRequired'] as bool? ??
          json['bridge_registration_required'] as bool? ??
          true,
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

class ProjectFactoryInitPhase {
  const ProjectFactoryInitPhase({
    required this.name,
    required this.status,
    required this.message,
    required this.blockers,
    required this.commandEvidence,
    required this.artifacts,
    this.startedAt,
    this.completedAt,
  });

  final String name;
  final String status;
  final String message;
  final String? startedAt;
  final String? completedAt;
  final List<Map<String, dynamic>> blockers;
  final List<Map<String, dynamic>> commandEvidence;
  final List<Map<String, dynamic>> artifacts;

  factory ProjectFactoryInitPhase.fromJson(Map<String, dynamic> json) {
    return ProjectFactoryInitPhase(
      name: json['name'] as String? ?? '',
      status: json['status'] as String? ?? 'pending',
      message: json['message'] as String? ?? '',
      startedAt: json['startedAt'] as String? ?? json['started_at'] as String?,
      completedAt:
          json['completedAt'] as String? ?? json['completed_at'] as String?,
      blockers: _mapList(json['blockers']),
      commandEvidence:
          _mapList(json['commandEvidence'] ?? json['command_evidence']),
      artifacts: _mapList(json['artifacts']),
    );
  }
}

class ProjectFactoryInitJob {
  const ProjectFactoryInitJob({
    required this.initJobId,
    required this.draftId,
    required this.createdAt,
    required this.updatedAt,
    required this.status,
    required this.currentPhase,
    required this.phases,
    required this.remoteResources,
    required this.blockers,
    required this.readyForBusinessLlm,
    required this.canContinueWithBlockedContext,
    this.chatSessionId,
    this.projectPath,
    this.workspacePath,
    this.generatedWorkspacePath,
    this.contextPack,
  });

  final String initJobId;
  final String draftId;
  final String? chatSessionId;
  final String createdAt;
  final String updatedAt;
  final String status;
  final String currentPhase;
  final String? projectPath;
  final String? workspacePath;
  final String? generatedWorkspacePath;
  final List<ProjectFactoryInitPhase> phases;
  final List<Map<String, dynamic>> remoteResources;
  final Map<String, dynamic>? contextPack;
  final List<Map<String, dynamic>> blockers;
  final bool readyForBusinessLlm;
  final bool canContinueWithBlockedContext;

  bool get isReady => status == 'ready';
  bool get isBlockedWithContext => status == 'blocked_with_context';

  factory ProjectFactoryInitJob.fromJson(Map<String, dynamic> json) {
    return ProjectFactoryInitJob(
      initJobId:
          json['initJobId'] as String? ?? json['init_job_id'] as String? ?? '',
      draftId: json['draftId'] as String? ?? json['draft_id'] as String? ?? '',
      chatSessionId: json['chatSessionId'] as String? ??
          json['chat_session_id'] as String?,
      createdAt:
          json['createdAt'] as String? ?? json['created_at'] as String? ?? '',
      updatedAt:
          json['updatedAt'] as String? ?? json['updated_at'] as String? ?? '',
      status: json['status'] as String? ?? 'queued',
      currentPhase: json['currentPhase'] as String? ??
          json['current_phase'] as String? ??
          '',
      projectPath:
          json['projectPath'] as String? ?? json['project_path'] as String?,
      workspacePath:
          json['workspacePath'] as String? ?? json['workspace_path'] as String?,
      generatedWorkspacePath: json['generatedWorkspacePath'] as String? ??
          json['generated_workspace_path'] as String?,
      phases: _mapList(json['phases'])
          .map(ProjectFactoryInitPhase.fromJson)
          .toList(growable: false),
      remoteResources:
          _mapList(json['remoteResources'] ?? json['remote_resources']),
      contextPack:
          _nullableMapFromJson(json['contextPack'] ?? json['context_pack']),
      blockers: _mapList(json['blockers']),
      readyForBusinessLlm: json['readyForBusinessLlm'] as bool? ??
          json['ready_for_business_llm'] as bool? ??
          false,
      canContinueWithBlockedContext:
          json['canContinueWithBlockedContext'] as bool? ??
              json['can_continue_with_blocked_context'] as bool? ??
              false,
    );
  }
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
    this.frontendStrategy = 'flutter',
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
  final String frontendStrategy;
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
      frontendStrategy: json['frontendStrategy'] as String? ??
          json['frontend_strategy'] as String? ??
          'flutter',
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
    this.frontendStrategy = 'flutter',
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
  final String frontendStrategy;
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
      frontendStrategy: json['frontendStrategy'] as String? ??
          json['frontend_strategy'] as String? ??
          'flutter',
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
    this.updatedAt,
    this.expiresAt,
    this.disabledAt,
    this.disabledReason,
    this.inviteSyncSummary,
    this.planHash,
    this.projectPath,
    this.manifestPath,
    this.auditEvents = const <Map<String, dynamic>>[],
  });

  final String previewId;
  final String sourceApp;
  final String status;
  final String previewUrl;
  final String? healthUrl;
  final String? error;
  final String? completedAt;
  final String? updatedAt;
  final String? expiresAt;
  final String? disabledAt;
  final String? disabledReason;
  final String? planHash;
  final String? projectPath;
  final String? manifestPath;
  final Map<String, dynamic>? inviteSyncSummary;
  final List<Map<String, dynamic>> plannedResources;
  final List<Map<String, dynamic>> appliedResources;
  final List<Map<String, dynamic>> logs;
  final List<Map<String, dynamic>> auditEvents;
  final String createdAt;

  bool get isActive => status == 'active';
  bool get isFailed => status == 'failed';
  bool get isApplyDisabled => status == 'apply_disabled';
  bool get isDisabled => status == 'disabled' || disabledAt != null;
  bool get isExpired => status == 'expired';

  factory WebPreview.fromJson(Map<String, dynamic> json) {
    return WebPreview(
      previewId: json['preview_id'] as String? ?? '',
      sourceApp: json['source_app'] as String? ?? '',
      status: json['status'] as String? ?? 'unknown',
      previewUrl: json['preview_url'] as String? ?? '',
      healthUrl: json['health_url'] as String?,
      error: json['error'] as String?,
      completedAt: json['completed_at'] as String?,
      updatedAt: json['updated_at'] as String?,
      expiresAt: json['expires_at'] as String?,
      disabledAt: json['disabled_at'] as String?,
      disabledReason: json['disabled_reason'] as String?,
      planHash: json['plan_hash'] as String?,
      projectPath: json['project_path'] as String?,
      manifestPath: json['manifest_path'] as String?,
      inviteSyncSummary: json['invite_sync_summary'] as Map<String, dynamic>?,
      plannedResources: _mapList(json['planned_resources']),
      appliedResources: _mapList(json['applied_resources']),
      logs: _mapList(json['logs']),
      auditEvents: _mapList(json['audit_events']),
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
    this.email,
    this.role = 'admin',
    required this.singleUse,
    required this.syncStatus,
    required this.tokenSha256,
    this.usedAt,
    this.revokedAt,
    this.expiredAt,
    this.resendCount = 0,
    this.lastSentAt,
    this.emailProvider,
    this.emailDeliveryStatus = 'not_requested',
    this.emailDeliveryError,
    this.manualDeliveryRequired = false,
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
  final String? email;
  final String role;
  final bool singleUse;
  final String? usedAt;
  final String? revokedAt;
  final String? expiredAt;
  final int resendCount;
  final String? lastSentAt;
  final String? emailProvider;
  final String emailDeliveryStatus;
  final String? emailDeliveryError;
  final bool manualDeliveryRequired;
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
      email: json['email'] as String?,
      role: json['role'] as String? ?? 'admin',
      singleUse: json['single_use'] as bool? ?? true,
      usedAt: json['used_at'] as String?,
      revokedAt: json['revoked_at'] as String?,
      expiredAt: json['expired_at'] as String?,
      resendCount: json['resend_count'] as int? ?? 0,
      lastSentAt: json['last_sent_at'] as String?,
      emailProvider: json['email_provider'] as String?,
      emailDeliveryStatus:
          json['email_delivery_status'] as String? ?? 'not_requested',
      emailDeliveryError: json['email_delivery_error'] as String?,
      manualDeliveryRequired:
          json['manual_delivery_required'] as bool? ?? false,
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

Map<String, dynamic>? _nullableMapFromJson(Object? value) {
  final mapped = _mapFromJson(value);
  return mapped.isEmpty && value == null ? null : mapped;
}

int? _intOrNull(Object? value) {
  if (value is int) return value;
  if (value is String) return int.tryParse(value);
  return null;
}
