class SddProjectsIndex {
  const SddProjectsIndex({required this.projects, this.defaultWorkspacePath});

  final List<SddProjectSummary> projects;
  final String? defaultWorkspacePath;

  factory SddProjectsIndex.fromJson(Map<String, dynamic> json) {
    final rawProjects = json['projects'];
    return SddProjectsIndex(
      defaultWorkspacePath: _trimmedString(json['default_workspace_path']),
      projects: rawProjects is List
          ? rawProjects
                .whereType<Map<String, dynamic>>()
                .map(SddProjectSummary.fromJson)
                .toList(growable: false)
          : const <SddProjectSummary>[],
    );
  }
}

class SddProjectSummary {
  const SddProjectSummary({
    required this.workspaceName,
    required this.workspacePath,
    required this.specCount,
    required this.diagramCount,
    required this.missingRequired,
    required this.hasManifest,
    required this.hasConstitution,
  });

  final String workspaceName;
  final String workspacePath;
  final int specCount;
  final int diagramCount;
  final List<String> missingRequired;
  final bool hasManifest;
  final bool hasConstitution;

  factory SddProjectSummary.fromJson(Map<String, dynamic> json) {
    return SddProjectSummary(
      workspaceName: json['workspace_name'] as String? ?? 'Unknown project',
      workspacePath: json['workspace_path'] as String? ?? '',
      specCount: json['spec_count'] as int? ?? 0,
      diagramCount: json['diagram_count'] as int? ?? 0,
      missingRequired: _stringList(json['missing_required']),
      hasManifest: json['has_manifest'] as bool? ?? false,
      hasConstitution: json['has_constitution'] as bool? ?? false,
    );
  }
}

class SddProject {
  const SddProject({
    required this.workspaceName,
    required this.workspacePath,
    required this.required,
    required this.architectureDiagrams,
    required this.specs,
    required this.missingRequired,
    this.manifest,
    this.constitution,
  });

  final String workspaceName;
  final String workspacePath;
  final bool required;
  final SddFile? manifest;
  final SddFile? constitution;
  final List<SddDiagram> architectureDiagrams;
  final List<SddSpec> specs;
  final List<String> missingRequired;

  bool get hasMissingRequired => missingRequired.isNotEmpty;

  factory SddProject.fromJson(Map<String, dynamic> json) {
    return SddProject(
      workspaceName: json['workspace_name'] as String? ?? 'Unknown project',
      workspacePath: json['workspace_path'] as String? ?? '',
      required: json['required'] as bool? ?? true,
      manifest: _fileFromJson(json['manifest']),
      constitution: _fileFromJson(json['constitution']),
      architectureDiagrams: _diagramList(json['architecture_diagrams']),
      specs: _specList(json['specs']),
      missingRequired: _stringList(json['missing_required']),
    );
  }
}

class SddSpec {
  const SddSpec({
    required this.id,
    required this.title,
    this.description = '',
    required this.path,
    required this.diagrams,
    required this.sliceDocs,
    required this.missing,
    this.lifecycleStatus = 'draft',
    this.traceabilityStatus = 'unknown',
    this.createdAt,
    this.updatedAt,
    this.generatedTitle = false,
    this.generatedDescription = false,
    this.userPinnedTitle = false,
    this.userPinnedDescription = false,
    this.taskTotal = 0,
    this.taskCompleted = 0,
    this.taskPending = 0,
    this.lastRunState,
    this.metadataStatus = 'missing',
    this.metadataWarnings = const <String>[],
    this.metadataStalePaths = const <String>[],
    this.spec,
    this.plan,
    this.tasks,
    this.specFiles = const <SddFile>[],
    this.planFiles = const <SddFile>[],
    this.taskFiles = const <SddFile>[],
  });

  final String id;
  final String title;
  final String description;
  final String path;
  final String lifecycleStatus;
  final String traceabilityStatus;
  final String? createdAt;
  final String? updatedAt;
  final bool generatedTitle;
  final bool generatedDescription;
  final bool userPinnedTitle;
  final bool userPinnedDescription;
  final int taskTotal;
  final int taskCompleted;
  final int taskPending;
  final String? lastRunState;
  final String metadataStatus;
  final List<String> metadataWarnings;
  final List<String> metadataStalePaths;
  final SddFile? spec;
  final SddFile? plan;
  final SddFile? tasks;
  final List<SddFile> specFiles;
  final List<SddFile> planFiles;
  final List<SddFile> taskFiles;
  final List<SddFile> sliceDocs;
  final List<SddDiagram> diagrams;
  final List<String> missing;

  List<SddFile> get allSpecFiles => _preferredFiles(specFiles, spec);
  List<SddFile> get allPlanFiles => _preferredFiles(planFiles, plan);
  List<SddFile> get allTaskFiles => _preferredFiles(taskFiles, tasks);

  factory SddSpec.fromJson(Map<String, dynamic> json) {
    final spec = _fileFromJson(json['spec']);
    final plan = _fileFromJson(json['plan']);
    final tasks = _fileFromJson(json['tasks']);
    final fallbackProgress = _taskProgressFromMarkdown(tasks?.content);
    final taskTotal =
        _intValue(json['task_total'] ?? json['taskTotal']) ??
        fallbackProgress?.total ??
        0;
    final taskCompleted =
        _intValue(json['task_completed'] ?? json['taskCompleted']) ??
        fallbackProgress?.completed ??
        0;
    return SddSpec(
      id: json['id'] as String? ?? '',
      title:
          json['title'] as String? ?? json['id'] as String? ?? 'Untitled spec',
      description: _trimmedString(json['description']) ?? '',
      path: json['path'] as String? ?? '',
      lifecycleStatus:
          _trimmedString(json['lifecycle_status'] ?? json['lifecycleStatus']) ??
          '',
      traceabilityStatus:
          _trimmedString(
            json['traceability_status'] ?? json['traceabilityStatus'],
          ) ??
          'unknown',
      createdAt: _trimmedString(json['created_at'] ?? json['createdAt']),
      updatedAt: _trimmedString(json['updated_at'] ?? json['updatedAt']),
      generatedTitle:
          _boolValue(json['generated_title'] ?? json['generatedTitle']) ??
          false,
      generatedDescription:
          _boolValue(
            json['generated_description'] ?? json['generatedDescription'],
          ) ??
          false,
      userPinnedTitle:
          _boolValue(json['user_pinned_title'] ?? json['userPinnedTitle']) ??
          false,
      userPinnedDescription:
          _boolValue(
            json['user_pinned_description'] ?? json['userPinnedDescription'],
          ) ??
          false,
      taskTotal: taskTotal,
      taskCompleted: taskCompleted,
      taskPending:
          _intValue(json['task_pending'] ?? json['taskPending']) ??
          (taskTotal - taskCompleted).clamp(0, taskTotal).toInt(),
      lastRunState: _trimmedString(
        json['last_run_state'] ?? json['lastRunState'],
      ),
      metadataStatus:
          _trimmedString(json['metadata_status'] ?? json['metadataStatus']) ??
          'missing',
      metadataWarnings: _stringList(
        json['metadata_warnings'] ?? json['metadataWarnings'],
      ),
      metadataStalePaths: _stringList(
        json['metadata_stale_paths'] ?? json['metadataStalePaths'],
      ),
      spec: spec,
      plan: plan,
      tasks: tasks,
      specFiles: _fileListWithFallback(
        json['spec_files'] ?? json['spec_documents'],
        spec,
      ),
      planFiles: _fileListWithFallback(
        json['plan_files'] ??
            json['plans'] ??
            (json['plan'] is List ? json['plan'] : null),
        plan,
      ),
      taskFiles: _fileListWithFallback(
        json['task_files'] ??
            json['tasks_files'] ??
            (json['tasks'] is List ? json['tasks'] : null),
        tasks,
      ),
      sliceDocs: _fileList(json['slice_docs']),
      diagrams: _diagramList(json['diagrams']),
      missing: _stringList(json['missing']),
    );
  }
}

class SddFile {
  const SddFile({
    required this.path,
    required this.sizeBytes,
    this.title,
    this.content,
    this.error,
  });

  final String path;
  final String? title;
  final int sizeBytes;
  final String? content;
  final String? error;

  bool get hasContent => content != null && content!.trim().isNotEmpty;

  factory SddFile.fromJson(Map<String, dynamic> json) {
    return SddFile(
      path: json['path'] as String? ?? '',
      title: _trimmedString(json['title']),
      sizeBytes: json['size_bytes'] as int? ?? 0,
      content: json['content'] as String?,
      error: _trimmedString(json['error']),
    );
  }
}

class SddDiagram extends SddFile {
  const SddDiagram({
    required super.path,
    required super.sizeBytes,
    required this.diagramType,
    required this.scope,
    super.title,
    super.content,
    super.error,
  });

  final String diagramType;
  final String scope;

  factory SddDiagram.fromJson(Map<String, dynamic> json) {
    return SddDiagram(
      path: json['path'] as String? ?? '',
      title: _trimmedString(json['title']),
      sizeBytes: json['size_bytes'] as int? ?? 0,
      content: json['content'] as String?,
      error: _trimmedString(json['error']),
      diagramType: json['diagram_type'] as String? ?? 'unknown',
      scope: json['scope'] as String? ?? '',
    );
  }
}

SddFile? _fileFromJson(Object? value) {
  if (value is! Map<String, dynamic>) return null;
  return SddFile.fromJson(value);
}

List<SddDiagram> _diagramList(Object? value) {
  if (value is! List) return const <SddDiagram>[];
  return value
      .whereType<Map<String, dynamic>>()
      .map(SddDiagram.fromJson)
      .toList(growable: false);
}

List<SddFile> _fileList(Object? value) {
  if (value is! List) return const <SddFile>[];
  return value
      .whereType<Map<String, dynamic>>()
      .map(SddFile.fromJson)
      .toList(growable: false);
}

List<SddFile> _fileListWithFallback(Object? value, SddFile? fallback) {
  final files = _fileList(value);
  if (files.isNotEmpty) return files;
  return fallback == null ? const <SddFile>[] : <SddFile>[fallback];
}

List<SddFile> _preferredFiles(List<SddFile> files, SddFile? fallback) {
  if (files.isNotEmpty) return files;
  return fallback == null ? const <SddFile>[] : <SddFile>[fallback];
}

List<SddSpec> _specList(Object? value) {
  if (value is! List) return const <SddSpec>[];
  return value
      .whereType<Map<String, dynamic>>()
      .map(SddSpec.fromJson)
      .toList(growable: false);
}

List<String> _stringList(Object? value) {
  if (value is! List) return const <String>[];
  return value
      .map((item) => item?.toString() ?? '')
      .where((item) => item.trim().isNotEmpty)
      .toList(growable: false);
}

int? _intValue(Object? value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '');
}

bool? _boolValue(Object? value) {
  if (value is bool) return value;
  final normalized = value?.toString().trim().toLowerCase();
  if (normalized == 'true') return true;
  if (normalized == 'false') return false;
  return null;
}

_SddTaskSummary? _taskProgressFromMarkdown(String? content) {
  if (content == null || content.trim().isEmpty) return null;
  var completed = 0;
  var total = 0;
  final checkbox = RegExp(r'^\s*-\s+\[([ xX])\]');
  for (final line in content.split('\n')) {
    final match = checkbox.firstMatch(line);
    if (match == null) continue;
    total += 1;
    if ((match.group(1) ?? '').toLowerCase() == 'x') completed += 1;
  }
  if (total == 0) return null;
  return _SddTaskSummary(completed: completed, total: total);
}

class _SddTaskSummary {
  const _SddTaskSummary({required this.completed, required this.total});

  final int completed;
  final int total;
}

String? _trimmedString(Object? value) {
  final text = value?.toString().trim();
  return text == null || text.isEmpty ? null : text;
}
