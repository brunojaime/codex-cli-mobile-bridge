import 'dart:convert';

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
    this.target,
    this.payload,
  });

  final int id;
  final String title;
  final String body;
  final ChatNotificationChannel channel;
  final String? summary;
  final ChatNotificationTarget? target;
  final String? payload;
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

/// Optional platform navigation capabilities; test and web services stay simple.
abstract interface class ChatNotificationNavigation {
  Stream<ChatNotificationTarget> get chatTaps;
  ChatNotificationTarget? takePendingChat();
  Future<void> readChat(String server, String sessionId, String workspacePath,
      {bool wholeProject = false});
  void setVisibleChat(String? server, String? sessionId);
}

class ChatNotificationTarget {
  const ChatNotificationTarget(
      {required this.server,
      required this.sessionId,
      required this.jobId,
      required this.workspacePath,
      this.messageId});
  final String server;
  final String sessionId;
  final String jobId;
  final String workspacePath;
  final String? messageId;
  String get payload => jsonEncode({
        'type': 'chat_completion',
        'server': server,
        'session_id': sessionId,
        'job_id': jobId,
        'workspace_path': workspacePath,
        'message_id': messageId
      });
  int get notificationId => stableNotificationId('$server:$sessionId');
  static ChatNotificationTarget? parse(String? payload) {
    try {
      final value = jsonDecode(payload ?? '') as Map<String, dynamic>;
      if (value['type'] != 'chat_completion') return null;
      for (final key in ['server', 'session_id', 'job_id', 'workspace_path']) {
        if (value[key] is! String || (value[key] as String).isEmpty) {
          return null;
        }
      }
      final server = Uri.tryParse(value['server'] as String);
      if (server == null ||
          !['http', 'https'].contains(server.scheme) ||
          server.host.isEmpty) {
        return null;
      }
      return ChatNotificationTarget(
          server: value['server'] as String,
          sessionId: value['session_id'] as String,
          jobId: value['job_id'] as String,
          workspacePath: value['workspace_path'] as String,
          messageId: value['message_id'] as String?);
    } catch (_) {
      return null;
    }
  }
}

// Stable across process restarts, unlike String.hashCode's contract.
int stableNotificationId(String value) {
  var id = 5381;
  for (final unit in value.codeUnits) {
    id = ((id * 33) ^ unit) & 0x7fffffff;
  }
  return id;
}

abstract interface class ChatPushNotificationSettings {
  Future<Map<String, dynamic>> pushStatus(String server);
  Future<void> enablePush(String server);
  Future<void> disablePush(String server);
  Future<void> testPush(String server);
}
