import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'checksum.dart';
import 'codex_app_updater_config.dart';
import 'download.dart';
import 'installer.dart';
import 'models.dart';

class CodexAppUpdaterController extends ChangeNotifier {
  CodexAppUpdaterController({
    http.Client? httpClient,
    CodexApkDownloader? downloader,
    CodexChecksumVerifier checksumVerifier = const CodexChecksumVerifier(),
    CodexInstallerLauncher installerLauncher =
        const MethodChannelCodexInstallerLauncher(),
  }) : _httpClient = httpClient ?? http.Client(),
       _ownsHttpClient = httpClient == null,
       _downloader = downloader,
       _checksumVerifier = checksumVerifier,
       _installerLauncher = installerLauncher;

  final http.Client _httpClient;
  final bool _ownsHttpClient;
  final CodexApkDownloader? _downloader;
  final CodexChecksumVerifier _checksumVerifier;
  final CodexInstallerLauncher _installerLauncher;

  CodexAppUpdateStatus status = CodexAppUpdateStatus.idle;
  CodexAppUpdateFailureReason? failureReason;
  CodexAppUpdateInfo? updateInfo;
  String? downloadedApkPath;
  int downloadedBytes = 0;
  int? totalBytes;
  Future<CodexAppUpdateInfo?>? _activeCheck;
  Future<bool>? _activeUpdate;
  String? _activeCheckUri;
  CodexAppUpdaterConfig? _pendingCheckConfig;

  bool get canRetryInstallPreparedApk => _canInstallPreparedApk;

  Future<CodexAppUpdateInfo?> checkForUpdate(CodexAppUpdaterConfig config) {
    if (!config.enabled || config.bridgeUrl.trim().isEmpty) {
      return Future.value(null);
    }
    final requestUri = config.updateUri().toString();
    if (_activeCheck != null) {
      if (_activeCheckUri != requestUri) {
        _pendingCheckConfig = config;
      }
      return _activeCheck!;
    }
    late final Future<CodexAppUpdateInfo?> check;
    check = _checkForUpdate(config).whenComplete(() {
      if (identical(_activeCheck, check)) {
        _activeCheck = null;
        _activeCheckUri = null;
        final pendingConfig = _pendingCheckConfig;
        _pendingCheckConfig = null;
        if (pendingConfig != null) {
          unawaited(checkForUpdate(pendingConfig));
        }
      }
    });
    _activeCheck = check;
    _activeCheckUri = requestUri;
    return check;
  }

  Future<CodexAppUpdateInfo?> _checkForUpdate(
    CodexAppUpdaterConfig config,
  ) async {
    _clearPreparedDownload();
    updateInfo = null;
    _setStatus(CodexAppUpdateStatus.checking);
    try {
      final response = await _httpClient.get(config.updateUri());
      if (response.statusCode < 200 || response.statusCode >= 300) {
        _fail(CodexAppUpdateFailureReason.bridgeUnavailable);
        return null;
      }
      final decoded = jsonDecode(response.body);
      if (decoded is! Map<String, Object?>) {
        _fail(CodexAppUpdateFailureReason.invalidResponse);
        return null;
      }
      final info = CodexAppUpdateInfo.fromJson(decoded);
      updateInfo = info;
      if (!info.available || !_isNewerThanCurrent(config, info)) {
        _setStatus(CodexAppUpdateStatus.upToDate);
      } else if (!info.hasInstallableAsset) {
        _fail(CodexAppUpdateFailureReason.noCompatibleAsset);
      } else if (info.required) {
        _setStatus(CodexAppUpdateStatus.updateRequired);
      } else {
        _setStatus(CodexAppUpdateStatus.updateAvailable);
      }
      return info;
    } on FormatException {
      _fail(CodexAppUpdateFailureReason.invalidResponse);
    } on Object {
      _fail(CodexAppUpdateFailureReason.bridgeUnavailable);
    }
    return null;
  }

  Future<bool> downloadAndPrepare(CodexAppUpdaterConfig config) async {
    final info = updateInfo;
    if (info == null || !info.hasInstallableAsset) {
      _fail(CodexAppUpdateFailureReason.noCompatibleAsset);
      return false;
    }
    final apkUrl = Uri.parse(info.apkUrl!);
    final fileName = info.apkAssetName ?? '${info.sourceApp}.apk';
    _setStatus(CodexAppUpdateStatus.downloading);
    try {
      final downloader = _downloader ?? const PlatformCodexApkDownloader();
      final apkPath = await downloader.download(
        apkUrl,
        fileName: fileName,
        onProgress: (received, total) {
          downloadedBytes = received;
          totalBytes = total;
          notifyListeners();
        },
      );
      downloadedApkPath = apkPath;
      _setStatus(CodexAppUpdateStatus.downloaded);
      _setStatus(CodexAppUpdateStatus.verifying);
      final expectedSha256 = info.sha256?.trim();
      if (expectedSha256 != null && expectedSha256.isNotEmpty) {
        final checksumMatches = await _checksumVerifier.verifySha256(
          apkPath,
          expectedSha256,
        );
        if (!checksumMatches) {
          _fail(CodexAppUpdateFailureReason.checksumMismatch);
          return false;
        }
      } else if (config.requireChecksum) {
        _fail(CodexAppUpdateFailureReason.checksumMismatch);
        return false;
      }
      _setStatus(CodexAppUpdateStatus.readyToInstall);
      return true;
    } on Object {
      _fail(CodexAppUpdateFailureReason.downloadFailed);
      return false;
    }
  }

  Future<bool> installPreparedApk() async {
    final apkPath = downloadedApkPath;
    if (!_canInstallPreparedApk || apkPath == null) {
      _fail(CodexAppUpdateFailureReason.noCompatibleAsset);
      return false;
    }
    _setStatus(CodexAppUpdateStatus.installing);
    final result = await _installerLauncher.launch(apkPath);
    switch (result) {
      case CodexInstallerLaunchResult.installerLaunched:
        _clearPreparedDownload();
        _setStatus(CodexAppUpdateStatus.dismissed);
        return true;
      case CodexInstallerLaunchResult.unknownSourcesPermissionRequired:
        _setWaitingForPermission();
        return false;
      case CodexInstallerLaunchResult.noActivity:
        _fail(CodexAppUpdateFailureReason.installerUnavailable);
        return false;
      case CodexInstallerLaunchResult.fileMissing:
        _clearPreparedDownload();
        _fail(CodexAppUpdateFailureReason.fileMissing);
        return false;
      case CodexInstallerLaunchResult.securityException:
        _fail(CodexAppUpdateFailureReason.securityException);
        return false;
      case CodexInstallerLaunchResult.invalidUri:
        _fail(CodexAppUpdateFailureReason.invalidUri);
        return false;
      case CodexInstallerLaunchResult.cancelledOrUnknown:
        _fail(CodexAppUpdateFailureReason.unknown);
        return false;
    }
  }

  Future<bool> updateNow(CodexAppUpdaterConfig config) {
    if (_activeUpdate != null) return _activeUpdate!;
    late final Future<bool> update;
    update = _updateNow(config).whenComplete(() {
      if (identical(_activeUpdate, update)) {
        _activeUpdate = null;
      }
    });
    _activeUpdate = update;
    return update;
  }

  Future<bool> _updateNow(CodexAppUpdaterConfig config) async {
    if (_canInstallPreparedApk) {
      return installPreparedApk();
    }
    if (_mustRefreshBeforeUpdating) {
      final info = await checkForUpdate(config);
      if (info == null || !info.hasInstallableAsset) {
        return false;
      }
    } else if (_isActiveOperation) {
      return false;
    }
    final prepared = await downloadAndPrepare(config);
    if (!prepared) return false;
    return installPreparedApk();
  }

  void dismiss() {
    if (updateInfo?.required ?? false) return;
    _setStatus(CodexAppUpdateStatus.dismissed);
  }

  @override
  void dispose() {
    if (_ownsHttpClient) _httpClient.close();
    super.dispose();
  }

  void _setStatus(CodexAppUpdateStatus value) {
    status = value;
    failureReason = null;
    notifyListeners();
  }

  void _fail(CodexAppUpdateFailureReason reason) {
    status = CodexAppUpdateStatus.failed;
    failureReason = reason;
    notifyListeners();
  }

  void _setWaitingForPermission() {
    status = CodexAppUpdateStatus.waitingForPermission;
    failureReason = CodexAppUpdateFailureReason.permissionRequired;
    notifyListeners();
  }

  bool get _mustRefreshBeforeUpdating {
    return switch (status) {
      CodexAppUpdateStatus.idle ||
      CodexAppUpdateStatus.upToDate ||
      CodexAppUpdateStatus.dismissed ||
      CodexAppUpdateStatus.failed => true,
      _ => false,
    };
  }

  bool get _isActiveOperation {
    return switch (status) {
      CodexAppUpdateStatus.checking ||
      CodexAppUpdateStatus.downloading ||
      CodexAppUpdateStatus.downloaded ||
      CodexAppUpdateStatus.verifying ||
      CodexAppUpdateStatus.waitingForPermission ||
      CodexAppUpdateStatus.installing => true,
      _ => false,
    };
  }

  bool get _canInstallPreparedApk {
    if (downloadedApkPath == null) return false;
    return switch (status) {
      CodexAppUpdateStatus.readyToInstall ||
      CodexAppUpdateStatus.waitingForPermission => true,
      CodexAppUpdateStatus.failed => switch (failureReason) {
        CodexAppUpdateFailureReason.permissionRequired ||
        CodexAppUpdateFailureReason.installerUnavailable ||
        CodexAppUpdateFailureReason.securityException ||
        CodexAppUpdateFailureReason.invalidUri ||
        CodexAppUpdateFailureReason.unknown => true,
        _ => false,
      },
      _ => false,
    };
  }

  void _clearPreparedDownload() {
    downloadedApkPath = null;
    downloadedBytes = 0;
    totalBytes = null;
  }

  bool _isNewerThanCurrent(
    CodexAppUpdaterConfig config,
    CodexAppUpdateInfo info,
  ) {
    final latestBuild = info.latestBuild;
    if (latestBuild != null) {
      return latestBuild > config.currentBuild;
    }
    return true;
  }
}
