import 'package:codex_developer_feedback_template/developer_feedback_template.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test(
    'local demo config defaults to the LOCAL_DEMO_MODE environment flag',
    () {
      const config = CodexLocalDemoConfig.fromEnvironment;

      expect(CodexLocalDemoConfig.environmentDefine, 'LOCAL_DEMO_MODE');
      expect(config.enabled, codexLocalDemoModeEnabled);
    },
  );

  test('local demo config selects local or production values', () {
    const enabled = CodexLocalDemoConfig(enabled: true);
    const disabled = CodexLocalDemoConfig(enabled: false);

    expect(
      enabled.select(localDemo: 'local-api', production: 'http-api'),
      'local-api',
    );
    expect(
      disabled.select(localDemo: 'local-api', production: 'http-api'),
      'http-api',
    );
  });

  test('local demo descriptor formats credentials for UI and README', () {
    const descriptor = CodexLocalDemoDescriptor(
      appName: 'Fixture App',
      tenant: 'tenant-demo',
      email: 'owner@example.com',
      password: 'StrongPass123',
      highlights: ['Seeded client', 'Seeded devices'],
    );

    expect(descriptor.credentialsText, contains('Tenant: tenant-demo'));
    expect(descriptor.credentialsText, contains('- Seeded devices'));
    expect(
      descriptor.credentialsMarkdown,
      contains('### Fixture App Local Demo'),
    );
    expect(descriptor.credentialsMarkdown, contains('Password: StrongPass123'));
  });

  test('local demo helpers expose standard build and APK scan strings', () {
    expect(codexLocalDemoDartDefine(), '--dart-define=LOCAL_DEMO_MODE=true');
    expect(
      codexLocalDemoBuildCommand(),
      'flutter build apk --release --dart-define=LOCAL_DEMO_MODE=true',
    );
    expect(codexLocalDemoLoopbackBlocklist, contains('localhost:8080'));
    expect(codexLocalDemoLoopbackBlocklist, contains('http://127.0.0.1'));
  });
}
