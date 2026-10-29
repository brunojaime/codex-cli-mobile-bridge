import 'feedback_queue_storage_stub.dart'
    if (dart.library.io) 'feedback_queue_storage_io.dart'
    if (dart.library.js_interop) 'feedback_queue_storage_web.dart'
    as platform;

abstract class DeveloperFeedbackQueueStorage {
  Future<String?> read(String key);
  Future<void> write(String key, String value);
}

/// Override in tests or a host with an approved encrypted storage port.
DeveloperFeedbackQueueStorage Function() developerFeedbackQueueStorageFactory =
    platform.createFeedbackQueueStorage;
