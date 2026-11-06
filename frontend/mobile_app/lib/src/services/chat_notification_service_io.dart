import 'dart:io';
import 'dart:convert';
import 'dart:async';
import 'dart:typed_data';
import 'dart:ui' as ui;
import 'package:flutter/widgets.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'bridge_push_client.dart';
import 'bridge_push_endpoint.dart';

import 'package:http/http.dart' as http;

import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import 'chat_notification_service.dart';
import 'proposal_notification.dart';

const Map<ChatNotificationChannel, _NotificationChannelSpec> _channelSpecs =
    <ChatNotificationChannel, _NotificationChannelSpec>{
  ChatNotificationChannel.generator: _NotificationChannelSpec(
    id: 'chat_completion_generator',
    name: 'Generator completion',
    description: 'Notifications for finished generator Codex responses.',
  ),
  ChatNotificationChannel.reviewer: _NotificationChannelSpec(
    id: 'chat_completion_reviewer',
    name: 'Reviewer completion',
    description: 'Notifications for finished reviewer Codex responses.',
  ),
  ChatNotificationChannel.summary: _NotificationChannelSpec(
    id: 'chat_completion_summary',
    name: 'Summary completion',
    description: 'Notifications for finished summary Codex responses.',
  ),
  ChatNotificationChannel.generic: _NotificationChannelSpec(
    id: 'chat_completion',
    name: 'Chat completion',
    description: 'Notifications for finished Codex chat responses.',
  ),
};

ChatNotificationService createChatNotificationService() {
  return _LocalChatNotificationService();
}

class _LocalChatNotificationService
    implements
        ChatNotificationService,
        ProposalNotificationService,
        ChatNotificationNavigation,
        ChatPushNotificationSettings {
  _LocalChatNotificationService({this.background = false}) {
    _push = BridgePushClient(
        display: (notice) => _showChatCompleted(notice, fromPush: true),
        openPayload: _handlePayload);
  }
  final bool background;
  late final BridgePushClient _push;
  @override
  Future<Map<String, dynamic>> pushStatus(String server) =>
      _push.status(server);
  @override
  Future<void> enablePush(String server) => _push.enable(server);
  @override
  Future<void> disablePush(String server) => _push.disable(server);
  @override
  Future<void> testPush(String server) => _push.test(server);

  final FlutterLocalNotificationsPlugin _plugin =
      FlutterLocalNotificationsPlugin();
  bool _initialized = false;
  final _chatTaps = StreamController<ChatNotificationTarget>.broadcast();
  ChatNotificationTarget? _pendingChat;
  String? _visibleServer;
  String? _visibleSession;
  final Map<String, int> _readVersions = {};

  @override
  Stream<ChatNotificationTarget> get chatTaps => _chatTaps.stream;

  @override
  ChatNotificationTarget? takePendingChat() {
    final target = _pendingChat;
    _pendingChat = null;
    return target;
  }

  @override
  void setVisibleChat(String? server, String? sessionId) {
    if (server != null && server != _visibleServer) {
      unawaited(_push.refresh(server).catchError((_) {}));
    }
    _visibleServer = server;
    _visibleSession = sessionId;
  }

  @override
  Future<void> readChat(String server, String sessionId, String workspacePath,
      {bool wholeProject = false}) async {
    unawaited(_push.read(server, sessionId, wholeProject: wholeProject));
    final key =
        wholeProject ? '$server:project:$workspacePath' : '$server:$sessionId';
    _readVersions[key] = (_readVersions[key] ?? 0) + 1;
    if (!_supportsNotifications || !_initialized) return;
    await _plugin.cancel(stableNotificationId('$server:$sessionId'));
    if (!wholeProject) return;
    await _plugin.cancel(stableNotificationId('$server:pending'));
    for (final notice in await _plugin.getActiveNotifications()) {
      final target = ChatNotificationTarget.parse(notice.payload);
      if (target?.server == server && target?.workspacePath == workspacePath) {
        await _plugin.cancel(notice.id!);
      }
    }
  }

  Future<Uint8List?> _projectLogo(ChatNotificationTarget target) async {
    final client = http.Client();
    try {
      final uri = Uri.parse(
          '${bridgePushServiceUrl(target.server)}/notifications/projects/${Uri.encodeComponent(target.sessionId)}/logo');
      final response = await client
          .send(http.Request('GET', uri))
          .timeout(const Duration(seconds: 2));
      if (response.statusCode != 200 ||
          (response.contentLength ?? 0) > 512 * 1024) {
        return null;
      }
      final bytes = <int>[];
      await for (final chunk
          in response.stream.timeout(const Duration(seconds: 2))) {
        bytes.addAll(chunk);
        if (bytes.length > 512 * 1024) return null;
      }
      // Decode the bounded raster locally before passing it to Android.
      if (bytes.length < 8) return null;
      final codec = await ui.instantiateImageCodec(Uint8List.fromList(bytes),
          targetWidth: 128, targetHeight: 128, allowUpscaling: false);
      try {
        final frame = await codec.getNextFrame();
        try {
          final png =
              await frame.image.toByteData(format: ui.ImageByteFormat.png);
          if (png == null) return null;
          return png.buffer.asUint8List();
        } finally {
          frame.image.dispose();
        }
      } finally {
        codec.dispose();
      }
    } catch (_) {
      return null;
    } finally {
      client.close();
    }
  }

  final _proposalTaps =
      StreamController<ProposalNotificationTarget>.broadcast();
  ProposalNotificationTarget? _pendingProposal;

  @override
  Stream<ProposalNotificationTarget> get proposalTaps => _proposalTaps.stream;

  @override
  ProposalNotificationTarget? takePendingProposal(String server) {
    final target = _pendingProposal;
    if (target?.server != server) return null;
    _pendingProposal = null;
    return target;
  }

  void _handlePayload(String? payload) {
    try {
      final data = jsonDecode(payload ?? '') as Map<String, dynamic>;
      if (data['type'] == 'bridge_push') {
        unawaited(_push.receive(data, open: true));
        return;
      }
    } catch (_) {/* Other notification kinds have their own parser. */}
    final chat = ChatNotificationTarget.parse(payload);
    if (chat != null) {
      _pendingChat = chat;
      _chatTaps.add(chat);
      return;
    }
    final target = ProposalNotificationTarget.parse(payload);
    if (target == null) return;
    _pendingProposal = target;
    _proposalTaps.add(target);
  }

  @override
  Future<void> showProposal(ProposalNotificationTarget target) async {
    if (!_supportsNotifications) return;
    if (!_initialized) await initialize();
    // Stable ID replaces the same notice rather than multiplying retries.
    var id = 5381;
    for (final unit in '${target.server}:${target.id}'.codeUnits) {
      id = ((id * 33) ^ unit) & 0x7fffffff;
    }
    await _plugin.show(
        id,
        'Propuesta de proyecto',
        'Hay una propuesta para revisar.',
        const NotificationDetails(
          android: AndroidNotificationDetails(
              'agent_proposals', 'Propuestas del agente',
              channelDescription:
                  'Propuestas de mejora que requieren una decisión.',
              importance: Importance.high,
              priority: Priority.high),
          iOS: DarwinNotificationDetails(threadIdentifier: 'agent_proposals'),
        ),
        payload: target.payload);
  }

  @override
  Future<void> initialize() async {
    if (_initialized || !_supportsNotifications) {
      return;
    }

    const initializationSettings = InitializationSettings(
      android: AndroidInitializationSettings('@mipmap/ic_launcher'),
      iOS: DarwinInitializationSettings(
        requestAlertPermission: false,
        requestBadgePermission: false,
        requestSoundPermission: false,
        defaultPresentAlert: true,
        defaultPresentBadge: true,
        defaultPresentSound: true,
      ),
    );

    await _plugin.initialize(initializationSettings,
        onDidReceiveNotificationResponse: (response) =>
            _handlePayload(response.payload));
    final launchDetails = await _plugin.getNotificationAppLaunchDetails();
    if (launchDetails?.didNotificationLaunchApp == true) {
      _handlePayload(launchDetails?.notificationResponse?.payload);
    }

    final androidImplementation = _plugin.resolvePlatformSpecificImplementation<
        AndroidFlutterLocalNotificationsPlugin>();
    for (final spec in _channelSpecs.values) {
      await androidImplementation?.createNotificationChannel(
        AndroidNotificationChannel(
          spec.id,
          spec.name,
          description: spec.description,
          importance: Importance.max,
        ),
      );
    }

    _initialized = true;
    if (Platform.isAndroid) {
      await _push.initialize(
          backgroundHandler: background ? null : bridgeBackgroundPush);
    }
    // Previous releases posted completion notices with no navigation payload.
    for (final notice in await _plugin.getActiveNotifications()) {
      if (notice.payload == null) await _plugin.cancel(notice.id!);
    }
  }

  @override
  Future<void> showChatCompleted(ChatCompletedNotification notification) =>
      _showChatCompleted(notification);

  Future<void> _showChatCompleted(ChatCompletedNotification notification,
      {bool fromPush = false}) async {
    if (!fromPush &&
        notification.target != null &&
        _push.ownsCompletions(notification.target!.server)) {
      return;
    }
    if (!_initialized) {
      await initialize();
    }
    if (!_supportsNotifications) {
      return;
    }

    final target = notification.target;
    bool visible() =>
        target != null &&
        target.server == _visibleServer &&
        target.sessionId == _visibleSession;
    if (visible()) return;
    final chatKey =
        target == null ? '' : '${target.server}:${target.sessionId}';
    final projectKey = target == null
        ? ''
        : '${target.server}:project:${target.workspacePath}';
    final chatVersion = _readVersions[chatKey];
    final projectVersion = _readVersions[projectKey];
    final logo = target == null || !Platform.isAndroid
        ? null
        : await _projectLogo(target);
    if (visible() ||
        _readVersions[chatKey] != chatVersion ||
        _readVersions[projectKey] != projectVersion) {
      return;
    }
    final channel = _resolveChannelSpec(notification.channel);
    await _plugin.show(
      notification.id,
      notification.title,
      notification.body,
      NotificationDetails(
        android: AndroidNotificationDetails(
          channel.id,
          channel.name,
          channelDescription: channel.description,
          importance: Importance.max,
          priority: Priority.high,
          ticker: notification.title,
          autoCancel: true,
          groupKey: target == null
              ? null
              : '${target.server}:${target.workspacePath}',
          largeIcon: logo == null ? null : ByteArrayAndroidBitmap(logo),
          subText: notification.summary,
          styleInformation: BigTextStyleInformation(notification.body),
        ),
        iOS: DarwinNotificationDetails(
          subtitle: notification.summary,
          threadIdentifier: target == null
              ? notification.channel.name
              : '${target.server}:${target.workspacePath}',
          presentAlert: true,
          presentBadge: true,
          presentSound: true,
        ),
      ),
      payload: notification.payload ?? target?.payload,
    );
  }

  bool get _supportsNotifications =>
      Platform.isAndroid || Platform.isIOS || Platform.isMacOS;

  _NotificationChannelSpec _resolveChannelSpec(
    ChatNotificationChannel channel,
  ) {
    return _channelSpecs[channel] ??
        _channelSpecs[ChatNotificationChannel.generic]!;
  }
}

class _NotificationChannelSpec {
  const _NotificationChannelSpec({
    required this.id,
    required this.name,
    required this.description,
  });

  final String id;
  final String name;
  final String description;
}

@pragma('vm:entry-point')
Future<void> bridgeBackgroundPush(RemoteMessage message) async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp();
  final service = _LocalChatNotificationService(background: true);
  await service.initialize();
  await service._push.receive(message.data);
}
