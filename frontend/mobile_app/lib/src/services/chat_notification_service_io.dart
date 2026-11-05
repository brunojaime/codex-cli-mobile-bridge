import 'dart:io';
import 'dart:async';

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
    implements ChatNotificationService, ProposalNotificationService {
  _LocalChatNotificationService();

  final FlutterLocalNotificationsPlugin _plugin =
      FlutterLocalNotificationsPlugin();
  bool _initialized = false;
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
    await androidImplementation?.requestNotificationsPermission();

    final iosImplementation = _plugin.resolvePlatformSpecificImplementation<
        IOSFlutterLocalNotificationsPlugin>();
    await iosImplementation?.requestPermissions(
      alert: true,
      badge: true,
      sound: true,
    );

    final macosImplementation = _plugin.resolvePlatformSpecificImplementation<
        MacOSFlutterLocalNotificationsPlugin>();
    await macosImplementation?.requestPermissions(
      alert: true,
      badge: true,
      sound: true,
    );

    _initialized = true;
  }

  @override
  Future<void> showChatCompleted(ChatCompletedNotification notification) async {
    if (!_initialized) {
      await initialize();
    }
    if (!_supportsNotifications) {
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
          ticker: '${channel.name} finished',
          styleInformation: BigTextStyleInformation(notification.body),
        ),
        iOS: DarwinNotificationDetails(
          subtitle: notification.summary,
          threadIdentifier: notification.channel.name,
          presentAlert: true,
          presentBadge: true,
          presentSound: true,
        ),
      ),
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
