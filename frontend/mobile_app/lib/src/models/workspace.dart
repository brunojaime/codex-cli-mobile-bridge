class Workspace {
  const Workspace({
    required this.name,
    required this.path,
  });

  final String name;
  final String path;

  factory Workspace.fromJson(Map<String, dynamic> json) {
    return Workspace(
      name: json['name'] as String,
      path: json['path'] as String,
    );
  }

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'name': name,
      'path': path,
    };
  }
}

/// Coordinator worktrees are implementation details, not user projects.
bool isTeamWorkspace(String path) =>
    RegExp(r'^nienfos-team-[a-f0-9]{24}-[0-9]+-[a-z_]+(?:-scratch)?$').hasMatch(
        path
                .replaceAll('\\', '/')
                .split('/')
                .where((s) => s.isNotEmpty)
                .lastOrNull ??
            '');
