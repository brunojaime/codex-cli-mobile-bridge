enum CodexAppUpdateStatus {
  idle,
  checking,
  upToDate,
  updateAvailable,
  updateRequired,
  downloading,
  downloaded,
  verifying,
  readyToInstall,
  waitingForPermission,
  installing,
  dismissed,
  failed,
}

enum CodexAppUpdateFailureReason {
  bridgeUnavailable,
  invalidResponse,
  noCompatibleAsset,
  downloadFailed,
  checksumMismatch,
  permissionRequired,
  fileMissing,
  securityException,
  invalidUri,
  installerUnavailable,
  unknown,
}

class CodexAppUpdateInfo {
  const CodexAppUpdateInfo({
    required this.sourceApp,
    required this.platform,
    required this.available,
    required this.required,
    this.displayName,
    this.currentVersion,
    this.currentBuild,
    this.latestVersion,
    this.latestBuild,
    this.releaseTag,
    this.releaseUrl,
    this.apkUrl,
    this.apkAssetName,
    this.sha256,
    this.sizeBytes,
    this.releaseNotes,
  });

  factory CodexAppUpdateInfo.fromJson(Map<String, Object?> json) {
    if (json['kind'] != 'codex.appUpdate' || json['version'] != 1) {
      throw const FormatException('Invalid app update response.');
    }
    final sourceApp = json['sourceApp'];
    final platform = json['platform'];
    final available = json['available'];
    final required = json['required'];
    if (sourceApp is! String ||
        platform is! String ||
        available is! bool ||
        required is! bool) {
      throw const FormatException('Missing required app update fields.');
    }
    return CodexAppUpdateInfo(
      sourceApp: sourceApp,
      displayName: _stringOrNull(json['displayName']),
      platform: platform,
      currentVersion: _stringOrNull(json['currentVersion']),
      currentBuild: _intOrNull(json['currentBuild']),
      latestVersion: _stringOrNull(json['latestVersion']),
      latestBuild: _intOrNull(json['latestBuild']),
      releaseTag: _stringOrNull(json['releaseTag']),
      releaseUrl: _stringOrNull(json['releaseUrl']),
      apkUrl: _stringOrNull(json['apkUrl']),
      apkAssetName: _stringOrNull(json['apkAssetName']),
      sha256: _stringOrNull(json['sha256']),
      sizeBytes: _intOrNull(json['sizeBytes']),
      releaseNotes: _stringOrNull(json['releaseNotes']),
      required: required,
      available: available,
    );
  }

  final String sourceApp;
  final String? displayName;
  final String platform;
  final String? currentVersion;
  final int? currentBuild;
  final String? latestVersion;
  final int? latestBuild;
  final String? releaseTag;
  final String? releaseUrl;
  final String? apkUrl;
  final String? apkAssetName;
  final String? sha256;
  final int? sizeBytes;
  final String? releaseNotes;
  final bool required;
  final bool available;

  bool get hasInstallableAsset =>
      available && apkUrl != null && apkUrl!.trim().isNotEmpty;
}

String? _stringOrNull(Object? value) => value is String ? value : null;

int? _intOrNull(Object? value) {
  if (value is int) return value;
  if (value is String) return int.tryParse(value);
  return null;
}
