# Developer Feedback App Onboarding

Use this checklist when a Flutter app should send marked screenshots, comments,
optional audio, and batch feedback into Codex Mobile Bridge.

## App Contract

Each app should expose one stable app identity:

- `sourceApp`: stable machine id, for example `smart-nienfos-smart-house`
- `sourceDisplayName`: human label, for example `Smart Nienfos Smart House`
- `bridgeUrl`: provided at build/run time with `CODEX_FEEDBACK_BRIDGE_URL`
- `enabled`: provided with `CODEX_FEEDBACK_TEMPLATE_ENABLED`

The app must not copy feedback queue, screenshot, audio, or Bridge submission
logic. It should only consume `codex_developer_feedback_template`.

## Flutter Integration

Add the package to the app `pubspec.yaml` with an explicit tag:

```yaml
dependencies:
  codex_developer_feedback_template:
    git:
      url: https://github.com/brunojaime/codex-cli-mobile-bridge.git
      path: packages/codex_developer_feedback_template
      ref: codex-developer-feedback-template-v0.4.5
```

Wrap the app shell once with `MaterialApp.builder`. Keep `MaterialApp` at the
top so the feedback UI is under `Directionality`, `MediaQuery`, navigator, and
scaffold messenger context:

```dart
import 'package:codex_developer_feedback_template/developer_feedback_template.dart';

const _feedbackSourceApp = String.fromEnvironment(
  'CODEX_FEEDBACK_SOURCE_APP',
  defaultValue: 'stable-source-app',
);
const _feedbackSourceDisplayName = String.fromEnvironment(
  'CODEX_FEEDBACK_SOURCE_NAME',
  defaultValue: 'Human App Name',
);

final _navigatorKey = GlobalKey<NavigatorState>();
final _scaffoldMessengerKey = GlobalKey<ScaffoldMessengerState>();

MaterialApp(
  navigatorKey: _navigatorKey,
  scaffoldMessengerKey: _scaffoldMessengerKey,
  builder: (context, child) {
    return DeveloperFeedbackTemplate(
      enabled: developerFeedbackTemplateEnabled,
      sourceApp: _feedbackSourceApp,
      sourceDisplayName: _feedbackSourceDisplayName,
      bridgeUrl: developerFeedbackBridgeUrl,
      navigatorKey: _navigatorKey,
      scaffoldMessengerKey: _scaffoldMessengerKey,
      child: child ?? const SizedBox.shrink(),
    );
  },
  home: const AppHome(),
);
```

Add a widget test that asserts the app root contains
`DeveloperFeedbackTemplate` with the expected `sourceApp`, `sourceDisplayName`,
and `bridgeUrl`.

## Local Demo Scaffold

New Flutter apps that need an installable Android demo should also use the
package local demo contract. The package provides no business data and no app
API implementation; it only standardizes the flag, descriptor, helper text, and
release validation.

Create `lib/src/local_demo_api.dart` with an app-owned API adapter:

```dart
import 'api_client.dart';

class LocalDemoBackendApi implements BackendApi {
  LocalDemoBackendApi();

  // Implement the app's BackendApi with deterministic in-memory seeds.
  // Keep product-specific records in this file, not in the feedback package.
}
```

In `main.dart`, import the public contract and choose the API at composition
time:

```dart
import 'package:codex_developer_feedback_template/developer_feedback_template.dart';

import 'src/local_demo_api.dart';

const localDemoConfig = CodexLocalDemoConfig.fromEnvironment;

const localDemoDescriptor = CodexLocalDemoDescriptor(
  appName: 'Human App Name',
  tenant: 'tenant-demo',
  email: 'owner@example.com',
  password: 'StrongPass123',
  highlights: ['Seeded workspace', 'Seeded admin user'],
);

final api = localDemoConfig.select(
  localDemo: LocalDemoBackendApi(),
  production: HttpBackendApi(baseUrl: resolvedBaseUrl),
);
```

Add a minimal test that proves the local API accepts the documented demo login
and exposes one seeded record:

```dart
test('local demo login exposes seeded data', () async {
  final api = LocalDemoBackendApi();

  final session = await api.login(
    tenantSlug: localDemoDescriptor.tenant,
    email: localDemoDescriptor.email,
    password: localDemoDescriptor.password,
  );

  expect(session.roles, contains('owner'));
  expect(await api.listSeededRecords(token: session.accessToken), isNotEmpty);
});
```

Document the command in the app README:

```sh
flutter build apk --release --dart-define=LOCAL_DEMO_MODE=true
```

Release workflows for demo APKs must fail fast if extracted APK strings include
app backend loopbacks such as `http://localhost`, `localhost:8080`,
`http://127.0.0.1`, or `10.0.2.2`. Generic Dart VM service strings may still
mention `localhost` or `127.0.0.1`; validate exact backend URL patterns.

## Bridge Registration

Register the app under the `codex_developer_feedback_template` component in:

```text
backend/app/infrastructure/config/app_release_associations.json
```

Also add an enabled app entry in:

```text
backend/app/infrastructure/config/app_updates.json
```

When the app id does not match the Bridge workspace name, pass an explicit
workspace alias to the Bridge:

```sh
FEEDBACK_SOURCE_WORKSPACE_ALIASES=smart-nienfos-smart-house:/home/batata/Projects/smart_nienfos
```

Multiple apps can point to the same workspace:

```sh
FEEDBACK_SOURCE_WORKSPACE_ALIASES=smart-nienfos-moldegon:/home/batata/Projects/smart_nienfos,smart-nienfos-admin:/home/batata/Projects/smart_nienfos,smart-nienfos-smart-house:/home/batata/Projects/smart_nienfos
```

## Doctor

Run the read-only doctor from this repo:

```sh
python scripts/developer_feedback_integration.py
```

For one app:

```sh
python scripts/developer_feedback_integration.py --app smart-nienfos-smart-house
```

For CI or machine-readable output:

```sh
python scripts/developer_feedback_integration.py --json --strict
```

`--strict` exits non-zero on warnings, including missing workspace aliases.
