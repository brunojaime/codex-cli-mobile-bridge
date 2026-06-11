import 'package:flutter/services.dart';

enum CodexInstallerLaunchResult {
  installerLaunched,
  unknownSourcesPermissionRequired,
  noActivity,
  fileMissing,
  securityException,
  invalidUri,
  cancelledOrUnknown,
}

abstract class CodexInstallerLauncher {
  Future<CodexInstallerLaunchResult> launch(String apkPath);
}

class MethodChannelCodexInstallerLauncher implements CodexInstallerLauncher {
  const MethodChannelCodexInstallerLauncher({
    MethodChannel channel = const MethodChannel('codex_app_updater/installer'),
  }) : _channel = channel;

  final MethodChannel _channel;

  @override
  Future<CodexInstallerLaunchResult> launch(String apkPath) async {
    try {
      final result = await _channel.invokeMethod<Object?>('launchInstaller', {
        'apkPath': apkPath,
      });
      return _launchResultFromPlatform(result);
    } on MissingPluginException {
      return CodexInstallerLaunchResult.noActivity;
    } on PlatformException catch (error) {
      return _launchResultFromCode(error.code);
    }
  }
}

CodexInstallerLaunchResult _launchResultFromPlatform(Object? value) {
  if (value is String) {
    return _launchResultFromCode(value);
  }
  if (value is Map) {
    return _launchResultFromCode(value['status'] as String?);
  }
  return CodexInstallerLaunchResult.cancelledOrUnknown;
}

CodexInstallerLaunchResult _launchResultFromCode(String? code) {
  return switch (code) {
    'installerLaunched' ||
    'launched' => CodexInstallerLaunchResult.installerLaunched,
    'unknownSourcesPermissionRequired' || 'permissionRequired' =>
      CodexInstallerLaunchResult.unknownSourcesPermissionRequired,
    'noActivity' ||
    'installerUnavailable' => CodexInstallerLaunchResult.noActivity,
    'fileMissing' || 'invalidPath' => CodexInstallerLaunchResult.fileMissing,
    'securityException' => CodexInstallerLaunchResult.securityException,
    'invalidUri' => CodexInstallerLaunchResult.invalidUri,
    _ => CodexInstallerLaunchResult.cancelledOrUnknown,
  };
}
