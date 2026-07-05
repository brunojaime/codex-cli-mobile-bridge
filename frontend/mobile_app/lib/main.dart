import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'package:codex_app_updater/codex_app_updater.dart';
import 'package:codex_bridge_workbench/codex_bridge_workbench.dart';
import 'package:package_info_plus/package_info_plus.dart';

import 'src/screens/chat_screen.dart';
import 'src/services/chat_notification_service.dart';
import 'src/services/api_client.dart';

const _configuredApiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: '',
);
const _configuredAppUpdaterEnabled = bool.fromEnvironment(
  'APP_UPDATER_ENABLED',
  defaultValue: true,
);
const _configuredCodexBridgeDevMode = bool.fromEnvironment(
  'CODEX_BRIDGE_DEV_MODE',
  defaultValue: false,
);
const _configuredCodexBridgeWorkspacePath = String.fromEnvironment(
  'CODEX_BRIDGE_WORKSPACE_PATH',
  defaultValue: 'codex-cli-mobile-bridge',
);
const _codexMobileSourceApp = 'codex-mobile';
const _fallbackAppVersion = '1.0.0';
const _fallbackAppBuild = 41;

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final apiBaseUrl = _configuredApiBaseUrl.isNotEmpty
      ? _configuredApiBaseUrl
      : _defaultApiBaseUrl();
  final packageInfo = await PackageInfo.fromPlatform();
  final notificationService = createChatNotificationService();
  await notificationService.initialize();
  runApp(
    CodexMobileApp(
      initialApiBaseUrl: apiBaseUrl,
      currentVersion: packageInfo.version,
      currentBuild: _parseBuildNumber(packageInfo.buildNumber),
      appUpdaterEnabled: shouldEnableCodexAppUpdater(),
      notificationService: notificationService,
    ),
  );
}

String _defaultApiBaseUrl() {
  if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) {
    return 'http://10.0.2.2:8000';
  }

  if (kIsWeb) {
    final host = Uri.base.host;
    if (host == 'localhost' || host == '127.0.0.1') {
      return 'http://localhost:8000';
    }
    return Uri.base.origin;
  }

  return 'http://localhost:8000';
}

int _parseBuildNumber(String buildNumber) {
  return int.tryParse(buildNumber.trim()) ?? _fallbackAppBuild;
}

@visibleForTesting
bool shouldEnableCodexAppUpdater({
  bool configuredEnabled = _configuredAppUpdaterEnabled,
  bool? isWebOverride,
  TargetPlatform? platformOverride,
}) {
  final isWeb = isWebOverride ?? kIsWeb;
  final platform = platformOverride ?? defaultTargetPlatform;
  return configuredEnabled && !isWeb && platform == TargetPlatform.android;
}

@visibleForTesting
bool isCodexBridgeDevModeEnabled({
  bool configuredEnabled = _configuredCodexBridgeDevMode,
}) {
  return configuredEnabled;
}

class CodexMobileApp extends StatefulWidget {
  const CodexMobileApp({
    super.key,
    required this.initialApiBaseUrl,
    this.currentVersion = _fallbackAppVersion,
    this.currentBuild = _fallbackAppBuild,
    this.appUpdaterEnabled = false,
    this.appUpdaterController,
    this.appUpdaterCheckOnStart = true,
    this.notificationService = const NoopChatNotificationService(),
  });

  final String initialApiBaseUrl;
  final String currentVersion;
  final int currentBuild;
  final bool appUpdaterEnabled;
  final CodexAppUpdaterController? appUpdaterController;
  final bool appUpdaterCheckOnStart;
  final ChatNotificationService notificationService;

  @override
  State<CodexMobileApp> createState() => _CodexMobileAppState();
}

class _CodexMobileAppState extends State<CodexMobileApp> {
  late String _activeBridgeUrl = widget.initialApiBaseUrl;

  void _handleActiveServerBaseUrlChanged(String baseUrl) {
    if (baseUrl == _activeBridgeUrl) {
      return;
    }
    setState(() {
      _activeBridgeUrl = baseUrl;
    });
  }

  @override
  Widget build(BuildContext context) {
    const background = Color(0xFF0B1020);
    const panel = Color(0xFF141C33);
    const accent = Color(0xFF55D6BE);
    const muted = Color(0xFF8B97B5);

    final scheme = ColorScheme.fromSeed(
      seedColor: accent,
      brightness: Brightness.dark,
      surface: panel,
    );

    return MaterialApp(
      title: 'Codex Remote',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        brightness: Brightness.dark,
        colorScheme: scheme,
        scaffoldBackgroundColor: background,
        textTheme: ThemeData.dark().textTheme.apply(
              bodyColor: Colors.white,
              displayColor: Colors.white,
            ),
        inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: panel,
          hintStyle: const TextStyle(color: muted),
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(18),
            borderSide: BorderSide.none,
          ),
        ),
        appBarTheme: const AppBarTheme(
          backgroundColor: background,
          foregroundColor: Colors.white,
          elevation: 0,
        ),
      ),
      home: ChatScreen(
        initialApiBaseUrl: widget.initialApiBaseUrl,
        notificationService: widget.notificationService,
        onActiveServerBaseUrlChanged: _handleActiveServerBaseUrlChanged,
      ),
      builder: (context, child) {
        final home = child ?? const SizedBox.shrink();
        return CodexBridgeDevModeWrapper(
          enabled: isCodexBridgeDevModeEnabled(),
          bridgeUrl: _activeBridgeUrl,
          workspacePath: _configuredCodexBridgeWorkspacePath,
          sddFeedbackSubmitter: _submitBridgeSddFeedback,
          sddActionSubmitter: _submitBridgeSddCodexAction,
          child: CodexAppUpdater(
            config: CodexAppUpdaterConfig(
              sourceApp: _codexMobileSourceApp,
              bridgeUrl: _activeBridgeUrl,
              currentVersion: widget.currentVersion,
              currentBuild: widget.currentBuild,
              enabled: widget.appUpdaterEnabled,
            ),
            controller: widget.appUpdaterController,
            checkOnStart: widget.appUpdaterCheckOnStart,
            child: home,
          ),
        );
      },
    );
  }
}

Future<SddFeedbackSubmissionResult> _submitBridgeSddFeedback(
  String bridgeUrl,
  SddFeedbackDraft draft,
) async {
  final item = await ApiClient(baseUrl: bridgeUrl).createFeedbackQueueItem(
    sourceApp: _codexMobileSourceApp,
    sourceDisplayName: 'Codex Mobile',
    comment: draft.comment,
    feedbackKind: draft.target.feedbackKind,
    contextMetadata: draft.target.toContextMetadata(),
    selectionBounds: draft.target.isDiagram
        ? const <String, double>{
            'left': 0,
            'top': 0,
            'width': 1,
            'height': 1,
          }
        : const <String, double>{},
  );
  return SddFeedbackSubmissionResult(id: item.id, status: item.status);
}

Future<SddCodexActionSubmissionResult> _submitBridgeSddCodexAction(
  String bridgeUrl,
  SddCodexActionDraft draft,
) async {
  final accepted = await ApiClient(baseUrl: bridgeUrl).sendMessage(
    draft.prompt,
    workspacePath: draft.executionWorkspacePath,
  );
  return SddCodexActionSubmissionResult(
    jobId: accepted.jobId,
    sessionId: accepted.sessionId,
    status: accepted.status,
  );
}
