import 'dart:io';
import 'dart:convert';
import 'package:crypto/crypto.dart';
import 'package:path_provider/path_provider.dart';
import 'feedback_queue_storage.dart';

DeveloperFeedbackQueueStorage createFeedbackQueueStorage() => _FileStorage();

class _FileStorage implements DeveloperFeedbackQueueStorage {
  Future<File> _file(String key) async {
    final support = await getApplicationSupportDirectory();
    final directory = Directory('${support.path}/codex-feedback');
    await directory.create(recursive: true);
    return File('${directory.path}/${sha256.convert(utf8.encode(key))}.json');
  }

  @override
  Future<String?> read(String key) async {
    final file = await _file(key);
    return await file.exists() ? file.readAsString() : null;
  }

  @override
  Future<void> write(String key, String value) async {
    final file = await _file(key);
    final pending = File(
      '${file.path}.${DateTime.now().microsecondsSinceEpoch}.pending',
    );
    await pending.writeAsString(value, flush: true);
    await pending.rename(file.path);
  }
}
