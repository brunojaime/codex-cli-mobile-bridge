class CodexAppUpdaterConfig {
  const CodexAppUpdaterConfig({
    required this.sourceApp,
    required this.bridgeUrl,
    required this.currentVersion,
    required this.currentBuild,
    this.platform = 'android',
    this.channel = 'stable',
    this.enabled = true,
    this.requireChecksum = false,
  });

  final String sourceApp;
  final String bridgeUrl;
  final String currentVersion;
  final int currentBuild;
  final String platform;
  final String channel;
  final bool enabled;
  final bool requireChecksum;

  Uri updateUri() {
    final base = Uri.parse(_trimTrailingSlash(bridgeUrl));
    final path = '${base.path}/app-updates/$sourceApp'.replaceAll('//', '/');
    return base.replace(
      path: path,
      queryParameters: {
        'platform': platform,
        'currentVersion': currentVersion,
        'currentBuild': currentBuild.toString(),
        'channel': channel,
      },
    );
  }
}

String _trimTrailingSlash(String value) =>
    value.endsWith('/') ? value.substring(0, value.length - 1) : value;
