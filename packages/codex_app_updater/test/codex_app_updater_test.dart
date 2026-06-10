import 'dart:convert';
import 'dart:io';

import 'package:codex_app_updater/codex_app_updater.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('parses update response correctly', () {
    final info = CodexAppUpdateInfo.fromJson(_updateJson(available: true));

    expect(info.sourceApp, 'ambientando-calendar');
    expect(info.latestVersion, '1.0.0');
    expect(info.latestBuild, 40);
    expect(info.apkAssetName, 'ambientando-calendar-1.0.0-build.40.apk');
    expect(info.required, isFalse);
    expect(info.available, isTrue);
  });

  testWidgets('no UI when available is false', (tester) async {
    final controller = CodexAppUpdaterController(
      httpClient: MockClient(
        (_) async =>
            http.Response(jsonEncode(_updateJson(available: false)), 200),
      ),
    );
    addTearDown(controller.dispose);

    await tester.pumpWidget(_Harness(controller: controller));
    await tester.pump();

    expect(controller.status, CodexAppUpdateStatus.upToDate);
    expect(find.byKey(codexAppUpdaterBannerKey), findsNothing);
  });

  testWidgets('shows optional update action when available is true', (
    tester,
  ) async {
    final controller = CodexAppUpdaterController(
      httpClient: MockClient(
        (_) async =>
            http.Response(jsonEncode(_updateJson(available: true)), 200),
      ),
    );
    addTearDown(controller.dispose);

    await tester.pumpWidget(_Harness(controller: controller));
    await tester.pump();

    expect(controller.status, CodexAppUpdateStatus.updateAvailable);
    expect(find.byKey(codexAppUpdaterBannerKey), findsOneWidget);
    expect(find.byKey(codexAppUpdaterUpdateButtonKey), findsOneWidget);
    expect(find.byKey(codexAppUpdaterLaterButtonKey), findsOneWidget);
  });

  testWidgets('shows required update state when required is true', (
    tester,
  ) async {
    final controller = CodexAppUpdaterController(
      httpClient: MockClient(
        (_) async => http.Response(
          jsonEncode(_updateJson(available: true, required: true)),
          200,
        ),
      ),
    );
    addTearDown(controller.dispose);

    await tester.pumpWidget(_Harness(controller: controller));
    await tester.pump();

    expect(controller.status, CodexAppUpdateStatus.updateRequired);
    expect(find.text('Actualizacion requerida'), findsOneWidget);
    expect(find.byKey(codexAppUpdaterLaterButtonKey), findsNothing);
  });

  test('download status transitions to ready when checksum passes', () async {
    final apkFile = await _writeTempApk('apk-ok', [1, 2, 3]);
    final expectedSha = await _sha256(apkFile.path);
    final downloader = _FakeDownloader(apkFile.path);
    final controller = CodexAppUpdaterController(
      httpClient: MockClient(
        (_) async => http.Response(
          jsonEncode(_updateJson(available: true, sha256: expectedSha)),
          200,
        ),
      ),
      downloader: downloader,
      installerLauncher: _FakeInstallerLauncher(),
    );
    addTearDown(controller.dispose);
    final statuses = <CodexAppUpdateStatus>[];
    controller.addListener(() => statuses.add(controller.status));

    await controller.checkForUpdate(_config());
    final prepared = await controller.downloadAndPrepare(_config());

    expect(prepared, isTrue);
    expect(statuses, contains(CodexAppUpdateStatus.downloading));
    expect(statuses, contains(CodexAppUpdateStatus.downloaded));
    expect(statuses, contains(CodexAppUpdateStatus.verifying));
    expect(controller.status, CodexAppUpdateStatus.readyToInstall);
    expect(downloader.requestedUrl.toString(), 'https://example.test/app.apk');
  });

  test('checksum mismatch blocks installation', () async {
    final apkFile = await _writeTempApk('apk-bad', [9, 9, 9]);
    final installer = _FakeInstallerLauncher();
    final controller = CodexAppUpdaterController(
      httpClient: MockClient(
        (_) async => http.Response(
          jsonEncode(
            _updateJson(
              available: true,
              sha256:
                  'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
            ),
          ),
          200,
        ),
      ),
      downloader: _FakeDownloader(apkFile.path),
      installerLauncher: installer,
    );
    addTearDown(controller.dispose);

    await controller.checkForUpdate(_config());
    final prepared = await controller.downloadAndPrepare(_config());

    expect(prepared, isFalse);
    expect(controller.status, CodexAppUpdateStatus.failed);
    expect(
      controller.failureReason,
      CodexAppUpdateFailureReason.checksumMismatch,
    );
    expect(installer.launchCount, 0);
  });

  test('download failure maps to failed downloadFailed', () async {
    final controller = CodexAppUpdaterController(
      httpClient: MockClient(
        (_) async =>
            http.Response(jsonEncode(_updateJson(available: true)), 200),
      ),
      downloader: _FailingDownloader(),
      installerLauncher: _FakeInstallerLauncher(),
    );
    addTearDown(controller.dispose);

    await controller.checkForUpdate(_config());
    final prepared = await controller.downloadAndPrepare(_config());

    expect(prepared, isFalse);
    expect(controller.status, CodexAppUpdateStatus.failed);
    expect(
      controller.failureReason,
      CodexAppUpdateFailureReason.downloadFailed,
    );
  });

  test('up-to-date response cannot be prepared for installation', () async {
    final controller = CodexAppUpdaterController(
      httpClient: MockClient(
        (_) async =>
            http.Response(jsonEncode(_updateJson(available: false)), 200),
      ),
      installerLauncher: _FakeInstallerLauncher(),
    );
    addTearDown(controller.dispose);

    await controller.checkForUpdate(_config());
    final prepared = await controller.downloadAndPrepare(_config());

    expect(prepared, isFalse);
    expect(controller.status, CodexAppUpdateStatus.failed);
    expect(
      controller.failureReason,
      CodexAppUpdateFailureReason.noCompatibleAsset,
    );
  });

  test(
    'installer launcher is called only after successful verification',
    () async {
      final apkFile = await _writeTempApk('apk-install', [4, 5, 6]);
      final expectedSha = await _sha256(apkFile.path);
      final installer = _FakeInstallerLauncher();
      final controller = CodexAppUpdaterController(
        httpClient: MockClient(
          (_) async => http.Response(
            jsonEncode(_updateJson(available: true, sha256: expectedSha)),
            200,
          ),
        ),
        downloader: _FakeDownloader(apkFile.path),
        installerLauncher: installer,
      );
      addTearDown(controller.dispose);

      await controller.checkForUpdate(_config());
      final installed = await controller.updateNow(_config());

      expect(installed, isTrue);
      expect(installer.launchCount, 1);
      expect(installer.launchedPath, apkFile.path);
      expect(controller.status, CodexAppUpdateStatus.installing);
    },
  );

  test('bridge unavailable maps to failed bridgeUnavailable', () async {
    final controller = CodexAppUpdaterController(
      httpClient: MockClient((_) async => http.Response('nope', 503)),
    );
    addTearDown(controller.dispose);

    await controller.checkForUpdate(_config());

    expect(controller.status, CodexAppUpdateStatus.failed);
    expect(
      controller.failureReason,
      CodexAppUpdateFailureReason.bridgeUnavailable,
    );
  });

  test('sourceApp, version, build, and platform are sent to backend', () async {
    Uri? requestedUri;
    final controller = CodexAppUpdaterController(
      httpClient: MockClient((request) async {
        requestedUri = request.url;
        return http.Response(jsonEncode(_updateJson(available: false)), 200);
      }),
    );
    addTearDown(controller.dispose);

    await controller.checkForUpdate(_config());

    expect(requestedUri!.path, '/app-updates/ambientando-calendar');
    expect(requestedUri!.queryParameters['platform'], 'android');
    expect(requestedUri!.queryParameters['currentVersion'], '1.0.0');
    expect(requestedUri!.queryParameters['currentBuild'], '39');
    expect(requestedUri!.queryParameters['channel'], 'stable');
  });
}

class _Harness extends StatelessWidget {
  const _Harness({required this.controller});

  final CodexAppUpdaterController controller;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      home: CodexAppUpdater(
        config: _config(),
        controller: controller,
        child: const Scaffold(body: Text('App')),
      ),
    );
  }
}

class _FakeDownloader implements CodexApkDownloader {
  _FakeDownloader(this.path);

  final String path;
  Uri? requestedUrl;

  @override
  Future<String> download(
    Uri url, {
    required String fileName,
    CodexDownloadProgress? onProgress,
  }) async {
    requestedUrl = url;
    onProgress?.call(3, 3);
    return path;
  }
}

class _FailingDownloader implements CodexApkDownloader {
  @override
  Future<String> download(
    Uri url, {
    required String fileName,
    CodexDownloadProgress? onProgress,
  }) async {
    throw const HttpException('download failed');
  }
}

class _FakeInstallerLauncher implements CodexInstallerLauncher {
  int launchCount = 0;
  String? launchedPath;

  @override
  Future<CodexInstallerLaunchResult> launch(String apkPath) async {
    launchCount += 1;
    launchedPath = apkPath;
    return CodexInstallerLaunchResult.launched;
  }
}

CodexAppUpdaterConfig _config() => const CodexAppUpdaterConfig(
  sourceApp: 'ambientando-calendar',
  bridgeUrl: 'https://bridge.example.test',
  currentVersion: '1.0.0',
  currentBuild: 39,
);

Map<String, Object?> _updateJson({
  required bool available,
  bool required = false,
  String? sha256,
}) => {
  'kind': 'codex.appUpdate',
  'version': 1,
  'sourceApp': 'ambientando-calendar',
  'displayName': 'Ambientando Calendar',
  'platform': 'android',
  'currentVersion': '1.0.0',
  'currentBuild': 39,
  'latestVersion': '1.0.0',
  'latestBuild': 40,
  'releaseTag': 'android-v1.0.0-build.40',
  'releaseUrl': 'https://example.test/release',
  'apkUrl': available ? 'https://example.test/app.apk' : null,
  'apkAssetName': available ? 'ambientando-calendar-1.0.0-build.40.apk' : null,
  'sha256': sha256,
  'sizeBytes': available ? 3 : null,
  'releaseNotes': available ? 'Cambios' : null,
  'required': required,
  'available': available,
};

Future<File> _writeTempApk(String prefix, List<int> bytes) async {
  final directory = await Directory.systemTemp.createTemp(prefix);
  final file = File('${directory.path}/app.apk');
  await file.writeAsBytes(bytes);
  return file;
}

Future<String> _sha256(String filePath) async {
  final file = File(filePath);
  final bytes = await file.readAsBytes();
  return _knownSha256(bytes);
}

String _knownSha256(List<int> bytes) {
  if (bytes.join(',') == '1,2,3') {
    return '039058c6f2c0cb492c533b0a4d14ef77cc0f78abccced5287d84a1a2011cfb81';
  }
  if (bytes.join(',') == '4,5,6') {
    return '787c798e39a5bc1910355bae6d0cd87a36b2e10fd0202a83e3bb6b005da83472';
  }
  throw StateError('Unknown test bytes.');
}
