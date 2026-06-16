import 'package:flutter/material.dart';

import 'codex_app_updater_config.dart';
import 'codex_app_updater_controller.dart';
import 'models.dart';

const codexAppUpdaterBannerKey = Key('codex-app-updater-banner');
const codexAppUpdaterUpdateButtonKey = Key('codex-app-updater-update-button');
const codexAppUpdaterLaterButtonKey = Key('codex-app-updater-later-button');

class CodexAppUpdater extends StatefulWidget {
  const CodexAppUpdater({
    required this.config,
    required this.child,
    this.controller,
    this.checkOnStart = true,
    this.checkOnResume = true,
    super.key,
  });

  final CodexAppUpdaterConfig config;
  final Widget child;
  final CodexAppUpdaterController? controller;
  final bool checkOnStart;
  final bool checkOnResume;

  @override
  State<CodexAppUpdater> createState() => _CodexAppUpdaterState();
}

class _CodexAppUpdaterState extends State<CodexAppUpdater>
    with WidgetsBindingObserver {
  late final CodexAppUpdaterController _controller =
      widget.controller ?? CodexAppUpdaterController();

  bool get _ownsController => widget.controller == null;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    if (widget.checkOnStart) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _controller.checkForUpdate(widget.config);
      });
    }
  }

  @override
  void didUpdateWidget(CodexAppUpdater oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.config != widget.config && widget.checkOnStart) {
      _controller.checkForUpdate(widget.config);
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    if (_ownsController) _controller.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && widget.checkOnResume) {
      _controller.checkForUpdate(widget.config);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.config.enabled) return widget.child;
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) {
        return Stack(
          children: [
            widget.child,
            if (_shouldShowBanner(_controller.status))
              Align(
                alignment: Alignment.topCenter,
                child: SafeArea(
                  child: _CodexAppUpdateBanner(
                    controller: _controller,
                    config: widget.config,
                  ),
                ),
              ),
          ],
        );
      },
    );
  }

  bool _shouldShowBanner(CodexAppUpdateStatus status) {
    return switch (status) {
      CodexAppUpdateStatus.updateAvailable ||
      CodexAppUpdateStatus.updateRequired ||
      CodexAppUpdateStatus.downloading ||
      CodexAppUpdateStatus.downloaded ||
      CodexAppUpdateStatus.verifying ||
      CodexAppUpdateStatus.readyToInstall ||
      CodexAppUpdateStatus.waitingForPermission ||
      CodexAppUpdateStatus.installing ||
      CodexAppUpdateStatus.failed => true,
      _ => false,
    };
  }
}

class _CodexAppUpdateBanner extends StatelessWidget {
  const _CodexAppUpdateBanner({required this.controller, required this.config});

  final CodexAppUpdaterController controller;
  final CodexAppUpdaterConfig config;

  @override
  Widget build(BuildContext context) {
    final info = controller.updateInfo;
    final theme = Theme.of(context);
    final status = controller.status;
    final title = _titleFor(status);
    final subtitle = _subtitleFor(
      status,
      info,
      controller.failureReason,
      controller,
    );
    final isError = status == CodexAppUpdateStatus.failed;
    final isBusy = _isBusy(status);
    final accentColor = isError
        ? theme.colorScheme.error
        : theme.colorScheme.primary;
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
      child: Material(
        key: codexAppUpdaterBannerKey,
        color: theme.colorScheme.surface,
        elevation: 10,
        shadowColor: theme.colorScheme.shadow.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(8),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 560),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Container(
                  width: 34,
                  height: 34,
                  decoration: BoxDecoration(
                    color: accentColor.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Icon(
                    isError
                        ? Icons.error_outline
                        : isBusy
                        ? Icons.downloading_rounded
                        : Icons.system_update_alt_rounded,
                    color: accentColor,
                    size: 20,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: theme.textTheme.titleSmall?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      if (subtitle != null) ...[
                        const SizedBox(height: 3),
                        Text(
                          subtitle,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: theme.colorScheme.onSurfaceVariant,
                          ),
                        ),
                      ],
                      if (isBusy) ...[
                        const SizedBox(height: 8),
                        ClipRRect(
                          borderRadius: BorderRadius.circular(999),
                          child: LinearProgressIndicator(
                            minHeight: 3,
                            value: _downloadProgress(controller),
                            backgroundColor: accentColor.withValues(
                              alpha: 0.14,
                            ),
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                _Actions(controller: controller, config: config),
              ],
            ),
          ),
        ),
      ),
    );
  }

  String _titleFor(CodexAppUpdateStatus status) {
    return switch (status) {
      CodexAppUpdateStatus.updateRequired => 'Actualización requerida',
      CodexAppUpdateStatus.downloading => 'Descargando actualización',
      CodexAppUpdateStatus.downloaded ||
      CodexAppUpdateStatus.verifying => 'Verificando actualización',
      CodexAppUpdateStatus.readyToInstall => 'Lista para instalar',
      CodexAppUpdateStatus.waitingForPermission => 'Permiso requerido',
      CodexAppUpdateStatus.installing => 'Instalador listo',
      CodexAppUpdateStatus.failed => 'No se pudo actualizar',
      _ => 'Actualización disponible',
    };
  }

  String? _subtitleFor(
    CodexAppUpdateStatus status,
    CodexAppUpdateInfo? info,
    CodexAppUpdateFailureReason? failure,
    CodexAppUpdaterController controller,
  ) {
    if (status == CodexAppUpdateStatus.failed) {
      return switch (failure) {
        CodexAppUpdateFailureReason.bridgeUnavailable =>
          'No pudimos consultar la nueva versión.',
        CodexAppUpdateFailureReason.invalidResponse =>
          'La información de actualización no se pudo leer.',
        CodexAppUpdateFailureReason.noCompatibleAsset =>
          'No hay una versión compatible para este dispositivo.',
        CodexAppUpdateFailureReason.downloadFailed =>
          'La descarga no se completó.',
        CodexAppUpdateFailureReason.checksumMismatch =>
          'La descarga no pasó la verificación.',
        CodexAppUpdateFailureReason.permissionRequired =>
          'Android necesita permiso para continuar.',
        CodexAppUpdateFailureReason.fileMissing =>
          'La descarga ya no está disponible.',
        CodexAppUpdateFailureReason.securityException =>
          'Android bloqueó el instalador.',
        CodexAppUpdateFailureReason.invalidUri =>
          'No se pudo preparar la instalación.',
        CodexAppUpdateFailureReason.installerUnavailable =>
          'No se pudo abrir el instalador.',
        _ => 'Intentemos nuevamente en un momento.',
      };
    }
    if (info == null) return null;
    final latest = _versionLabel(info.latestVersion, info.latestBuild);
    if (status == CodexAppUpdateStatus.waitingForPermission) {
      return 'Habilitá el permiso y tocá Instalar para seguir.';
    }
    if (status == CodexAppUpdateStatus.downloading) {
      return _downloadLabel(controller);
    }
    if (status == CodexAppUpdateStatus.downloaded ||
        status == CodexAppUpdateStatus.verifying) {
      return 'Estamos preparando todo para instalar.';
    }
    if (status == CodexAppUpdateStatus.readyToInstall) {
      return 'La descarga ya está lista.';
    }
    if (status == CodexAppUpdateStatus.installing) {
      return 'Seguí los pasos de Android para terminar.';
    }
    if (latest == null) return 'Hay una nueva versión lista para instalar.';
    return 'Versión $latest lista para instalar.';
  }

  String? _versionLabel(String? version, int? build) {
    if ((version == null || version.isEmpty) && build == null) return null;
    if (build == null) return version;
    if (version == null || version.isEmpty) return 'build $build';
    return '$version ($build)';
  }

  bool _isBusy(CodexAppUpdateStatus status) {
    return switch (status) {
      CodexAppUpdateStatus.downloading ||
      CodexAppUpdateStatus.downloaded ||
      CodexAppUpdateStatus.verifying ||
      CodexAppUpdateStatus.installing => true,
      _ => false,
    };
  }

  double? _downloadProgress(CodexAppUpdaterController controller) {
    final total = controller.totalBytes;
    if (controller.status != CodexAppUpdateStatus.downloading ||
        total == null ||
        total <= 0) {
      return null;
    }
    return (controller.downloadedBytes / total).clamp(0, 1).toDouble();
  }

  String _downloadLabel(CodexAppUpdaterController controller) {
    final total = controller.totalBytes;
    if (total == null || total <= 0) return 'Preparando la descarga...';
    return 'Descargando ${_formatBytes(controller.downloadedBytes)} de ${_formatBytes(total)}.';
  }

  String _formatBytes(int bytes) {
    if (bytes >= 1024 * 1024) {
      return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
    }
    if (bytes >= 1024) {
      return '${(bytes / 1024).toStringAsFixed(0)} KB';
    }
    return '$bytes B';
  }
}

class _Actions extends StatelessWidget {
  const _Actions({required this.controller, required this.config});

  final CodexAppUpdaterController controller;
  final CodexAppUpdaterConfig config;

  @override
  Widget build(BuildContext context) {
    final status = controller.status;
    final canInstall = controller.canRetryInstallPreparedApk;
    final busy =
        status == CodexAppUpdateStatus.checking ||
        status == CodexAppUpdateStatus.downloading ||
        status == CodexAppUpdateStatus.downloaded ||
        status == CodexAppUpdateStatus.verifying ||
        status == CodexAppUpdateStatus.installing;
    final info = controller.updateInfo;
    if (busy) {
      return const SizedBox.shrink();
    }
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      alignment: WrapAlignment.end,
      children: [
        if (status == CodexAppUpdateStatus.updateAvailable &&
            !(info?.required ?? false))
          TextButton(
            key: codexAppUpdaterLaterButtonKey,
            onPressed: controller.dismiss,
            child: const Text('Luego'),
          ),
        FilledButton(
          key: codexAppUpdaterUpdateButtonKey,
          onPressed: busy
              ? null
              : () {
                  if (canInstall) {
                    controller.installPreparedApk();
                  } else {
                    controller.updateNow(config);
                  }
                },
          child: Text(canInstall ? 'Instalar' : 'Actualizar'),
        ),
      ],
    );
  }
}
