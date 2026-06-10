import 'package:flutter/services.dart';

enum CodexInstallerLaunchResult { launched, permissionRequired, unavailable }

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
      final result = await _channel.invokeMethod<String>('launchInstaller', {
        'apkPath': apkPath,
      });
      return switch (result) {
        'launched' => CodexInstallerLaunchResult.launched,
        'permissionRequired' => CodexInstallerLaunchResult.permissionRequired,
        _ => CodexInstallerLaunchResult.unavailable,
      };
    } on MissingPluginException {
      return CodexInstallerLaunchResult.unavailable;
    } on PlatformException catch (error) {
      if (error.code == 'permissionRequired') {
        return CodexInstallerLaunchResult.permissionRequired;
      }
      return CodexInstallerLaunchResult.unavailable;
    }
  }
}
