import 'package:flutter/material.dart';
import 'package:codex_mobile_frontend/src/screens/session_file_screen.dart';
import 'package:codex_mobile_frontend/src/services/api_client.dart';

void main() => runApp(MaterialApp(
    theme: ThemeData.dark(),
    home: SessionFileScreen(
      apiClient: ApiClient(
          baseUrl: const String.fromEnvironment('PROBE_API',
              defaultValue: 'http://127.0.0.1:18118')),
      sessionId: 'd1cae0c2-127b-407f-82fc-ce5b19698890',
      target: 'reports/html-preview-153/fixture/index.html',
      onExternalLink: (_) async {},
    )));
