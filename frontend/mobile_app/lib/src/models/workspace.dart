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
}
