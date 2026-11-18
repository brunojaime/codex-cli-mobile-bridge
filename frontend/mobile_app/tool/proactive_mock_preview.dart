// Isolated visual preview. Never used by the production app or release workflow.
import 'package:codex_mobile_frontend/src/screens/chat_screen.dart';
import 'package:codex_mobile_frontend/src/services/chat_notification_service.dart';
import 'package:flutter/material.dart';

void main() {
  runApp(MaterialApp(
    debugShowCheckedModeBanner: false,
    title: 'Propuestas del agente · maqueta',
    theme: ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      scaffoldBackgroundColor: const Color(0xFF0B1020),
      colorScheme: ColorScheme.fromSeed(
        seedColor: const Color(0xFF55D6BE),
        brightness: Brightness.dark,
        surface: const Color(0xFF141C33),
      ),
      appBarTheme: const AppBarTheme(backgroundColor: Color(0xFF0B1020)),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(minimumSize: const Size(48, 48)),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(minimumSize: const Size(48, 48)),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(minimumSize: const Size(48, 48)),
      ),
    ),
    home: const ChatScreen(
      initialApiBaseUrl: '',
      notificationService: NoopChatNotificationService(),
      enableServerBootstrap: false,
    ),
  ));
}
