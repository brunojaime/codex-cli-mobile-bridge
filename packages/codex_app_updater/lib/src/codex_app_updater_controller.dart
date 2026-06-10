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

  Future<CodexAppUpdateInfo?> checkForUpdate(
    CodexAppUpdaterConfig config,
  ) async {
    if (!config.enabled || config.bridgeUrl.trim().isEmpty) {
      return null;
    }
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
      if (!info.available) {
        _setStatus(CodexAppUpdateStatus.upToDate);
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
      final downloader = _downloader ?? HttpCodexApkDownloader();
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
    if (status != CodexAppUpdateStatus.readyToInstall || apkPath == null) {
      _fail(CodexAppUpdateFailureReason.noCompatibleAsset);
      return false;
    }
    _setStatus(CodexAppUpdateStatus.installing);
    final result = await _installerLauncher.launch(apkPath);
    switch (result) {
      case CodexInstallerLaunchResult.launched:
        return true;
      case CodexInstallerLaunchResult.permissionRequired:
        _fail(CodexAppUpdateFailureReason.permissionRequired);
        return false;
      case CodexInstallerLaunchResult.unavailable:
        _fail(CodexAppUpdateFailureReason.installerUnavailable);
        return false;
    }
  }

  Future<bool> updateNow(CodexAppUpdaterConfig config) async {
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
}
