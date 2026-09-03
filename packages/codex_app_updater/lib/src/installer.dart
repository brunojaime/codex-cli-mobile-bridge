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
  Future<CodexInstallerLaunchOutcome> launch(String apkPath);
}

class CodexInstallerLaunchOutcome {
  const CodexInstallerLaunchOutcome(this.result, {this.message});

  final CodexInstallerLaunchResult result;
  final String? message;
}

class MethodChannelCodexInstallerLauncher implements CodexInstallerLauncher {
  const MethodChannelCodexInstallerLauncher({
    MethodChannel channel = const MethodChannel('codex_app_updater/installer'),
  }) : _channel = channel;

  final MethodChannel _channel;

  @override
  Future<CodexInstallerLaunchOutcome> launch(String apkPath) async {
    try {
      final result = await _channel.invokeMethod<Object?>('launchInstaller', {
        'apkPath': apkPath,
      });
      return _launchOutcomeFromPlatform(result);
    } on MissingPluginException {
      return const CodexInstallerLaunchOutcome(
        CodexInstallerLaunchResult.noActivity,
        message: 'El complemento del instalador no está disponible.',
      );
    } on PlatformException catch (error) {
      return CodexInstallerLaunchOutcome(
        _launchResultFromCode(error.code),
        message: error.message,
      );
    }
  }
}

CodexInstallerLaunchOutcome _launchOutcomeFromPlatform(Object? value) {
  if (value is String) {
    return CodexInstallerLaunchOutcome(_launchResultFromCode(value));
  }
  if (value is Map) {
    return CodexInstallerLaunchOutcome(
      _launchResultFromCode(value['status'] as String?),
      message: value['message'] as String?,
    );
  }
  return const CodexInstallerLaunchOutcome(
    CodexInstallerLaunchResult.cancelledOrUnknown,
  );
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
