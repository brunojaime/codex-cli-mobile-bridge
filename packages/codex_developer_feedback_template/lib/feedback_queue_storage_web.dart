import 'package:web/web.dart' as web;
import 'feedback_queue_storage.dart';

DeveloperFeedbackQueueStorage createFeedbackQueueStorage() => _BrowserStorage();

class _BrowserStorage implements DeveloperFeedbackQueueStorage {
  @override
  Future<String?> read(String key) async =>
      web.window.localStorage.getItem(key);
  @override
  Future<void> write(String key, String value) async =>
      web.window.localStorage.setItem(key, value);
}
