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
    required this.path,
    required this.diagrams,
    required this.sliceDocs,
    required this.missing,
    this.spec,
    this.plan,
    this.tasks,
    this.specFiles = const <SddFile>[],
    this.planFiles = const <SddFile>[],
    this.taskFiles = const <SddFile>[],
  });

  final String id;
  final String title;
  final String path;
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
    return SddSpec(
      id: json['id'] as String? ?? '',
      title:
          json['title'] as String? ?? json['id'] as String? ?? 'Untitled spec',
      path: json['path'] as String? ?? '',
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

String? _trimmedString(Object? value) {
  final text = value?.toString().trim();
  return text == null || text.isEmpty ? null : text;
}
