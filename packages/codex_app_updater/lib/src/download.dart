import 'dart:async';
import 'dart:io';

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

class HttpCodexApkDownloader implements CodexApkDownloader {
  HttpCodexApkDownloader({http.Client? httpClient}) : _httpClient = httpClient;

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
