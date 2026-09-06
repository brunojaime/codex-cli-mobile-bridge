import 'package:codex_mobile_frontend/src/screens/operations_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  testWidgets('operations screen requests a separate control connection', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues(<String, Object>{});

    await tester.pumpWidget(
      const MaterialApp(
        home: OperationsScreen(bridgeBaseUrl: 'https://device.tailnet.ts.net'),
      ),
    );
    await tester.pump();

    expect(find.text('Operations'), findsOneWidget);
    expect(find.text('Configure connection'), findsOneWidget);

    await tester.tap(find.text('Configure connection'));
    await tester.pumpAndSettle();

    expect(find.text('Control Agent connection'), findsOneWidget);
    expect(find.widgetWithText(TextField, 'Control URL'), findsOneWidget);
    final urlField = tester.widget<TextField>(
      find.widgetWithText(TextField, 'Control URL'),
    );
    expect(urlField.controller!.text, 'https://device.tailnet.ts.net/ops');
  });
}
