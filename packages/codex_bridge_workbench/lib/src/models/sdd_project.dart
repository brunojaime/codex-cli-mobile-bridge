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

  SddProject copyWith({
    String? workspaceName,
    String? workspacePath,
    bool? required,
    SddFile? manifest,
    SddFile? constitution,
    List<SddDiagram>? architectureDiagrams,
    List<SddSpec>? specs,
    List<String>? missingRequired,
  }) {
    return SddProject(
      workspaceName: workspaceName ?? this.workspaceName,
      workspacePath: workspacePath ?? this.workspacePath,
      required: required ?? this.required,
      manifest: manifest ?? this.manifest,
      constitution: constitution ?? this.constitution,
      architectureDiagrams: architectureDiagrams ?? this.architectureDiagrams,
      specs: specs ?? this.specs,
      missingRequired: missingRequired ?? this.missingRequired,
    );
  }

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
    this.tree,
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
  final SddSpecTree? tree;
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
      tree: _specTreeFromJson(json['tree']),
      missing: _stringList(json['missing']),
    );
  }
}

class SddSpecTree {
  const SddSpecTree({
    required this.plans,
    required this.diagrams,
    required this.complete,
    this.file,
    this.missing = const <String>[],
  });

  final SddFile? file;
  final List<SddDiagram> diagrams;
  final List<SddPlanNode> plans;
  final bool complete;
  final List<String> missing;

  bool get isComplete => complete && missing.isEmpty;

  factory SddSpecTree.fromJson(Map<String, dynamic> json) {
    final file = _fileFromJson(json['file']);
    final plans = _planNodeList(json['plans']);
    final missing = _stringList(json['missing']);
    final explicitComplete = _boolValue(json['complete']);
    return SddSpecTree(
      file: file,
      diagrams: _diagramList(json['diagrams']),
      plans: plans,
      complete:
          explicitComplete ?? _computedTreeComplete(file: file, plans: plans),
      missing: missing,
    );
  }
}

class SddPlanNode {
  const SddPlanNode({
    required this.id,
    required this.title,
    required this.number,
    required this.status,
    required this.description,
    required this.diagrams,
    required this.tasks,
    this.file,
  });

  final String id;
  final String title;
  final int number;
  final String status;
  final String description;
  final SddFile? file;
  final List<SddDiagram> diagrams;
  final List<SddTaskNode> tasks;

  factory SddPlanNode.fromJson(Map<String, dynamic> json) {
    return SddPlanNode(
      id: json['id'] as String? ?? '',
      title: json['title'] as String? ?? 'Plan',
      number: json['number'] as int? ?? 0,
      status: json['status'] as String? ?? 'planned',
      description: _trimmedString(json['description']) ?? '',
      file: _fileFromJson(json['file']),
      diagrams: _diagramList(json['diagrams']),
      tasks: _taskNodeList(json['tasks']),
    );
  }
}

class SddTaskNode {
  const SddTaskNode({
    required this.id,
    required this.title,
    required this.number,
    required this.status,
    required this.description,
    required this.diagrams,
    this.file,
  });

  final String id;
  final String title;
  final int number;
  final String status;
  final String description;
  final SddFile? file;
  final List<SddDiagram> diagrams;

  factory SddTaskNode.fromJson(Map<String, dynamic> json) {
    return SddTaskNode(
      id: json['id'] as String? ?? '',
      title: json['title'] as String? ?? 'Task',
      number: json['number'] as int? ?? 0,
      status: json['status'] as String? ?? 'planned',
      description: _trimmedString(json['description']) ?? '',
      file: _fileFromJson(json['file']),
      diagrams: _diagramList(json['diagrams']),
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

class SddWorkbenchKanban {
  const SddWorkbenchKanban({
    required this.scope,
    required this.board,
    required this.latestUpdate,
    required this.historySummary,
    required this.curator,
    required this.evidence,
    required this.continuity,
  });

  final SddKanbanScope scope;
  final SddKanbanBoard board;
  final SddCuratorUpdate? latestUpdate;
  final Map<String, dynamic> historySummary;
  final Map<String, dynamic> curator;
  final List<Map<String, dynamic>> evidence;
  final List<Map<String, dynamic>> continuity;

  factory SddWorkbenchKanban.fromJson(Map<String, dynamic> json) {
    return SddWorkbenchKanban(
      scope: SddKanbanScope.fromJson(_mapValue(json['scope'])),
      board: SddKanbanBoard.fromJson(_mapValue(json['board'])),
      latestUpdate: _mapValueOrNull(json['latestUpdate']) == null
          ? null
          : SddCuratorUpdate.fromJson(_mapValue(json['latestUpdate'])),
      historySummary: _mapValue(json['historySummary']),
      curator: _mapValue(json['curator']),
      evidence: _mapList(json['evidence']),
      continuity: _mapList(json['continuity']),
    );
  }
}

class SddKanbanScope {
  const SddKanbanScope({
    required this.id,
    required this.type,
    required this.title,
    this.workspacePath,
    this.specId,
    this.draftId,
    this.jobId,
  });

  final String id;
  final String type;
  final String title;
  final String? workspacePath;
  final String? specId;
  final String? draftId;
  final String? jobId;

  factory SddKanbanScope.fromJson(Map<String, dynamic> json) {
    return SddKanbanScope(
      id: json['id'] as String? ?? '',
      type: json['type'] as String? ?? 'workspace',
      title: json['title'] as String? ?? 'Workbench',
      workspacePath: _trimmedString(json['workspacePath']),
      specId: _trimmedString(json['specId']),
      draftId: _trimmedString(json['draftId']),
      jobId: _trimmedString(json['jobId']),
    );
  }
}

class SddKanbanBoard {
  const SddKanbanBoard({
    required this.snapshotId,
    required this.evidenceHash,
    required this.updatedAt,
    required this.columns,
    required this.cards,
    required this.counts,
    required this.delta,
    required this.refresh,
  });

  final String snapshotId;
  final String evidenceHash;
  final String updatedAt;
  final List<SddKanbanColumn> columns;
  final List<SddKanbanCard> cards;
  final Map<String, int> counts;
  final Map<String, dynamic> delta;
  final Map<String, dynamic> refresh;

  factory SddKanbanBoard.fromJson(Map<String, dynamic> json) {
    return SddKanbanBoard(
      snapshotId: json['snapshotId'] as String? ?? '',
      evidenceHash: json['evidenceHash'] as String? ?? '',
      updatedAt: json['updatedAt'] as String? ?? '',
      columns: _kanbanColumnList(json['columns']),
      cards: _kanbanCardList(json['cards']),
      counts: _intMap(json['counts']),
      delta: _mapValue(json['delta']),
      refresh: _mapValue(json['refresh']),
    );
  }

  SddKanbanCard? cardById(String id) {
    for (final card in cards) {
      if (card.id == id) return card;
    }
    return null;
  }
}

class SddKanbanColumn {
  const SddKanbanColumn({
    required this.id,
    required this.label,
    required this.cardIds,
    required this.count,
  });

  final String id;
  final String label;
  final List<String> cardIds;
  final int count;

  factory SddKanbanColumn.fromJson(Map<String, dynamic> json) {
    return SddKanbanColumn(
      id: json['id'] as String? ?? '',
      label: json['label'] as String? ?? '',
      cardIds: _stringList(json['cardIds']),
      count: _intValue(json['count']) ?? 0,
    );
  }
}

class SddKanbanCard {
  const SddKanbanCard({
    required this.id,
    required this.type,
    required this.title,
    required this.column,
    required this.status,
    required this.scopeId,
    required this.sourcePath,
    required this.order,
    required this.confirmed,
    required this.inferred,
    required this.confidence,
    required this.badges,
    required this.detail,
    required this.evidence,
    required this.manualCommands,
  });

  final String id;
  final String type;
  final String title;
  final String column;
  final String status;
  final String scopeId;
  final String sourcePath;
  final int order;
  final bool confirmed;
  final bool inferred;
  final String confidence;
  final List<String> badges;
  final String detail;
  final List<Map<String, dynamic>> evidence;
  final List<String> manualCommands;

  factory SddKanbanCard.fromJson(Map<String, dynamic> json) {
    return SddKanbanCard(
      id: json['id'] as String? ?? '',
      type: json['type'] as String? ?? 'card',
      title: json['title'] as String? ?? 'Untitled card',
      column: json['column'] as String? ?? 'backlog',
      status: json['status'] as String? ?? '',
      scopeId: json['scopeId'] as String? ?? '',
      sourcePath: json['sourcePath'] as String? ?? '',
      order: _intValue(json['order']) ?? 0,
      confirmed: _boolValue(json['confirmed']) ?? false,
      inferred: _boolValue(json['inferred']) ?? false,
      confidence: json['confidence'] as String? ?? 'observed',
      badges: _stringList(json['badges']),
      detail: _trimmedString(json['detail']) ?? '',
      evidence: _mapList(json['evidence']),
      manualCommands: _stringList(json['manualCommands']),
    );
  }
}

class SddCuratorUpdate {
  const SddCuratorUpdate({
    required this.id,
    required this.timestamp,
    required this.title,
    required this.summary,
    required this.changedCards,
    required this.changedCounts,
    required this.importantEvidence,
    required this.blockers,
    required this.risks,
    required this.nextWatch,
  });

  final String id;
  final String timestamp;
  final String title;
  final String summary;
  final List<String> changedCards;
  final Map<String, dynamic> changedCounts;
  final List<Map<String, dynamic>> importantEvidence;
  final List<String> blockers;
  final List<String> risks;
  final String nextWatch;

  factory SddCuratorUpdate.fromJson(Map<String, dynamic> json) {
    return SddCuratorUpdate(
      id: json['id'] as String? ?? '',
      timestamp: json['timestamp'] as String? ?? '',
      title: json['title'] as String? ?? 'Curator update',
      summary: json['summary'] as String? ?? '',
      changedCards: _stringList(json['changedCards']),
      changedCounts: _mapValue(json['changedCounts']),
      importantEvidence: _mapList(json['importantEvidence']),
      blockers: _stringList(json['blockers']),
      risks: _stringList(json['risks']),
      nextWatch: json['nextWatch'] as String? ?? '',
    );
  }
}

class SddKanbanHistory {
  const SddKanbanHistory({required this.scopeId, required this.items});

  final String? scopeId;
  final List<SddCuratorUpdate> items;

  factory SddKanbanHistory.fromJson(Map<String, dynamic> json) {
    final rawHistory = json['history'];
    return SddKanbanHistory(
      scopeId: _trimmedString(json['scopeId']),
      items: rawHistory is List
          ? rawHistory
                .whereType<Map<String, dynamic>>()
                .map(SddCuratorUpdate.fromJson)
                .toList(growable: false)
          : const <SddCuratorUpdate>[],
    );
  }
}

SddFile? _fileFromJson(Object? value) {
  if (value is! Map<String, dynamic>) return null;
  return SddFile.fromJson(value);
}

SddSpecTree? _specTreeFromJson(Object? value) {
  if (value is! Map<String, dynamic>) return null;
  return SddSpecTree.fromJson(value);
}

List<SddPlanNode> _planNodeList(Object? value) {
  if (value is! List) return const <SddPlanNode>[];
  return value
      .whereType<Map<String, dynamic>>()
      .map(SddPlanNode.fromJson)
      .toList(growable: false);
}

List<SddTaskNode> _taskNodeList(Object? value) {
  if (value is! List) return const <SddTaskNode>[];
  return value
      .whereType<Map<String, dynamic>>()
      .map(SddTaskNode.fromJson)
      .toList(growable: false);
}

bool _computedTreeComplete({
  required SddFile? file,
  required List<SddPlanNode> plans,
}) {
  if (file == null || plans.isEmpty) return false;
  for (final plan in plans) {
    if (plan.file == null || plan.tasks.isEmpty) return false;
    for (final task in plan.tasks) {
      if (task.file == null) return false;
    }
  }
  return true;
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

List<SddKanbanColumn> _kanbanColumnList(Object? value) {
  if (value is! List) return const <SddKanbanColumn>[];
  return value
      .whereType<Map<String, dynamic>>()
      .map(SddKanbanColumn.fromJson)
      .toList(growable: false);
}

List<SddKanbanCard> _kanbanCardList(Object? value) {
  if (value is! List) return const <SddKanbanCard>[];
  return value
      .whereType<Map<String, dynamic>>()
      .map(SddKanbanCard.fromJson)
      .toList(growable: false);
}

Map<String, dynamic> _mapValue(Object? value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) {
    return value.map((key, value) => MapEntry(key.toString(), value));
  }
  return <String, dynamic>{};
}

Map<String, dynamic>? _mapValueOrNull(Object? value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) {
    return value.map((key, value) => MapEntry(key.toString(), value));
  }
  return null;
}

List<Map<String, dynamic>> _mapList(Object? value) {
  if (value is! List) return const <Map<String, dynamic>>[];
  return value
      .whereType<Map>()
      .map((item) => item.map((key, value) => MapEntry(key.toString(), value)))
      .toList(growable: false);
}

Map<String, int> _intMap(Object? value) {
  if (value is! Map) return const <String, int>{};
  return value.map(
    (key, value) => MapEntry(key.toString(), _intValue(value) ?? 0),
  );
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
