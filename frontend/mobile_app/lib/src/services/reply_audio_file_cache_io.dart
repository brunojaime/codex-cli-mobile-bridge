import 'dart:io';

import 'package:path_provider/path_provider.dart';

Future<String> cacheReplyAudioFile(
  List<int> bytes, {
  required String fileExtension,
}) async {
  final directory = await getTemporaryDirectory();
  final normalizedExtension =
      fileExtension.startsWith('.') ? fileExtension : '.$fileExtension';
  final file = File(
    '${directory.path}/codex-reply-${DateTime.now().microsecondsSinceEpoch}$normalizedExtension',
  );
  await file.writeAsBytes(bytes, flush: true);
  return file.path;
}

Future<void> deleteReplyAudioFile(String path) async {
  final file = File(path);
  if (await file.exists()) {
    await file.delete();
  }
}
