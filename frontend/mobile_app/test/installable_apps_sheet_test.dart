import 'package:codex_app_updater/codex_app_updater.dart';
import 'package:codex_mobile_frontend/src/services/api_client.dart';
import 'package:codex_mobile_frontend/src/widgets/installable_apps_sheet.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  testWidgets('shows empty installable app list', (tester) async {
    await tester.pumpWidget(
      _harness(
        http.Response(
          '{"kind":"codex.installableApps","version":1,"apps":[]}',
          200,
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Apps'), findsOneWidget);
    expect(find.text('No installable apps'), findsOneWidget);
  });

  testWidgets('shows API errors', (tester) async {
    await tester.pumpWidget(_harness(http.Response('broken', 500)));
    await tester.pumpAndSettle();

    expect(find.textContaining('Could not load apps'), findsOneWidget);
  });

  testWidgets('shows available and disabled apps', (tester) async {
    await tester.pumpWidget(_harness(http.Response(_appsJson(), 200)));
    await tester.pumpAndSettle();

    expect(find.text('SAT Showroom'), findsOneWidget);
    expect(find.text('Codex Disabled'), findsOneWidget);
    expect(find.text('1.0.0+12  •  Available'), findsOneWidget);
    expect(find.text('No release  •  Disabled'), findsOneWidget);
    expect(find.text('Install'), findsOneWidget);
    expect(find.text('Unavailable'), findsOneWidget);
  });

  testWidgets('install button downloads and opens installer', (tester) async {
    final controller = _RecordingInstallController();
    addTearDown(controller.dispose);

    await tester.pumpWidget(
      _harness(
        http.Response(_appsJson(), 200),
        controller: controller,
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Install'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(controller.installCallCount, 1);
    expect(
      controller.requestedApkUrl.toString(),
      'http://bridge.test/app-updates/sat-showroom/apk/tag/sat-showroom.apk',
    );
    expect(controller.requestedSourceApp, 'sat-showroom');
    expect(find.text('Installer opened'), findsOneWidget);
  });

  testWidgets('checksum failure is visible', (tester) async {
    final controller = _RecordingInstallController(
      result: false,
      configuredFailureReason: CodexAppUpdateFailureReason.checksumMismatch,
    );
    addTearDown(controller.dispose);

    await tester.pumpWidget(
      _harness(
        http.Response(_appsJson(sha256: 'a' * 64), 200),
        controller: controller,
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Install'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.text('Checksum failed'), findsOneWidget);
  });
}

Widget _harness(
  http.Response response, {
  CodexAppUpdaterController? controller,
}) {
  return MaterialApp(
    home: Scaffold(
      body: InstallableAppsSheet(
        apiClient: ApiClient(
          baseUrl: 'http://bridge.test',
          client: MockClient((request) async {
            expect(request.url.path, '/installable-apps');
            return response;
          }),
        ),
        updaterController: controller,
      ),
    ),
  );
}

String _appsJson({String? sha256}) {
  return '''
  {
    "kind": "codex.installableApps",
    "version": 1,
    "apps": [
      {
        "kind": "codex.installableApp",
        "version": 1,
        "sourceApp": "sat-showroom",
        "displayName": "SAT Showroom",
        "repo": "brunojaime/sat-showroom",
        "releaseChannel": "stable",
        "latestVersion": "1.0.0",
        "latestBuild": 12,
        "releaseTag": "android-v1.0.0-build.12",
        "apkUrl": "http://bridge.test/app-updates/sat-showroom/apk/tag/sat-showroom.apk",
        "apkAssetName": "sat-showroom.apk",
        "sizeBytes": 2097152,
        "sha256": ${sha256 == null ? 'null' : '"$sha256"'},
        "available": true,
        "enabled": true,
        "packageId": "com.sat.showroom",
        "installStatusHint": "available"
      },
      {
        "kind": "codex.installableApp",
        "version": 1,
        "sourceApp": "codex-disabled",
        "displayName": "Codex Disabled",
        "repo": "brunojaime/codex-disabled",
        "releaseChannel": "stable",
        "available": false,
        "enabled": false,
        "installStatusHint": "disabled"
      }
    ]
  }
  ''';
}

class _RecordingInstallController extends CodexAppUpdaterController {
  _RecordingInstallController({
    this.result = true,
    this.configuredFailureReason,
  });

  final bool result;
  final CodexAppUpdateFailureReason? configuredFailureReason;
  int installCallCount = 0;
  Uri? requestedApkUrl;
  String? requestedSourceApp;

  @override
  Future<bool> installExternalApk({
    required Uri apkUrl,
    required String sourceApp,
    String? displayName,
    String? apkAssetName,
    String? sha256,
    int? sizeBytes,
    bool requireChecksum = false,
  }) async {
    installCallCount += 1;
    requestedApkUrl = apkUrl;
    requestedSourceApp = sourceApp;
    status =
        result ? CodexAppUpdateStatus.dismissed : CodexAppUpdateStatus.failed;
    failureReason = configuredFailureReason;
    notifyListeners();
    return result;
  }
}
