import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';

import 'src/screens/chat_screen.dart';

const _configuredApiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: '',
);

void main() {
  final apiBaseUrl = _configuredApiBaseUrl.isNotEmpty
      ? _configuredApiBaseUrl
      : _defaultApiBaseUrl();
  runApp(CodexMobileApp(initialApiBaseUrl: apiBaseUrl));
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

class CodexMobileApp extends StatelessWidget {
  const CodexMobileApp({
    super.key,
    required this.initialApiBaseUrl,
  });

  final String initialApiBaseUrl;

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
      home: ChatScreen(initialApiBaseUrl: initialApiBaseUrl),
    );
  }
}
