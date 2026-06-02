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
    this.source = 'external',
    this.backingAppId,
    this.status,
    this.selectable = true,
    this.selectableReason,
    this.disabledReason,
    this.lookupError,
  });

  final String serverId;
  final String summary;
  final String source;
  final String? backingAppId;
  final String? status;
  final bool selectable;
  final String? selectableReason;
  final String? disabledReason;
  final String? lookupError;

  factory CodexMcpServer.fromJson(Map<String, dynamic> json) {
    return CodexMcpServer(
      serverId: json['server_id'] as String? ?? '',
      summary: json['summary'] as String? ?? '',
      source: json['source'] as String? ?? 'external',
      backingAppId: json['backing_app_id'] as String?,
      status: json['status'] as String?,
      selectable: json['selectable'] as bool? ?? true,
      selectableReason: json['selectable_reason'] as String?,
      disabledReason: json['disabled_reason'] as String?,
      lookupError: json['lookup_error'] as String?,
    );
  }
}

class CodexMcpAppTool {
  const CodexMcpAppTool({
    required this.name,
    this.title,
    this.description,
    this.readOnly = false,
    this.destructive = false,
    this.idempotent = false,
    this.openWorld = false,
    this.inputSchema = const <String, dynamic>{},
  });

  final String name;
  final String? title;
  final String? description;
  final bool readOnly;
  final bool destructive;
  final bool idempotent;
  final bool openWorld;
  final Map<String, dynamic> inputSchema;

  factory CodexMcpAppTool.fromJson(Map<String, dynamic> json) {
    return CodexMcpAppTool(
      name: json['name'] as String? ?? '',
      title: json['title'] as String?,
      description: json['description'] as String?,
      readOnly: json['read_only'] as bool? ?? false,
      destructive: json['destructive'] as bool? ?? false,
      idempotent: json['idempotent'] as bool? ?? false,
      openWorld: json['open_world'] as bool? ?? false,
      inputSchema: (json['input_schema'] as Map<String, dynamic>?) ??
          const <String, dynamic>{},
    );
  }
}

class CodexMcpAppResource {
  const CodexMcpAppResource({
    required this.name,
    required this.uri,
    this.title,
    this.description,
    this.mimeType,
  });

  final String name;
  final String uri;
  final String? title;
  final String? description;
  final String? mimeType;

  factory CodexMcpAppResource.fromJson(Map<String, dynamic> json) {
    return CodexMcpAppResource(
      name: json['name'] as String? ?? '',
      uri: json['uri'] as String? ?? '',
      title: json['title'] as String?,
      description: json['description'] as String?,
      mimeType: json['mime_type'] as String?,
    );
  }
}

class CodexMcpAppPromptArgument {
  const CodexMcpAppPromptArgument({
    required this.name,
    this.description,
    this.required = false,
  });

  final String name;
  final String? description;
  final bool required;

  factory CodexMcpAppPromptArgument.fromJson(Map<String, dynamic> json) {
    return CodexMcpAppPromptArgument(
      name: json['name'] as String? ?? '',
      description: json['description'] as String?,
      required: json['required'] as bool? ?? false,
    );
  }
}

class CodexMcpAppPrompt {
  const CodexMcpAppPrompt({
    required this.name,
    this.title,
    this.description,
    this.arguments = const <CodexMcpAppPromptArgument>[],
  });

  final String name;
  final String? title;
  final String? description;
  final List<CodexMcpAppPromptArgument> arguments;

  factory CodexMcpAppPrompt.fromJson(Map<String, dynamic> json) {
    return CodexMcpAppPrompt(
      name: json['name'] as String? ?? '',
      title: json['title'] as String?,
      description: json['description'] as String?,
      arguments: (json['arguments'] as List<dynamic>? ?? const <dynamic>[])
          .map((item) =>
              CodexMcpAppPromptArgument.fromJson(item as Map<String, dynamic>))
          .toList(),
    );
  }
}

class CodexMcpAppPreview {
  const CodexMcpAppPreview({
    required this.toolName,
    this.arguments = const <String, dynamic>{},
    this.result,
    this.isError = false,
    this.error,
  });

  final String toolName;
  final Map<String, dynamic> arguments;
  final Object? result;
  final bool isError;
  final String? error;

  factory CodexMcpAppPreview.fromJson(Map<String, dynamic> json) {
    return CodexMcpAppPreview(
      toolName: json['tool_name'] as String? ?? '',
      arguments: (json['arguments'] as Map<String, dynamic>?) ??
          const <String, dynamic>{},
      result: json['result'],
      isError: json['is_error'] as bool? ?? false,
      error: json['error'] as String?,
    );
  }
}

class CodexMcpApp {
  const CodexMcpApp({
    required this.appId,
    required this.name,
    required this.description,
    required this.recommendedServerId,
    required this.transport,
    required this.command,
    required this.specPath,
    this.args = const <String>[],
    this.env = const <String, String>{},
    this.tags = const <String>[],
    this.supportsUiExtension = false,
    this.uiEntryUri,
    this.installed = false,
    this.installState = 'missing',
    this.serverPresent = false,
    this.serverPresenceKnown = false,
    this.configMatches,
    this.tools = const <CodexMcpAppTool>[],
    this.resources = const <CodexMcpAppResource>[],
    this.prompts = const <CodexMcpAppPrompt>[],
    this.preview,
    this.driftSummary,
    this.disabledReason,
    this.lookupError,
    this.validationError,
    this.protocolError,
  });

  final String appId;
  final String name;
  final String description;
  final String recommendedServerId;
  final String transport;
  final String command;
  final String specPath;
  final List<String> args;
  final Map<String, String> env;
  final List<String> tags;
  final bool supportsUiExtension;
  final String? uiEntryUri;
  final bool installed;
  final String installState;
  final bool serverPresent;
  final bool serverPresenceKnown;
  final bool? configMatches;
  final List<CodexMcpAppTool> tools;
  final List<CodexMcpAppResource> resources;
  final List<CodexMcpAppPrompt> prompts;
  final CodexMcpAppPreview? preview;
  final String? driftSummary;
  final String? disabledReason;
  final String? lookupError;
  final String? validationError;
  final String? protocolError;

  String get launchSummary =>
      ([command, ...args].where((part) => part.trim().isNotEmpty)).join(' ');

  factory CodexMcpApp.fromJson(Map<String, dynamic> json) {
    return CodexMcpApp(
      appId: json['app_id'] as String? ?? '',
      name: json['name'] as String? ?? '',
      description: json['description'] as String? ?? '',
      recommendedServerId: json['recommended_server_id'] as String? ?? '',
      transport: json['transport'] as String? ?? 'stdio',
      command: json['command'] as String? ?? '',
      specPath: json['spec_path'] as String? ?? '',
      args: (json['args'] as List<dynamic>? ?? const <dynamic>[])
          .map((item) => item as String)
          .toList(),
      env: ((json['env'] as Map<String, dynamic>?) ?? const <String, dynamic>{})
          .map((key, value) => MapEntry(key, value.toString())),
      tags: (json['tags'] as List<dynamic>? ?? const <dynamic>[])
          .map((item) => item as String)
          .toList(),
      supportsUiExtension: json['supports_ui_extension'] as bool? ?? false,
      uiEntryUri: json['ui_entry_uri'] as String?,
      installed: json['installed'] as bool? ?? false,
      installState: json['install_state'] as String? ?? 'missing',
      serverPresent: json['server_present'] as bool? ?? false,
      serverPresenceKnown: json['server_presence_known'] as bool? ?? false,
      configMatches: json['config_matches'] as bool?,
      tools: (json['tools'] as List<dynamic>? ?? const <dynamic>[])
          .map((item) => CodexMcpAppTool.fromJson(item as Map<String, dynamic>))
          .toList(),
      resources: (json['resources'] as List<dynamic>? ?? const <dynamic>[])
          .map((item) =>
              CodexMcpAppResource.fromJson(item as Map<String, dynamic>))
          .toList(),
      prompts: (json['prompts'] as List<dynamic>? ?? const <dynamic>[])
          .map((item) =>
              CodexMcpAppPrompt.fromJson(item as Map<String, dynamic>))
          .toList(),
      preview: json['preview'] is Map<String, dynamic>
          ? CodexMcpAppPreview.fromJson(json['preview'] as Map<String, dynamic>)
          : null,
      driftSummary: json['drift_summary'] as String?,
      disabledReason: json['disabled_reason'] as String?,
      lookupError: json['lookup_error'] as String?,
      validationError: json['validation_error'] as String?,
      protocolError: json['protocol_error'] as String?,
    );
  }
}

class CodexMcpAppInstallResult {
  const CodexMcpAppInstallResult({
    required this.appId,
    required this.serverId,
    required this.alreadyInstalled,
    required this.reconciled,
    required this.command,
    required this.summary,
  });

  final String appId;
  final String serverId;
  final bool alreadyInstalled;
  final bool reconciled;
  final String command;
  final String summary;

  factory CodexMcpAppInstallResult.fromJson(Map<String, dynamic> json) {
    return CodexMcpAppInstallResult(
      appId: json['app_id'] as String? ?? '',
      serverId: json['server_id'] as String? ?? '',
      alreadyInstalled: json['already_installed'] as bool? ?? false,
      reconciled: json['reconciled'] as bool? ?? false,
      command: json['command'] as String? ?? '',
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
    this.usageLabel,
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
  final String? usageLabel;
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
      usageLabel: json['usage_label'] as String?,
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
    this.mcpApps = const <CodexMcpApp>[],
    this.mcpServerInventoryComplete = true,
    this.mcpRawOutput,
    this.mcpError,
    this.configPath,
  });

  final CodexStatus status;
  final List<CodexConfigProfile> profiles;
  final List<CodexSkill> skills;
  final List<CodexMcpServer> mcpServers;
  final List<CodexMcpApp> mcpApps;
  final bool mcpServerInventoryComplete;
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
      mcpApps: (json['mcp_apps'] as List<dynamic>? ?? const <dynamic>[])
          .map((item) => CodexMcpApp.fromJson(item as Map<String, dynamic>))
          .toList(),
      mcpServerInventoryComplete:
          json['mcp_server_inventory_complete'] as bool? ?? true,
      mcpRawOutput: json['mcp_raw_output'] as String?,
      mcpError: json['mcp_error'] as String?,
      configPath: json['config_path'] as String?,
    );
  }
}
