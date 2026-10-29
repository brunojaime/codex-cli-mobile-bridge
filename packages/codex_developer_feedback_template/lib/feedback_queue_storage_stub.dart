import 'feedback_queue_storage.dart';

DeveloperFeedbackQueueStorage createFeedbackQueueStorage() =>
    throw UnsupportedError(
      'Persistent feedback storage is unavailable on this platform.',
    );
