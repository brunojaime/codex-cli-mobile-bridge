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
    final title = _titleFor(status, info);
    final subtitle = _subtitleFor(status, info, controller.failureReason);
    return Material(
      key: codexAppUpdaterBannerKey,
      color: theme.colorScheme.surface,
      elevation: 8,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 720),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(
                status == CodexAppUpdateStatus.failed
                    ? Icons.error_outline
                    : Icons.system_update_alt,
                color: status == CodexAppUpdateStatus.failed
                    ? theme.colorScheme.error
                    : theme.colorScheme.primary,
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(title, style: theme.textTheme.titleSmall),
                    if (subtitle != null) ...[
                      const SizedBox(height: 4),
                      Text(subtitle, style: theme.textTheme.bodySmall),
                    ],
                    if ((info?.releaseNotes ?? '').isNotEmpty) ...[
                      const SizedBox(height: 6),
                      Text(
                        info!.releaseNotes!,
                        maxLines: 3,
                        overflow: TextOverflow.ellipsis,
                        style: theme.textTheme.bodySmall,
                      ),
                    ],
                  ],
                ),
              ),
              const SizedBox(width: 12),
              _Actions(controller: controller, config: config),
            ],
          ),
        ),
      ),
    );
  }

  String _titleFor(CodexAppUpdateStatus status, CodexAppUpdateInfo? info) {
    final name = info?.displayName ?? info?.sourceApp ?? 'App';
    return switch (status) {
      CodexAppUpdateStatus.updateRequired => 'Actualizacion requerida',
      CodexAppUpdateStatus.downloading => 'Descargando actualizacion',
      CodexAppUpdateStatus.downloaded ||
      CodexAppUpdateStatus.verifying => 'Verificando actualizacion',
      CodexAppUpdateStatus.readyToInstall => 'Lista para instalar',
      CodexAppUpdateStatus.waitingForPermission => 'Permiso requerido',
      CodexAppUpdateStatus.installing => 'Abriendo instalador',
      CodexAppUpdateStatus.failed => 'No se pudo actualizar',
      _ => 'Actualizacion disponible para $name',
    };
  }

  String? _subtitleFor(
    CodexAppUpdateStatus status,
    CodexAppUpdateInfo? info,
    CodexAppUpdateFailureReason? failure,
  ) {
    if (status == CodexAppUpdateStatus.failed) {
      return switch (failure) {
        CodexAppUpdateFailureReason.bridgeUnavailable =>
          'El Bridge no esta disponible.',
        CodexAppUpdateFailureReason.invalidResponse =>
          'El Bridge devolvio una respuesta invalida.',
        CodexAppUpdateFailureReason.noCompatibleAsset =>
          'No hay un APK compatible para instalar.',
        CodexAppUpdateFailureReason.downloadFailed => 'La descarga fallo.',
        CodexAppUpdateFailureReason.checksumMismatch =>
          'La verificacion SHA-256 fallo.',
        CodexAppUpdateFailureReason.permissionRequired =>
          'Android requiere permiso para instalar apps desconocidas.',
        CodexAppUpdateFailureReason.fileMissing =>
          'El APK descargado ya no esta disponible.',
        CodexAppUpdateFailureReason.securityException =>
          'Android bloqueo el instalador por seguridad.',
        CodexAppUpdateFailureReason.invalidUri =>
          'No se pudo preparar el APK para Android.',
        CodexAppUpdateFailureReason.installerUnavailable =>
          'No se pudo abrir el instalador Android.',
        _ => 'Ocurrio un error inesperado.',
      };
    }
    if (info == null) return null;
    final current = _versionLabel(info.currentVersion, info.currentBuild);
    final latest = _versionLabel(info.latestVersion, info.latestBuild);
    if (current == null && latest == null) return null;
    if (status == CodexAppUpdateStatus.waitingForPermission) {
      return 'Habilita instalar apps desconocidas para esta app y toca Instalar.';
    }
    if (current == null) return 'Nueva version: $latest';
    if (latest == null) return 'Version instalada: $current';
    return 'Version instalada: $current. Nueva version: $latest.';
  }

  String? _versionLabel(String? version, int? build) {
    if ((version == null || version.isEmpty) && build == null) return null;
    if (build == null) return version;
    if (version == null || version.isEmpty) return 'build $build';
    return '$version ($build)';
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
        status == CodexAppUpdateStatus.verifying ||
        status == CodexAppUpdateStatus.installing;
    final info = controller.updateInfo;
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
            child: const Text('Mas tarde'),
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
