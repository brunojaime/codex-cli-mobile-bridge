class InstallableApp {
  const InstallableApp({
    required this.sourceApp,
    required this.displayName,
    required this.repo,
    required this.releaseChannel,
    required this.available,
    required this.enabled,
    required this.installStatusHint,
    this.latestVersion,
    this.latestBuild,
    this.releaseTag,
    this.apkUrl,
    this.apkAssetName,
    this.sizeBytes,
    this.sha256,
    this.packageId,
  });

  factory InstallableApp.fromJson(Map<String, dynamic> json) {
    return InstallableApp(
      sourceApp: json['sourceApp'] as String? ?? '',
      displayName: json['displayName'] as String? ?? '',
      repo: json['repo'] as String? ?? '',
      releaseChannel: json['releaseChannel'] as String? ?? 'stable',
      latestVersion: json['latestVersion'] as String?,
      latestBuild: _intOrNull(json['latestBuild']),
      releaseTag: json['releaseTag'] as String?,
      apkUrl: json['apkUrl'] as String?,
      apkAssetName: json['apkAssetName'] as String?,
      sizeBytes: _intOrNull(json['sizeBytes']),
      sha256: json['sha256'] as String?,
      available: json['available'] as bool? ?? false,
      enabled: json['enabled'] as bool? ?? false,
      packageId: json['packageId'] as String?,
      installStatusHint:
          json['installStatusHint'] as String? ?? 'no_release_available',
    );
  }

  final String sourceApp;
  final String displayName;
  final String repo;
  final String releaseChannel;
  final String? latestVersion;
  final int? latestBuild;
  final String? releaseTag;
  final String? apkUrl;
  final String? apkAssetName;
  final int? sizeBytes;
  final String? sha256;
  final bool available;
  final bool enabled;
  final String? packageId;
  final String installStatusHint;

  bool get canInstall =>
      enabled && available && apkUrl != null && apkUrl!.trim().isNotEmpty;

  String get title => displayName.trim().isEmpty ? sourceApp : displayName;

  String get versionLabel {
    final version = latestVersion;
    final build = latestBuild;
    if (version != null && build != null) return '$version+$build';
    if (version != null) return version;
    if (build != null) return 'build $build';
    return 'No release';
  }
}

int? _intOrNull(Object? value) {
  if (value is int) return value;
  if (value is String) return int.tryParse(value);
  return null;
}
