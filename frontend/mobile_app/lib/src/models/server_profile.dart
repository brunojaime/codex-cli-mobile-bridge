class ServerProfile {
  const ServerProfile({
    required this.id,
    required this.name,
    required this.baseUrl,
  });

  final String id;
  final String name;
  final String baseUrl;

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
      'base_url': baseUrl,
    };
  }

  factory ServerProfile.fromJson(Map<String, dynamic> json) {
    return ServerProfile(
      id: json['id'] as String,
      name: json['name'] as String,
      baseUrl: json['base_url'] as String,
    );
  }
}
