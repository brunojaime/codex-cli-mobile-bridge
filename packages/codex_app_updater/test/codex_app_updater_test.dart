import 'dart:async';
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

  testWidgets('stale available response for installed build stays hidden', (
    tester,
  ) async {
    final controller = CodexAppUpdaterController(
      httpClient: MockClient(
        (_) async => http.Response(
          jsonEncode(
            _updateJson(available: true, currentBuild: 55, latestBuild: 55),
          ),
          200,
        ),
      ),
    );
    addTearDown(controller.dispose);

    await tester.pumpWidget(
      _Harness(controller: controller, config: _config(currentBuild: 55)),
    );
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

  testWidgets('available update hides raw release notes and current version', (
    tester,
  ) async {
    const releaseNotes =
        '**Full Changelog**: https://github.com/example/app/compare/old...new';
    final controller = CodexAppUpdaterController(
      httpClient: MockClient(
        (_) async => http.Response(
          jsonEncode(_updateJson(available: true, releaseNotes: releaseNotes)),
          200,
        ),
      ),
    );
    addTearDown(controller.dispose);

    await tester.pumpWidget(_Harness(controller: controller));
    await tester.pump();

    expect(controller.status, CodexAppUpdateStatus.updateAvailable);
    expect(find.byKey(codexAppUpdaterBannerKey), findsOneWidget);
    expect(find.textContaining('Full Changelog'), findsNothing);
    expect(find.textContaining('github.com/example/app'), findsNothing);
    expect(find.textContaining('Versión instalada'), findsNothing);
    expect(find.textContaining('Version instalada'), findsNothing);
    expect(find.textContaining('1.0.0 (39)'), findsNothing);
  });

  testWidgets('available response without APK keeps update action for retry', (
    tester,
  ) async {
    final controller = CodexAppUpdaterController(
      httpClient: MockClient(
        (_) async => http.Response(
          jsonEncode(_updateJson(available: true, includeApk: false)),
          200,
        ),
      ),
    );
    addTearDown(controller.dispose);

    await tester.pumpWidget(_Harness(controller: controller));
    await tester.pump();

    expect(controller.status, CodexAppUpdateStatus.failed);
    expect(
      controller.failureReason,
      CodexAppUpdateFailureReason.noCompatibleAsset,
    );
    expect(find.byKey(codexAppUpdaterBannerKey), findsOneWidget);
    expect(find.byKey(codexAppUpdaterUpdateButtonKey), findsOneWidget);
  });

  test('updateNow rechecks after stale no-APK failure', () async {
    final apkFile = await _writeTempApk('apk-retry', [1, 2, 3]);
    final expectedSha = await _sha256(apkFile.path);
    var requestCount = 0;
    final downloader = _FakeDownloader(apkFile.path);
    final installer = _FakeInstallerLauncher();
    final controller = CodexAppUpdaterController(
      httpClient: MockClient((_) async {
        requestCount += 1;
        if (requestCount == 1) {
          return http.Response(
            jsonEncode(_updateJson(available: true, includeApk: false)),
            200,
          );
        }
        return http.Response(
          jsonEncode(_updateJson(available: true, sha256: expectedSha)),
          200,
        );
      }),
      downloader: downloader,
      installerLauncher: installer,
    );
    addTearDown(controller.dispose);

    await controller.checkForUpdate(_config());

    expect(controller.status, CodexAppUpdateStatus.failed);
    expect(controller.updateInfo?.apkUrl, isNull);

    final updated = await controller.updateNow(_config());

    expect(updated, isTrue);
    expect(requestCount, 2);
    expect(controller.updateInfo?.apkUrl, 'https://example.test/app.apk');
    expect(downloader.downloadCount, 1);
    expect(downloader.requestedUrl.toString(), 'https://example.test/app.apk');
    expect(installer.launchCount, 1);
    expect(controller.status, CodexAppUpdateStatus.dismissed);
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
    expect(find.text('Actualización requerida'), findsOneWidget);
    expect(find.byKey(codexAppUpdaterLaterButtonKey), findsNothing);
  });

  test('config change while check is active rechecks newest build', () async {
    final firstResponse = Completer<http.Response>();
    final requestedBuilds = <String?>[];
    final controller = CodexAppUpdaterController(
      httpClient: MockClient((request) {
        requestedBuilds.add(request.url.queryParameters['currentBuild']);
        if (requestedBuilds.length == 1) {
          return firstResponse.future;
        }
        return Future.value(
          http.Response(
            jsonEncode(
              _updateJson(available: true, currentBuild: 55, latestBuild: 55),
            ),
            200,
          ),
        );
      }),
    );
    addTearDown(controller.dispose);

    final firstCheck = controller.checkForUpdate(_config(currentBuild: 50));
    controller.checkForUpdate(_config(currentBuild: 55));

    firstResponse.complete(
      http.Response(
        jsonEncode(
          _updateJson(available: true, currentBuild: 50, latestBuild: 55),
        ),
        200,
      ),
    );
    await firstCheck;
    for (var tick = 0; tick < 10 && requestedBuilds.length < 2; tick += 1) {
      await Future<void>.delayed(Duration.zero);
    }

    expect(requestedBuilds, <String?>['50', '55']);
    expect(controller.status, CodexAppUpdateStatus.upToDate);
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
      expect(controller.status, CodexAppUpdateStatus.dismissed);
    },
  );

  test('download OK and launcher OK dismisses stale update prompt', () async {
    final apkFile = await _writeTempApk('apk-launch-ok', [1, 2, 3]);
    final installer = _FakeInstallerLauncher();
    final controller = CodexAppUpdaterController(
      httpClient: MockClient(
        (_) async =>
            http.Response(jsonEncode(_updateJson(available: true)), 200),
      ),
      downloader: _FakeDownloader(apkFile.path),
      installerLauncher: installer,
    );
    addTearDown(controller.dispose);

    final installed = await controller.updateNow(_config());

    expect(installed, isTrue);
    expect(installer.launchCount, 1);
    expect(installer.launchedPath, apkFile.path);
    expect(controller.status, CodexAppUpdateStatus.dismissed);
  });

  test(
    'download OK and unknown sources permission required is recoverable',
    () async {
      final apkFile = await _writeTempApk('apk-permission', [1, 2, 3]);
      final downloader = _FakeDownloader(apkFile.path);
      final installer = _FakeInstallerLauncher(
        results: const [
          CodexInstallerLaunchResult.unknownSourcesPermissionRequired,
          CodexInstallerLaunchResult.installerLaunched,
        ],
      );
      final controller = CodexAppUpdaterController(
        httpClient: MockClient(
          (_) async =>
              http.Response(jsonEncode(_updateJson(available: true)), 200),
        ),
        downloader: downloader,
        installerLauncher: installer,
      );
      addTearDown(controller.dispose);

      final first = await controller.updateNow(_config());

      expect(first, isFalse);
      expect(controller.status, CodexAppUpdateStatus.waitingForPermission);
      expect(
        controller.failureReason,
        CodexAppUpdateFailureReason.permissionRequired,
      );
      expect(controller.downloadedApkPath, apkFile.path);
      expect(downloader.downloadCount, 1);
      expect(installer.launchCount, 1);

      final retry = await controller.updateNow(_config());

      expect(retry, isTrue);
      expect(controller.status, CodexAppUpdateStatus.dismissed);
      expect(downloader.downloadCount, 1);
      expect(installer.launchCount, 2);
      expect(installer.launchedPath, apkFile.path);
    },
  );

  test('waiting for permission exposes install retry action', () async {
    final apkFile = await _writeTempApk('apk-permission-ui', [1, 2, 3]);
    final installer = _FakeInstallerLauncher(
      results: const [
        CodexInstallerLaunchResult.unknownSourcesPermissionRequired,
      ],
    );
    final controller = CodexAppUpdaterController(
      httpClient: MockClient(
        (_) async =>
            http.Response(jsonEncode(_updateJson(available: true)), 200),
      ),
      downloader: _FakeDownloader(apkFile.path),
      installerLauncher: installer,
    );
    addTearDown(controller.dispose);

    await controller.updateNow(_config());

    expect(controller.status, CodexAppUpdateStatus.waitingForPermission);
    expect(controller.canRetryInstallPreparedApk, isTrue);
  });

  test('native launcher failure keeps prepared APK retryable', () async {
    final apkFile = await _writeTempApk('apk-native-fail', [1, 2, 3]);
    final downloader = _FakeDownloader(apkFile.path);
    final installer = _FakeInstallerLauncher(
      results: const [
        CodexInstallerLaunchResult.securityException,
        CodexInstallerLaunchResult.installerLaunched,
      ],
    );
    final controller = CodexAppUpdaterController(
      httpClient: MockClient(
        (_) async =>
            http.Response(jsonEncode(_updateJson(available: true)), 200),
      ),
      downloader: downloader,
      installerLauncher: installer,
    );
    addTearDown(controller.dispose);

    final first = await controller.updateNow(_config());

    expect(first, isFalse);
    expect(controller.status, CodexAppUpdateStatus.failed);
    expect(
      controller.failureReason,
      CodexAppUpdateFailureReason.securityException,
    );
    expect(controller.downloadedApkPath, apkFile.path);

    final retry = await controller.updateNow(_config());

    expect(retry, isTrue);
    expect(controller.status, CodexAppUpdateStatus.dismissed);
    expect(downloader.downloadCount, 1);
    expect(installer.launchCount, 2);
  });

  test(
    'double install tap after permission does not launch in parallel',
    () async {
      final apkFile = await _writeTempApk('apk-install-coalesce', [1, 2, 3]);
      final launchCompleter = Completer<CodexInstallerLaunchResult>();
      final installer = _CompletingInstallerLauncher(launchCompleter.future);
      final controller = CodexAppUpdaterController(
        httpClient: MockClient(
          (_) async =>
              http.Response(jsonEncode(_updateJson(available: true)), 200),
        ),
        downloader: _FakeDownloader(apkFile.path),
        installerLauncher: installer,
      );
      addTearDown(controller.dispose);

      await controller.checkForUpdate(_config());
      expect(await controller.downloadAndPrepare(_config()), isTrue);
      final first = controller.updateNow(_config());
      final second = controller.updateNow(_config());

      expect(identical(first, second), isTrue);
      await Future<void>.delayed(Duration.zero);
      expect(installer.launchCount, 1);

      launchCompleter.complete(CodexInstallerLaunchResult.installerLaunched);

      expect(await first, isTrue);
      expect(await second, isTrue);
      expect(installer.launchCount, 1);
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

  testWidgets('failed bridge check shows update action for retry', (
    tester,
  ) async {
    final controller = CodexAppUpdaterController(
      httpClient: MockClient((_) async => http.Response('nope', 503)),
    );
    addTearDown(controller.dispose);

    await tester.pumpWidget(_Harness(controller: controller));
    await tester.pump();

    expect(controller.status, CodexAppUpdateStatus.failed);
    expect(find.byKey(codexAppUpdaterBannerKey), findsOneWidget);
    expect(find.byKey(codexAppUpdaterUpdateButtonKey), findsOneWidget);
  });

  test(
    'double update tap after failure coalesces into one retry flow',
    () async {
      final apkFile = await _writeTempApk('apk-coalesce', [4, 5, 6]);
      final expectedSha = await _sha256(apkFile.path);
      var requestCount = 0;
      final retryResponse = Completer<http.Response>();
      final downloader = _FakeDownloader(apkFile.path);
      final installer = _FakeInstallerLauncher();
      final controller = CodexAppUpdaterController(
        httpClient: MockClient((_) {
          requestCount += 1;
          if (requestCount == 1) {
            return Future.value(
              http.Response(
                jsonEncode(_updateJson(available: true, includeApk: false)),
                200,
              ),
            );
          }
          return retryResponse.future;
        }),
        downloader: downloader,
        installerLauncher: installer,
      );
      addTearDown(controller.dispose);

      await controller.checkForUpdate(_config());
      expect(controller.status, CodexAppUpdateStatus.failed);
      expect(controller.updateInfo?.apkUrl, isNull);

      final first = controller.updateNow(_config());
      final second = controller.updateNow(_config());

      expect(identical(first, second), isTrue);
      await Future<void>.delayed(Duration.zero);
      expect(requestCount, 2);

      retryResponse.complete(
        http.Response(
          jsonEncode(_updateJson(available: true, sha256: expectedSha)),
          200,
        ),
      );

      expect(await first, isTrue);
      expect(await second, isTrue);
      expect(requestCount, 2);
      expect(downloader.downloadCount, 1);
      expect(installer.launchCount, 1);
      expect(controller.updateInfo?.apkUrl, 'https://example.test/app.apk');
    },
  );

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
  const _Harness({required this.controller, this.config = _defaultConfig});

  final CodexAppUpdaterController controller;
  final CodexAppUpdaterConfig config;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      home: CodexAppUpdater(
        config: config,
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
  int downloadCount = 0;

  @override
  Future<String> download(
    Uri url, {
    required String fileName,
    CodexDownloadProgress? onProgress,
  }) async {
    downloadCount += 1;
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
  _FakeInstallerLauncher({List<CodexInstallerLaunchResult>? results})
    : _results = List<CodexInstallerLaunchResult>.from(
        results ?? const [CodexInstallerLaunchResult.installerLaunched],
      );

  final List<CodexInstallerLaunchResult> _results;
  int launchCount = 0;
  String? launchedPath;

  @override
  Future<CodexInstallerLaunchResult> launch(String apkPath) async {
    launchCount += 1;
    launchedPath = apkPath;
    if (_results.length > 1) {
      return _results.removeAt(0);
    }
    return _results.first;
  }
}

class _CompletingInstallerLauncher implements CodexInstallerLauncher {
  _CompletingInstallerLauncher(this.result);

  final Future<CodexInstallerLaunchResult> result;
  int launchCount = 0;

  @override
  Future<CodexInstallerLaunchResult> launch(String apkPath) {
    launchCount += 1;
    return result;
  }
}

const _defaultConfig = CodexAppUpdaterConfig(
  sourceApp: 'ambientando-calendar',
  bridgeUrl: 'https://bridge.example.test',
  currentVersion: '1.0.0',
  currentBuild: 39,
);

CodexAppUpdaterConfig _config({int currentBuild = 39}) => CodexAppUpdaterConfig(
  sourceApp: 'ambientando-calendar',
  bridgeUrl: 'https://bridge.example.test',
  currentVersion: '1.0.0',
  currentBuild: currentBuild,
);

Map<String, Object?> _updateJson({
  required bool available,
  bool required = false,
  String? sha256,
  bool includeApk = true,
  int currentBuild = 39,
  int latestBuild = 40,
  String? releaseNotes,
}) => {
  'kind': 'codex.appUpdate',
  'version': 1,
  'sourceApp': 'ambientando-calendar',
  'displayName': 'Ambientando Calendar',
  'platform': 'android',
  'currentVersion': '1.0.0',
  'currentBuild': currentBuild,
  'latestVersion': '1.0.0',
  'latestBuild': latestBuild,
  'releaseTag': 'android-v1.0.0-build.$latestBuild',
  'releaseUrl': 'https://example.test/release',
  'apkUrl': available && includeApk ? 'https://example.test/app.apk' : null,
  'apkAssetName': available && includeApk
      ? 'ambientando-calendar-1.0.0-build.$latestBuild.apk'
      : null,
  'sha256': sha256,
  'sizeBytes': available ? 3 : null,
  'releaseNotes': available ? releaseNotes ?? 'Cambios' : null,
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
