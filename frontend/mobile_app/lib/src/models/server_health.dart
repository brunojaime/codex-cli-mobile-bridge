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
