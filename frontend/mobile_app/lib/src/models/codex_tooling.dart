class CodexRunOptions {
  const CodexRunOptions({
    this.profile,
    this.searchEnabled = false,
    this.skillIds = const <String>[],
    this.mcpServerIds = const <String>[],
    this.configOverrides = const <String>[],
  });

  final String? profile;
  final bool searchEnabled;
  final List<String> skillIds;
  final List<String> mcpServerIds;
  final List<String> configOverrides;

  bool get isEmpty =>
      (profile == null || profile!.trim().isEmpty) &&
      !searchEnabled &&
      skillIds.isEmpty &&
      mcpServerIds.isEmpty &&
      configOverrides.isEmpty;

  CodexRunOptions copyWith({
    String? profile,
    bool? searchEnabled,
    List<String>? skillIds,
    List<String>? mcpServerIds,
    List<String>? configOverrides,
    bool clearProfile = false,
  }) {
    return CodexRunOptions(
      profile: clearProfile ? null : profile ?? this.profile,
      searchEnabled: searchEnabled ?? this.searchEnabled,
      skillIds: skillIds ?? this.skillIds,
      mcpServerIds: mcpServerIds ?? this.mcpServerIds,
      configOverrides: configOverrides ?? this.configOverrides,
    );
  }

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      if (profile != null && profile!.trim().isNotEmpty) 'profile': profile,
      'search_enabled': searchEnabled,
      'skill_ids': skillIds,
      'mcp_server_ids': mcpServerIds,
      'config_overrides': configOverrides,
    };
  }
}

class CodexSkill {
  const CodexSkill({
    required this.skillId,
    required this.name,
    required this.description,
    required this.source,
    required this.path,
  });

  final String skillId;
  final String name;
  final String description;
  final String source;
  final String path;

  factory CodexSkill.fromJson(Map<String, dynamic> json) {
    return CodexSkill(
      skillId: json['skill_id'] as String? ?? '',
      name: json['name'] as String? ?? '',
      description: json['description'] as String? ?? '',
      source: json['source'] as String? ?? '',
      path: json['path'] as String? ?? '',
    );
  }
}

class CodexConfigProfile {
  const CodexConfigProfile({
    required this.name,
  });

  final String name;

  factory CodexConfigProfile.fromJson(Map<String, dynamic> json) {
    return CodexConfigProfile(
      name: json['name'] as String? ?? '',
    );
  }
}

class CodexMcpServer {
  const CodexMcpServer({
    required this.serverId,
    required this.summary,
  });

  final String serverId;
  final String summary;

  factory CodexMcpServer.fromJson(Map<String, dynamic> json) {
    return CodexMcpServer(
      serverId: json['server_id'] as String? ?? '',
      summary: json['summary'] as String? ?? '',
    );
  }
}

class CodexStatus {
  const CodexStatus({
    required this.cliAvailable,
    required this.command,
    required this.statusSummary,
    this.version,
    this.loggedIn = false,
    this.authMode,
    this.rawStatus,
    this.usageAvailable = false,
    this.usageSummary,
    this.error,
  });

  final bool cliAvailable;
  final String command;
  final String? version;
  final bool loggedIn;
  final String? authMode;
  final String statusSummary;
  final String? rawStatus;
  final bool usageAvailable;
  final String? usageSummary;
  final String? error;

  factory CodexStatus.fromJson(Map<String, dynamic> json) {
    return CodexStatus(
      cliAvailable: json['cli_available'] as bool? ?? false,
      command: json['command'] as String? ?? '',
      version: json['version'] as String?,
      loggedIn: json['logged_in'] as bool? ?? false,
      authMode: json['auth_mode'] as String?,
      statusSummary: json['status_summary'] as String? ?? '',
      rawStatus: json['raw_status'] as String?,
      usageAvailable: json['usage_available'] as bool? ?? false,
      usageSummary: json['usage_summary'] as String?,
      error: json['error'] as String?,
    );
  }
}

class CodexToolingSnapshot {
  const CodexToolingSnapshot({
    required this.status,
    this.profiles = const <CodexConfigProfile>[],
    this.skills = const <CodexSkill>[],
    this.mcpServers = const <CodexMcpServer>[],
    this.mcpRawOutput,
    this.mcpError,
    this.configPath,
  });

  final CodexStatus status;
  final List<CodexConfigProfile> profiles;
  final List<CodexSkill> skills;
  final List<CodexMcpServer> mcpServers;
  final String? mcpRawOutput;
  final String? mcpError;
  final String? configPath;

  factory CodexToolingSnapshot.fromJson(Map<String, dynamic> json) {
    return CodexToolingSnapshot(
      status: CodexStatus.fromJson(json['status'] as Map<String, dynamic>),
      profiles: (json['profiles'] as List<dynamic>? ?? const <dynamic>[])
          .map((item) =>
              CodexConfigProfile.fromJson(item as Map<String, dynamic>))
          .toList(),
      skills: (json['skills'] as List<dynamic>? ?? const <dynamic>[])
          .map((item) => CodexSkill.fromJson(item as Map<String, dynamic>))
          .toList(),
      mcpServers: (json['mcp_servers'] as List<dynamic>? ?? const <dynamic>[])
          .map((item) => CodexMcpServer.fromJson(item as Map<String, dynamic>))
          .toList(),
      mcpRawOutput: json['mcp_raw_output'] as String?,
      mcpError: json['mcp_error'] as String?,
      configPath: json['config_path'] as String?,
    );
  }
}
