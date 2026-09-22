import 'dart:convert';

import 'package:codex_mobile_frontend/src/services/api_client.dart';
import 'package:codex_mobile_frontend/src/widgets/project_secrets_sheet.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  for (final size in <Size>[
    const Size(430, 932),
    const Size(768, 1024),
  ]) {
    testWidgets('lays out without overflow at ${size.width.toInt()}px',
        (tester) async {
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final client = ApiClient(
        baseUrl: 'http://bridge.test',
        client: MockClient(
          (request) async => http.Response(
            '{"workspace_path":"/projects/cms","workspace_name":"cms","env_file":".env","names":["A_VERY_LONG_SECRET_NAME_THAT_MUST_STAY_INSIDE_THE_AVAILABLE_WIDTH","CMS_URL"]}',
            200,
          ),
        ),
      );
      await tester.pumpWidget(_harness(client));
      await tester.pumpAndSettle();
      await tester.tap(
        find.byKey(const ValueKey<String>('add-project-secret')),
      );
      await tester.pump();

      final buttonSize = tester.getSize(
        find.byKey(const ValueKey<String>('save-project-secret')),
      );
      expect(buttonSize.height, greaterThanOrEqualTo(48));
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('lists only names and saves a write-only project secret',
      (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    var requestCount = 0;
    final client = ApiClient(
      baseUrl: 'http://bridge.test',
      client: MockClient((request) async {
        requestCount += 1;
        if (request.method == 'GET') {
          return http.Response(
            '{"workspace_path":"/projects/cms","workspace_name":"cms","env_file":".env","names":["CMS_URL"]}',
            200,
          );
        }
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        expect(body['name'], 'CMS_PASSWORD');
        expect(body['value'], 'test-only-password');
        return http.Response(
          '{"workspace_path":"/projects/cms","workspace_name":"cms","env_file":".env","names":["CMS_PASSWORD","CMS_URL"]}',
          200,
        );
      }),
    );

    await tester.pumpWidget(_harness(client));
    await tester.pumpAndSettle();

    expect(find.text('Project secrets'), findsOneWidget);
    expect(find.text('CMS_URL'), findsOneWidget);
    expect(find.text('Add secret'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey<String>('add-project-secret')));
    await tester.pump();
    final valueField = tester.widget<EditableText>(
      find.descendant(
        of: find.byKey(const ValueKey<String>('project-secret-value')),
        matching: find.byType(EditableText),
      ),
    );
    expect(valueField.obscureText, isTrue);
    await tester.enterText(
      find.byKey(const ValueKey<String>('project-secret-name')),
      'CMS_PASSWORD',
    );
    await tester.enterText(
      find.byKey(const ValueKey<String>('project-secret-value')),
      'test-only-password',
    );
    await tester.tap(find.byKey(const ValueKey<String>('save-project-secret')));
    await tester.pumpAndSettle();

    expect(requestCount, 2);
    expect(find.text('CMS_PASSWORD'), findsOneWidget);
    expect(
      find.text('CMS_PASSWORD saved in .env. Its value cannot be viewed here.'),
      findsOneWidget,
    );
    expect(find.text('test-only-password'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('shows validation without sending malformed names',
      (tester) async {
    var requestCount = 0;
    final client = ApiClient(
      baseUrl: 'http://bridge.test',
      client: MockClient((request) async {
        requestCount += 1;
        return http.Response(
          '{"workspace_path":"/projects/cms","workspace_name":"cms","env_file":".env","names":[]}',
          200,
        );
      }),
    );
    await tester.pumpWidget(_harness(client));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey<String>('add-project-secret')));
    await tester.pump();
    await tester.enterText(
      find.byKey(const ValueKey<String>('project-secret-name')),
      '9 INVALID',
    );
    await tester.enterText(
      find.byKey(const ValueKey<String>('project-secret-value')),
      'test-value',
    );
    await tester.tap(find.byKey(const ValueKey<String>('save-project-secret')));
    await tester.pump();

    expect(
      find.text(
        'Use letters, numbers, and underscores; do not start with a number.',
      ),
      findsOneWidget,
    );
    expect(requestCount, 1);
  });

  testWidgets('shows a recoverable load error on desktop', (tester) async {
    tester.view.physicalSize = const Size(1440, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final client = ApiClient(
      baseUrl: 'http://bridge.test',
      client: MockClient((request) async => http.Response('unavailable', 503)),
    );

    await tester.pumpWidget(_harness(client));
    await tester.pumpAndSettle();

    expect(
        find.textContaining('Could not load project secrets'), findsOneWidget);
    expect(find.byTooltip('Refresh'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

Widget _harness(ApiClient client) {
  return MaterialApp(
    theme: ThemeData.dark(useMaterial3: true),
    home: Scaffold(
      body: ProjectSecretsSheet(
        apiClient: client,
        workspacePath: '/projects/cms',
        workspaceName: 'CMS Project With A Long but Manageable Name',
      ),
    ),
  );
}
