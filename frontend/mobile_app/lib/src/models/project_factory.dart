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

class ProjectFactoryDraftRequest {
  const ProjectFactoryDraftRequest({
    required this.name,
    required this.businessType,
    required this.primaryGoal,
    this.slug,
    this.platforms = const <String>['ios', 'android', 'web'],
    this.backend = 'fastapi',
    this.logoMode = 'generate',
    this.visualReferencePaths = const <String>[],
  });

  final String name;
  final String businessType;
  final String primaryGoal;
  final String? slug;
  final List<String> platforms;
  final String backend;
  final String logoMode;
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
      'visualReferencePaths': visualReferencePaths,
    };
  }
}

class ProjectFactoryDraft {
  const ProjectFactoryDraft({
    required this.draftId,
    required this.createdAt,
    required this.manifestPlan,
  });

  final String draftId;
  final String createdAt;
  final Map<String, dynamic> manifestPlan;

  factory ProjectFactoryDraft.fromJson(Map<String, dynamic> json) {
    return ProjectFactoryDraft(
      draftId: json['draft_id'] as String,
      createdAt: json['created_at'] as String,
      manifestPlan: (json['manifest_plan'] as Map<String, dynamic>?) ??
          <String, dynamic>{},
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

List<String> _stringList(Object? value) {
  if (value is! List) {
    return <String>[];
  }
  return value.whereType<String>().toList(growable: false);
}
