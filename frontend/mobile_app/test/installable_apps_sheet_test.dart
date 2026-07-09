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

  testWidgets('shows preview app metadata and installability', (tester) async {
    await tester.pumpWidget(_harness(http.Response(_previewAppsJson(), 200)));
    await tester.pumpAndSettle();

    expect(find.text('Clinica Norte Preview'), findsOneWidget);
    expect(find.text('0.1.0+1  •  Available'), findsOneWidget);
    expect(find.textContaining('Channel: preview'), findsOneWidget);
    expect(find.textContaining('Profile: preview'), findsOneWidget);
    expect(find.textContaining('Production pending'), findsOneWidget);
    expect(find.textContaining('Real preview data'), findsOneWidget);
    expect(find.text('Preview: https://preview.nienfos.com/clinica-norte'),
        findsOneWidget);
    expect(
        find.textContaining('android-preview-v0.1.0-build.1'), findsOneWidget);
    expect(find.text('Install'), findsOneWidget);
  });

  testWidgets('shows clear non-installable preview states', (tester) async {
    await tester.pumpWidget(
      _harness(http.Response(_previewAppsJson(includeApk: false), 200)),
    );
    await tester.pumpAndSettle();

    expect(find.text('Clinica Norte Preview'), findsOneWidget);
    expect(find.textContaining('Missing APK asset'), findsOneWidget);
    expect(find.text('Unavailable'), findsOneWidget);
    expect(find.textContaining('Production pending'), findsOneWidget);
  });

  testWidgets('renders production and mock flags for preview apps',
      (tester) async {
    await tester.pumpWidget(
      _harness(
        http.Response(
          _previewAppsJson(productionReady: true, mockOrDemo: true),
          200,
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('Production ready'), findsOneWidget);
    expect(find.textContaining('Mock/demo'), findsOneWidget);
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

  testWidgets('install rewrites loopback APK URL to active bridge host',
      (tester) async {
    final controller = _RecordingInstallController();
    addTearDown(controller.dispose);

    await tester.pumpWidget(
      _harness(
        http.Response(
          _appsJson(
            apkUrl:
                'http://127.0.0.1:8000/app-updates/sat-showroom/apk/tag/sat-showroom.apk?platform=android&channel=stable',
          ),
          200,
        ),
        baseUrl: 'http://bridge.tailnet.test',
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
      'http://bridge.tailnet.test/app-updates/sat-showroom/apk/tag/sat-showroom.apk?platform=android&channel=stable',
    );
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
  String baseUrl = 'http://bridge.test',
  CodexAppUpdaterController? controller,
}) {
  return MaterialApp(
    home: Scaffold(
      body: InstallableAppsSheet(
        apiClient: ApiClient(
          baseUrl: baseUrl,
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

String _appsJson({String? sha256, String? apkUrl}) {
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
        "apkUrl": "${apkUrl ?? 'http://bridge.test/app-updates/sat-showroom/apk/tag/sat-showroom.apk'}",
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

String _previewAppsJson({
  bool includeApk = true,
  bool productionReady = false,
  bool mockOrDemo = false,
}) {
  final apkFields = includeApk
      ? '''
        "latestVersion": "0.1.0",
        "latestBuild": 1,
        "releaseTag": "android-preview-v0.1.0-build.1",
        "apkUrl": "http://bridge.test/app-updates/clinica-norte/apk/tag/clinica-norte.apk",
        "apkAssetName": "clinica-norte.apk",
        "sizeBytes": 2097152,
      '''
      : '''
        "releaseTag": "android-preview-v0.1.0-build.1",
        "apkAssetName": "clinica-norte.apk",
      ''';
  return '''
  {
    "kind": "codex.installableApps",
    "version": 1,
    "apps": [
      {
        "kind": "codex.installableApp",
        "version": 1,
        "sourceApp": "clinica-norte",
        "displayName": "Clinica Norte Preview",
        "repo": "brunojaime/clinica-norte",
        "releaseChannel": "preview",
        $apkFields
        "sha256": null,
        "available": $includeApk,
        "enabled": true,
        "packageId": "com.clinica.norte",
        "installStatusHint": "${includeApk ? 'available' : 'missing_apk_asset'}",
        "previewUrl": "https://preview.nienfos.com/clinica-norte",
        "runtimeProfile": "preview",
        "productionReady": $productionReady,
        "mockOrDemo": $mockOrDemo,
        "releaseMetadata": {"initialPreviewRelease": true}
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
