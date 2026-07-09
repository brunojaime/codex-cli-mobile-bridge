const codexLocalDemoModeEnabled = bool.fromEnvironment(
  CodexLocalDemoConfig.environmentDefine,
);

class CodexLocalDemoConfig {
  const CodexLocalDemoConfig({this.enabled = codexLocalDemoModeEnabled});

  static const environmentDefine = 'LOCAL_DEMO_MODE';
  static const fromEnvironment = CodexLocalDemoConfig();

  final bool enabled;

  bool get disabled => !enabled;

  T select<T>({required T localDemo, required T production}) {
    return enabled ? localDemo : production;
  }
}

class CodexLocalDemoDescriptor {
  const CodexLocalDemoDescriptor({
    required this.appName,
    required this.tenant,
    required this.email,
    required this.password,
    this.highlights = const [],
  });

  final String appName;
  final String tenant;
  final String email;
  final String password;
  final List<String> highlights;

  List<String> get credentialLines => [
    'App: $appName',
    'Tenant: $tenant',
    'Email: $email',
    'Password: $password',
  ];

  String get credentialsText => codexLocalDemoCredentialsText(this);

  String get credentialsMarkdown => codexLocalDemoCredentialsMarkdown(this);
}

String codexLocalDemoCredentialsText(CodexLocalDemoDescriptor descriptor) {
  final lines = [...descriptor.credentialLines];
  if (descriptor.highlights.isNotEmpty) {
    lines
      ..add('Highlights:')
      ..addAll(descriptor.highlights.map((highlight) => '- $highlight'));
  }
  return lines.join('\n');
}

String codexLocalDemoCredentialsMarkdown(CodexLocalDemoDescriptor descriptor) {
  final buffer = StringBuffer()
    ..writeln('### ${descriptor.appName} Local Demo')
    ..writeln()
    ..writeln('```text')
    ..writeln('Tenant: ${descriptor.tenant}')
    ..writeln('Email: ${descriptor.email}')
    ..writeln('Password: ${descriptor.password}')
    ..writeln('```');
  if (descriptor.highlights.isNotEmpty) {
    buffer
      ..writeln()
      ..writeln('Seeded demo data:');
    for (final highlight in descriptor.highlights) {
      buffer.writeln('- $highlight');
    }
  }
  return buffer.toString().trimRight();
}

String codexLocalDemoDartDefine() {
  return '--dart-define=${CodexLocalDemoConfig.environmentDefine}=true';
}

String codexLocalDemoBuildCommand({
  String command = 'flutter build apk --release',
}) {
  return '$command ${codexLocalDemoDartDefine()}';
}

const codexLocalDemoLoopbackBlocklist = [
  'http://localhost',
  'https://localhost',
  'localhost:8080',
  'http://127.0.0.1',
  'https://127.0.0.1',
  '10.0.2.2',
];
