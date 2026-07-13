class ServerHealth {
  const ServerHealth({
    required this.serverName,
    required this.backendMode,
    required this.projectsRoot,
    this.backendVersion,
    this.backendCommit,
    this.features = const <String, bool>{},
    required this.audioTranscriptionBackend,
    required this.audioTranscriptionResolvedBackend,
    required this.audioTranscriptionReady,
    required this.speechSynthesisBackend,
    required this.speechSynthesisReady,
    required this.tailscaleInstalled,
    required this.tailscaleOnline,
    this.audioTranscriptionDetail,
    this.speechSynthesisDetail,
    this.speechSynthesisVoice,
    this.speechSynthesisResponseFormat,
    this.tailscaleTailnetName,
    this.tailscaleDeviceName,
    this.tailscaleMagicDnsName,
    this.tailscaleIpv4,
    this.tailscaleSuggestedUrl,
    this.preferredClientUrl,
    this.publicBaseUrls = const <String>[],
    this.environmentIdentity,
  });

  final String serverName;
  final String backendMode;
  final String projectsRoot;
  final String? backendVersion;
  final String? backendCommit;
  final Map<String, bool> features;
  final String audioTranscriptionBackend;
  final String audioTranscriptionResolvedBackend;
  final bool audioTranscriptionReady;
  final String? audioTranscriptionDetail;
  final String speechSynthesisBackend;
  final bool speechSynthesisReady;
  final String? speechSynthesisDetail;
  final String? speechSynthesisVoice;
  final String? speechSynthesisResponseFormat;
  final bool tailscaleInstalled;
  final bool tailscaleOnline;
  final String? tailscaleTailnetName;
  final String? tailscaleDeviceName;
  final String? tailscaleMagicDnsName;
  final String? tailscaleIpv4;
  final String? tailscaleSuggestedUrl;
  final String? preferredClientUrl;
  final List<String> publicBaseUrls;
  final BridgeEnvironmentIdentity? environmentIdentity;

  factory ServerHealth.fromJson(Map<String, dynamic> json) {
    return ServerHealth(
      serverName: json['server_name'] as String,
      backendMode: json['backend_mode'] as String,
      projectsRoot: json['projects_root'] as String,
      backendVersion: json['backend_version'] as String?,
      backendCommit: json['backend_commit'] as String?,
      features: _boolMapFromJson(json['features']),
      audioTranscriptionBackend:
          json['audio_transcription_backend'] as String? ?? 'auto',
      audioTranscriptionResolvedBackend:
          json['audio_transcription_resolved_backend'] as String? ?? 'unknown',
      audioTranscriptionReady:
          json['audio_transcription_ready'] as bool? ?? false,
      audioTranscriptionDetail: json['audio_transcription_detail'] as String?,
      speechSynthesisBackend:
          json['speech_synthesis_backend'] as String? ?? 'disabled',
      speechSynthesisReady: json['speech_synthesis_ready'] as bool? ?? false,
      speechSynthesisDetail: json['speech_synthesis_detail'] as String?,
      speechSynthesisVoice: json['speech_synthesis_voice'] as String?,
      speechSynthesisResponseFormat:
          json['speech_synthesis_response_format'] as String?,
      tailscaleInstalled: json['tailscale_installed'] as bool? ?? false,
      tailscaleOnline: json['tailscale_online'] as bool? ?? false,
      tailscaleTailnetName: json['tailscale_tailnet_name'] as String?,
      tailscaleDeviceName: json['tailscale_device_name'] as String?,
      tailscaleMagicDnsName: json['tailscale_magic_dns_name'] as String?,
      tailscaleIpv4: json['tailscale_ipv4'] as String?,
      tailscaleSuggestedUrl: json['tailscale_suggested_url'] as String?,
      preferredClientUrl: json['preferred_client_url'] as String?,
      publicBaseUrls: _stringListFromJson(json['public_base_urls']),
      environmentIdentity: json['environment_identity'] is Map<String, dynamic>
          ? BridgeEnvironmentIdentity.fromJson(
              json['environment_identity'] as Map<String, dynamic>,
            )
          : null,
    );
  }

  static List<String> _stringListFromJson(Object? value) {
    if (value is! List) return const <String>[];
    return value
        .map((item) => item?.toString() ?? '')
        .where((item) => item.trim().isNotEmpty)
        .toList(growable: false);
  }

  static Map<String, bool> _boolMapFromJson(Object? value) {
    if (value is! Map) return const <String, bool>{};
    return value.map(
      (key, raw) => MapEntry(key.toString(), raw == true),
    )..removeWhere((key, _) => key.trim().isEmpty);
  }
}

class BridgeEnvironmentIdentity {
  const BridgeEnvironmentIdentity({
    required this.environment,
    required this.mode,
    this.stageId,
    this.specId,
    this.branch,
    this.worktreePath,
    required this.backendUrl,
    required this.appChannel,
    required this.appLabel,
    required this.updaterChannel,
    required this.color,
    this.stageRuntime,
    this.allowedCapabilities = const <String>[],
    this.deniedCapabilities = const <String>[],
  });

  final String environment;
  final String mode;
  final String? stageId;
  final String? specId;
  final String? branch;
  final String? worktreePath;
  final String backendUrl;
  final String appChannel;
  final String appLabel;
  final String updaterChannel;
  final String color;
  final BridgeStageRuntime? stageRuntime;
  final List<String> allowedCapabilities;
  final List<String> deniedCapabilities;

  bool get canEnqueueDevHandoff =>
      environment == 'prod' &&
      allowedCapabilities.contains('enqueue_dev_handoff') &&
      !deniedCapabilities.contains('enqueue_dev_handoff');

  String get displayLabel {
    final upperEnvironment = environment.toUpperCase();
    if (environment == 'dev' && stageId != null && branch != null) {
      return '$upperEnvironment - $stageId - $branch';
    }
    return '$upperEnvironment - $appChannel';
  }

  factory BridgeEnvironmentIdentity.fromJson(Map<String, dynamic> json) {
    return BridgeEnvironmentIdentity(
      environment: json['environment'] as String? ?? 'prod',
      mode: json['mode'] as String? ?? 'normal',
      stageId: json['stage_id'] as String?,
      specId: json['spec_id'] as String?,
      branch: json['branch'] as String?,
      worktreePath: json['worktree_path'] as String?,
      backendUrl: json['backend_url'] as String? ?? '',
      appChannel: json['app_channel'] as String? ?? 'prod',
      appLabel: json['app_label'] as String? ?? 'Codex Mobile Bridge',
      updaterChannel: json['updater_channel'] as String? ?? 'prod',
      color: json['color'] as String? ?? '#2563EB',
      stageRuntime: json['stage_runtime'] is Map<String, dynamic>
          ? BridgeStageRuntime.fromJson(
              json['stage_runtime'] as Map<String, dynamic>,
            )
          : null,
      allowedCapabilities: ServerHealth._stringListFromJson(
        json['allowed_capabilities'],
      ),
      deniedCapabilities: ServerHealth._stringListFromJson(
        json['denied_capabilities'],
      ),
    );
  }
}

class BridgeStageRuntime {
  const BridgeStageRuntime({
    this.url,
    this.port,
    this.health,
    this.lastRestartAt,
    this.lastHealthcheckAt,
  });

  final String? url;
  final int? port;
  final String? health;
  final String? lastRestartAt;
  final String? lastHealthcheckAt;

  factory BridgeStageRuntime.fromJson(Map<String, dynamic> json) {
    return BridgeStageRuntime(
      url: json['url'] as String?,
      port: json['port'] is int
          ? json['port'] as int
          : int.tryParse('${json['port'] ?? ''}'),
      health: json['health'] as String?,
      lastRestartAt: json['last_restart_at'] as String?,
      lastHealthcheckAt: json['last_healthcheck_at'] as String?,
    );
  }
}
