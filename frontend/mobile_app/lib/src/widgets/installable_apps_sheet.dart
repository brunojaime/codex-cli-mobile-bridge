import 'dart:async';

import 'package:codex_app_updater/codex_app_updater.dart';
import 'package:flutter/material.dart';

import '../models/installable_app.dart';
import '../services/api_client.dart';

class InstallableAppsSheet extends StatefulWidget {
  const InstallableAppsSheet({
    super.key,
    required this.apiClient,
    this.updaterController,
  });

  final ApiClient apiClient;
  final CodexAppUpdaterController? updaterController;

  @override
  State<InstallableAppsSheet> createState() => _InstallableAppsSheetState();
}

class _InstallableAppsSheetState extends State<InstallableAppsSheet> {
  late final CodexAppUpdaterController _updaterController =
      widget.updaterController ?? CodexAppUpdaterController();
  late final bool _ownsUpdaterController = widget.updaterController == null;
  late Future<List<InstallableApp>> _appsFuture;
  String? _activeSourceApp;
  String? _statusText;
  String? _errorText;

  @override
  void initState() {
    super.initState();
    _appsFuture = widget.apiClient.listInstallableApps();
    _updaterController.addListener(_handleUpdaterChanged);
  }

  @override
  void dispose() {
    _updaterController.removeListener(_handleUpdaterChanged);
    if (_ownsUpdaterController) {
      _updaterController.dispose();
    }
    super.dispose();
  }

  void _reload() {
    setState(() {
      _errorText = null;
      _statusText = null;
      _appsFuture = widget.apiClient.listInstallableApps();
    });
  }

  void _handleUpdaterChanged() {
    if (!mounted || _activeSourceApp == null) return;
    setState(() {
      _statusText = _statusLabel(_updaterController.status);
      if (_updaterController.status == CodexAppUpdateStatus.failed) {
        _errorText = _failureLabel(_updaterController.failureReason);
      }
    });
  }

  Future<void> _install(InstallableApp app) async {
    final apkUrl = app.apkUrl;
    if (!app.canInstall || apkUrl == null) return;
    setState(() {
      _activeSourceApp = app.sourceApp;
      _statusText = 'Starting download';
      _errorText = null;
    });
    final resolvedApkUrl = _resolveInstallableApkUrl(
      widget.apiClient.baseUrl,
      apkUrl,
    );
    final installed = await _updaterController.installExternalApk(
      apkUrl: resolvedApkUrl,
      sourceApp: app.sourceApp,
      displayName: app.displayName,
      apkAssetName: app.apkAssetName,
      sha256: app.sha256,
      sizeBytes: app.sizeBytes,
    );
    if (!mounted) return;
    setState(() {
      _statusText = installed ? 'Installer opened' : _statusText;
      if (!installed && _errorText == null) {
        _errorText = _failureLabel(_updaterController.failureReason);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.apps_rounded),
                const SizedBox(width: 12),
                const Expanded(
                  child: Text(
                    'Apps',
                    style: TextStyle(fontSize: 22, fontWeight: FontWeight.w700),
                  ),
                ),
                IconButton(
                  tooltip: 'Refresh',
                  onPressed: _reload,
                  icon: const Icon(Icons.refresh_rounded),
                ),
              ],
            ),
            const SizedBox(height: 12),
            FutureBuilder<List<InstallableApp>>(
              future: _appsFuture,
              builder: (context, snapshot) {
                if (snapshot.connectionState != ConnectionState.done) {
                  return const Padding(
                    padding: EdgeInsets.symmetric(vertical: 40),
                    child: Center(child: CircularProgressIndicator()),
                  );
                }
                if (snapshot.hasError) {
                  return _MessagePanel(
                    icon: Icons.error_outline_rounded,
                    text: 'Could not load apps.\n${snapshot.error}',
                  );
                }
                final apps = snapshot.data ?? const <InstallableApp>[];
                if (apps.isEmpty) {
                  return const _MessagePanel(
                    icon: Icons.apps_outage_rounded,
                    text: 'No installable apps',
                  );
                }
                return Flexible(
                  child: ListView.separated(
                    shrinkWrap: true,
                    itemCount: apps.length,
                    separatorBuilder: (_, __) => const SizedBox(height: 10),
                    itemBuilder: (context, index) {
                      final app = apps[index];
                      return _InstallableAppCard(
                        app: app,
                        installing: _activeSourceApp == app.sourceApp &&
                            _updaterController.isActiveOperation,
                        statusText: _activeSourceApp == app.sourceApp
                            ? _statusText
                            : null,
                        errorText: _activeSourceApp == app.sourceApp
                            ? _errorText
                            : null,
                        onInstall: app.canInstall
                            ? () => unawaited(_install(app))
                            : null,
                      );
                    },
                  ),
                );
              },
            ),
          ],
        ),
      ),
    );
  }
}

class _InstallableAppCard extends StatelessWidget {
  const _InstallableAppCard({
    required this.app,
    required this.installing,
    required this.statusText,
    required this.errorText,
    required this.onInstall,
  });

  final InstallableApp app;
  final bool installing;
  final String? statusText;
  final String? errorText;
  final VoidCallback? onInstall;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return DecoratedBox(
      decoration: BoxDecoration(
        color:
            theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.45),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.android_rounded),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        app.title,
                        style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        '${app.versionLabel}  •  ${_statusHintLabel(app)}',
                        style: theme.textTheme.bodySmall,
                      ),
                    ],
                  ),
                ),
                FilledButton.icon(
                  onPressed: installing ? null : onInstall,
                  icon: installing
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.download_rounded),
                  label: Text(app.canInstall ? 'Install' : 'Unavailable'),
                ),
              ],
            ),
            if (app.sizeBytes != null || app.packageId != null) ...[
              const SizedBox(height: 8),
              Text(
                [
                  if (app.sizeBytes != null) _formatBytes(app.sizeBytes!),
                  if (app.packageId != null) app.packageId!,
                ].join('  •  '),
                style: theme.textTheme.bodySmall,
              ),
            ],
            if (statusText != null) ...[
              const SizedBox(height: 8),
              Text(statusText!, style: theme.textTheme.bodySmall),
            ],
            if (errorText != null) ...[
              const SizedBox(height: 8),
              Text(
                errorText!,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.error,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _MessagePanel extends StatelessWidget {
  const _MessagePanel({required this.icon, required this.text});

  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 40),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 36),
            const SizedBox(height: 12),
            Text(text, textAlign: TextAlign.center),
          ],
        ),
      ),
    );
  }
}

String _statusHintLabel(InstallableApp app) {
  if (!app.enabled) return 'Disabled';
  if (app.canInstall) return 'Available';
  return switch (app.installStatusHint) {
    'release_metadata_unavailable' => 'Release metadata unavailable',
    'missing_apk_asset' => 'Missing APK asset',
    'disabled' => 'Disabled',
    _ => 'No release available',
  };
}

Uri _resolveInstallableApkUrl(String bridgeBaseUrl, String apkUrl) {
  final baseUri = Uri.parse(bridgeBaseUrl.trim().replaceAll(RegExp(r'/$'), ''));
  final candidate = Uri.parse(apkUrl.trim());
  if (!candidate.hasScheme) {
    return baseUri.resolve(apkUrl.trim());
  }
  if (_isLoopbackHost(candidate.host) && !_isLoopbackHost(baseUri.host)) {
    return baseUri.replace(
      path: candidate.path,
      query: candidate.hasQuery ? candidate.query : null,
    );
  }
  return candidate;
}

bool _isLoopbackHost(String host) {
  final normalized = host.toLowerCase();
  return normalized == 'localhost' ||
      normalized == '127.0.0.1' ||
      normalized == '0.0.0.0' ||
      normalized == '10.0.2.2' ||
      normalized == '::1';
}

String _statusLabel(CodexAppUpdateStatus status) {
  return switch (status) {
    CodexAppUpdateStatus.downloading => 'Downloading APK',
    CodexAppUpdateStatus.downloaded => 'Downloaded APK',
    CodexAppUpdateStatus.verifying => 'Verifying checksum',
    CodexAppUpdateStatus.readyToInstall => 'Ready to install',
    CodexAppUpdateStatus.installing => 'Opening Android installer',
    CodexAppUpdateStatus.waitingForPermission => 'Android permission required',
    CodexAppUpdateStatus.dismissed => 'Installer opened',
    CodexAppUpdateStatus.failed => 'Install failed',
    _ => 'Preparing install',
  };
}

String _failureLabel(CodexAppUpdateFailureReason? reason) {
  return switch (reason) {
    CodexAppUpdateFailureReason.checksumMismatch => 'Checksum failed',
    CodexAppUpdateFailureReason.downloadFailed => 'Failed download',
    CodexAppUpdateFailureReason.permissionRequired =>
      'Android permission required',
    CodexAppUpdateFailureReason.installerUnavailable => 'Installer unavailable',
    CodexAppUpdateFailureReason.fileMissing => 'Downloaded APK missing',
    CodexAppUpdateFailureReason.securityException => 'Android blocked install',
    _ => 'Install failed',
  };
}

String _formatBytes(int bytes) {
  final mb = bytes / (1024 * 1024);
  if (mb >= 1) return '${mb.toStringAsFixed(1)} MB';
  final kb = bytes / 1024;
  if (kb >= 1) return '${kb.toStringAsFixed(1)} KB';
  return '$bytes B';
}
