class ServerHealth {
  const ServerHealth({
    required this.serverName,
    required this.backendMode,
    required this.projectsRoot,
    required this.audioTranscriptionBackend,
    required this.audioTranscriptionResolvedBackend,
    required this.audioTranscriptionReady,
    required this.tailscaleInstalled,
    required this.tailscaleOnline,
    this.audioTranscriptionDetail,
    this.tailscaleTailnetName,
    this.tailscaleDeviceName,
    this.tailscaleMagicDnsName,
    this.tailscaleIpv4,
    this.tailscaleSuggestedUrl,
  });

  final String serverName;
  final String backendMode;
  final String projectsRoot;
  final String audioTranscriptionBackend;
  final String audioTranscriptionResolvedBackend;
  final bool audioTranscriptionReady;
  final String? audioTranscriptionDetail;
  final bool tailscaleInstalled;
  final bool tailscaleOnline;
  final String? tailscaleTailnetName;
  final String? tailscaleDeviceName;
  final String? tailscaleMagicDnsName;
  final String? tailscaleIpv4;
  final String? tailscaleSuggestedUrl;

  factory ServerHealth.fromJson(Map<String, dynamic> json) {
    return ServerHealth(
      serverName: json['server_name'] as String,
      backendMode: json['backend_mode'] as String,
      projectsRoot: json['projects_root'] as String,
      audioTranscriptionBackend: json['audio_transcription_backend'] as String? ?? 'auto',
      audioTranscriptionResolvedBackend:
          json['audio_transcription_resolved_backend'] as String? ?? 'unknown',
      audioTranscriptionReady: json['audio_transcription_ready'] as bool? ?? false,
      audioTranscriptionDetail: json['audio_transcription_detail'] as String?,
      tailscaleInstalled: json['tailscale_installed'] as bool? ?? false,
      tailscaleOnline: json['tailscale_online'] as bool? ?? false,
      tailscaleTailnetName: json['tailscale_tailnet_name'] as String?,
      tailscaleDeviceName: json['tailscale_device_name'] as String?,
      tailscaleMagicDnsName: json['tailscale_magic_dns_name'] as String?,
      tailscaleIpv4: json['tailscale_ipv4'] as String?,
      tailscaleSuggestedUrl: json['tailscale_suggested_url'] as String?,
    );
  }
}
