import 'chat_notification_service_stub.dart'
    if (dart.library.io) 'chat_notification_service_io.dart' as impl;

enum ChatNotificationChannel { generic, generator, reviewer, summary }

abstract class ChatNotificationService {
  const ChatNotificationService();

  Future<void> initialize();

  Future<void> showChatCompleted(ChatCompletedNotification notification);
}

class ChatCompletedNotification {
  const ChatCompletedNotification({
    required this.id,
    required this.title,
    required this.body,
    required this.channel,
    this.summary,
  });

  final int id;
  final String title;
  final String body;
  final ChatNotificationChannel channel;
  final String? summary;
}

class NoopChatNotificationService implements ChatNotificationService {
  const NoopChatNotificationService();

  @override
  Future<void> initialize() async {}

  @override
  Future<void> showChatCompleted(ChatCompletedNotification notification) async {
    return;
  }
}

ChatNotificationService createChatNotificationService() {
  return impl.createChatNotificationService();
}
