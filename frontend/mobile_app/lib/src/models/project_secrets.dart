class ProjectSecrets {
  const ProjectSecrets({
    required this.workspacePath,
    required this.workspaceName,
    required this.envFile,
    required this.names,
  });

  factory ProjectSecrets.fromJson(Map<String, dynamic> json) {
    return ProjectSecrets(
      workspacePath: json['workspace_path'] as String? ?? '',
      workspaceName: json['workspace_name'] as String? ?? '',
      envFile: json['env_file'] as String? ?? '.env',
      names: ((json['names'] as List<dynamic>?) ?? const <dynamic>[])
          .whereType<String>()
          .toList(growable: false),
    );
  }

  final String workspacePath;
  final String workspaceName;
  final String envFile;
  final List<String> names;
}
