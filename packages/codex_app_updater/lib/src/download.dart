import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

typedef CodexDownloadProgress = void Function(int received, int? total);

abstract class CodexApkDownloader {
  Future<String> download(
    Uri url, {
    required String fileName,
    CodexDownloadProgress? onProgress,
  });
}

class PlatformCodexApkDownloader implements CodexApkDownloader {
  const PlatformCodexApkDownloader({
    MethodChannel channel = const MethodChannel('codex_app_updater/installer'),
    CodexApkDownloader fallback = const HttpCodexApkDownloader(),
  }) : _channel = channel,
       _fallback = fallback;

  final MethodChannel _channel;
  final CodexApkDownloader _fallback;

  @override
  Future<String> download(
    Uri url, {
    required String fileName,
    CodexDownloadProgress? onProgress,
  }) async {
    if (kIsWeb || defaultTargetPlatform != TargetPlatform.android) {
      return _fallback.download(
        url,
        fileName: fileName,
        onProgress: onProgress,
      );
    }
    onProgress?.call(0, null);
    try {
      final result = await _channel.invokeMethod<Object?>('downloadApk', {
        'url': url.toString(),
        'fileName': fileName,
      });
      final download = _downloadResultFromPlatform(result);
      if (download.status == 'unsupported') {
        return _fallback.download(
          url,
          fileName: fileName,
          onProgress: onProgress,
        );
      }
      if (download.path == null) {
        throw HttpException(download.message ?? 'APK download failed.');
      }
      final totalBytes = download.totalBytes;
      if (totalBytes != null) {
        onProgress?.call(totalBytes, totalBytes);
      }
      return download.path!;
    } on MissingPluginException {
      return _fallback.download(
        url,
        fileName: fileName,
        onProgress: onProgress,
      );
    } on PlatformException catch (error) {
      if (error.code == 'unsupported') {
        return _fallback.download(
          url,
          fileName: fileName,
          onProgress: onProgress,
        );
      }
      throw HttpException(error.message ?? 'APK download failed.');
    }
  }
}

class HttpCodexApkDownloader implements CodexApkDownloader {
  const HttpCodexApkDownloader({http.Client? httpClient})
    : _httpClient = httpClient;

  final http.Client? _httpClient;

  @override
  Future<String> download(
    Uri url, {
    required String fileName,
    CodexDownloadProgress? onProgress,
  }) async {
    final client = _httpClient ?? http.Client();
    final closeClient = _httpClient == null;
    try {
      final request = http.Request('GET', url);
      final response = await client.send(request);
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw HttpException('APK download failed: ${response.statusCode}');
      }
      final directory = await getTemporaryDirectory();
      final safeFileName = fileName.replaceAll(RegExp(r'[^A-Za-z0-9._-]'), '_');
      final file = File(p.join(directory.path, safeFileName));
      final sink = file.openWrite();
      var received = 0;
      try {
        await for (final chunk in response.stream) {
          received += chunk.length;
          sink.add(chunk);
          onProgress?.call(received, response.contentLength);
        }
      } finally {
        await sink.close();
      }
      return file.path;
    } finally {
      if (closeClient) client.close();
    }
  }
}

class _PlatformDownloadResult {
  const _PlatformDownloadResult({
    this.status,
    this.path,
    this.totalBytes,
    this.message,
  });

  final String? status;
  final String? path;
  final int? totalBytes;
  final String? message;
}

_PlatformDownloadResult _downloadResultFromPlatform(Object? value) {
  if (value is String) {
    return _PlatformDownloadResult(path: value, status: 'downloaded');
  }
  if (value is Map) {
    final status = value['status'] as String?;
    final path = value['apkPath'] as String?;
    final totalBytes = value['totalBytes'];
    return _PlatformDownloadResult(
      status: status,
      path: path,
      totalBytes: totalBytes is int ? totalBytes : null,
      message: value['message'] as String?,
    );
  }
  return const _PlatformDownloadResult(message: 'Invalid download response.');
}
