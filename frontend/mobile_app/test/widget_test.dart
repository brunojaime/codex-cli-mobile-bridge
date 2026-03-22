import 'package:codex_mobile_frontend/main.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  testWidgets('renders Codex Remote shell', (tester) async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    await tester.pumpWidget(
      const CodexMobileApp(initialApiBaseUrl: 'http://localhost:8000'),
    );

    expect(find.text('Codex Remote'), findsOneWidget);
    expect(find.textContaining('local machine'), findsOneWidget);
  });
}
