class ProjectDocuments {
  const ProjectDocuments({
    required this.workspacePath,
    required this.workspaceName,
    required this.standard,
    required this.root,
    required this.source,
    required this.evidence,
    required this.modules,
    required this.charter,
  });

  final String workspacePath;
  final String workspaceName;
  final String standard;
  final String root;
  final String source;
  final Map<String, dynamic> evidence;
  final List<ProjectDocumentModule> modules;
  final ProjectDocumentCharterSummary charter;

  factory ProjectDocuments.fromJson(Map<String, dynamic> json) {
    return ProjectDocuments(
      workspacePath: _string(json['workspace_path']),
      workspaceName: _string(json['workspace_name']),
      standard: _string(json['standard']),
      root: _string(json['root']),
      source: _string(json['source']),
      evidence: _map(json['evidence']),
      modules: _list(json['modules'])
          .map(ProjectDocumentModule.fromJson)
          .toList(growable: false),
      charter: ProjectDocumentCharterSummary.fromJson(_map(json['charter'])),
    );
  }
}

class ProjectDocumentModule {
  const ProjectDocumentModule({
    required this.id,
    required this.title,
    required this.path,
    required this.exists,
    required this.status,
    required this.loadByDefault,
    required this.description,
    required this.validation,
  });

  final String id;
  final String title;
  final String path;
  final bool exists;
  final String status;
  final bool loadByDefault;
  final String description;
  final ProjectDocumentValidationSummary? validation;

  factory ProjectDocumentModule.fromJson(Map<String, dynamic> json) {
    final validation = json['validation'];
    return ProjectDocumentModule(
      id: _string(json['id']),
      title: _string(json['title']),
      path: _string(json['path']),
      exists: _bool(json['exists']),
      status: _string(json['status']),
      loadByDefault: _bool(json['load_by_default']),
      description: _string(json['description']),
      validation: validation is Map
          ? ProjectDocumentValidationSummary.fromJson(_map(validation))
          : null,
    );
  }
}

class ProjectDocumentValidationSummary {
  const ProjectDocumentValidationSummary({
    required this.ok,
    required this.blockingCount,
  });

  final bool ok;
  final int blockingCount;

  factory ProjectDocumentValidationSummary.fromJson(Map<String, dynamic> json) {
    return ProjectDocumentValidationSummary(
      ok: _bool(json['ok']),
      blockingCount: _int(json['blocking_count']),
    );
  }
}

class ProjectDocumentCharterSummary {
  const ProjectDocumentCharterSummary({
    required this.path,
    required this.status,
    required this.latestRender,
    required this.latestRelease,
    required this.validation,
    required this.render,
  });

  final String path;
  final String status;
  final String? latestRender;
  final String? latestRelease;
  final ProjectDocumentValidationSummary validation;
  final ProjectDocumentRenderState render;

  factory ProjectDocumentCharterSummary.fromJson(Map<String, dynamic> json) {
    return ProjectDocumentCharterSummary(
      path: _string(json['path']),
      status: _string(json['status']),
      latestRender: _nullableString(json['latest_render']),
      latestRelease: _nullableString(json['latest_release']),
      validation: ProjectDocumentValidationSummary.fromJson(
        _map(json['validation']),
      ),
      render: ProjectDocumentRenderState.fromJson(_map(json['render'])),
    );
  }
}

class ProjectDocumentCharterDetail {
  const ProjectDocumentCharterDetail({
    required this.workspacePath,
    required this.workspaceName,
    required this.standard,
    required this.source,
    required this.evidence,
    required this.metadata,
    required this.brand,
    required this.sourceSummary,
    required this.render,
    required this.renderManifest,
    required this.validation,
    required this.latestRelease,
  });

  final String workspacePath;
  final String workspaceName;
  final String standard;
  final String source;
  final Map<String, dynamic> evidence;
  final Map<String, dynamic> metadata;
  final Map<String, dynamic> brand;
  final ProjectDocumentSourceSummary sourceSummary;
  final ProjectDocumentRenderState render;
  final Map<String, dynamic> renderManifest;
  final ProjectDocumentValidationResult validation;
  final String? latestRelease;

  bool get hasFreshRender {
    if (!render.exists) {
      return false;
    }
    final sourceHash = sourceSummary.sha256;
    final manifestSourceHash = _nullableString(renderManifest['source_hash']);
    if (sourceHash == null || sourceHash.isEmpty) {
      return false;
    }
    return manifestSourceHash == sourceHash;
  }

  String get status => _string(metadata['status']);

  String? get draftVersion {
    final versions = metadata['versions'];
    return versions is Map ? _nullableString(versions['draft']) : null;
  }

  String? get deliveredVersion {
    final versions = metadata['versions'];
    return versions is Map ? _nullableString(versions['delivered']) : null;
  }

  String? get updatedAt {
    final timestamps = metadata['timestamps'];
    return timestamps is Map ? _nullableString(timestamps['updated_at']) : null;
  }

  factory ProjectDocumentCharterDetail.fromJson(Map<String, dynamic> json) {
    return ProjectDocumentCharterDetail(
      workspacePath: _string(json['workspace_path']),
      workspaceName: _string(json['workspace_name']),
      standard: _string(json['standard']),
      source: _string(json['source']),
      evidence: _map(json['evidence']),
      metadata: _map(json['metadata']),
      brand: _map(json['brand']),
      sourceSummary: ProjectDocumentSourceSummary.fromJson(
        _map(json['source_summary']),
      ),
      render: ProjectDocumentRenderState.fromJson(_map(json['render'])),
      renderManifest: _map(json['render_manifest']),
      validation: ProjectDocumentValidationResult.fromJson(
        _map(json['validation']),
      ),
      latestRelease: _nullableString(json['latest_release']),
    );
  }
}

class ProjectDocumentSourceSummary {
  const ProjectDocumentSourceSummary({
    required this.path,
    required this.exists,
    required this.title,
    required this.sizeBytes,
    required this.sha256,
    required this.sectionHeadings,
    required this.excerpt,
  });

  final String path;
  final bool exists;
  final String? title;
  final int sizeBytes;
  final String? sha256;
  final List<String> sectionHeadings;
  final String excerpt;

  factory ProjectDocumentSourceSummary.fromJson(Map<String, dynamic> json) {
    return ProjectDocumentSourceSummary(
      path: _string(json['path']),
      exists: _bool(json['exists']),
      title: _nullableString(json['title']),
      sizeBytes: _int(json['size_bytes']),
      sha256: _nullableString(json['sha256']),
      sectionHeadings: _stringList(json['section_headings']),
      excerpt: _string(json['excerpt']),
    );
  }
}

class ProjectDocumentRenderState {
  const ProjectDocumentRenderState({
    required this.path,
    required this.exists,
    required this.sizeBytes,
    required this.sha256,
    required this.sourceHash,
    required this.renderHash,
    required this.status,
    required this.content,
    required this.truncated,
  });

  final String path;
  final bool exists;
  final int sizeBytes;
  final String? sha256;
  final String? sourceHash;
  final String? renderHash;
  final String status;
  final String? content;
  final bool truncated;

  factory ProjectDocumentRenderState.fromJson(Map<String, dynamic> json) {
    return ProjectDocumentRenderState(
      path: _string(json['path']),
      exists: _bool(json['exists']),
      sizeBytes: _int(json['size_bytes']),
      sha256: _nullableString(json['sha256']),
      sourceHash: _nullableString(json['source_hash']),
      renderHash: _nullableString(json['render_hash']),
      status: _string(json['status'], fallback: 'missing'),
      content: _nullableString(json['content']),
      truncated: _bool(json['truncated']),
    );
  }
}

class ProjectDocumentValidationResult {
  const ProjectDocumentValidationResult({
    required this.ok,
    required this.generatedAt,
    required this.blockingCount,
    required this.issues,
  });

  final bool ok;
  final String? generatedAt;
  final int blockingCount;
  final List<ProjectDocumentValidationIssue> issues;

  List<ProjectDocumentValidationIssue> get blockingIssues =>
      issues.where((issue) => issue.blocking).toList(growable: false);

  factory ProjectDocumentValidationResult.fromJson(Map<String, dynamic> json) {
    return ProjectDocumentValidationResult(
      ok: _bool(json['ok']),
      generatedAt: _nullableString(json['generated_at']),
      blockingCount: _int(json['blocking_count']),
      issues: _list(json['issues'])
          .map(ProjectDocumentValidationIssue.fromJson)
          .toList(growable: false),
    );
  }
}

class ProjectDocumentValidationIssue {
  const ProjectDocumentValidationIssue({
    required this.severity,
    required this.code,
    required this.field,
    required this.message,
    required this.nextAction,
    required this.blocking,
    required this.affectedFile,
  });

  final String severity;
  final String code;
  final String field;
  final String message;
  final String nextAction;
  final bool blocking;
  final String affectedFile;

  factory ProjectDocumentValidationIssue.fromJson(Map<String, dynamic> json) {
    return ProjectDocumentValidationIssue(
      severity: _string(json['severity']),
      code: _string(json['code']),
      field: _string(json['field']),
      message: _string(json['message']),
      nextAction: _string(json['next_action']),
      blocking: _bool(json['blocking']),
      affectedFile: _string(json['affected_file']),
    );
  }
}

class ProjectDocumentCharterValidationResponse {
  const ProjectDocumentCharterValidationResponse({
    required this.workspacePath,
    required this.validation,
  });

  final String workspacePath;
  final ProjectDocumentValidationResult validation;

  factory ProjectDocumentCharterValidationResponse.fromJson(
    Map<String, dynamic> json,
  ) {
    return ProjectDocumentCharterValidationResponse(
      workspacePath: _string(json['workspace_path']),
      validation: ProjectDocumentValidationResult.fromJson(
        _map(json['validation']),
      ),
    );
  }
}

class ProjectDocumentCharterRenderResponse {
  const ProjectDocumentCharterRenderResponse({
    required this.workspacePath,
    required this.render,
    required this.renderManifest,
  });

  final String workspacePath;
  final ProjectDocumentRenderState render;
  final Map<String, dynamic> renderManifest;

  factory ProjectDocumentCharterRenderResponse.fromJson(
    Map<String, dynamic> json,
  ) {
    return ProjectDocumentCharterRenderResponse(
      workspacePath: _string(json['workspace_path']),
      render: ProjectDocumentRenderState.fromJson(_map(json['render'])),
      renderManifest: _map(json['render_manifest']),
    );
  }
}

class ProjectDocumentCharterReleaseResponse {
  const ProjectDocumentCharterReleaseResponse({
    required this.workspacePath,
    required this.ok,
    required this.releaseVersion,
    required this.releasePath,
    required this.recommendedImpact,
    required this.validation,
    required this.release,
  });

  final String workspacePath;
  final bool? ok;
  final String? releaseVersion;
  final String? releasePath;
  final String? recommendedImpact;
  final ProjectDocumentValidationResult? validation;
  final ProjectDocumentRelease? release;

  factory ProjectDocumentCharterReleaseResponse.fromJson(
    Map<String, dynamic> json,
  ) {
    final validation = json['validation'];
    final release = json['release'];
    return ProjectDocumentCharterReleaseResponse(
      workspacePath: _string(json['workspace_path']),
      ok: json['ok'] is bool ? json['ok'] as bool : null,
      releaseVersion: _nullableString(json['release_version']),
      releasePath: _nullableString(json['release_path']),
      recommendedImpact: _nullableString(json['recommended_impact']),
      validation: validation is Map
          ? ProjectDocumentValidationResult.fromJson(_map(validation))
          : null,
      release: release is Map
          ? ProjectDocumentRelease.fromJson(_map(release))
          : null,
    );
  }
}

class ProjectDocumentCharterReleasesResponse {
  const ProjectDocumentCharterReleasesResponse({
    required this.workspacePath,
    required this.releases,
  });

  final String workspacePath;
  final List<ProjectDocumentRelease> releases;

  factory ProjectDocumentCharterReleasesResponse.fromJson(
    Map<String, dynamic> json,
  ) {
    return ProjectDocumentCharterReleasesResponse(
      workspacePath: _string(json['workspace_path']),
      releases: _list(json['releases'])
          .map(ProjectDocumentRelease.fromJson)
          .toList(growable: false),
    );
  }
}

class ProjectDocumentRelease {
  const ProjectDocumentRelease({
    required this.version,
    required this.path,
    required this.exists,
    required this.manifest,
    required this.metadata,
    required this.artifacts,
    required this.source,
    required this.render,
  });

  final String version;
  final String path;
  final bool exists;
  final Map<String, dynamic> manifest;
  final Map<String, dynamic> metadata;
  final List<String> artifacts;
  final ProjectDocumentFileContent? source;
  final ProjectDocumentFileContent? render;

  String? get releasedAt {
    final candidates = <Object?>[
      manifest['released_at'],
      manifest['generated_at'],
      metadata['released_at'],
    ];
    for (final candidate in candidates) {
      final value = _nullableString(candidate);
      if (value != null) {
        return value;
      }
    }
    return null;
  }

  factory ProjectDocumentRelease.fromJson(Map<String, dynamic> json) {
    final source = json['source'];
    final render = json['render'];
    return ProjectDocumentRelease(
      version: _string(json['version']),
      path: _string(json['path']),
      exists: _bool(json['exists']),
      manifest: _map(json['manifest']),
      metadata: _map(json['metadata']),
      artifacts: _stringList(json['artifacts']),
      source: source is Map
          ? ProjectDocumentFileContent.fromJson(_map(source))
          : null,
      render: render is Map
          ? ProjectDocumentFileContent.fromJson(_map(render))
          : null,
    );
  }
}

class ProjectDocumentFileContent {
  const ProjectDocumentFileContent({
    required this.path,
    required this.exists,
    required this.sizeBytes,
    required this.sha256,
    required this.content,
    required this.truncated,
  });

  final String path;
  final bool exists;
  final int sizeBytes;
  final String? sha256;
  final String? content;
  final bool truncated;

  factory ProjectDocumentFileContent.fromJson(Map<String, dynamic> json) {
    return ProjectDocumentFileContent(
      path: _string(json['path']),
      exists: _bool(json['exists']),
      sizeBytes: _int(json['size_bytes']),
      sha256: _nullableString(json['sha256']),
      content: _nullableString(json['content']),
      truncated: _bool(json['truncated']),
    );
  }
}

Map<String, dynamic> _map(Object? value) {
  if (value is Map<String, dynamic>) {
    return value;
  }
  if (value is Map) {
    return value.map((key, item) => MapEntry('$key', item));
  }
  return <String, dynamic>{};
}

List<Map<String, dynamic>> _list(Object? value) {
  if (value is List) {
    return value.whereType<Map>().map(_map).toList(growable: false);
  }
  return const <Map<String, dynamic>>[];
}

List<String> _stringList(Object? value) {
  if (value is List) {
    return value.map(_string).where((item) => item.isNotEmpty).toList(
          growable: false,
        );
  }
  return const <String>[];
}

String _string(Object? value, {String fallback = ''}) {
  if (value == null) {
    return fallback;
  }
  final text = '$value'.trim();
  return text.isEmpty ? fallback : text;
}

String? _nullableString(Object? value) {
  if (value == null) {
    return null;
  }
  final text = '$value'.trim();
  return text.isEmpty ? null : text;
}

bool _bool(Object? value) => value is bool ? value : false;

int _int(Object? value) {
  if (value is int) {
    return value;
  }
  if (value is num) {
    return value.toInt();
  }
  return 0;
}
