import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'package:codex_app_updater/codex_app_updater.dart';
import 'package:package_info_plus/package_info_plus.dart';

import 'src/screens/chat_screen.dart';
import 'src/services/chat_notification_service.dart';

const _configuredApiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: '',
);
const _codexAppUpdaterSourceApp = String.fromEnvironment(
  'CODEX_APP_UPDATER_SOURCE_APP',
  defaultValue: 'codex-mobile',
);
const _codexAppUpdaterEnabled = bool.fromEnvironment(
  'CODEX_APP_UPDATER_ENABLED',
);
const _codexAppUpdaterBridgeUrl = String.fromEnvironment(
  'CODEX_APP_UPDATER_BRIDGE_URL',
);
const _codexAppVersion = String.fromEnvironment(
  'CODEX_APP_VERSION',
  defaultValue: '1.0.0',
);
const _codexAppBuild = int.fromEnvironment('CODEX_APP_BUILD', defaultValue: 36);

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

class CodexMobileApp extends StatefulWidget {
  const CodexMobileApp({
    super.key,
    required this.initialApiBaseUrl,
    this.notificationService = const NoopChatNotificationService(),
    this.appUpdaterController,
    this.appUpdaterBridgeUrl,
    this.appUpdaterEnabled,
    this.appVersion,
    this.appBuild,
  });

  final String initialApiBaseUrl;
  final ChatNotificationService notificationService;
  final CodexAppUpdaterController? appUpdaterController;
  final String? appUpdaterBridgeUrl;
  final bool? appUpdaterEnabled;
  final String? appVersion;
  final int? appBuild;

  @override
  State<CodexMobileApp> createState() => _CodexMobileAppState();
}

class _CodexMobileAppState extends State<CodexMobileApp> {
  String _appVersion = _codexAppVersion;
  int _appBuild = _codexAppBuild;
  bool _appVersionLoaded = false;

  @override
  void initState() {
    super.initState();
    _loadAppVersion();
  }

  Future<void> _loadAppVersion() async {
    try {
      final info = await PackageInfo.fromPlatform();
      final build = int.tryParse(info.buildNumber);
      if (!mounted) return;
      setState(() {
        _appVersion = info.version;
        if (build != null) _appBuild = build;
        _appVersionLoaded = true;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _appVersionLoaded = true);
    }
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
      builder: (context, child) {
        Widget wrapped = child ?? const SizedBox.shrink();
        final updaterBridgeUrl = widget.appUpdaterBridgeUrl ??
            (_codexAppUpdaterBridgeUrl.isNotEmpty
                ? _codexAppUpdaterBridgeUrl
                : widget.initialApiBaseUrl);
        final updaterVersionReady =
            (widget.appVersion != null && widget.appBuild != null) ||
                _appVersionLoaded;
        final updaterEnabled =
            (widget.appUpdaterEnabled ?? _codexAppUpdaterEnabled) &&
                updaterBridgeUrl.isNotEmpty &&
                updaterVersionReady;
        if (updaterEnabled) {
          wrapped = CodexAppUpdater(
            config: CodexAppUpdaterConfig(
              sourceApp: _codexAppUpdaterSourceApp,
              bridgeUrl: updaterBridgeUrl,
              currentVersion: widget.appVersion ?? _appVersion,
              currentBuild: widget.appBuild ?? _appBuild,
            ),
            controller: widget.appUpdaterController,
            child: wrapped,
          );
        }
        return wrapped;
      },
      home: ChatScreen(
        initialApiBaseUrl: widget.initialApiBaseUrl,
        notificationService: widget.notificationService,
      ),
    );
  }
}
