import 'dart:convert';

import 'package:codex_mobile_frontend/src/services/api_client.dart';
import 'package:codex_mobile_frontend/src/widgets/project_secrets_sheet.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
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

  testWidgets(
      'edits name and hidden value, copies only name, cancels and confirms deletion',
      (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    var names = <String>['TOKEN', 'OTHER'];
    var value = 'original-private';
    var writes = 0;
    String? clipboard;
    tester.binding.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, (call) async {
      if (call.method == 'Clipboard.setData') {
        clipboard = (call.arguments as Map)['text'] as String;
      }
      return null;
    });
    addTearDown(() => tester.binding.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, null));
    final client = ApiClient(
        baseUrl: 'http://bridge.test',
        client: MockClient((request) async {
          if (request.method == 'PATCH') {
            writes++;
            final body = jsonDecode(request.body) as Map<String, dynamic>;
            final old = body['name'] as String;
            names[names.indexOf(old)] = body['new_name'] as String;
            if (body.containsKey('value')) value = body['value'] as String;
          } else if (request.method == 'DELETE') {
            writes++;
            names.remove(request.url.queryParameters['name']);
          }
          return http.Response(
              jsonEncode({
                'workspace_path': '/projects/cms',
                'workspace_name': 'cms',
                'env_file': '.env',
                'names': names
              }),
              200);
        }));
    await tester.pumpWidget(_harness(client));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Actions for TOKEN'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Copy name'));
    await tester.pumpAndSettle();
    expect(clipboard, 'TOKEN');
    await tester.tap(find.text('TOKEN'));
    await tester.pumpAndSettle();
    final nameField = find.byKey(const ValueKey<String>('project-secret-name'));
    final valueField =
        find.byKey(const ValueKey<String>('project-secret-value'));
    expect(tester.widget<TextFormField>(valueField).controller!.text, isEmpty);
    expect(
        tester
            .widget<EditableText>(find.descendant(
                of: valueField, matching: find.byType(EditableText)))
            .obscureText,
        isTrue);
    await tester.enterText(nameField, 'RENAMED');
    await tester.ensureVisible(find.text('Save changes'));
    await tester.tap(find.text('Save changes'));
    await tester.pumpAndSettle();
    expect(value, 'original-private');
    expect(names, contains('RENAMED'));
    expect(names, isNot(contains('TOKEN')));
    await tester.ensureVisible(find.text('RENAMED'));
    await tester.tap(find.text('RENAMED'));
    await tester.pumpAndSettle();
    await tester.enterText(valueField, 'new-private');
    await tester.ensureVisible(find.text('Save changes'));
    await tester.tap(find.text('Save changes'));
    await tester.pumpAndSettle();
    expect(value, 'new-private');
    expect(find.text('new-private'), findsNothing);
    for (final confirm in [false, true]) {
      await tester.ensureVisible(find.byTooltip('Actions for RENAMED'));
      await tester.tap(find.byTooltip('Actions for RENAMED'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Delete secret'));
      await tester.pumpAndSettle();
      await tester.tap(confirm
          ? find.byKey(const ValueKey<String>('confirm-delete-secret'))
          : find.text('Cancel'));
      await tester.pumpAndSettle();
      expect(names.contains('RENAMED'), !confirm);
    }
    expect(writes, 3);
    expect(names, ['OTHER']);
    expect(tester.takeException(), isNull);
  });

  testWidgets('failed edit keeps input hidden and cancel clears it',
      (tester) async {
    final client = ApiClient(
        baseUrl: 'http://bridge.test',
        client: MockClient((request) async => request.method == 'GET'
            ? http.Response(
                '{"workspace_path":"/projects/cms","workspace_name":"cms","env_file":".env","names":["TOKEN"]}',
                200)
            : http.Response('private-server-value', 409)));
    await tester.pumpWidget(_harness(client));
    await tester.pumpAndSettle();
    await tester.tap(find.text('TOKEN'));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey<String>('project-secret-value')),
        'private-input');
    await tester.ensureVisible(find.text('Save changes'));
    await tester.tap(find.text('Save changes'));
    await tester.pumpAndSettle();
    expect(find.textContaining('private-server-value'), findsNothing);
    expect(find.textContaining('Could not save the secret'), findsOneWidget);
    await tester.ensureVisible(find.text('Cancel'));
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('TOKEN'));
    await tester.pumpAndSettle();
    expect(
        tester
            .widget<TextFormField>(
                find.byKey(const ValueKey<String>('project-secret-value')))
            .controller!
            .text,
        isEmpty);
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
