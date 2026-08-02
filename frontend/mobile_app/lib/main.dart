import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'package:codex_bridge_workbench/codex_bridge_workbench.dart';

import 'src/screens/chat_screen.dart';
import 'src/models/codex_tooling.dart';
import 'src/services/chat_notification_service.dart';
import 'src/services/api_client.dart';

const _configuredApiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: '',
);
const _configuredCodexBridgeDevMode = bool.fromEnvironment(
  'CODEX_BRIDGE_DEV_MODE',
  defaultValue: false,
);
const _configuredCodexBridgeWorkspacePath = String.fromEnvironment(
  'CODEX_BRIDGE_WORKSPACE_PATH',
  defaultValue: _defaultCodexBridgeWorkspacePath,
);
const _defaultCodexBridgeWorkspacePath = 'codex-cli-mobile-bridge';
const _configuredBridgeSourceApp = String.fromEnvironment(
  'BRIDGE_APP_SOURCE_APP',
  defaultValue: 'codex-mobile',
);
const _configuredBridgeAppLabel = String.fromEnvironment(
  'BRIDGE_APP_LABEL',
  defaultValue: 'Codex Mobile Bridge',
);
const _configuredBridgeUpdaterChannel = String.fromEnvironment(
  'BRIDGE_UPDATER_CHANNEL',
  defaultValue: 'prod',
);

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final apiBaseUrl = _configuredApiBaseUrl.isNotEmpty
      ? _configuredApiBaseUrl
      : _defaultApiBaseUrl();
  final notificationService = createChatNotificationService();
  await notificationService.initialize();
  runApp(
    CodexMobileApp(
      initialApiBaseUrl: apiBaseUrl,
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

@visibleForTesting
bool isCodexBridgeDevModeEnabled({
  bool configuredEnabled = _configuredCodexBridgeDevMode,
}) {
  return configuredEnabled;
}

@visibleForTesting
String? resolveCodexBridgeWorkbenchWorkspacePath({
  bool? devAppBuild,
  String configuredWorkspacePath = _configuredCodexBridgeWorkspacePath,
}) {
  final trimmed = configuredWorkspacePath.trim();
  if (trimmed.isEmpty) {
    return null;
  }
  final isDevApp = devAppBuild ?? _isDevAppBuild();
  if (isDevApp && trimmed == _defaultCodexBridgeWorkspacePath) {
    return null;
  }
  return trimmed;
}

class CodexMobileApp extends StatefulWidget {
  const CodexMobileApp({
    super.key,
    required this.initialApiBaseUrl,
    this.notificationService = const NoopChatNotificationService(),
  });

  final String initialApiBaseUrl;
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
    final accent =
        _isDevAppBuild() ? const Color(0xFF38BDF8) : const Color(0xFF55D6BE);
    const muted = Color(0xFF8B97B5);

    final scheme = ColorScheme.fromSeed(
      seedColor: accent,
      brightness: Brightness.dark,
      surface: panel,
    );

    return MaterialApp(
      title: _configuredBridgeAppLabel,
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
          workspacePath: resolveCodexBridgeWorkbenchWorkspacePath(),
          sddFeedbackSubmitter: _submitBridgeSddFeedback,
          sddActionSubmitter: _submitBridgeSddCodexAction,
          child: home,
        );
      },
    );
  }
}

bool _isDevAppBuild() {
  return _configuredBridgeUpdaterChannel.toLowerCase() == 'dev' ||
      _configuredBridgeSourceApp.toLowerCase().endsWith('-dev') ||
      _configuredBridgeAppLabel.toLowerCase().contains('dev');
}

Future<SddFeedbackSubmissionResult> _submitBridgeSddFeedback(
  String bridgeUrl,
  SddFeedbackDraft draft,
) async {
  final item = await ApiClient(baseUrl: bridgeUrl).createFeedbackQueueItem(
    sourceApp: _configuredBridgeSourceApp,
    sourceDisplayName: _configuredBridgeAppLabel,
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
    codexRunOptions: codexRunOptionsForSddAction(draft),
  );
  return SddCodexActionSubmissionResult(
    jobId: accepted.jobId,
    sessionId: accepted.sessionId,
    status: accepted.status,
  );
}

@visibleForTesting
CodexRunOptions? codexRunOptionsForSddAction(SddCodexActionDraft draft) {
  final metadata = draft.request.target.diagramSelectionMetadata;
  final renderer = metadata['renderer']?.toString();
  final renderedFormat = metadata['renderedFormat']?.toString();
  final sourceFormat = metadata['sourceFormat']?.toString();
  if (renderer == 'diagram-mcp-rendering-engine' ||
      renderedFormat == 'svg' ||
      sourceFormat == 'svg') {
    return const CodexRunOptions(
      mcpServerIds: <String>['diagram-mcp-rendering-engine'],
    );
  }
  return null;
}
