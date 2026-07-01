import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:codex_app_updater/codex_app_updater.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:package_info_plus/package_info_plus.dart';

import 'developer_feedback_audio_recorder.dart';
import 'developer_feedback_audio_recorder_contract.dart';

export 'codex_local_demo.dart';

typedef DeveloperFeedbackRecorderFactory =
    DeveloperFeedbackAudioRecorder Function();
typedef DeveloperFeedbackCopyText = Future<void> Function(String text);
typedef DeveloperFeedbackBridgeSubmit =
    Future<void> Function(DeveloperFeedbackItem item);
typedef DeveloperFeedbackBridgeSubmitBatch =
    Future<void> Function(DeveloperFeedbackBatch batch);
typedef DeveloperFeedbackContextMetadataBuilder =
    Map<String, Object?> Function(BuildContext context);

const developerFeedbackTemplateEnabled =
    bool.fromEnvironment('CODEX_FEEDBACK_TEMPLATE_ENABLED') ||
    bool.fromEnvironment('DEVELOPER_FEEDBACK_TEMPLATE_ENABLED') ||
    bool.fromEnvironment('ENABLE_DEVELOPER_FEEDBACK_TEMPLATE');
const developerFeedbackBridgeUrl = String.fromEnvironment(
  'CODEX_FEEDBACK_BRIDGE_URL',
);
const developerFeedbackAppUpdaterBridgeUrl = String.fromEnvironment(
  'CODEX_APP_UPDATER_BRIDGE_URL',
);
const developerFeedbackSourceApp = String.fromEnvironment(
  'CODEX_FEEDBACK_SOURCE_APP',
  defaultValue: 'unknown',
);
const developerFeedbackSourceDisplayName = String.fromEnvironment(
  'CODEX_FEEDBACK_SOURCE_NAME',
);
const developerFeedbackRoleAuthEnabled = bool.fromEnvironment(
  'CODEX_FEEDBACK_ROLE_AUTH_ENABLED',
);
const developerFeedbackAdminRoleLoginEnabled = bool.fromEnvironment(
  'CODEX_FEEDBACK_ADMIN_ROLE_LOGIN_ENABLED',
);
const developerFeedbackRoleGateEnabled =
    developerFeedbackRoleAuthEnabled || developerFeedbackAdminRoleLoginEnabled;
const developerFeedbackAdminRoleId = String.fromEnvironment(
  'CODEX_FEEDBACK_ADMIN_ROLE_ID',
  defaultValue: 'admin',
);
const developerFeedbackAdminRoleLabel = String.fromEnvironment(
  'CODEX_FEEDBACK_ADMIN_ROLE_LABEL',
  defaultValue: 'Administrador',
);
const developerFeedbackAdminUsername = String.fromEnvironment(
  'CODEX_FEEDBACK_ADMIN_USERNAME',
  defaultValue: 'admin',
);
const developerFeedbackAdminPassword = String.fromEnvironment(
  'CODEX_FEEDBACK_ADMIN_PASSWORD',
  defaultValue: 'admin',
);
const developerFeedbackImageCaptureKind = 'codex.liveFeedback.imageCapture';
const developerFeedbackGuidedTraceKind = 'codex.liveFeedback.guidedTrace';

const developerFeedbackToolbarKey = Key('developer-feedback-toolbar');
const developerFeedbackToolbarCollapseKey = Key(
  'developer-feedback-toolbar-collapse',
);
const developerFeedbackToolbarExpandKey = Key(
  'developer-feedback-toolbar-expand',
);
const developerFeedbackSwitchKey = Key('developer-feedback-switch');
const developerFeedbackOverlayKey = Key('developer-feedback-overlay');
const developerFeedbackCommentKey = Key('developer-feedback-comment');
const developerFeedbackSaveKey = Key('developer-feedback-save');
const developerFeedbackPendingKey = Key('developer-feedback-pending');
const developerFeedbackCopyKey = Key('developer-feedback-copy');
const developerFeedbackClearKey = Key('developer-feedback-clear');
const developerFeedbackPresetDropdownKey = Key(
  'developer-feedback-preset-dropdown',
);
const developerFeedbackReleaseWhenCompleteKey = Key(
  'developer-feedback-release-when-complete',
);
const developerFeedbackSendBatchKey = Key('developer-feedback-send-batch');
const developerFeedbackPreviewItemKey = Key('developer-feedback-preview-item');
const developerFeedbackPreviewCommentKey = Key(
  'developer-feedback-preview-comment',
);
const developerFeedbackEditCommentKey = Key('developer-feedback-edit-comment');
const developerFeedbackPreviewThumbnailKey = Key(
  'developer-feedback-preview-thumbnail',
);
const developerFeedbackPreviewBoundsKey = Key(
  'developer-feedback-preview-bounds',
);
const developerFeedbackPreviewAudioKey = Key(
  'developer-feedback-preview-audio',
);
const developerFeedbackRunsKey = Key('developer-feedback-runs');
const developerFeedbackRunStatusKey = Key('developer-feedback-run-status');
const developerFeedbackRefreshRunKey = Key('developer-feedback-refresh-run');
const developerFeedbackHistoryKey = Key('developer-feedback-history');
const developerFeedbackHistoryItemKey = Key('developer-feedback-history-item');
const developerFeedbackHistoryRefreshKey = Key(
  'developer-feedback-history-refresh',
);
const developerFeedbackSummaryKey = Key('developer-feedback-summary');
const developerFeedbackSummaryOpenKey = Key('developer-feedback-summary-open');
const developerFeedbackNotificationBellKey = Key(
  'developer-feedback-notification-bell',
);
const developerFeedbackNotificationCenterKey = Key(
  'developer-feedback-notification-center',
);
const developerFeedbackNotificationItemKey = Key(
  'developer-feedback-notification-item',
);
const developerFeedbackNotificationMarkReadKey = Key(
  'developer-feedback-notification-mark-read',
);
const developerFeedbackQuickAskActionKey = Key(
  'developer-feedback-quick-ask-action',
);
const developerFeedbackQuickAskQuestionKey = Key(
  'developer-feedback-quick-ask-question',
);
const developerFeedbackQuickAskSubmitKey = Key(
  'developer-feedback-quick-ask-submit',
);
const developerFeedbackQuickAskAnswerKey = Key(
  'developer-feedback-quick-ask-answer',
);
const developerFeedbackQuickAskHistoryKey = Key(
  'developer-feedback-quick-ask-history',
);
const developerFeedbackQuickAskHistoryItemKey = Key(
  'developer-feedback-quick-ask-history-item',
);
const developerFeedbackQuickAskPreviewKey = Key(
  'developer-feedback-quick-ask-preview',
);
const developerFeedbackQuickAskBoundsKey = Key(
  'developer-feedback-quick-ask-bounds',
);
const developerFeedbackQuickAskActKey = Key('developer-feedback-quick-ask-act');
const developerFeedbackCommentActionKey = Key(
  'developer-feedback-comment-action',
);
const developerFeedbackGuidedTraceStartKey = Key(
  'developer-feedback-guided-trace-start',
);
const developerFeedbackGuidedTraceStopKey = Key(
  'developer-feedback-guided-trace-stop',
);
const developerFeedbackGuidedTraceDiscardKey = Key(
  'developer-feedback-guided-trace-discard',
);
const developerFeedbackGuidedTraceBannerKey = Key(
  'developer-feedback-guided-trace-banner',
);
const developerFeedbackGuidedTraceCommentKey = Key(
  'developer-feedback-guided-trace-comment',
);
const developerFeedbackGuidedTraceAttachKey = Key(
  'developer-feedback-guided-trace-attach',
);
const developerFeedbackGuidedTraceRerecordKey = Key(
  'developer-feedback-guided-trace-rerecord',
);
const developerFeedbackResetSelectionKey = Key(
  'developer-feedback-reset-selection',
);
const developerFeedbackBridgeUnavailableKey = Key(
  'developer-feedback-bridge-unavailable',
);
const developerFeedbackRoleLoginKey = Key('developer-feedback-role-login');
const developerFeedbackRoleDropdownKey = Key(
  'developer-feedback-role-dropdown',
);
const developerFeedbackRoleButtonKey = Key('developer-feedback-role-button');
const developerFeedbackUsernameKey = Key('developer-feedback-username');
const developerFeedbackPasswordKey = Key('developer-feedback-password');
const developerFeedbackCredentialLoginKey = Key(
  'developer-feedback-credential-login',
);
const developerFeedbackRoleLoginErrorKey = Key(
  'developer-feedback-role-login-error',
);

String resolveDeveloperFeedbackBridgeUrl({
  String feedbackBridgeUrl = developerFeedbackBridgeUrl,
  String appUpdaterBridgeUrl = developerFeedbackAppUpdaterBridgeUrl,
}) {
  final feedback = feedbackBridgeUrl.trim();
  if (feedback.isNotEmpty) return feedback;
  return appUpdaterBridgeUrl.trim();
}

String resolveCodexAppUpdaterBridgeUrl({
  String appUpdaterBridgeUrl = developerFeedbackAppUpdaterBridgeUrl,
  String feedbackBridgeUrl = developerFeedbackBridgeUrl,
}) {
  final updater = appUpdaterBridgeUrl.trim();
  if (updater.isNotEmpty) return updater;
  return feedbackBridgeUrl.trim();
}

class DeveloperFeedbackRole {
  const DeveloperFeedbackRole({
    required this.id,
    required this.label,
    this.isAdmin = false,
  });

  static const admin = DeveloperFeedbackRole(
    id: developerFeedbackAdminRoleId,
    label: developerFeedbackAdminRoleLabel,
    isAdmin: true,
  );

  final String id;
  final String label;
  final bool isAdmin;
}

class DeveloperFeedbackCredential {
  const DeveloperFeedbackCredential({
    required this.username,
    required this.password,
    required this.roleId,
  });

  static const admin = DeveloperFeedbackCredential(
    username: developerFeedbackAdminUsername,
    password: developerFeedbackAdminPassword,
    roleId: developerFeedbackAdminRoleId,
  );

  final String username;
  final String password;
  final String roleId;
}

class DeveloperFeedbackRoleSession {
  const DeveloperFeedbackRoleSession({
    required this.role,
    this.username,
    this.credentialLogin = false,
  });

  final DeveloperFeedbackRole role;
  final String? username;
  final bool credentialLogin;
}

class DeveloperFeedbackRoleScope extends InheritedWidget {
  const DeveloperFeedbackRoleScope({
    required this.session,
    required super.child,
    super.key,
  });

  final DeveloperFeedbackRoleSession? session;

  static DeveloperFeedbackRoleSession? maybeOf(BuildContext context) {
    return context
        .dependOnInheritedWidgetOfExactType<DeveloperFeedbackRoleScope>()
        ?.session;
  }

  static DeveloperFeedbackRoleSession of(BuildContext context) {
    final session = maybeOf(context);
    assert(session != null, 'No DeveloperFeedbackRoleScope found.');
    return session!;
  }

  @override
  bool updateShouldNotify(covariant DeveloperFeedbackRoleScope oldWidget) {
    return oldWidget.session != session;
  }
}

class CodexDeveloperRoleGate extends StatefulWidget {
  const CodexDeveloperRoleGate({
    required this.child,
    this.enabled = developerFeedbackRoleGateEnabled,
    this.roles = const <DeveloperFeedbackRole>[DeveloperFeedbackRole.admin],
    this.credentials = const <DeveloperFeedbackCredential>[
      DeveloperFeedbackCredential.admin,
    ],
    this.allowRoleLogin = developerFeedbackAdminRoleLoginEnabled,
    this.allowCredentialLogin = developerFeedbackRoleAuthEnabled,
    this.title = 'Ingresar',
    this.onSessionChanged,
    super.key,
  });

  final Widget child;
  final bool enabled;
  final List<DeveloperFeedbackRole> roles;
  final List<DeveloperFeedbackCredential> credentials;
  final bool allowRoleLogin;
  final bool allowCredentialLogin;
  final String title;
  final ValueChanged<DeveloperFeedbackRoleSession?>? onSessionChanged;

  @override
  State<CodexDeveloperRoleGate> createState() => _CodexDeveloperRoleGateState();
}

class _CodexDeveloperRoleGateState extends State<CodexDeveloperRoleGate> {
  final _usernameController = TextEditingController();
  final _passwordController = TextEditingController();
  DeveloperFeedbackRole? _selectedRole;
  DeveloperFeedbackRoleSession? _session;
  String? _error;

  @override
  void dispose() {
    _usernameController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.enabled) {
      return DeveloperFeedbackRoleScope(session: null, child: widget.child);
    }
    final session = _session;
    if (session != null) {
      return DeveloperFeedbackRoleScope(session: session, child: widget.child);
    }
    final showRoleLogin = widget.allowRoleLogin && widget.roles.isNotEmpty;
    final showCredentialLogin =
        widget.allowCredentialLogin && widget.credentials.isNotEmpty;
    if (!showRoleLogin && !showCredentialLogin) {
      return DeveloperFeedbackRoleScope(session: null, child: widget.child);
    }
    final selectedRole = _selectedRoleOrDefault();
    return Scaffold(
      key: developerFeedbackRoleLoginKey,
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: <Widget>[
                  Text(
                    widget.title,
                    style: Theme.of(context).textTheme.headlineSmall,
                  ),
                  if (showRoleLogin) ...[
                    const SizedBox(height: 20),
                    DropdownButtonFormField<DeveloperFeedbackRole>(
                      key: developerFeedbackRoleDropdownKey,
                      initialValue: selectedRole,
                      decoration: const InputDecoration(
                        labelText: 'Rol',
                        border: OutlineInputBorder(),
                      ),
                      items: [
                        for (final role in widget.roles)
                          DropdownMenuItem(
                            value: role,
                            child: Text(role.label),
                          ),
                      ],
                      onChanged: (role) {
                        setState(() => _selectedRole = role);
                      },
                    ),
                    const SizedBox(height: 12),
                    FilledButton.icon(
                      key: developerFeedbackRoleButtonKey,
                      onPressed: selectedRole == null
                          ? null
                          : () => _setSession(
                              DeveloperFeedbackRoleSession(role: selectedRole),
                            ),
                      icon: Icon(
                        selectedRole?.isAdmin == true
                            ? Icons.admin_panel_settings_outlined
                            : Icons.badge_outlined,
                      ),
                      label: const Text('Ingresar'),
                    ),
                  ],
                  if (showCredentialLogin) ...[
                    const SizedBox(height: 12),
                    TextField(
                      key: developerFeedbackUsernameKey,
                      controller: _usernameController,
                      decoration: const InputDecoration(
                        labelText: 'Usuario',
                        border: OutlineInputBorder(),
                      ),
                      textInputAction: TextInputAction.next,
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      key: developerFeedbackPasswordKey,
                      controller: _passwordController,
                      obscureText: true,
                      decoration: const InputDecoration(
                        labelText: 'Password',
                        border: OutlineInputBorder(),
                      ),
                      onSubmitted: (_) => _loginWithCredentials(),
                    ),
                    if (_error != null) ...[
                      const SizedBox(height: 10),
                      Text(
                        _error!,
                        key: developerFeedbackRoleLoginErrorKey,
                        style: TextStyle(
                          color: Theme.of(context).colorScheme.error,
                        ),
                      ),
                    ],
                    const SizedBox(height: 16),
                    FilledButton.icon(
                      key: developerFeedbackCredentialLoginKey,
                      onPressed: _loginWithCredentials,
                      icon: const Icon(Icons.login),
                      label: const Text('Ingresar'),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  DeveloperFeedbackRole? _selectedRoleOrDefault() {
    if (widget.roles.isEmpty) return null;
    final selectedRole = _selectedRole;
    if (selectedRole != null && widget.roles.contains(selectedRole)) {
      return selectedRole;
    }
    return widget.roles.first;
  }

  void _loginWithCredentials() {
    final username = _usernameController.text.trim();
    final password = _passwordController.text;
    for (final credential in widget.credentials) {
      if (credential.username == username && credential.password == password) {
        final role = _roleById(credential.roleId);
        if (role != null) {
          _setSession(
            DeveloperFeedbackRoleSession(
              role: role,
              username: username,
              credentialLogin: true,
            ),
          );
          return;
        }
      }
    }
    setState(() => _error = 'Usuario o password invalidos.');
  }

  DeveloperFeedbackRole? _roleById(String id) {
    for (final role in widget.roles) {
      if (role.id == id) return role;
    }
    return null;
  }

  void _setSession(DeveloperFeedbackRoleSession session) {
    setState(() {
      _session = session;
      _error = null;
    });
    widget.onSessionChanged?.call(session);
  }
}

const _transparentPngBase64 =
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=';

class DeveloperFeedbackTemplate extends StatefulWidget {
  const DeveloperFeedbackTemplate({
    required this.child,
    required this.enabled,
    this.sourceApp = developerFeedbackSourceApp,
    this.sourceDisplayName = developerFeedbackSourceDisplayName,
    this.bridgeUrl = developerFeedbackBridgeUrl,
    this.navigatorKey,
    this.scaffoldMessengerKey,
    this.recorderFactory = createDeveloperFeedbackAudioRecorder,
    this.copyText,
    this.bridgeSubmit,
    this.bridgeSubmitBatch,
    this.contextMetadataBuilder,
    this.httpClient,
    this.initialEditMode = false,
    this.appUpdaterEnabled = true,
    this.appUpdaterBridgeUrl = developerFeedbackAppUpdaterBridgeUrl,
    this.appUpdaterCurrentVersion,
    this.appUpdaterCurrentBuild,
    this.appUpdaterPlatform = 'android',
    this.appUpdaterChannel = 'stable',
    this.appUpdaterRequireChecksum = false,
    this.appUpdaterController,
    this.appUpdaterCheckOnStart = true,
    this.appUpdaterCheckOnResume = true,
    this.guidedTraceEnabled = true,
    this.guidedTraceFrameInterval = const Duration(seconds: 5),
    this.guidedTraceMaxFrames = 8,
    this.guidedTraceMaxEvents = 160,
    this.guidedTraceMaxDuration = const Duration(minutes: 2),
    super.key,
  });

  final Widget child;
  final bool enabled;
  final String sourceApp;
  final String sourceDisplayName;
  final String bridgeUrl;
  final GlobalKey<NavigatorState>? navigatorKey;
  final GlobalKey<ScaffoldMessengerState>? scaffoldMessengerKey;
  final DeveloperFeedbackRecorderFactory recorderFactory;
  final DeveloperFeedbackCopyText? copyText;
  final DeveloperFeedbackBridgeSubmit? bridgeSubmit;
  final DeveloperFeedbackBridgeSubmitBatch? bridgeSubmitBatch;
  final DeveloperFeedbackContextMetadataBuilder? contextMetadataBuilder;
  final http.Client? httpClient;
  final bool initialEditMode;
  final bool appUpdaterEnabled;
  final String appUpdaterBridgeUrl;
  final String? appUpdaterCurrentVersion;
  final int? appUpdaterCurrentBuild;
  final String appUpdaterPlatform;
  final String appUpdaterChannel;
  final bool appUpdaterRequireChecksum;
  final CodexAppUpdaterController? appUpdaterController;
  final bool appUpdaterCheckOnStart;
  final bool appUpdaterCheckOnResume;

  /// Enables the floating toolbar action that records a structured walkthrough.
  ///
  /// Existing integrations keep the default enabled behavior and can opt out
  /// without changing the feedback queue or batch submission contracts.
  final bool guidedTraceEnabled;

  /// Interval for automatic screen captures while a guided trace is recording.
  final Duration guidedTraceFrameInterval;

  /// Maximum screenshots kept inside one guided trace payload.
  final int guidedTraceMaxFrames;

  /// Maximum timeline events kept inside one guided trace payload.
  final int guidedTraceMaxEvents;

  /// Maximum recording duration before the guided trace auto-stops.
  final Duration guidedTraceMaxDuration;

  @override
  State<DeveloperFeedbackTemplate> createState() =>
      _DeveloperFeedbackTemplateState();
}

class CodexDeveloperFeedbackTemplate extends DeveloperFeedbackTemplate {
  const CodexDeveloperFeedbackTemplate({
    required super.child,
    required super.enabled,
    required super.sourceApp,
    required super.bridgeUrl,
    super.sourceDisplayName,
    super.navigatorKey,
    super.scaffoldMessengerKey,
    super.recorderFactory,
    super.copyText,
    super.bridgeSubmit,
    super.bridgeSubmitBatch,
    super.contextMetadataBuilder,
    super.httpClient,
    super.initialEditMode,
    super.appUpdaterEnabled,
    super.appUpdaterBridgeUrl,
    super.appUpdaterCurrentVersion,
    super.appUpdaterCurrentBuild,
    super.appUpdaterPlatform,
    super.appUpdaterChannel,
    super.appUpdaterRequireChecksum,
    super.appUpdaterController,
    super.appUpdaterCheckOnStart,
    super.appUpdaterCheckOnResume,
    super.guidedTraceEnabled,
    super.guidedTraceFrameInterval,
    super.guidedTraceMaxFrames,
    super.guidedTraceMaxEvents,
    super.guidedTraceMaxDuration,
    super.key,
  });
}

class _DeveloperFeedbackTemplateState extends State<DeveloperFeedbackTemplate> {
  final _captureKey = GlobalKey();
  final _toolbarMeasureKey = GlobalKey();
  final List<DeveloperFeedbackItem> _items = <DeveloperFeedbackItem>[];
  final List<_SubmittedFeedbackBatch> _submittedBatches =
      <_SubmittedFeedbackBatch>[];
  final List<_QuickAskRecord> _localQuickAsks = <_QuickAskRecord>[];
  final Set<String> _quickAskPollingIds = <String>{};
  String? _pendingQuickAskId;
  var _unreadNotificationCount = 0;
  var _unreadQuickAskCount = 0;
  var _quickAskGeneration = 0;
  var _quickAskCancellation = Completer<void>();
  var _notificationRefreshScheduled = false;
  var _editMode = false;
  var _dialogOpen = false;
  var _selectionReady = false;
  var _toolbarExpanded = true;
  var _guidedTraceCaptureInProgress = false;
  var _guidedTraceStarting = false;
  var _guidedTraceStopping = false;
  var _drawing = <Offset>[];
  Offset? _toolbarOffset;
  Size? _toolbarSize;
  _GuidedTraceRecording? _guidedTraceRecording;
  Timer? _guidedTraceFrameTimer;
  Timer? _guidedTraceUiTimer;
  Timer? _guidedTraceMaxDurationTimer;

  @override
  void initState() {
    super.initState();
    _editMode = widget.initialEditMode;
  }

  @override
  void didUpdateWidget(covariant DeveloperFeedbackTemplate oldWidget) {
    super.didUpdateWidget(oldWidget);
    final disabled = oldWidget.enabled && !widget.enabled;
    final bridgeChanged =
        _effectiveBridgeUrlFor(oldWidget) != _effectiveBridgeUrl;
    final sourceChanged = oldWidget.sourceApp != widget.sourceApp;
    final contextChanged =
        bridgeChanged ||
        sourceChanged ||
        oldWidget.sourceDisplayName != widget.sourceDisplayName ||
        oldWidget.httpClient != widget.httpClient ||
        oldWidget.contextMetadataBuilder != widget.contextMetadataBuilder;
    if (disabled || contextChanged) {
      _cancelQuickAskBackgroundWork();
      if (bridgeChanged || sourceChanged) {
        _clearQuickAskContext();
      } else if (disabled) {
        _cancelActiveQuickAsks();
      }
    }
    if (bridgeChanged || sourceChanged) {
      _notificationRefreshScheduled = false;
      _unreadNotificationCount = 0;
    }
  }

  @override
  void dispose() {
    _guidedTraceFrameTimer?.cancel();
    _guidedTraceUiTimer?.cancel();
    _guidedTraceMaxDurationTimer?.cancel();
    unawaited(_guidedTraceRecording?.recorder?.cancel());
    _cancelQuickAskBackgroundWork();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.enabled) return _appContent;
    _scheduleNotificationRefresh();
    final safePadding = MediaQuery.paddingOf(context);
    final bridgeAvailable = _effectiveBridgeUrl.isNotEmpty;

    return LayoutBuilder(
      builder: (context, constraints) {
        final viewport = Size(constraints.maxWidth, constraints.maxHeight);
        final toolbarOffset = _effectiveToolbarOffset(viewport, safePadding);
        _scheduleToolbarMeasurement(viewport, safePadding);

        return Stack(
          children: <Widget>[
            RepaintBoundary(
              key: _captureKey,
              child: Listener(
                onPointerDown: _recordGuidedTracePointerDown,
                onPointerUp: _recordGuidedTracePointerUp,
                onPointerCancel: _recordGuidedTracePointerCancel,
                child: _appContent,
              ),
            ),
            if (_editMode && !_dialogOpen)
              Positioned.fill(
                child: _DrawingOverlay(
                  key: developerFeedbackOverlayKey,
                  points: _drawing,
                  onStart: _startDrawing,
                  onUpdate: _updateDrawing,
                  onComplete: _completeDrawing,
                ),
              ),
            if (_editMode && !_dialogOpen && _selectionReady)
              Positioned(
                left: 16,
                right: 16,
                bottom: safePadding.bottom + 128,
                child: _SelectionActions(
                  onComment: () => _openFeedbackDialog(List.of(_drawing)),
                  onQuickAsk: bridgeAvailable
                      ? () => _openQuickAskDialog(List.of(_drawing))
                      : () => _openBridgeUnavailableDialog(),
                  onReset: _resetDrawing,
                ),
              ),
            Positioned(
              left: toolbarOffset.dx,
              top: toolbarOffset.dy,
              child: _DraggableToolbarShell(
                key: _toolbarMeasureKey,
                onDragUpdate: (delta) =>
                    _moveToolbar(delta, viewport, safePadding),
                child: _Toolbar(
                  expanded: _toolbarExpanded,
                  editMode: _editMode,
                  compact: viewport.width < 600,
                  pendingCount: _items.length,
                  submittedCount: _submittedBatches.length,
                  bridgeAvailable: bridgeAvailable,
                  unreadNotificationCount: _unreadNotificationCount,
                  quickAskActivityCount: _quickAskActivityCount,
                  onEditModeChanged: (value) => setState(() {
                    _editMode = value;
                    if (!value) {
                      _drawing = <Offset>[];
                      _selectionReady = false;
                    }
                  }),
                  onExpandedChanged: _setToolbarExpanded,
                  onOpenPending: _items.isEmpty ? null : _openPendingDialog,
                  onOpenRuns: _submittedBatches.isEmpty
                      ? null
                      : _openRunsDialog,
                  onOpenHistory: bridgeAvailable
                      ? _openHistoryDialog
                      : _openBridgeUnavailableDialog,
                  onOpenNotifications: bridgeAvailable
                      ? _openNotificationCenterDialog
                      : _openBridgeUnavailableDialog,
                  onOpenQuickAskHistory: bridgeAvailable
                      ? _openQuickAskHistoryDialog
                      : _openBridgeUnavailableDialog,
                  guidedTraceEnabled: widget.guidedTraceEnabled,
                  guidedTraceRecording: _guidedTraceRecording != null,
                  guidedTraceBusy: _guidedTraceStarting || _guidedTraceStopping,
                  onStartGuidedTrace: _startGuidedTrace,
                  onStopGuidedTrace: _stopGuidedTrace,
                ),
              ),
            ),
            if (_guidedTraceRecording != null && !_dialogOpen)
              Positioned(
                left: 16,
                right: 16,
                bottom: safePadding.bottom + 72,
                child: _GuidedTraceRecordingBanner(
                  recording: _guidedTraceRecording!,
                  stopping: _guidedTraceStopping,
                  onStop: _stopGuidedTrace,
                  onDiscard: _discardGuidedTrace,
                ),
              ),
          ],
        );
      },
    );
  }

  Widget get _appContent {
    return _DeveloperFeedbackAppUpdater(
      enabled: _shouldEnableIntegratedAppUpdater,
      sourceApp: widget.sourceApp,
      bridgeUrl: _effectiveAppUpdaterBridgeUrl,
      currentVersion: widget.appUpdaterCurrentVersion,
      currentBuild: widget.appUpdaterCurrentBuild,
      platform: widget.appUpdaterPlatform,
      channel: widget.appUpdaterChannel,
      requireChecksum: widget.appUpdaterRequireChecksum,
      controller: widget.appUpdaterController,
      checkOnStart: widget.appUpdaterCheckOnStart,
      checkOnResume: widget.appUpdaterCheckOnResume,
      child: widget.child,
    );
  }

  int get _quickAskActivityCount =>
      _unreadQuickAskCount +
      _currentLocalQuickAsks.where((record) => record.isActive).length;

  Iterable<_QuickAskRecord> get _currentLocalQuickAsks {
    return _localQuickAsks.where(
      (record) => record.sourceApp == widget.sourceApp,
    );
  }

  String get _effectiveBridgeUrl => _effectiveBridgeUrlFor(widget);

  String _effectiveBridgeUrlFor(DeveloperFeedbackTemplate value) {
    return resolveDeveloperFeedbackBridgeUrl(
      feedbackBridgeUrl: value.bridgeUrl,
      appUpdaterBridgeUrl: value.appUpdaterBridgeUrl,
    );
  }

  String get _effectiveAppUpdaterBridgeUrl {
    return resolveCodexAppUpdaterBridgeUrl(
      appUpdaterBridgeUrl: widget.appUpdaterBridgeUrl,
      feedbackBridgeUrl: widget.bridgeUrl,
    );
  }

  bool get _shouldEnableIntegratedAppUpdater {
    return widget.appUpdaterEnabled &&
        !kIsWeb &&
        defaultTargetPlatform == TargetPlatform.android &&
        widget.sourceApp.trim().isNotEmpty &&
        widget.sourceApp.trim() != 'unknown' &&
        _effectiveAppUpdaterBridgeUrl.isNotEmpty;
  }

  BuildContext get _modalContext =>
      widget.navigatorKey?.currentState?.overlay?.context ??
      widget.navigatorKey?.currentContext ??
      context;

  bool _isQuickAskWorkActive(int generation) {
    return mounted &&
        widget.enabled &&
        generation == _quickAskGeneration &&
        _effectiveBridgeUrl.isNotEmpty;
  }

  void _cancelQuickAskBackgroundWork() {
    _quickAskGeneration += 1;
    if (!_quickAskCancellation.isCompleted) {
      _quickAskCancellation.complete();
    }
    _quickAskCancellation = Completer<void>();
    _quickAskPollingIds.clear();
  }

  Future<void> _waitForQuickAskPollDelay(int generation) async {
    if (!_isQuickAskWorkActive(generation)) return;
    final cancellation = _quickAskCancellation.future;
    final completer = Completer<void>();
    Timer? timer;
    void complete() {
      if (!completer.isCompleted) completer.complete();
    }

    timer = Timer(const Duration(seconds: 2), complete);
    unawaited(
      cancellation.then((_) {
        timer?.cancel();
        complete();
      }),
    );
    try {
      await completer.future;
    } finally {
      timer.cancel();
    }
  }

  void _cancelActiveQuickAsks() {
    for (var index = 0; index < _localQuickAsks.length; index += 1) {
      final record = _localQuickAsks[index];
      if (record.isActive) {
        _localQuickAsks[index] = record.copyWith(status: 'canceled');
      }
    }
  }

  void _clearQuickAskContext() {
    _localQuickAsks.clear();
    _unreadQuickAskCount = 0;
  }

  Offset _effectiveToolbarOffset(Size viewport, EdgeInsets safePadding) {
    final current = _toolbarOffset;
    if (current != null) {
      return _clampToolbarOffset(current, viewport, safePadding);
    }
    final size = _toolbarClampSize;
    return _clampToolbarOffset(
      Offset(viewport.width - size.width - 12, safePadding.top + 12),
      viewport,
      safePadding,
    );
  }

  Offset _clampToolbarOffset(
    Offset offset,
    Size viewport,
    EdgeInsets safePadding,
  ) {
    const margin = 8.0;
    final size = _toolbarClampSize;
    final maxX = math.max(margin, viewport.width - size.width - margin);
    final maxY = math.max(
      safePadding.top + margin,
      viewport.height - size.height - safePadding.bottom - margin,
    );
    return Offset(
      offset.dx.clamp(margin, maxX),
      offset.dy.clamp(safePadding.top + margin, maxY),
    );
  }

  Size get _toolbarClampSize {
    const collapsedEstimate = Size(48, 48);
    if (!_toolbarExpanded) {
      final measured = _toolbarSize ?? Size.zero;
      return Size(
        math.max(measured.width, collapsedEstimate.width),
        math.max(measured.height, collapsedEstimate.height),
      );
    }
    const baseEstimate = Size(360, 48);
    const pendingEstimate = Size(520, 48);
    final measured = _toolbarSize ?? Size.zero;
    final estimate =
        _items.isEmpty &&
            _submittedBatches.isEmpty &&
            _effectiveBridgeUrl.isEmpty
        ? baseEstimate
        : pendingEstimate;
    return Size(
      math.max(measured.width, estimate.width),
      math.max(measured.height, estimate.height),
    );
  }

  void _moveToolbar(Offset delta, Size viewport, EdgeInsets safePadding) {
    setState(() {
      final start = _effectiveToolbarOffset(viewport, safePadding);
      _toolbarOffset = _clampToolbarOffset(
        start + delta,
        viewport,
        safePadding,
      );
    });
  }

  void _setToolbarExpanded(bool expanded) {
    setState(() {
      _toolbarExpanded = expanded;
      _toolbarSize = null;
      if (!expanded) {
        _editMode = false;
        _drawing = <Offset>[];
        _selectionReady = false;
      }
    });
  }

  void _scheduleToolbarMeasurement(Size viewport, EdgeInsets safePadding) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final renderObject = _toolbarMeasureKey.currentContext
          ?.findRenderObject();
      if (renderObject is! RenderBox || !renderObject.hasSize) return;
      final measured = renderObject.size;
      if (_toolbarSize == measured) return;
      setState(() {
        _toolbarSize = measured;
        final current = _toolbarOffset;
        if (current != null) {
          _toolbarOffset = _clampToolbarOffset(current, viewport, safePadding);
        }
      });
    });
  }

  void _startDrawing(Offset point) {
    setState(() {
      _selectionReady = false;
      _drawing = <Offset>[point];
    });
  }

  void _updateDrawing(Offset point) {
    setState(() {
      _selectionReady = false;
      _drawing = <Offset>[..._drawing, point];
    });
  }

  void _completeDrawing() {
    setState(() {
      _selectionReady = _hasEnoughSelection(_drawing);
      if (!_selectionReady) _drawing = <Offset>[];
    });
  }

  void _resetDrawing() {
    setState(() {
      _selectionReady = false;
      _drawing = <Offset>[];
    });
  }

  Future<void> _openFeedbackDialog(List<Offset> points) async {
    if (points.isEmpty) return;
    final screenshotPngBase64 = await _captureMarkedScreenshot(points);
    if (!mounted) return;
    setState(() => _dialogOpen = true);
    await showDialog<void>(
      context: widget.navigatorKey?.currentContext ?? context,
      builder: (context) => _FeedbackDialog(
        recorder: widget.recorderFactory(),
        onSave: (draft) async {
          if (!mounted) return;
          final now = DateTime.now().toUtc();
          final item = DeveloperFeedbackItem(
            id: 'feedback-${now.microsecondsSinceEpoch}',
            createdAt: now,
            sourceApp: widget.sourceApp,
            sourceDisplayName: widget.sourceDisplayName,
            comment: draft.comment,
            screenshotPngBase64: screenshotPngBase64,
            selectionPoints: points,
            audio: draft.audio,
            contextMetadata: _currentContextMetadata(),
          );
          setState(() {
            _items.add(item);
            _drawing = <Offset>[];
            _selectionReady = false;
          });
          _showMessage('Feedback agregado a la cola.');
        },
      ),
    );
    if (mounted) {
      setState(() {
        _dialogOpen = false;
        _drawing = <Offset>[];
        _selectionReady = false;
      });
    }
  }

  Future<void> _openQuickAskDialog(List<Offset> points) async {
    if (points.isEmpty) return;
    if (_effectiveBridgeUrl.isEmpty) {
      _openBridgeUnavailableDialog();
      return;
    }
    final screenshotPngBase64 = await _captureMarkedScreenshot(points);
    if (!mounted) return;
    setState(() => _dialogOpen = true);
    final question = await showDialog<String>(
      context: _modalContext,
      builder: (dialogContext) => _QuickAskQuestionDialog(
        onCancel: () => Navigator.of(dialogContext).pop(),
        onSubmit: (question) => Navigator.of(dialogContext).pop(question),
      ),
    );
    if (mounted) {
      if (question != null && question.trim().isNotEmpty) {
        _queueQuickAsk(
          question: question.trim(),
          screenshotPngBase64: screenshotPngBase64,
          points: points,
        );
      }
      setState(() {
        _dialogOpen = false;
        _drawing = <Offset>[];
        _selectionReady = false;
      });
    }
  }

  void _queueQuickAsk({
    required String question,
    required String screenshotPngBase64,
    required List<Offset> points,
  }) {
    final now = DateTime.now().toUtc();
    final localId = 'quick-ask-local-${now.microsecondsSinceEpoch}';
    final localRecord = _QuickAskRecord(
      quickAskId: localId,
      sourceApp: widget.sourceApp,
      sourceDisplayName: widget.sourceDisplayName,
      question: question,
      status: 'queued',
      createdAt: now.toIso8601String(),
      selectionBounds: _selectionBoundsFromPoints(points),
      screenshotPngBase64: screenshotPngBase64,
    );
    setState(() => _localQuickAsks.insert(0, localRecord));
    _showMessage('Pregunta enviada. Te aviso cuando tenga respuesta.');
    final generation = _quickAskGeneration;
    unawaited(
      _submitQuickAskInBackground(
        generation: generation,
        localId: localId,
        question: question,
        screenshotPngBase64: screenshotPngBase64,
        points: points,
      ),
    );
  }

  Future<void> _submitQuickAskInBackground({
    required int generation,
    required String localId,
    required String question,
    required String screenshotPngBase64,
    required List<Offset> points,
  }) async {
    final baseUrl = _effectiveBridgeUrl.replaceAll(RegExp(r'/$'), '');
    final ownsClient = widget.httpClient == null;
    final client = widget.httpClient ?? http.Client();
    final quickAskItem = DeveloperFeedbackItem(
      id: localId,
      createdAt: DateTime.now().toUtc(),
      sourceApp: widget.sourceApp,
      sourceDisplayName: widget.sourceDisplayName,
      comment: question,
      screenshotPngBase64: screenshotPngBase64,
      selectionPoints: points,
      audio: null,
      contextMetadata: _currentContextMetadata(),
    );
    var currentId = localId;
    try {
      if (!_isQuickAskWorkActive(generation)) return;
      final response = await client.post(
        Uri.parse('$baseUrl/feedback-quick-asks/ask'),
        headers: const <String, String>{'Content-Type': 'application/json'},
        body: jsonEncode(<String, Object?>{
          'sourceApp': widget.sourceApp,
          if (widget.sourceDisplayName.trim().isNotEmpty)
            'sourceDisplayName': widget.sourceDisplayName,
          'question': question,
          'screenshotMimeType': 'image/png',
          'screenshotPngBase64': screenshotPngBase64,
          'selectionPoints': points
              .map((point) => <String, double>{'x': point.dx, 'y': point.dy})
              .toList(),
          'selectionBounds': quickAskItem.selectionBounds,
          'contextMetadata': quickAskItem.contextMetadata,
        }),
      );
      if (!_isQuickAskWorkActive(generation)) return;
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw Exception('HTTP ${response.statusCode}: ${response.body}');
      }
      final accepted = jsonDecode(response.body) as Map<String, Object?>;
      final quickAskId =
          ((accepted['quick_ask_id'] as String?) ??
                  (accepted['quickAskId'] as String?))
              ?.trim();
      if (quickAskId == null || quickAskId.isEmpty) {
        throw Exception('Missing quick_ask_id');
      }
      currentId = quickAskId;
      final acceptedRecord = _QuickAskRecord.fromJson(<String, Object?>{
        ...accepted,
        'quickAskId': quickAskId,
        'sourceApp': widget.sourceApp,
        if (widget.sourceDisplayName.trim().isNotEmpty)
          'sourceDisplayName': widget.sourceDisplayName,
        'question': question,
        'status': (accepted['status'] as String?) ?? 'running',
        'createdAt': quickAskItem.createdAt.toIso8601String(),
        'selectionBounds': quickAskItem.selectionBounds,
        'screenshotPngBase64': screenshotPngBase64,
      });
      _replaceQuickAskRecord(localId, acceptedRecord);
      if (!_isQuickAskWorkActive(generation)) return;
      await _pollQuickAskUntilDone(
        generation: generation,
        client: client,
        baseUrl: baseUrl,
        quickAskId: quickAskId,
        fallback: acceptedRecord,
      );
    } catch (_) {
      if (!_isQuickAskWorkActive(generation)) return;
      _replaceQuickAskRecord(
        currentId,
        _quickAskById(currentId)?.copyWith(status: 'failed') ??
            _QuickAskRecord(
              quickAskId: currentId,
              sourceApp: widget.sourceApp,
              sourceDisplayName: widget.sourceDisplayName,
              question: question,
              status: 'failed',
              createdAt: quickAskItem.createdAt.toIso8601String(),
              selectionBounds: quickAskItem.selectionBounds,
              screenshotPngBase64: screenshotPngBase64,
            ),
      );
      _notifyQuickAskReady('No se pudo enviar la pregunta rápida.');
    } finally {
      if (ownsClient) client.close();
    }
  }

  Future<void> _pollQuickAskUntilDone({
    required int generation,
    required http.Client client,
    required String baseUrl,
    required String quickAskId,
    required _QuickAskRecord fallback,
  }) async {
    if (!_isQuickAskWorkActive(generation)) return;
    if (!_quickAskPollingIds.add(quickAskId)) return;
    try {
      for (var attempt = 0; attempt < 150; attempt += 1) {
        if (!_isQuickAskWorkActive(generation)) return;
        final statusResponse = await client.get(
          Uri.parse('$baseUrl/feedback-quick-asks/$quickAskId'),
        );
        if (!_isQuickAskWorkActive(generation)) return;
        if (statusResponse.statusCode < 200 ||
            statusResponse.statusCode >= 300) {
          throw Exception(
            'HTTP ${statusResponse.statusCode}: ${statusResponse.body}',
          );
        }
        final status = jsonDecode(statusResponse.body) as Map<String, Object?>;
        final detail = _QuickAskRecord.fromJson(status).mergedWith(fallback);
        _upsertQuickAskRecord(detail);
        if (detail.isCompleted) {
          _notifyQuickAskReady('Respuesta lista en Preguntas rápidas.');
          return;
        }
        if (detail.isFailed) {
          throw Exception(status['status_detail'] ?? 'Quick ask failed');
        }
        await _waitForQuickAskPollDelay(generation);
        if (!_isQuickAskWorkActive(generation)) return;
      }
      _upsertQuickAskRecord(fallback.copyWith(status: 'running'));
    } finally {
      if (generation == _quickAskGeneration) {
        _quickAskPollingIds.remove(quickAskId);
      }
    }
  }

  void _replaceQuickAskRecord(String previousId, _QuickAskRecord record) {
    if (!mounted) return;
    setState(() {
      _localQuickAsks.removeWhere(
        (candidate) => candidate.quickAskId == previousId,
      );
      _localQuickAsks.insert(0, record);
    });
  }

  void _upsertQuickAskRecord(_QuickAskRecord record) {
    if (!mounted) return;
    setState(() {
      final index = _localQuickAsks.indexWhere(
        (candidate) => candidate.quickAskId == record.quickAskId,
      );
      if (index == -1) {
        _localQuickAsks.insert(0, record);
      } else {
        _localQuickAsks[index] = record;
      }
    });
  }

  _QuickAskRecord? _quickAskById(String quickAskId) {
    for (final record in _currentLocalQuickAsks) {
      if (record.quickAskId == quickAskId) return record;
    }
    return null;
  }

  void _notifyQuickAskReady(String message) {
    if (!mounted || !widget.enabled) return;
    setState(() => _unreadQuickAskCount += 1);
    _showMessage(message);
  }

  Map<String, Object?> _currentContextMetadata() {
    final contextForMetadata = widget.navigatorKey?.currentContext ?? context;
    final media = MediaQuery.maybeOf(contextForMetadata);
    final route = ModalRoute.of(contextForMetadata);
    final metadata = <String, Object?>{
      if ((route?.settings.name ?? '').trim().isNotEmpty)
        'routeName': route!.settings.name,
      if (media != null) ...<String, Object?>{
        'screenWidth': media.size.width,
        'screenHeight': media.size.height,
        'devicePixelRatio': media.devicePixelRatio,
        'orientation': media.orientation.name,
      },
    };
    final extra = widget.contextMetadataBuilder?.call(contextForMetadata);
    if (extra != null) metadata.addAll(extra);
    return _jsonSafeMetadata(metadata);
  }

  Future<String> _captureMarkedScreenshot(List<Offset> points) async {
    try {
      if (_isWidgetTestBinding()) return _transparentPngBase64;
      final boundary =
          _captureKey.currentContext?.findRenderObject()
              as RenderRepaintBoundary?;
      if (boundary == null) return _transparentPngBase64;
      const pixelRatio = 1.0;
      final baseImage = await boundary
          .toImage(pixelRatio: pixelRatio)
          .timeout(const Duration(seconds: 1));
      final recorder = ui.PictureRecorder();
      final canvas = Canvas(
        recorder,
        Rect.fromLTWH(
          0,
          0,
          baseImage.width.toDouble(),
          baseImage.height.toDouble(),
        ),
      );
      canvas.drawImage(baseImage, Offset.zero, Paint());
      if (points.length > 1) {
        final path = Path()
          ..moveTo(points.first.dx * pixelRatio, points.first.dy * pixelRatio);
        for (final point in points.skip(1)) {
          path.lineTo(point.dx * pixelRatio, point.dy * pixelRatio);
        }
        canvas.drawPath(
          path,
          Paint()
            ..color = Colors.redAccent
            ..style = PaintingStyle.stroke
            ..strokeWidth = 4 * pixelRatio
            ..strokeCap = StrokeCap.round
            ..strokeJoin = StrokeJoin.round,
        );
      }
      final markedImage = await recorder
          .endRecording()
          .toImage(baseImage.width, baseImage.height)
          .timeout(const Duration(seconds: 1));
      final byteData = await markedImage
          .toByteData(format: ui.ImageByteFormat.png)
          .timeout(const Duration(seconds: 1));
      baseImage.dispose();
      markedImage.dispose();
      if (byteData == null) return _transparentPngBase64;
      return base64Encode(
        Uint8List.view(
          byteData.buffer,
          byteData.offsetInBytes,
          byteData.lengthInBytes,
        ),
      );
    } catch (_) {
      return _transparentPngBase64;
    }
  }

  Future<_CapturedFeedbackScreenshot> _captureGuidedTraceScreenshot() async {
    try {
      if (_isWidgetTestBinding()) {
        return const _CapturedFeedbackScreenshot(
          pngBase64: _transparentPngBase64,
          width: 1,
          height: 1,
          pixelRatio: 1,
        );
      }
      final boundary =
          _captureKey.currentContext?.findRenderObject()
              as RenderRepaintBoundary?;
      if (boundary == null) return _CapturedFeedbackScreenshot.transparent();
      const pixelRatio = 1.0;
      final image = await boundary
          .toImage(pixelRatio: pixelRatio)
          .timeout(const Duration(seconds: 1));
      final byteData = await image
          .toByteData(format: ui.ImageByteFormat.png)
          .timeout(const Duration(seconds: 1));
      final width = image.width;
      final height = image.height;
      image.dispose();
      if (byteData == null) return _CapturedFeedbackScreenshot.transparent();
      return _CapturedFeedbackScreenshot(
        pngBase64: base64Encode(
          Uint8List.view(
            byteData.buffer,
            byteData.offsetInBytes,
            byteData.lengthInBytes,
          ),
        ),
        width: width,
        height: height,
        pixelRatio: pixelRatio,
      );
    } catch (_) {
      return _CapturedFeedbackScreenshot.transparent();
    }
  }

  void _startGuidedTrace() {
    unawaited(_startGuidedTraceAsync());
  }

  Future<void> _startGuidedTraceAsync() async {
    if (!widget.guidedTraceEnabled ||
        _guidedTraceRecording != null ||
        _guidedTraceStarting) {
      return;
    }
    setState(() => _guidedTraceStarting = true);
    final now = DateTime.now().toUtc();
    DeveloperFeedbackAudioRecorder? recorder;
    var audioStarted = false;
    try {
      final candidate = widget.recorderFactory();
      if (await candidate.isSupported.timeout(const Duration(seconds: 1))) {
        await candidate.start().timeout(const Duration(seconds: 2));
        recorder = candidate;
        audioStarted = true;
      } else {
        await candidate.cancel();
      }
    } catch (_) {
      await recorder?.cancel();
      recorder = null;
      audioStarted = false;
    }
    try {
      final recording = _GuidedTraceRecording(
        id: 'trace-${now.microsecondsSinceEpoch}',
        startedAt: now,
        recorder: recorder,
        audioStarted: audioStarted,
      );
      recording.contextSnapshots.add(_newGuidedTraceContextSnapshot(recording));
      _addGuidedTraceEvent(
        recording,
        DeveloperFeedbackTraceEvent(
          id: recording.nextEventId(),
          type: 'session_started',
          atMs: recording.elapsedMs,
          contextSnapshotId: recording.contextSnapshots.first['id'] as String?,
        ),
      );
      if (!mounted) {
        await recorder?.cancel();
        return;
      }
      setState(() {
        _guidedTraceRecording = recording;
        _guidedTraceStarting = false;
        _editMode = false;
        _drawing = <Offset>[];
        _selectionReady = false;
      });
      _startGuidedTraceTimers();
      await _captureGuidedTraceFrame(reason: 'initial_screen', force: true);
      _showMessage(
        audioStarted
            ? 'Grabando recorrido con audio.'
            : 'Grabando recorrido sin audio.',
      );
    } catch (_) {
      await recorder?.cancel();
      if (mounted) setState(() => _guidedTraceStarting = false);
      _showMessage('No se pudo iniciar el recorrido.');
    }
  }

  void _startGuidedTraceTimers() {
    _guidedTraceFrameTimer?.cancel();
    _guidedTraceUiTimer?.cancel();
    _guidedTraceMaxDurationTimer?.cancel();
    _guidedTraceFrameTimer = Timer.periodic(
      _effectiveGuidedTraceFrameInterval,
      (_) => unawaited(_captureGuidedTraceFrame(reason: 'interval')),
    );
    _guidedTraceUiTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted && _guidedTraceRecording != null) setState(() {});
    });
    final maxDuration = _effectiveGuidedTraceMaxDuration;
    if (maxDuration > Duration.zero) {
      _guidedTraceMaxDurationTimer = Timer(maxDuration, () {
        if (mounted && _guidedTraceRecording != null) {
          _showMessage('Recorrido detenido por duración máxima.');
          _stopGuidedTrace();
        }
      });
    }
  }

  Duration get _effectiveGuidedTraceFrameInterval {
    final interval = widget.guidedTraceFrameInterval;
    if (interval <= Duration.zero) return const Duration(seconds: 5);
    return interval;
  }

  int get _effectiveGuidedTraceMaxFrames =>
      math.max(1, widget.guidedTraceMaxFrames);

  int get _effectiveGuidedTraceMaxEvents =>
      math.max(8, widget.guidedTraceMaxEvents);

  Duration get _effectiveGuidedTraceMaxDuration {
    final duration = widget.guidedTraceMaxDuration;
    if (duration <= Duration.zero) return Duration.zero;
    return duration;
  }

  void _stopGuidedTrace() {
    unawaited(_stopGuidedTraceAsync());
  }

  Future<void> _stopGuidedTraceAsync() async {
    final recording = _guidedTraceRecording;
    if (recording == null || _guidedTraceStopping) return;
    setState(() => _guidedTraceStopping = true);
    _guidedTraceFrameTimer?.cancel();
    _guidedTraceUiTimer?.cancel();
    _guidedTraceMaxDurationTimer?.cancel();
    await _captureGuidedTraceFrame(reason: 'stopped', force: true);
    DeveloperFeedbackAudioClip? audio;
    if (recording.audioStarted) {
      try {
        audio = await recording.recorder?.stop().timeout(
          const Duration(seconds: 2),
        );
      } catch (_) {
        await recording.recorder?.cancel();
      }
    }
    final endedAt = DateTime.now().toUtc();
    final trace = DeveloperFeedbackGuidedTrace(
      id: recording.id,
      startedAt: recording.startedAt,
      endedAt: endedAt,
      durationMs: endedAt.difference(recording.startedAt).inMilliseconds,
      truncated: recording.truncated,
      droppedFrameCount: recording.droppedFrameCount,
      droppedEventCount: recording.droppedEventCount,
      maxFrames: _effectiveGuidedTraceMaxFrames,
      maxEvents: _effectiveGuidedTraceMaxEvents,
      audio: audio == null
          ? null
          : DeveloperFeedbackTraceAudio(
              attachmentId: '${recording.id}_audio',
              mimeType: audio.mimeType,
              durationMs: audio.durationMs,
              transcriptAvailable: false,
            ),
      timeline: List.of(recording.events),
      frames: List.of(recording.frames),
      contextSnapshots: List.of(recording.contextSnapshots),
    );
    if (trace.timeline.isEmpty && trace.frames.isEmpty && audio == null) {
      setState(() {
        _guidedTraceRecording = null;
        _guidedTraceStopping = false;
      });
      _showMessage('No se grabó contenido para el recorrido.');
      return;
    }
    setState(() {
      _guidedTraceRecording = null;
      _guidedTraceStopping = false;
      _dialogOpen = true;
    });
    final result = await showDialog<_GuidedTracePreviewResult>(
      context: widget.navigatorKey?.currentContext ?? context,
      barrierDismissible: false,
      builder: (context) => _GuidedTracePreviewDialog(
        trace: trace,
        audio: audio,
        onAttach: (comment) => Navigator.of(
          context,
        ).pop(_GuidedTracePreviewResult.attach(comment: comment)),
        onDiscard: () => Navigator.of(
          context,
        ).pop(const _GuidedTracePreviewResult.discard()),
        onRerecord: () => Navigator.of(
          context,
        ).pop(const _GuidedTracePreviewResult.rerecord()),
      ),
    );
    if (!mounted) return;
    setState(() => _dialogOpen = false);
    switch (result?.action) {
      case _GuidedTracePreviewAction.attach:
        _queueGuidedTrace(trace: trace, audio: audio, comment: result!.comment);
      case _GuidedTracePreviewAction.rerecord:
        _showMessage('Recorrido descartado.');
        _startGuidedTrace();
      case _GuidedTracePreviewAction.discard:
      case null:
        _showMessage('Recorrido descartado.');
    }
  }

  void _discardGuidedTrace() {
    final recording = _guidedTraceRecording;
    _guidedTraceFrameTimer?.cancel();
    _guidedTraceUiTimer?.cancel();
    _guidedTraceMaxDurationTimer?.cancel();
    setState(() {
      _guidedTraceRecording = null;
      _guidedTraceStarting = false;
      _guidedTraceStopping = false;
    });
    unawaited(recording?.recorder?.cancel());
    _showMessage('Recorrido descartado.');
  }

  void _queueGuidedTrace({
    required DeveloperFeedbackGuidedTrace trace,
    required DeveloperFeedbackAudioClip? audio,
    required String comment,
  }) {
    final now = DateTime.now().toUtc();
    final fallbackScreenshot = trace.frames.isEmpty
        ? _transparentPngBase64
        : trace.frames.last.screenshotPngBase64 ?? _transparentPngBase64;
    final item = DeveloperFeedbackItem(
      id: 'feedback-${now.microsecondsSinceEpoch}',
      createdAt: now,
      sourceApp: widget.sourceApp,
      sourceDisplayName: widget.sourceDisplayName,
      comment: comment.trim(),
      screenshotPngBase64: fallbackScreenshot,
      selectionPoints: const <Offset>[],
      audio: audio,
      contextMetadata: _currentContextMetadata(),
      screen: _currentScreenSnapshot(),
      guidedTrace: trace,
    );
    setState(() => _items.add(item));
    _showMessage('Recorrido agregado a la cola.');
  }

  Future<void> _captureGuidedTraceFrame({
    required String reason,
    bool force = false,
  }) async {
    final recording = _guidedTraceRecording;
    if (recording == null || _guidedTraceCaptureInProgress) return;
    if (!force && recording.frames.length >= _effectiveGuidedTraceMaxFrames) {
      return;
    }
    final now = DateTime.now().toUtc();
    if (!force &&
        recording.lastFrameAt != null &&
        now.difference(recording.lastFrameAt!) <
            const Duration(milliseconds: 750)) {
      return;
    }
    _guidedTraceCaptureInProgress = true;
    try {
      final screenshot = await _captureGuidedTraceScreenshot();
      final contextSnapshot = _newGuidedTraceContextSnapshot(recording);
      final contextSnapshotId = contextSnapshot['id'] as String;
      final frameId = recording.nextFrameId();
      final frame = DeveloperFeedbackTraceFrame(
        id: frameId,
        attachmentId: '${frameId}_png',
        atMs: recording.elapsedMs,
        width: screenshot.width,
        height: screenshot.height,
        pixelRatio: screenshot.pixelRatio,
        screen: _currentScreenSnapshot(),
        screenshotMimeType: 'image/png',
        screenshotPngBase64: screenshot.pngBase64,
      );
      if (!mounted || _guidedTraceRecording != recording) return;
      setState(() {
        recording.contextSnapshots.add(contextSnapshot);
        _trimGuidedTraceContextSnapshots(recording);
        if (recording.frames.length >= _effectiveGuidedTraceMaxFrames) {
          recording.frames.removeAt(0);
          recording.droppedFrameCount += 1;
          recording.truncated = true;
        }
        recording.frames.add(frame);
        recording.lastFrameAt = now;
        _addGuidedTraceEvent(
          recording,
          DeveloperFeedbackTraceEvent(
            id: recording.nextEventId(),
            type: 'screen_frame',
            atMs: recording.elapsedMs,
            frameId: frameId,
            contextSnapshotId: contextSnapshotId,
            data: <String, Object?>{'reason': reason},
          ),
        );
      });
    } finally {
      _guidedTraceCaptureInProgress = false;
    }
  }

  void _addGuidedTraceEvent(
    _GuidedTraceRecording recording,
    DeveloperFeedbackTraceEvent event,
  ) {
    if (recording.events.length >= _effectiveGuidedTraceMaxEvents) {
      recording.events.removeAt(0);
      recording.droppedEventCount += 1;
      recording.truncated = true;
    }
    recording.events.add(event);
  }

  void _trimGuidedTraceContextSnapshots(_GuidedTraceRecording recording) {
    final maxSnapshots = _effectiveGuidedTraceMaxFrames + 2;
    while (recording.contextSnapshots.length > maxSnapshots) {
      recording.contextSnapshots.removeAt(0);
      recording.truncated = true;
    }
  }

  Map<String, Object?> _newGuidedTraceContextSnapshot(
    _GuidedTraceRecording recording,
  ) {
    return <String, Object?>{
      'id': recording.nextContextSnapshotId(),
      'observedAtMs': recording.elapsedMs,
      ..._currentContextMetadata(),
    };
  }

  DeveloperFeedbackScreenSnapshot _currentScreenSnapshot() {
    final contextForMetadata = widget.navigatorKey?.currentContext ?? context;
    final media = MediaQuery.maybeOf(contextForMetadata);
    final route = ModalRoute.of(contextForMetadata);
    return DeveloperFeedbackScreenSnapshot(
      route: route?.settings.name,
      name: route?.settings.name,
      metadata: <String, Object?>{
        if (media != null) ...<String, Object?>{
          'screenWidth': media.size.width,
          'screenHeight': media.size.height,
          'devicePixelRatio': media.devicePixelRatio,
          'orientation': media.orientation.name,
        },
      },
    );
  }

  void _recordGuidedTracePointerDown(PointerDownEvent event) {
    _recordGuidedTracePointerEvent('pointer_down', event.localPosition);
  }

  void _recordGuidedTracePointerUp(PointerUpEvent event) {
    _recordGuidedTracePointerEvent('pointer_up', event.localPosition);
    unawaited(_captureGuidedTraceFrame(reason: 'gesture_end'));
  }

  void _recordGuidedTracePointerCancel(PointerCancelEvent event) {
    _recordGuidedTracePointerEvent('pointer_cancel', event.localPosition);
  }

  void _recordGuidedTracePointerEvent(String kind, Offset position) {
    final recording = _guidedTraceRecording;
    if (recording == null) return;
    final normalized = _normalizeGuidedTracePosition(position);
    _addGuidedTraceEvent(
      recording,
      DeveloperFeedbackTraceEvent(
        id: recording.nextEventId(),
        type: 'gesture',
        atMs: recording.elapsedMs,
        data: <String, Object?>{
          'gesture': <String, Object?>{
            'kind': kind,
            'position': <String, double>{
              'x': normalized.dx,
              'y': normalized.dy,
            },
          },
        },
      ),
    );
  }

  Offset _normalizeGuidedTracePosition(Offset position) {
    final renderObject = _captureKey.currentContext?.findRenderObject();
    final size = renderObject is RenderBox ? renderObject.size : Size.zero;
    if (size.width <= 0 || size.height <= 0) return position;
    return Offset(
      (position.dx / size.width).clamp(0.0, 1.0),
      (position.dy / size.height).clamp(0.0, 1.0),
    );
  }

  bool _isWidgetTestBinding() {
    var isTestBinding = false;
    assert(() {
      isTestBinding = WidgetsBinding.instance.runtimeType.toString().contains(
        'TestWidgetsFlutterBinding',
      );
      return true;
    }());
    return isTestBinding;
  }

  Future<_DeveloperFeedbackWorkflowPresets> _loadWorkflowPresets() async {
    if (_effectiveBridgeUrl.isEmpty) {
      return _DeveloperFeedbackWorkflowPresets.fallback();
    }
    final baseUrl = _effectiveBridgeUrl.replaceAll(RegExp(r'/$'), '');
    final ownsClient = widget.httpClient == null;
    final client = widget.httpClient ?? http.Client();
    try {
      final response = await client.get(
        Uri.parse('$baseUrl/feedback-workflow-presets'),
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw Exception('HTTP ${response.statusCode}: ${response.body}');
      }
      return _DeveloperFeedbackWorkflowPresets.fromJson(
        jsonDecode(response.body) as Map<String, Object?>,
      );
    } catch (_) {
      return _DeveloperFeedbackWorkflowPresets.fallback();
    } finally {
      if (ownsClient) client.close();
    }
  }

  Future<bool> _submitFeedbackBatchToBridge({
    required String workflowPresetId,
    required bool releaseWhenComplete,
  }) async {
    if (_items.isEmpty) return false;
    final batch = DeveloperFeedbackBatch(
      batchId:
          'feedback-batch-${DateTime.now().toUtc().microsecondsSinceEpoch}',
      sourceApp: widget.sourceApp,
      sourceDisplayName: widget.sourceDisplayName,
      workflowPresetId: workflowPresetId,
      releaseWhenComplete: releaseWhenComplete,
      quickAskId: _pendingQuickAskId,
      items: List.of(_items),
    );
    final customBatchSubmit = widget.bridgeSubmitBatch;
    if (customBatchSubmit != null) {
      try {
        await customBatchSubmit(batch);
        setState(() {
          _items.clear();
          _pendingQuickAskId = null;
          _submittedBatches.insert(0, _SubmittedFeedbackBatch.local());
        });
        _showMessage('Feedback enviado a Codex CLI.');
        return true;
      } catch (_) {
        _showMessage('Guardado local; no se pudo enviar a Codex CLI.');
        return false;
      }
    }
    final customSubmit = widget.bridgeSubmit;
    if (customSubmit != null) {
      try {
        for (final item in List<DeveloperFeedbackItem>.of(_items)) {
          await customSubmit(item);
        }
        setState(() {
          _items.clear();
          _pendingQuickAskId = null;
          _submittedBatches.insert(0, _SubmittedFeedbackBatch.local());
        });
        _showMessage('Feedback enviado a Codex CLI.');
        return true;
      } catch (_) {
        _showMessage('Guardado local; no se pudo enviar a Codex CLI.');
        return false;
      }
    }
    if (_effectiveBridgeUrl.isEmpty) {
      _showBridgeUnavailableMessage();
      return false;
    }
    final baseUrl = _effectiveBridgeUrl.replaceAll(RegExp(r'/$'), '');
    final ownsClient = widget.httpClient == null;
    final client = widget.httpClient ?? http.Client();
    try {
      final response = await client.post(
        Uri.parse('$baseUrl/feedback-batches/start-session'),
        headers: const <String, String>{'Content-Type': 'application/json'},
        body: jsonEncode(batch.toBridgeJson()),
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw Exception('HTTP ${response.statusCode}: ${response.body}');
      }
      final submittedBatch = _SubmittedFeedbackBatch.fromStartResponse(
        jsonDecode(response.body) as Map<String, Object?>,
      );
      setState(() {
        _items.clear();
        _pendingQuickAskId = null;
        if (submittedBatch != null) _submittedBatches.insert(0, submittedBatch);
      });
      _showMessage('Feedback enviado a Codex CLI.');
      return true;
    } catch (_) {
      _showMessage('Guardado local; no se pudo enviar a Codex CLI.');
      return false;
    } finally {
      if (ownsClient) client.close();
    }
  }

  void _openPendingDialog() {
    final presetsFuture = _loadWorkflowPresets();
    var selectedPresetId = '';
    var releaseWhenComplete = false;
    var sending = false;
    showDialog<void>(
      context: widget.navigatorKey?.currentContext ?? context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) {
          final availableWidth = math.max(
            0.0,
            MediaQuery.sizeOf(context).width - 48,
          );
          final dialogWidth = math.min(560.0, availableWidth);
          final compactActions = MediaQuery.sizeOf(context).width < 420;
          return AlertDialog(
            title: const Text('Cola de feedback'),
            actionsOverflowDirection: VerticalDirection.down,
            actionsOverflowAlignment: OverflowBarAlignment.end,
            content: SizedBox(
              width: dialogWidth,
              child: _items.isEmpty
                  ? const Text('No hay feedback pendiente.')
                  : Column(
                      mainAxisSize: MainAxisSize.min,
                      children: <Widget>[
                        ConstrainedBox(
                          constraints: BoxConstraints(
                            maxHeight: math.min(
                              240.0,
                              MediaQuery.sizeOf(context).height * 0.32,
                            ),
                          ),
                          child: ListView.separated(
                            shrinkWrap: true,
                            cacheExtent: 1000,
                            itemCount: _items.length,
                            separatorBuilder: (_, _) =>
                                const Divider(height: 20),
                            itemBuilder: (context, index) {
                              final item = _items[index];
                              return Container(
                                key: developerFeedbackPreviewItemKey,
                                padding: const EdgeInsets.all(10),
                                decoration: BoxDecoration(
                                  border: Border.all(
                                    color: Theme.of(
                                      context,
                                    ).colorScheme.outlineVariant,
                                  ),
                                  borderRadius: BorderRadius.circular(8),
                                  color: Theme.of(
                                    context,
                                  ).colorScheme.surfaceContainerHighest,
                                ),
                                child: Row(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: <Widget>[
                                    _FeedbackPreviewThumbnail(item: item),
                                    const SizedBox(width: 12),
                                    Expanded(
                                      child: Column(
                                        crossAxisAlignment:
                                            CrossAxisAlignment.start,
                                        children: <Widget>[
                                          SelectableText(
                                            _feedbackPreviewComment(item),
                                            key:
                                                developerFeedbackPreviewCommentKey,
                                            maxLines: 4,
                                            style: Theme.of(
                                              context,
                                            ).textTheme.bodyMedium,
                                          ),
                                          const SizedBox(height: 8),
                                          Wrap(
                                            spacing: 8,
                                            runSpacing: 4,
                                            children: <Widget>[
                                              _PreviewMetaChip(
                                                key:
                                                    developerFeedbackPreviewBoundsKey,
                                                icon: Icons.crop_free,
                                                label: _formatSelectionBounds(
                                                  item.selectionBounds,
                                                ),
                                              ),
                                              _PreviewMetaChip(
                                                key:
                                                    developerFeedbackPreviewAudioKey,
                                                icon: item.audio == null
                                                    ? Icons.mic_off_outlined
                                                    : Icons.mic_none_outlined,
                                                label: _formatAudioSummary(
                                                  item.audio,
                                                ),
                                              ),
                                              if (item.guidedTrace != null)
                                                _PreviewMetaChip(
                                                  icon: Icons.timeline,
                                                  label:
                                                      '${item.guidedTrace!.frames.length} pantallas · '
                                                      '${item.guidedTrace!.timeline.length} eventos',
                                                ),
                                            ],
                                          ),
                                        ],
                                      ),
                                    ),
                                    Column(
                                      mainAxisSize: MainAxisSize.min,
                                      children: <Widget>[
                                        IconButton(
                                          key: developerFeedbackEditCommentKey,
                                          tooltip: 'Editar comentario',
                                          onPressed: sending
                                              ? null
                                              : () async {
                                                  await _editQueuedComment(
                                                    item,
                                                  );
                                                  if (context.mounted) {
                                                    setDialogState(() {});
                                                  }
                                                },
                                          icon: const Icon(Icons.edit_outlined),
                                        ),
                                        IconButton(
                                          tooltip: 'Eliminar',
                                          onPressed: sending
                                              ? null
                                              : () {
                                                  setState(() {
                                                    _items.remove(item);
                                                    if (_items.isEmpty) {
                                                      _pendingQuickAskId = null;
                                                    }
                                                  });
                                                  setDialogState(() {});
                                                },
                                          icon: const Icon(
                                            Icons.delete_outline,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ],
                                ),
                              );
                            },
                          ),
                        ),
                        const SizedBox(height: 16),
                        FutureBuilder<_DeveloperFeedbackWorkflowPresets>(
                          future: presetsFuture,
                          builder: (context, snapshot) {
                            final presets =
                                snapshot.data ??
                                _DeveloperFeedbackWorkflowPresets.fallback();
                            final presetIds = presets.presets
                                .map((preset) => preset.id)
                                .toSet();
                            final value =
                                selectedPresetId.isNotEmpty &&
                                    presetIds.contains(selectedPresetId)
                                ? selectedPresetId
                                : presets.defaultPresetId;
                            return DropdownButtonFormField<String>(
                              key: developerFeedbackPresetDropdownKey,
                              initialValue: value,
                              decoration: const InputDecoration(
                                labelText: 'Preset',
                                border: OutlineInputBorder(),
                              ),
                              isExpanded: true,
                              items: presets.presets
                                  .map(
                                    (preset) => DropdownMenuItem<String>(
                                      value: preset.id,
                                      child: Text(
                                        preset.name,
                                        overflow: TextOverflow.ellipsis,
                                      ),
                                    ),
                                  )
                                  .toList(),
                              onChanged: sending
                                  ? null
                                  : (value) {
                                      if (value == null) return;
                                      setDialogState(() {
                                        selectedPresetId = value;
                                      });
                                    },
                            );
                          },
                        ),
                        Row(
                          children: <Widget>[
                            Checkbox(
                              key: developerFeedbackReleaseWhenCompleteKey,
                              value: releaseWhenComplete,
                              onChanged: sending
                                  ? null
                                  : (value) {
                                      setDialogState(() {
                                        releaseWhenComplete = value ?? false;
                                      });
                                    },
                            ),
                            Expanded(
                              child: Text(
                                compactActions
                                    ? 'Release al finalizar'
                                    : 'Generar release al finalizar',
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
            ),
            actions: <Widget>[
              if (compactActions) ...<Widget>[
                IconButton(
                  key: developerFeedbackClearKey,
                  tooltip: 'Borrar todo',
                  onPressed: _items.isEmpty || sending
                      ? null
                      : () {
                          setState(() {
                            _items.clear();
                            _pendingQuickAskId = null;
                          });
                          setDialogState(() {});
                        },
                  icon: const Icon(Icons.delete_sweep_outlined),
                ),
                IconButton.filled(
                  key: developerFeedbackCopyKey,
                  tooltip: 'Copiar exportación',
                  onPressed: _items.isEmpty || sending ? null : _copyExport,
                  icon: const Icon(Icons.copy),
                ),
                IconButton.filled(
                  key: developerFeedbackSendBatchKey,
                  tooltip: sending ? 'Enviando' : 'Enviar',
                  onPressed: _items.isEmpty || sending
                      ? null
                      : () async {
                          setDialogState(() => sending = true);
                          final presets = await presetsFuture;
                          final sent = await _submitFeedbackBatchToBridge(
                            workflowPresetId: selectedPresetId.isEmpty
                                ? presets.defaultPresetId
                                : selectedPresetId,
                            releaseWhenComplete: releaseWhenComplete,
                          );
                          if (!context.mounted) return;
                          if (sent) {
                            Navigator.of(context).pop();
                            return;
                          }
                          setDialogState(() => sending = false);
                        },
                  icon: const Icon(Icons.send),
                ),
              ] else ...<Widget>[
                TextButton(
                  key: developerFeedbackClearKey,
                  onPressed: _items.isEmpty || sending
                      ? null
                      : () {
                          setState(() {
                            _items.clear();
                            _pendingQuickAskId = null;
                          });
                          setDialogState(() {});
                        },
                  child: const Text('Borrar todo'),
                ),
                FilledButton.icon(
                  key: developerFeedbackCopyKey,
                  onPressed: _items.isEmpty || sending ? null : _copyExport,
                  icon: const Icon(Icons.copy),
                  label: const Text('Copiar exportación'),
                ),
                FilledButton.icon(
                  key: developerFeedbackSendBatchKey,
                  onPressed: _items.isEmpty || sending
                      ? null
                      : () async {
                          setDialogState(() => sending = true);
                          final presets = await presetsFuture;
                          final sent = await _submitFeedbackBatchToBridge(
                            workflowPresetId: selectedPresetId.isEmpty
                                ? presets.defaultPresetId
                                : selectedPresetId,
                            releaseWhenComplete: releaseWhenComplete,
                          );
                          if (!context.mounted) return;
                          if (sent) {
                            Navigator.of(context).pop();
                            return;
                          }
                          setDialogState(() => sending = false);
                        },
                  icon: const Icon(Icons.send),
                  label: Text(sending ? 'Enviando' : 'Enviar'),
                ),
              ],
            ],
          );
        },
      ),
    );
  }

  Future<void> _editQueuedComment(DeveloperFeedbackItem item) async {
    final updated = await showDialog<String>(
      context: widget.navigatorKey?.currentContext ?? context,
      builder: (context) =>
          _EditFeedbackCommentDialog(initialComment: item.comment),
    );
    if (updated == null || updated == item.comment || !mounted) return;
    setState(() {
      final index = _items.indexWhere((candidate) => candidate.id == item.id);
      if (index != -1) _items[index] = item.copyWith(comment: updated);
    });
  }

  void _openRunsDialog() {
    var refreshing = <String>{};
    showDialog<void>(
      context: widget.navigatorKey?.currentContext ?? context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) {
          final availableWidth = math.max(
            0.0,
            MediaQuery.sizeOf(context).width - 48,
          );
          return AlertDialog(
            title: const Text('Runs de feedback'),
            content: SizedBox(
              width: math.min(560.0, availableWidth),
              child: _submittedBatches.isEmpty
                  ? const Text('No hay runs enviados.')
                  : ListView.separated(
                      shrinkWrap: true,
                      itemCount: _submittedBatches.length,
                      separatorBuilder: (_, _) => const Divider(height: 20),
                      itemBuilder: (context, index) {
                        final batch = _submittedBatches[index];
                        final batchId = batch.batchId;
                        final canRefresh =
                            batchId != null &&
                            _effectiveBridgeUrl.isNotEmpty &&
                            !refreshing.contains(batchId);
                        return Row(
                          crossAxisAlignment: CrossAxisAlignment.center,
                          children: <Widget>[
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: <Widget>[
                                  Text(
                                    batch.title,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                  const SizedBox(height: 4),
                                  Text(
                                    batch.statusLabel,
                                    key: developerFeedbackRunStatusKey,
                                    maxLines: 2,
                                    overflow: TextOverflow.ellipsis,
                                    style: Theme.of(
                                      context,
                                    ).textTheme.bodySmall,
                                  ),
                                ],
                              ),
                            ),
                            if (batch.hasSummary)
                              IconButton(
                                key: developerFeedbackSummaryOpenKey,
                                tooltip: 'Resumen',
                                onPressed: () => _openSummaryDialog(batch),
                                icon: const Icon(Icons.article_outlined),
                              ),
                            IconButton(
                              key: developerFeedbackRefreshRunKey,
                              tooltip: 'Actualizar',
                              onPressed: canRefresh
                                  ? () async {
                                      setDialogState(() {
                                        refreshing = {...refreshing, batchId};
                                      });
                                      await _refreshSubmittedBatch(batchId);
                                      if (!context.mounted) return;
                                      setDialogState(() {
                                        refreshing = {...refreshing}
                                          ..remove(batchId);
                                      });
                                    }
                                  : null,
                              icon: refreshing.contains(batchId)
                                  ? const SizedBox.square(
                                      dimension: 20,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                      ),
                                    )
                                  : const Icon(Icons.refresh),
                            ),
                          ],
                        );
                      },
                    ),
            ),
            actions: <Widget>[
              TextButton(
                onPressed: () => Navigator.of(context).pop(),
                child: const Text('Cerrar'),
              ),
            ],
          );
        },
      ),
    );
  }

  Future<void> _refreshSubmittedBatch(String batchId) async {
    final baseUrl = _effectiveBridgeUrl.replaceAll(RegExp(r'/$'), '');
    final ownsClient = widget.httpClient == null;
    final client = widget.httpClient ?? http.Client();
    try {
      final response = await client.get(
        Uri.parse('$baseUrl/feedback-batches/$batchId'),
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw Exception('HTTP ${response.statusCode}: ${response.body}');
      }
      final updated = _SubmittedFeedbackBatch.fromStatusResponse(
        jsonDecode(response.body) as Map<String, Object?>,
      );
      setState(() {
        final index = _submittedBatches.indexWhere(
          (batch) => batch.batchId == batchId,
        );
        if (index >= 0) _submittedBatches[index] = updated;
        if (updated.notificationUnread && _unreadNotificationCount == 0) {
          _unreadNotificationCount = 1;
        }
      });
    } catch (_) {
      _showMessage('No se pudo actualizar el run.');
    } finally {
      if (ownsClient) client.close();
    }
  }

  void _openHistoryDialog() {
    var initialized = false;
    var loading = true;
    var error = false;
    var batches = <_SubmittedFeedbackBatch>[];
    showDialog<void>(
      context: widget.navigatorKey?.currentContext ?? context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) {
          Future<void> loadHistory() async {
            setDialogState(() {
              loading = true;
              error = false;
            });
            try {
              final loaded = await _loadFeedbackHistory();
              if (!context.mounted) return;
              setDialogState(() {
                batches = loaded;
                loading = false;
              });
            } catch (_) {
              if (!context.mounted) return;
              setDialogState(() {
                loading = false;
                error = true;
              });
            }
          }

          if (!initialized) {
            initialized = true;
            unawaited(loadHistory());
          }

          final availableWidth = math.max(
            0.0,
            MediaQuery.sizeOf(context).width - 48,
          );
          return AlertDialog(
            title: const Text('Historial de feedback'),
            content: SizedBox(
              width: math.min(560.0, availableWidth),
              child: loading
                  ? const Center(child: CircularProgressIndicator())
                  : error
                  ? const Text('No se pudo cargar el historial.')
                  : batches.isEmpty
                  ? const Text('No hay feedback enviado.')
                  : ListView.separated(
                      shrinkWrap: true,
                      itemCount: batches.length,
                      separatorBuilder: (_, _) => const Divider(height: 20),
                      itemBuilder: (context, index) {
                        final batch = batches[index];
                        return Column(
                          key: developerFeedbackHistoryItemKey,
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: <Widget>[
                            Text(
                              batch.title,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                            const SizedBox(height: 4),
                            Text(
                              batch.historyLabel,
                              maxLines: 3,
                              overflow: TextOverflow.ellipsis,
                              style: Theme.of(context).textTheme.bodySmall,
                            ),
                            if (batch.hasSummary)
                              Align(
                                alignment: Alignment.centerLeft,
                                child: TextButton.icon(
                                  key: developerFeedbackSummaryOpenKey,
                                  onPressed: () => _openSummaryDialog(batch),
                                  icon: const Icon(Icons.article_outlined),
                                  label: const Text('Resumen'),
                                ),
                              ),
                          ],
                        );
                      },
                    ),
            ),
            actions: <Widget>[
              IconButton(
                key: developerFeedbackHistoryRefreshKey,
                tooltip: 'Actualizar',
                onPressed: loading ? null : () => unawaited(loadHistory()),
                icon: const Icon(Icons.refresh),
              ),
              TextButton(
                onPressed: () => Navigator.of(context).pop(),
                child: const Text('Cerrar'),
              ),
            ],
          );
        },
      ),
    );
  }

  Future<List<_SubmittedFeedbackBatch>> _loadFeedbackHistory() async {
    final baseUrl = _effectiveBridgeUrl.replaceAll(RegExp(r'/$'), '');
    final ownsClient = widget.httpClient == null;
    final client = widget.httpClient ?? http.Client();
    try {
      final uri = Uri.parse('$baseUrl/feedback-batches').replace(
        queryParameters: <String, String>{'sourceApp': widget.sourceApp},
      );
      final response = await client.get(uri);
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw Exception('HTTP ${response.statusCode}: ${response.body}');
      }
      final decoded = jsonDecode(response.body) as List<Object?>;
      return decoded
          .whereType<Map>()
          .map(
            (item) => _SubmittedFeedbackBatch.fromStatusResponse(
              item.cast<String, Object?>(),
            ),
          )
          .toList();
    } finally {
      if (ownsClient) client.close();
    }
  }

  void _openQuickAskHistoryDialog() {
    if (_unreadQuickAskCount > 0) {
      setState(() => _unreadQuickAskCount = 0);
    }
    var initialized = false;
    var loading = true;
    var error = false;
    var records = <_QuickAskRecord>[];
    showDialog<void>(
      context: widget.navigatorKey?.currentContext ?? context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) {
          Future<void> loadHistory() async {
            setDialogState(() {
              loading = true;
              error = false;
            });
            try {
              final loaded = await _loadQuickAskHistory();
              if (!context.mounted) return;
              setDialogState(() {
                records = _mergeQuickAskRecords(loaded);
                loading = false;
              });
            } catch (_) {
              if (!context.mounted) return;
              final localRecords = _sortQuickAskRecords(_currentLocalQuickAsks);
              setDialogState(() {
                loading = false;
                records = localRecords;
                error = localRecords.isEmpty;
              });
            }
          }

          if (!initialized) {
            initialized = true;
            unawaited(loadHistory());
          }

          final contentConstraints = _dialogContentConstraints(
            context,
            maxWidth: 620,
          );
          return AlertDialog(
            title: const Text('Preguntas rápidas'),
            content: SizedBox(
              width: contentConstraints.maxWidth,
              height: contentConstraints.maxHeight,
              child: loading
                  ? const Center(child: CircularProgressIndicator())
                  : error
                  ? const Text('No se pudieron cargar las preguntas.')
                  : records.isEmpty
                  ? const Text('No hay preguntas rápidas.')
                  : ListView.separated(
                      itemCount: records.length,
                      separatorBuilder: (_, _) => const SizedBox(height: 8),
                      itemBuilder: (context, index) {
                        final record = records[index];
                        return _QuickAskHistoryTile(
                          key: developerFeedbackQuickAskHistoryItemKey,
                          record: record,
                          onTap: () => unawaited(
                            _openQuickAskDetailDialog(record.quickAskId),
                          ),
                        );
                      },
                    ),
            ),
            actions: <Widget>[
              IconButton(
                tooltip: 'Actualizar',
                onPressed: loading ? null : () => unawaited(loadHistory()),
                icon: const Icon(Icons.refresh),
              ),
              TextButton(
                onPressed: () => Navigator.of(context).pop(),
                child: const Text('Cerrar'),
              ),
            ],
          );
        },
      ),
    );
  }

  Future<List<_QuickAskRecord>> _loadQuickAskHistory() async {
    final baseUrl = _effectiveBridgeUrl.replaceAll(RegExp(r'/$'), '');
    final ownsClient = widget.httpClient == null;
    final client = widget.httpClient ?? http.Client();
    try {
      final uri = Uri.parse('$baseUrl/feedback-quick-asks').replace(
        queryParameters: <String, String>{'sourceApp': widget.sourceApp},
      );
      final response = await client.get(uri);
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw Exception('HTTP ${response.statusCode}: ${response.body}');
      }
      final decoded = jsonDecode(response.body) as List<Object?>;
      return decoded
          .whereType<Map>()
          .map((item) => _QuickAskRecord.fromJson(item.cast<String, Object?>()))
          .toList();
    } finally {
      if (ownsClient) client.close();
    }
  }

  List<_QuickAskRecord> _mergeQuickAskRecords(List<_QuickAskRecord> remote) {
    final byId = <String, _QuickAskRecord>{};
    for (final record in _currentLocalQuickAsks) {
      byId[record.quickAskId] = record;
    }
    for (final record in remote) {
      byId[record.quickAskId] = record.mergedWith(byId[record.quickAskId]);
    }
    return _sortQuickAskRecords(byId.values);
  }

  Future<void> _openQuickAskDetailDialog(String quickAskId) async {
    try {
      final localDetail = _quickAskById(quickAskId);
      final detail = quickAskId.startsWith('quick-ask-local-')
          ? localDetail
          : (await _loadQuickAskDetail(quickAskId)).mergedWith(localDetail);
      if (detail == null) return;
      if (!mounted) return;
      showDialog<void>(
        context: widget.navigatorKey?.currentContext ?? context,
        builder: (context) {
          final contentConstraints = _dialogContentConstraints(
            context,
            maxWidth: 620,
          );
          final screenshot = detail.screenshotPngBase64;
          return AlertDialog(
            title: const Text('Detalle de pregunta'),
            content: SizedBox(
              width: contentConstraints.maxWidth,
              height: contentConstraints.maxHeight,
              child: SingleChildScrollView(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    if (screenshot != null)
                      ClipRRect(
                        borderRadius: BorderRadius.circular(6),
                        child: Image.memory(
                          base64Decode(screenshot),
                          key: developerFeedbackQuickAskPreviewKey,
                          height: 160,
                          width: double.infinity,
                          fit: BoxFit.contain,
                        ),
                      ),
                    const SizedBox(height: 12),
                    _DetailBlock(
                      label: 'Pregunta',
                      child: SelectableText(detail.question),
                    ),
                    const SizedBox(height: 12),
                    _DetailBlock(
                      label: 'Estado',
                      child: Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: <Widget>[
                          _StatusChip(
                            icon: detail.statusIcon,
                            label: detail.statusLabel,
                          ),
                          _PreviewMetaChip(
                            key: developerFeedbackQuickAskBoundsKey,
                            icon: Icons.crop_free,
                            label: _formatSelectionBounds(
                              detail.selectionBounds,
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 12),
                    _DetailBlock(
                      label: 'Respuesta',
                      child: SelectableText(
                        detail.answer ?? 'Sin respuesta todavía.',
                        key: developerFeedbackQuickAskAnswerKey,
                      ),
                    ),
                    const SizedBox(height: 12),
                    _DetailBlock(
                      label: 'Referencia',
                      child: Text(
                        detail.historyLabel,
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ),
                  ],
                ),
              ),
            ),
            actions: <Widget>[
              if (detail.screenshotPngBase64 != null)
                FilledButton.icon(
                  key: developerFeedbackQuickAskActKey,
                  onPressed: () {
                    Navigator.of(context).pop();
                    _actFromQuickAsk(detail);
                  },
                  icon: const Icon(Icons.play_arrow),
                  label: const Text('Actuar'),
                ),
              TextButton(
                onPressed: () => Navigator.of(context).pop(),
                child: const Text('Cerrar'),
              ),
            ],
          );
        },
      );
    } catch (_) {
      _showMessage('No se pudo cargar la pregunta.');
    }
  }

  void _actFromQuickAsk(_QuickAskRecord detail) {
    final screenshot = detail.screenshotPngBase64;
    if (screenshot == null || screenshot.isEmpty) return;
    final now = DateTime.now().toUtc();
    final answer = (detail.answer ?? '').trim();
    final item = DeveloperFeedbackItem(
      id: 'feedback-${now.microsecondsSinceEpoch}',
      createdAt: now,
      sourceApp: detail.sourceApp.isEmpty ? widget.sourceApp : detail.sourceApp,
      sourceDisplayName: detail.sourceDisplayName.isEmpty
          ? widget.sourceDisplayName
          : detail.sourceDisplayName,
      comment: [
        'Act from quick ask ${detail.quickAskId}.',
        'Question: ${detail.question}',
        if (answer.isNotEmpty) 'Prior quick ask answer: $answer',
      ].join('\n'),
      screenshotPngBase64: screenshot,
      selectionPoints: _pointsFromBounds(detail.selectionBounds),
      audio: null,
    );
    setState(() {
      _items
        ..clear()
        ..add(item);
      _pendingQuickAskId = detail.quickAskId;
      _drawing = <Offset>[];
      _selectionReady = false;
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _openPendingDialog();
    });
  }

  Future<_QuickAskRecord> _loadQuickAskDetail(String quickAskId) async {
    final baseUrl = _effectiveBridgeUrl.replaceAll(RegExp(r'/$'), '');
    final ownsClient = widget.httpClient == null;
    final client = widget.httpClient ?? http.Client();
    try {
      final response = await client.get(
        Uri.parse('$baseUrl/feedback-quick-asks/$quickAskId'),
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw Exception('HTTP ${response.statusCode}: ${response.body}');
      }
      return _QuickAskRecord.fromJson(
        jsonDecode(response.body) as Map<String, Object?>,
      );
    } finally {
      if (ownsClient) client.close();
    }
  }

  void _openNotificationCenterDialog() {
    var initialized = false;
    var loading = true;
    var error = false;
    var batches = <_SubmittedFeedbackBatch>[];
    showDialog<void>(
      context: widget.navigatorKey?.currentContext ?? context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) {
          Future<void> loadNotifications() async {
            setDialogState(() {
              loading = true;
              error = false;
            });
            try {
              final loaded = await _loadFeedbackHistory();
              if (!context.mounted) return;
              setDialogState(() {
                batches = _sortNotificationCenterBatches(loaded);
                loading = false;
              });
              _setUnreadCountFromBatches(loaded);
            } catch (_) {
              if (!context.mounted) return;
              setDialogState(() {
                loading = false;
                error = true;
              });
            }
          }

          if (!initialized) {
            initialized = true;
            unawaited(loadNotifications());
          }

          final availableWidth = math.max(
            0.0,
            MediaQuery.sizeOf(context).width - 48,
          );
          return AlertDialog(
            key: developerFeedbackNotificationCenterKey,
            title: const Text('Notificaciones'),
            content: SizedBox(
              width: math.min(560.0, availableWidth),
              child: loading
                  ? const Center(child: CircularProgressIndicator())
                  : error
                  ? const Text('No se pudieron cargar las notificaciones.')
                  : batches.isEmpty
                  ? const Text('No hay notificaciones.')
                  : ListView(
                      shrinkWrap: true,
                      children: <Widget>[
                        ..._notificationSection(
                          context,
                          title: 'Terminados',
                          batches: batches
                              .where((batch) => batch.isCompleted)
                              .toList(),
                          setDialogState: setDialogState,
                          allBatches: batches,
                        ),
                        ..._notificationSection(
                          context,
                          title: 'Activos',
                          batches: batches
                              .where((batch) => batch.isActive)
                              .toList(),
                          setDialogState: setDialogState,
                          allBatches: batches,
                        ),
                        ..._notificationSection(
                          context,
                          title: 'Fallidos',
                          batches: batches
                              .where((batch) => batch.isFailed)
                              .toList(),
                          setDialogState: setDialogState,
                          allBatches: batches,
                        ),
                      ],
                    ),
            ),
            actions: <Widget>[
              IconButton(
                tooltip: 'Actualizar',
                onPressed: loading
                    ? null
                    : () => unawaited(loadNotifications()),
                icon: const Icon(Icons.refresh),
              ),
              TextButton(
                onPressed: () => Navigator.of(context).pop(),
                child: const Text('Cerrar'),
              ),
            ],
          );
        },
      ),
    );
  }

  List<Widget> _notificationSection(
    BuildContext context, {
    required String title,
    required List<_SubmittedFeedbackBatch> batches,
    required StateSetter setDialogState,
    required List<_SubmittedFeedbackBatch> allBatches,
  }) {
    if (batches.isEmpty) return <Widget>[];
    return <Widget>[
      Padding(
        padding: const EdgeInsets.only(top: 8, bottom: 8),
        child: Text(title, style: Theme.of(context).textTheme.titleSmall),
      ),
      for (final batch in batches)
        ListTile(
          key: ValueKey<String>(
            'developer-feedback-notification-item-${batch.batchId ?? batch.title}',
          ),
          contentPadding: EdgeInsets.zero,
          title: Text(
            batch.title,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
          subtitle: Text(
            batch.notificationLabel,
            maxLines: 3,
            overflow: TextOverflow.ellipsis,
          ),
          leading: Icon(
            batch.isFailed
                ? Icons.error_outline
                : batch.isActive
                ? Icons.timelapse
                : Icons.check_circle_outline,
          ),
          trailing: Wrap(
            spacing: 4,
            children: <Widget>[
              if (batch.hasSummary)
                IconButton(
                  key: developerFeedbackSummaryOpenKey,
                  tooltip: 'Resumen',
                  onPressed: () => _openSummaryDialog(batch),
                  icon: const Icon(Icons.article_outlined),
                ),
              if (batch.notificationUnread && batch.batchId != null)
                IconButton(
                  key: developerFeedbackNotificationMarkReadKey,
                  tooltip: 'Marcar leído',
                  onPressed: () async {
                    final updated = await _markNotificationRead(batch.batchId!);
                    if (updated == null || !context.mounted) return;
                    setDialogState(() {
                      final index = allBatches.indexWhere(
                        (current) => current.batchId == updated.batchId,
                      );
                      if (index >= 0) allBatches[index] = updated;
                    });
                    _setUnreadCountFromBatches(allBatches);
                  },
                  icon: const Icon(Icons.mark_email_read_outlined),
                ),
            ],
          ),
        ),
    ];
  }

  Future<_SubmittedFeedbackBatch?> _markNotificationRead(String batchId) async {
    final baseUrl = _effectiveBridgeUrl.replaceAll(RegExp(r'/$'), '');
    final ownsClient = widget.httpClient == null;
    final client = widget.httpClient ?? http.Client();
    try {
      final response = await client.patch(
        Uri.parse('$baseUrl/feedback-batches/$batchId/notification'),
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw Exception('HTTP ${response.statusCode}: ${response.body}');
      }
      return _SubmittedFeedbackBatch.fromStatusResponse(
        jsonDecode(response.body) as Map<String, Object?>,
      );
    } catch (_) {
      _showMessage('No se pudo marcar la notificación.');
      return null;
    } finally {
      if (ownsClient) client.close();
    }
  }

  List<_SubmittedFeedbackBatch> _sortNotificationCenterBatches(
    List<_SubmittedFeedbackBatch> batches,
  ) {
    return List<_SubmittedFeedbackBatch>.of(batches)..sort((a, b) {
      final unread =
          (b.notificationUnread ? 1 : 0) - (a.notificationUnread ? 1 : 0);
      if (unread != 0) return unread;
      return a.status.compareTo(b.status);
    });
  }

  void _setUnreadCountFromBatches(List<_SubmittedFeedbackBatch> batches) {
    if (!mounted) return;
    setState(() {
      _unreadNotificationCount = batches
          .where((batch) => batch.notificationUnread)
          .length;
    });
  }

  void _scheduleNotificationRefresh() {
    if (_notificationRefreshScheduled || _effectiveBridgeUrl.isEmpty) {
      return;
    }
    _notificationRefreshScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      unawaited(_refreshNotificationCount());
    });
  }

  Future<void> _refreshNotificationCount() async {
    try {
      final batches = await _loadFeedbackHistory();
      if (!mounted) return;
      _setUnreadCountFromBatches(batches);
    } catch (_) {
      if (!mounted) return;
      setState(() => _unreadNotificationCount = 0);
    }
  }

  void _openSummaryDialog(_SubmittedFeedbackBatch batch) {
    showDialog<void>(
      context: widget.navigatorKey?.currentContext ?? context,
      builder: (context) {
        final availableWidth = math.max(
          0.0,
          MediaQuery.sizeOf(context).width - 48,
        );
        return AlertDialog(
          title: const Text('Resumen final'),
          content: SizedBox(
            width: math.min(560.0, availableWidth),
            child: SingleChildScrollView(
              child: Text(
                batch.summary ?? '',
                key: developerFeedbackSummaryKey,
              ),
            ),
          ),
          actions: <Widget>[
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Cerrar'),
            ),
          ],
        );
      },
    );
  }

  Future<void> _copyExport() async {
    final export = DeveloperFeedbackExport(items: List.of(_items)).toJsonText();
    try {
      final copyText = widget.copyText;
      if (copyText == null) {
        await Clipboard.setData(ClipboardData(text: export));
      } else {
        await copyText(export);
      }
      _showMessage('Cola copiada.');
    } catch (_) {
      _showMessage(
        'Exportación generada; copiala desde la integración disponible.',
      );
    }
  }

  void _showMessage(String message) {
    final messenger =
        widget.scaffoldMessengerKey?.currentState ??
        ScaffoldMessenger.maybeOf(context);
    messenger?.showSnackBar(SnackBar(content: Text(message)));
  }

  void _showBridgeUnavailableMessage() {
    _showMessage(
      'Bridge no configurado: definí CODEX_FEEDBACK_BRIDGE_URL o '
      'CODEX_APP_UPDATER_BRIDGE_URL para usar esta acción.',
    );
  }

  void _openBridgeUnavailableDialog() {
    showDialog<void>(
      context: _modalContext,
      builder: (context) => AlertDialog(
        key: developerFeedbackBridgeUnavailableKey,
        title: const Text('Bridge no configurado'),
        content: const Text(
          'No se pudo obtener la URL de Codex Mobile Bridge. '
          'Notificaciones, historial y preguntas rápidas necesitan Bridge. '
          'Revisá CODEX_FEEDBACK_BRIDGE_URL o CODEX_APP_UPDATER_BRIDGE_URL '
          'en el build de la app.',
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cerrar'),
          ),
        ],
      ),
    );
  }
}

class _DeveloperFeedbackAppUpdater extends StatefulWidget {
  const _DeveloperFeedbackAppUpdater({
    required this.enabled,
    required this.sourceApp,
    required this.bridgeUrl,
    required this.currentVersion,
    required this.currentBuild,
    required this.platform,
    required this.channel,
    required this.requireChecksum,
    required this.controller,
    required this.checkOnStart,
    required this.checkOnResume,
    required this.child,
  });

  final bool enabled;
  final String sourceApp;
  final String bridgeUrl;
  final String? currentVersion;
  final int? currentBuild;
  final String platform;
  final String channel;
  final bool requireChecksum;
  final CodexAppUpdaterController? controller;
  final bool checkOnStart;
  final bool checkOnResume;
  final Widget child;

  @override
  State<_DeveloperFeedbackAppUpdater> createState() =>
      _DeveloperFeedbackAppUpdaterState();
}

class _DeveloperFeedbackAppUpdaterState
    extends State<_DeveloperFeedbackAppUpdater> {
  Future<PackageInfo>? _packageInfoFuture;

  @override
  void initState() {
    super.initState();
    _maybeLoadPackageInfo();
  }

  @override
  void didUpdateWidget(covariant _DeveloperFeedbackAppUpdater oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.enabled != widget.enabled ||
        oldWidget.currentVersion != widget.currentVersion ||
        oldWidget.currentBuild != widget.currentBuild) {
      _maybeLoadPackageInfo();
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.enabled) return widget.child;
    final explicitVersion = widget.currentVersion?.trim();
    final explicitBuild = widget.currentBuild;
    if (explicitVersion != null &&
        explicitVersion.isNotEmpty &&
        explicitBuild != null) {
      return _buildUpdater(explicitVersion, explicitBuild);
    }
    final packageInfoFuture = _packageInfoFuture;
    if (packageInfoFuture == null) return widget.child;
    return FutureBuilder<PackageInfo>(
      future: packageInfoFuture,
      builder: (context, snapshot) {
        final packageInfo = snapshot.data;
        if (packageInfo == null) return widget.child;
        final version = explicitVersion?.isNotEmpty == true
            ? explicitVersion!
            : packageInfo.version;
        final build = explicitBuild ?? int.tryParse(packageInfo.buildNumber);
        if (version.trim().isEmpty || build == null) return widget.child;
        return _buildUpdater(version, build);
      },
    );
  }

  void _maybeLoadPackageInfo() {
    final explicitVersion = widget.currentVersion?.trim();
    if (!widget.enabled ||
        (explicitVersion != null &&
            explicitVersion.isNotEmpty &&
            widget.currentBuild != null)) {
      _packageInfoFuture = null;
      return;
    }
    _packageInfoFuture ??= PackageInfo.fromPlatform();
  }

  Widget _buildUpdater(String currentVersion, int currentBuild) {
    return CodexAppUpdater(
      config: CodexAppUpdaterConfig(
        sourceApp: widget.sourceApp,
        bridgeUrl: widget.bridgeUrl,
        currentVersion: currentVersion,
        currentBuild: currentBuild,
        platform: widget.platform,
        channel: widget.channel,
        enabled: widget.enabled,
        requireChecksum: widget.requireChecksum,
      ),
      controller: widget.controller,
      checkOnStart: widget.checkOnStart,
      checkOnResume: widget.checkOnResume,
      child: widget.child,
    );
  }
}

class _SelectionActions extends StatelessWidget {
  const _SelectionActions({
    required this.onComment,
    required this.onQuickAsk,
    required this.onReset,
  });

  final VoidCallback onComment;
  final VoidCallback? onQuickAsk;
  final VoidCallback onReset;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.bottomCenter,
      child: Material(
        color: Theme.of(context).colorScheme.surface,
        elevation: 6,
        borderRadius: BorderRadius.circular(8),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
          child: Wrap(
            alignment: WrapAlignment.center,
            crossAxisAlignment: WrapCrossAlignment.center,
            spacing: 8,
            runSpacing: 4,
            children: <Widget>[
              TextButton.icon(
                key: developerFeedbackResetSelectionKey,
                onPressed: onReset,
                icon: const Icon(Icons.refresh),
                label: const Text('Rehacer'),
              ),
              if (onQuickAsk != null)
                FilledButton.icon(
                  key: developerFeedbackQuickAskActionKey,
                  onPressed: onQuickAsk,
                  icon: const Icon(Icons.help_outline),
                  label: const Text('Preguntar'),
                ),
              FilledButton.icon(
                key: developerFeedbackCommentActionKey,
                onPressed: onComment,
                icon: const Icon(Icons.mode_comment_outlined),
                label: const Text('Comentar'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _DraggableToolbarShell extends StatelessWidget {
  const _DraggableToolbarShell({
    required this.child,
    required this.onDragUpdate,
    super.key,
  });

  final Widget child;
  final ValueChanged<Offset> onDragUpdate;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.translucent,
      onPanUpdate: (details) => onDragUpdate(details.delta),
      child: child,
    );
  }
}

class _Toolbar extends StatelessWidget {
  const _Toolbar({
    required this.expanded,
    required this.editMode,
    required this.compact,
    required this.pendingCount,
    required this.submittedCount,
    required this.bridgeAvailable,
    required this.unreadNotificationCount,
    required this.quickAskActivityCount,
    required this.onEditModeChanged,
    required this.onExpandedChanged,
    required this.onOpenPending,
    required this.onOpenRuns,
    required this.onOpenHistory,
    required this.onOpenNotifications,
    required this.onOpenQuickAskHistory,
    required this.guidedTraceEnabled,
    required this.guidedTraceRecording,
    required this.guidedTraceBusy,
    required this.onStartGuidedTrace,
    required this.onStopGuidedTrace,
  });

  final bool expanded;
  final bool editMode;
  final bool compact;
  final int pendingCount;
  final int submittedCount;
  final bool bridgeAvailable;
  final int unreadNotificationCount;
  final int quickAskActivityCount;
  final ValueChanged<bool> onEditModeChanged;
  final ValueChanged<bool> onExpandedChanged;
  final VoidCallback? onOpenPending;
  final VoidCallback? onOpenRuns;
  final VoidCallback? onOpenHistory;
  final VoidCallback? onOpenNotifications;
  final VoidCallback? onOpenQuickAskHistory;
  final bool guidedTraceEnabled;
  final bool guidedTraceRecording;
  final bool guidedTraceBusy;
  final VoidCallback onStartGuidedTrace;
  final VoidCallback onStopGuidedTrace;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final hasOverlay = Overlay.maybeOf(context) != null;
    String? toolbarTooltip(String value) => hasOverlay ? value : null;
    final buttonConstraints = compact
        ? const BoxConstraints.tightFor(width: 40, height: 40)
        : null;
    final buttonPadding = compact ? EdgeInsets.zero : null;
    final toolbarPadding = compact
        ? const EdgeInsets.symmetric(horizontal: 4, vertical: 4)
        : const EdgeInsets.symmetric(horizontal: 10, vertical: 6);
    final itemSpacing = compact ? 2.0 : 6.0;
    if (!expanded) {
      return Material(
        key: developerFeedbackToolbarKey,
        color: colorScheme.surface,
        elevation: 6,
        borderRadius: BorderRadius.circular(8),
        child: SizedBox.square(
          dimension: 48,
          child: IconButton(
            key: developerFeedbackToolbarExpandKey,
            tooltip: toolbarTooltip('Expandir feedback'),
            onPressed: () => onExpandedChanged(true),
            icon: _ToolbarStatusBadge(
              pendingCount: pendingCount,
              submittedCount: submittedCount,
              unreadNotificationCount: unreadNotificationCount,
              quickAskActivityCount: quickAskActivityCount,
              child: const Icon(Icons.bug_report_outlined),
            ),
          ),
        ),
      );
    }

    return Material(
      key: developerFeedbackToolbarKey,
      color: colorScheme.surface,
      elevation: 6,
      borderRadius: BorderRadius.circular(8),
      clipBehavior: Clip.antiAlias,
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxWidth: math.max(48.0, MediaQuery.sizeOf(context).width - 16),
        ),
        child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Padding(
            padding: toolbarPadding,
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                IconButton(
                  key: developerFeedbackToolbarCollapseKey,
                  constraints: buttonConstraints,
                  padding: buttonPadding,
                  tooltip: toolbarTooltip('Contraer feedback'),
                  onPressed: () => onExpandedChanged(false),
                  icon: const Icon(Icons.keyboard_arrow_right),
                ),
                InkWell(
                  borderRadius: BorderRadius.circular(6),
                  onTap: () => onEditModeChanged(!editMode),
                  child: Padding(
                    padding: EdgeInsets.only(left: compact ? 0 : 4),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: <Widget>[
                        if (compact)
                          const Icon(Icons.bug_report_outlined)
                        else
                          const Text('Plantilla'),
                        SizedBox(width: compact ? 4 : 8),
                        Switch(
                          key: developerFeedbackSwitchKey,
                          value: editMode,
                          onChanged: onEditModeChanged,
                        ),
                      ],
                    ),
                  ),
                ),
                if (guidedTraceEnabled) ...<Widget>[
                  SizedBox(width: itemSpacing),
                  IconButton(
                    key: guidedTraceRecording
                        ? developerFeedbackGuidedTraceStopKey
                        : developerFeedbackGuidedTraceStartKey,
                    constraints: buttonConstraints,
                    padding: buttonPadding,
                    tooltip: toolbarTooltip(
                      guidedTraceRecording
                          ? 'Detener recorrido'
                          : 'Grabar recorrido',
                    ),
                    onPressed: guidedTraceBusy
                        ? null
                        : guidedTraceRecording
                        ? onStopGuidedTrace
                        : onStartGuidedTrace,
                    icon: Icon(
                      guidedTraceRecording
                          ? Icons.stop_circle_outlined
                          : Icons.radio_button_checked,
                    ),
                  ),
                ],
                if (pendingCount > 0) ...<Widget>[
                  SizedBox(width: itemSpacing),
                  IconButton(
                    key: developerFeedbackPendingKey,
                    constraints: buttonConstraints,
                    padding: buttonPadding,
                    tooltip: toolbarTooltip('Pendientes'),
                    onPressed: onOpenPending,
                    icon: Badge.count(
                      count: pendingCount,
                      child: const Icon(Icons.pending_actions),
                    ),
                  ),
                ],
                if (submittedCount > 0) ...<Widget>[
                  SizedBox(width: itemSpacing),
                  IconButton(
                    key: developerFeedbackRunsKey,
                    constraints: buttonConstraints,
                    padding: buttonPadding,
                    tooltip: toolbarTooltip('Runs'),
                    onPressed: onOpenRuns,
                    icon: Badge.count(
                      count: submittedCount,
                      child: const Icon(Icons.track_changes),
                    ),
                  ),
                ],
                ...<Widget>[
                  SizedBox(width: itemSpacing),
                  IconButton(
                    key: developerFeedbackNotificationBellKey,
                    constraints: buttonConstraints,
                    padding: buttonPadding,
                    tooltip: toolbarTooltip('Notificaciones'),
                    onPressed: onOpenNotifications,
                    icon: !bridgeAvailable
                        ? const Icon(Icons.notifications_off_outlined)
                        : unreadNotificationCount > 0
                        ? Badge.count(
                            count: unreadNotificationCount,
                            child: const Icon(Icons.notifications_outlined),
                          )
                        : const Icon(Icons.notifications_none),
                  ),
                  IconButton(
                    key: developerFeedbackHistoryKey,
                    constraints: buttonConstraints,
                    padding: buttonPadding,
                    tooltip: toolbarTooltip('Historial'),
                    onPressed: onOpenHistory,
                    icon: Icon(
                      bridgeAvailable
                          ? Icons.history
                          : Icons.history_toggle_off,
                    ),
                  ),
                  IconButton(
                    key: developerFeedbackQuickAskHistoryKey,
                    constraints: buttonConstraints,
                    padding: buttonPadding,
                    tooltip: toolbarTooltip('Preguntas rápidas'),
                    onPressed: onOpenQuickAskHistory,
                    icon: !bridgeAvailable
                        ? const Icon(Icons.manage_search)
                        : quickAskActivityCount > 0
                        ? Badge.count(
                            count: quickAskActivityCount,
                            child: const Icon(Icons.manage_search),
                          )
                        : const Icon(Icons.manage_search),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _ToolbarStatusBadge extends StatelessWidget {
  const _ToolbarStatusBadge({
    required this.pendingCount,
    required this.submittedCount,
    required this.unreadNotificationCount,
    required this.quickAskActivityCount,
    required this.child,
  });

  final int pendingCount;
  final int submittedCount;
  final int unreadNotificationCount;
  final int quickAskActivityCount;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final count =
        pendingCount +
        submittedCount +
        unreadNotificationCount +
        quickAskActivityCount;
    if (count <= 0) return child;
    return Badge.count(count: count, child: child);
  }
}

class _GuidedTraceRecordingBanner extends StatelessWidget {
  const _GuidedTraceRecordingBanner({
    required this.recording,
    required this.stopping,
    required this.onStop,
    required this.onDiscard,
  });

  final _GuidedTraceRecording recording;
  final bool stopping;
  final VoidCallback onStop;
  final VoidCallback onDiscard;

  @override
  Widget build(BuildContext context) {
    final duration = Duration(milliseconds: recording.elapsedMs);
    final minutes = duration.inMinutes.toString().padLeft(2, '0');
    final seconds = duration.inSeconds.remainder(60).toString().padLeft(2, '0');
    return Align(
      alignment: Alignment.bottomCenter,
      child: Material(
        key: developerFeedbackGuidedTraceBannerKey,
        color: Theme.of(context).colorScheme.surface,
        elevation: 6,
        borderRadius: BorderRadius.circular(8),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
          child: Wrap(
            alignment: WrapAlignment.center,
            crossAxisAlignment: WrapCrossAlignment.center,
            spacing: 8,
            runSpacing: 4,
            children: <Widget>[
              Chip(
                avatar: const Icon(Icons.radio_button_checked, size: 18),
                label: Text(
                  '$minutes:$seconds · ${recording.frames.length} pantallas',
                ),
              ),
              TextButton.icon(
                key: developerFeedbackGuidedTraceDiscardKey,
                onPressed: stopping ? null : onDiscard,
                icon: const Icon(Icons.delete_outline),
                label: const Text('Descartar'),
              ),
              FilledButton.icon(
                key: developerFeedbackGuidedTraceStopKey,
                onPressed: stopping ? null : onStop,
                icon: const Icon(Icons.stop_circle_outlined),
                label: Text(stopping ? 'Procesando' : 'Detener'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _GuidedTracePreviewDialog extends StatefulWidget {
  const _GuidedTracePreviewDialog({
    required this.trace,
    required this.audio,
    required this.onAttach,
    required this.onDiscard,
    required this.onRerecord,
  });

  final DeveloperFeedbackGuidedTrace trace;
  final DeveloperFeedbackAudioClip? audio;
  final ValueChanged<String> onAttach;
  final VoidCallback onDiscard;
  final VoidCallback onRerecord;

  @override
  State<_GuidedTracePreviewDialog> createState() =>
      _GuidedTracePreviewDialogState();
}

class _GuidedTracePreviewDialogState extends State<_GuidedTracePreviewDialog> {
  final _commentController = TextEditingController();

  @override
  void dispose() {
    _commentController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final availableWidth = math.max(0.0, MediaQuery.sizeOf(context).width - 48);
    final dialogWidth = math.min(520.0, availableWidth);
    final recording =
        widget.trace.toJson()['recording'] as Map<String, Object?>;
    final durationMs = (recording['durationMs'] as int?) ?? 0;
    final duration = Duration(milliseconds: durationMs);
    final seconds = math.max(1, duration.inSeconds);
    return AlertDialog(
      title: const Text('Recorrido grabado'),
      content: SizedBox(
        width: dialogWidth,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Wrap(
              spacing: 8,
              runSpacing: 4,
              children: <Widget>[
                _PreviewMetaChip(
                  icon: Icons.image_outlined,
                  label: '${widget.trace.frames.length} pantallas',
                ),
                _PreviewMetaChip(
                  icon: Icons.timeline,
                  label: '${widget.trace.timeline.length} eventos',
                ),
                _PreviewMetaChip(
                  icon: widget.audio == null
                      ? Icons.mic_off_outlined
                      : Icons.mic_none_outlined,
                  label: widget.audio == null
                      ? 'Audio: sin adjunto'
                      : _formatAudioSummary(widget.audio),
                ),
                _PreviewMetaChip(
                  icon: Icons.timer_outlined,
                  label: '$seconds s',
                ),
              ],
            ),
            const SizedBox(height: 12),
            TextField(
              key: developerFeedbackGuidedTraceCommentKey,
              controller: _commentController,
              minLines: 3,
              maxLines: 5,
              decoration: const InputDecoration(
                labelText: 'Comentario',
                helperText: 'Opcional si el recorrido/audio explica el cambio',
                border: OutlineInputBorder(),
              ),
            ),
          ],
        ),
      ),
      actions: <Widget>[
        TextButton(onPressed: widget.onDiscard, child: const Text('Descartar')),
        TextButton.icon(
          key: developerFeedbackGuidedTraceRerecordKey,
          onPressed: widget.onRerecord,
          icon: const Icon(Icons.refresh),
          label: const Text('Regrabar'),
        ),
        FilledButton.icon(
          key: developerFeedbackGuidedTraceAttachKey,
          onPressed: () => widget.onAttach(_commentController.text),
          icon: const Icon(Icons.playlist_add_check),
          label: const Text('Agregar a cola'),
        ),
      ],
    );
  }
}

class _DrawingOverlay extends StatefulWidget {
  const _DrawingOverlay({
    required this.points,
    required this.onStart,
    required this.onUpdate,
    required this.onComplete,
    super.key,
  });

  final List<Offset> points;
  final ValueChanged<Offset> onStart;
  final ValueChanged<Offset> onUpdate;
  final VoidCallback onComplete;

  @override
  State<_DrawingOverlay> createState() => _DrawingOverlayState();
}

class _DrawingOverlayState extends State<_DrawingOverlay> {
  final List<Offset> _gesturePoints = <Offset>[];

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onPanStart: (details) => _start(details.localPosition),
      onPanUpdate: (details) => _update(details.localPosition),
      onPanEnd: (_) => _complete(),
      child: CustomPaint(
        painter: _SelectionPainter(
          _gesturePoints.isEmpty ? widget.points : _gesturePoints,
        ),
        child: const SizedBox.expand(),
      ),
    );
  }

  void _start(Offset point) {
    setState(() {
      _gesturePoints
        ..clear()
        ..add(point);
    });
    widget.onStart(point);
  }

  void _update(Offset point) {
    setState(() => _gesturePoints.add(point));
    widget.onUpdate(point);
  }

  void _complete() {
    if (_gesturePoints.isEmpty) return;
    widget.onComplete();
    setState(_gesturePoints.clear);
  }
}

bool _hasEnoughSelection(List<Offset> points) {
  const minimumSelectionDistance = 180.0;
  const minimumSelectionPoints = 8;
  const minimumSelectionSpan = 72.0;
  if (points.length < minimumSelectionPoints) return false;
  var left = points.first.dx;
  var right = points.first.dx;
  var top = points.first.dy;
  var bottom = points.first.dy;
  var distance = 0.0;
  for (var i = 1; i < points.length; i += 1) {
    final point = points[i];
    left = math.min(left, point.dx);
    right = math.max(right, point.dx);
    top = math.min(top, point.dy);
    bottom = math.max(bottom, point.dy);
    distance += (points[i] - points[i - 1]).distance;
  }
  return distance >= minimumSelectionDistance &&
      right - left >= minimumSelectionSpan &&
      bottom - top >= minimumSelectionSpan;
}

class _SelectionPainter extends CustomPainter {
  const _SelectionPainter(this.points);

  final List<Offset> points;

  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawRect(
      Offset.zero & size,
      Paint()..color = const Color(0x22000000),
    );
    if (points.length < 2) return;
    final paint = Paint()
      ..color = Colors.redAccent
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3
      ..strokeCap = StrokeCap.round;
    final path = Path()..moveTo(points.first.dx, points.first.dy);
    for (final point in points.skip(1)) {
      path.lineTo(point.dx, point.dy);
    }
    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(_SelectionPainter oldDelegate) =>
      !listEquals(points, oldDelegate.points);
}

class _FeedbackDialog extends StatefulWidget {
  const _FeedbackDialog({required this.recorder, required this.onSave});

  final DeveloperFeedbackAudioRecorder recorder;
  final Future<void> Function(_FeedbackDraft draft) onSave;

  @override
  State<_FeedbackDialog> createState() => _FeedbackDialogState();
}

class _FeedbackDialogState extends State<_FeedbackDialog> {
  static const _maxRecordingDuration = Duration(seconds: 30);

  final _commentController = TextEditingController();
  DeveloperFeedbackAudioClip? _audio;
  var _recording = false;
  var _audioUnsupported = false;
  var _audioBusy = false;
  var _saving = false;
  Timer? _maxRecordingTimer;

  @override
  void initState() {
    super.initState();
    _commentController.addListener(() => setState(() {}));
    widget.recorder.isSupported.then((supported) {
      if (mounted) setState(() => _audioUnsupported = !supported);
    });
  }

  @override
  void dispose() {
    _maxRecordingTimer?.cancel();
    _commentController.dispose();
    unawaited(widget.recorder.cancel());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final availableWidth = math.max(0.0, MediaQuery.sizeOf(context).width - 48);
    final dialogWidth = math.min(460.0, availableWidth);
    final compactDialog = MediaQuery.sizeOf(context).width < 420;
    final hasContent =
        _commentController.text.trim().isNotEmpty || _audio != null;
    return AlertDialog(
      title: const Text('Guardar feedback'),
      content: SizedBox(
        width: dialogWidth,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            TextField(
              key: developerFeedbackCommentKey,
              controller: _commentController,
              minLines: 3,
              maxLines: 5,
              decoration: const InputDecoration(
                labelText: 'Comentario',
                helperText: 'Opcional si adjuntas audio',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 12),
            Align(
              alignment: Alignment.centerLeft,
              child: OutlinedButton.icon(
                key: const Key('developer-feedback-audio'),
                onPressed: _audioBusy || _saving
                    ? null
                    : _audioUnsupported
                    ? _showUnsupportedAudio
                    : _toggleAudio,
                icon: Icon(_recording ? Icons.stop : Icons.mic),
                label: Text(
                  _audioBusy
                      ? (compactDialog ? 'Procesando' : 'Procesando audio')
                      : _audio == null
                      ? (_recording
                            ? (compactDialog
                                  ? 'Detener audio'
                                  : 'Detener audio (30 s máx.)')
                            : (compactDialog
                                  ? 'Grabar audio'
                                  : 'Grabar audio (30 s máx.)'))
                      : 'Audio adjunto',
                ),
              ),
            ),
          ],
        ),
      ),
      actions: <Widget>[
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancelar'),
        ),
        FilledButton(
          key: developerFeedbackSaveKey,
          onPressed: !hasContent || _recording || _audioBusy || _saving
              ? null
              : () async {
                  setState(() => _saving = true);
                  await widget.onSave(
                    _FeedbackDraft(
                      comment: _commentController.text.trim(),
                      audio: _audio,
                    ),
                  );
                  if (!context.mounted) return;
                  Navigator.of(context).pop();
                },
          child: Text(_saving ? 'Guardando' : 'Guardar'),
        ),
      ],
    );
  }

  Future<void> _toggleAudio() async {
    if (!mounted) return;
    if (_audioBusy) return;
    if (_recording) {
      await _stopRecording();
      return;
    }

    setState(() {
      _audioBusy = true;
      _audio = null;
    });
    try {
      await widget.recorder.start();
      if (!mounted) return;
      _maxRecordingTimer?.cancel();
      _maxRecordingTimer = Timer(
        _maxRecordingDuration,
        () => unawaited(_stopRecording()),
      );
      setState(() {
        _recording = true;
        _audioBusy = false;
      });
    } catch (error) {
      await widget.recorder.cancel();
      if (!mounted) return;
      setState(() {
        _recording = false;
        _audioBusy = false;
        if (error is UnsupportedError) _audioUnsupported = true;
      });
      if (error is UnsupportedError) {
        _showUnsupportedAudio();
      } else {
        _showAudioError();
      }
    }
  }

  Future<void> _stopRecording() async {
    if (!mounted) return;
    if (_audioBusy) return;
    setState(() => _audioBusy = true);
    _maxRecordingTimer?.cancel();
    _maxRecordingTimer = null;
    try {
      final clip = await widget.recorder.stop();
      if (!mounted) return;
      setState(() {
        _audio = clip;
        _recording = false;
        _audioBusy = false;
      });
    } catch (_) {
      await widget.recorder.cancel();
      if (!mounted) return;
      setState(() {
        _audio = null;
        _recording = false;
        _audioBusy = false;
      });
      _showAudioError();
    }
  }

  void _showUnsupportedAudio() {
    ScaffoldMessenger.maybeOf(context)?.showSnackBar(
      const SnackBar(content: Text('Audio no soportado en este entorno.')),
    );
  }

  void _showAudioError() {
    ScaffoldMessenger.maybeOf(
      context,
    )?.showSnackBar(const SnackBar(content: Text('No se pudo grabar audio.')));
  }
}

class _EditFeedbackCommentDialog extends StatefulWidget {
  const _EditFeedbackCommentDialog({required this.initialComment});

  final String initialComment;

  @override
  State<_EditFeedbackCommentDialog> createState() =>
      _EditFeedbackCommentDialogState();
}

class _EditFeedbackCommentDialogState
    extends State<_EditFeedbackCommentDialog> {
  late final TextEditingController _controller = TextEditingController(
    text: widget.initialComment,
  );

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Editar comentario'),
      content: TextField(
        key: developerFeedbackCommentKey,
        controller: _controller,
        minLines: 3,
        maxLines: 8,
        decoration: const InputDecoration(
          labelText: 'Comentario',
          border: OutlineInputBorder(),
        ),
      ),
      actions: <Widget>[
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancelar'),
        ),
        FilledButton(
          onPressed: () {
            final value = _controller.text.trim();
            if (value.isEmpty) return;
            Navigator.of(context).pop(value);
          },
          child: const Text('Guardar'),
        ),
      ],
    );
  }
}

class _FeedbackPreviewThumbnail extends StatelessWidget {
  const _FeedbackPreviewThumbnail({required this.item});

  final DeveloperFeedbackItem item;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(6),
      child: Image.memory(
        _decodePreviewImage(item.screenshotPngBase64),
        key: developerFeedbackPreviewThumbnailKey,
        width: 72,
        height: 72,
        fit: BoxFit.cover,
        errorBuilder: (context, error, stackTrace) => Container(
          width: 72,
          height: 72,
          color: Theme.of(context).colorScheme.surfaceContainerHighest,
          alignment: Alignment.center,
          child: const Icon(Icons.broken_image_outlined),
        ),
      ),
    );
  }
}

class _PreviewMetaChip extends StatelessWidget {
  const _PreviewMetaChip({required this.icon, required this.label, super.key});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(6),
        color: theme.colorScheme.surface,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(icon, size: 14, color: theme.colorScheme.onSurfaceVariant),
          const SizedBox(width: 4),
          Flexible(
            child: Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: theme.textTheme.labelSmall,
            ),
          ),
        ],
      ),
    );
  }
}

class _StatusChip extends StatelessWidget {
  const _StatusChip({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(6),
        color: theme.colorScheme.secondaryContainer,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(icon, size: 16, color: theme.colorScheme.onSecondaryContainer),
          const SizedBox(width: 6),
          Text(
            label,
            style: theme.textTheme.labelMedium?.copyWith(
              color: theme.colorScheme.onSecondaryContainer,
            ),
          ),
        ],
      ),
    );
  }
}

class _DetailBlock extends StatelessWidget {
  const _DetailBlock({required this.label, required this.child});

  final String label;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Text(label, style: Theme.of(context).textTheme.labelLarge),
        const SizedBox(height: 6),
        child,
      ],
    );
  }
}

class _QuickAskHistoryTile extends StatelessWidget {
  const _QuickAskHistoryTile({
    required this.record,
    required this.onTap,
    super.key,
  });

  final _QuickAskRecord record;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Material(
      color: theme.colorScheme.surfaceContainerHighest,
      borderRadius: BorderRadius.circular(8),
      child: InkWell(
        borderRadius: BorderRadius.circular(8),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Icon(record.statusIcon, size: 20),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      record.question,
                      maxLines: 3,
                      overflow: TextOverflow.ellipsis,
                      style: theme.textTheme.bodyLarge,
                    ),
                  ),
                  const SizedBox(width: 8),
                  const Icon(Icons.chevron_right, size: 20),
                ],
              ),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 6,
                children: <Widget>[
                  _StatusChip(
                    icon: record.statusIcon,
                    label: record.statusLabel,
                  ),
                  if (record.createdAtLabel.isNotEmpty)
                    _PreviewMetaChip(
                      icon: Icons.schedule,
                      label: record.createdAtLabel,
                    ),
                  if ((record.jobId ?? '').isNotEmpty)
                    _PreviewMetaChip(
                      icon: Icons.work_outline,
                      label: 'job ${record.jobId}',
                    ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _QuickAskQuestionDialog extends StatefulWidget {
  const _QuickAskQuestionDialog({
    required this.onCancel,
    required this.onSubmit,
  });

  final VoidCallback onCancel;
  final ValueChanged<String> onSubmit;

  @override
  State<_QuickAskQuestionDialog> createState() =>
      _QuickAskQuestionDialogState();
}

class _QuickAskQuestionDialogState extends State<_QuickAskQuestionDialog> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final contentConstraints = _dialogContentConstraints(
      context,
      maxWidth: 520,
    );
    return AlertDialog(
      title: const Text('Pregunta rápida'),
      content: SizedBox(
        width: contentConstraints.maxWidth,
        child: TextField(
          key: developerFeedbackQuickAskQuestionKey,
          controller: _controller,
          minLines: 3,
          maxLines: 5,
          decoration: const InputDecoration(
            labelText: 'Pregunta',
            border: OutlineInputBorder(),
          ),
        ),
      ),
      actions: <Widget>[
        TextButton(onPressed: widget.onCancel, child: const Text('Cerrar')),
        FilledButton.icon(
          key: developerFeedbackQuickAskSubmitKey,
          onPressed: () {
            final question = _controller.text.trim();
            if (question.isEmpty) return;
            widget.onSubmit(question);
          },
          icon: const Icon(Icons.help_outline),
          label: const Text('Enviar'),
        ),
      ],
    );
  }
}

Uint8List _decodePreviewImage(String screenshotPngBase64) {
  try {
    return base64Decode(screenshotPngBase64);
  } catch (_) {
    return base64Decode(_transparentPngBase64);
  }
}

class _QuickAskRecord {
  const _QuickAskRecord({
    required this.quickAskId,
    required this.sourceApp,
    required this.sourceDisplayName,
    required this.question,
    required this.status,
    required this.createdAt,
    required this.selectionBounds,
    this.answer,
    this.screenshotPngBase64,
    this.jobId,
    this.sessionId,
    this.runId,
  });

  factory _QuickAskRecord.fromJson(Map<String, Object?> json) {
    return _QuickAskRecord(
      quickAskId:
          (json['quick_ask_id'] as String?) ??
          (json['quickAskId'] as String?) ??
          'unknown',
      sourceApp:
          (json['source_app'] as String?) ??
          (json['sourceApp'] as String?) ??
          '',
      sourceDisplayName:
          (json['source_display_name'] as String?) ??
          (json['sourceDisplayName'] as String?) ??
          '',
      question: (json['question'] as String?) ?? 'Pregunta sin texto',
      status: (json['status'] as String?) ?? 'pending',
      createdAt:
          (json['created_at'] as String?) ??
          (json['createdAt'] as String?) ??
          '',
      selectionBounds:
          ((json['selection_bounds'] as Map?) ??
                  (json['selectionBounds'] as Map?))
              ?.map(
                (key, value) => MapEntry(
                  key.toString(),
                  value is num ? value.toDouble() : 0.0,
                ),
              ) ??
          <String, double>{'left': 0, 'top': 0, 'width': 0, 'height': 0},
      answer: json['answer'] as String?,
      screenshotPngBase64:
          (json['screenshot_png_base64'] as String?) ??
          (json['screenshotPngBase64'] as String?),
      jobId: (json['job_id'] as String?) ?? (json['jobId'] as String?),
      sessionId:
          (json['session_id'] as String?) ?? (json['sessionId'] as String?),
      runId: (json['run_id'] as String?) ?? (json['runId'] as String?),
    );
  }

  final String quickAskId;
  final String sourceApp;
  final String sourceDisplayName;
  final String question;
  final String status;
  final String createdAt;
  final Map<String, double> selectionBounds;
  final String? answer;
  final String? screenshotPngBase64;
  final String? jobId;
  final String? sessionId;
  final String? runId;

  _QuickAskRecord copyWith({
    String? quickAskId,
    String? sourceApp,
    String? sourceDisplayName,
    String? question,
    String? status,
    String? createdAt,
    Map<String, double>? selectionBounds,
    String? answer,
    String? screenshotPngBase64,
    String? jobId,
    String? sessionId,
    String? runId,
  }) {
    return _QuickAskRecord(
      quickAskId: quickAskId ?? this.quickAskId,
      sourceApp: sourceApp ?? this.sourceApp,
      sourceDisplayName: sourceDisplayName ?? this.sourceDisplayName,
      question: question ?? this.question,
      status: status ?? this.status,
      createdAt: createdAt ?? this.createdAt,
      selectionBounds: selectionBounds ?? this.selectionBounds,
      answer: answer ?? this.answer,
      screenshotPngBase64: screenshotPngBase64 ?? this.screenshotPngBase64,
      jobId: jobId ?? this.jobId,
      sessionId: sessionId ?? this.sessionId,
      runId: runId ?? this.runId,
    );
  }

  _QuickAskRecord mergedWith(_QuickAskRecord? fallback) {
    if (fallback == null) return this;
    return _QuickAskRecord(
      quickAskId: quickAskId == 'unknown' ? fallback.quickAskId : quickAskId,
      sourceApp: sourceApp.isEmpty ? fallback.sourceApp : sourceApp,
      sourceDisplayName: sourceDisplayName.isEmpty
          ? fallback.sourceDisplayName
          : sourceDisplayName,
      question: question == 'Pregunta sin texto' ? fallback.question : question,
      status: status,
      createdAt: createdAt.isEmpty ? fallback.createdAt : createdAt,
      selectionBounds: _selectionBoundsIsEmpty(selectionBounds)
          ? fallback.selectionBounds
          : selectionBounds,
      answer: (answer ?? '').isEmpty ? fallback.answer : answer,
      screenshotPngBase64: (screenshotPngBase64 ?? '').isEmpty
          ? fallback.screenshotPngBase64
          : screenshotPngBase64,
      jobId: (jobId ?? '').isEmpty ? fallback.jobId : jobId,
      sessionId: (sessionId ?? '').isEmpty ? fallback.sessionId : sessionId,
      runId: (runId ?? '').isEmpty ? fallback.runId : runId,
    );
  }

  bool get isCompleted => status == 'completed';

  bool get isFailed => status == 'failed';

  bool get isCanceled => status == 'canceled' || status == 'cancelled';

  bool get isActive => !isCompleted && !isFailed && !isCanceled;

  String get statusLabel {
    return switch (status) {
      'completed' => 'Completada',
      'failed' => 'Fallida',
      'canceled' || 'cancelled' => 'Cancelada',
      'queued' => 'Enviando',
      'pending' || 'running' => 'En curso',
      _ => status,
    };
  }

  IconData get statusIcon {
    if (isCompleted) return Icons.check_circle_outline;
    if (isFailed) return Icons.error_outline;
    if (isCanceled) return Icons.pause_circle_outline;
    if (status == 'queued') return Icons.outbox_outlined;
    return Icons.timelapse;
  }

  String get createdAtLabel => _formatIsoDateTime(createdAt);

  String get historyLabel {
    final parts = <String>[
      statusLabel,
      if (createdAtLabel.isNotEmpty) createdAtLabel,
      if ((jobId ?? '').isNotEmpty) 'job $jobId',
      if ((sessionId ?? '').isNotEmpty) 'session $sessionId',
      if ((runId ?? '').isNotEmpty) 'run $runId',
    ];
    return parts.join(' · ');
  }
}

class _SubmittedFeedbackBatch {
  const _SubmittedFeedbackBatch({
    required this.status,
    this.batchId,
    this.jobId,
    this.sessionId,
    this.statusDetail,
    this.summary,
    this.summaryLineCount = 0,
    this.notificationUnread = false,
  });

  final String? batchId;
  final String? jobId;
  final String? sessionId;
  final String status;
  final String? statusDetail;
  final String? summary;
  final int summaryLineCount;
  final bool notificationUnread;

  factory _SubmittedFeedbackBatch.local() {
    return const _SubmittedFeedbackBatch(status: 'running');
  }

  static _SubmittedFeedbackBatch? fromStartResponse(Map<String, Object?> json) {
    final batchId =
        (json['feedback_batch_id'] as String?) ?? (json['batchId'] as String?);
    final jobId = (json['job_id'] as String?) ?? (json['jobId'] as String?);
    final sessionId =
        (json['session_id'] as String?) ?? (json['sessionId'] as String?);
    if ((batchId ?? '').trim().isEmpty && (jobId ?? '').trim().isEmpty) {
      return null;
    }
    return _SubmittedFeedbackBatch(
      batchId: batchId,
      jobId: jobId,
      sessionId: sessionId,
      status: (json['status'] as String?) ?? 'running',
    );
  }

  factory _SubmittedFeedbackBatch.fromStatusResponse(
    Map<String, Object?> json,
  ) {
    return _SubmittedFeedbackBatch(
      batchId: (json['batch_id'] as String?) ?? (json['batchId'] as String?),
      jobId: (json['job_id'] as String?) ?? (json['jobId'] as String?),
      sessionId:
          (json['session_id'] as String?) ?? (json['sessionId'] as String?),
      status:
          (json['status'] as String?) ??
          (json['workflowStatus'] as String?) ??
          'pending',
      statusDetail: json['status_detail'] as String?,
      summary:
          (json['summary'] as String?) ?? (json['finalSummary'] as String?),
      summaryLineCount: (json['summary_line_count'] as num?)?.toInt() ?? 0,
      notificationUnread:
          (json['notification_unread'] as bool?) ??
          (json['notificationUnread'] as bool?) ??
          false,
    );
  }

  String get title {
    if ((batchId ?? '').isNotEmpty) return 'Batch $batchId';
    if ((jobId ?? '').isNotEmpty) return 'Job $jobId';
    return 'Run local';
  }

  String get statusLabel {
    final detail = (statusDetail ?? '').trim();
    final base = 'Estado: $status';
    return detail.isEmpty ? base : '$base · $detail';
  }

  String get historyLabel {
    final ids = <String>[
      if ((jobId ?? '').isNotEmpty) 'job $jobId',
      if ((sessionId ?? '').isNotEmpty) 'session $sessionId',
    ].join(' · ');
    final summarySuffix = hasSummary
        ? ' · resumen ${summaryLineCount} líneas'
        : '';
    final base = ids.isEmpty ? statusLabel : '$statusLabel · $ids';
    return '$base$summarySuffix';
  }

  bool get hasSummary => (summary ?? '').trim().isNotEmpty;

  bool get isCompleted => status == 'completed';

  bool get isFailed => status == 'failed';

  bool get isActive => !isCompleted && !isFailed;

  String get notificationLabel {
    final parts = <String>[
      statusLabel,
      if (notificationUnread) 'no leído',
      if (hasSummary) 'resumen disponible',
      if ((jobId ?? '').isNotEmpty) 'job $jobId',
      if ((sessionId ?? '').isNotEmpty) 'session $sessionId',
    ];
    return parts.join(' · ');
  }
}

class _FeedbackDraft {
  const _FeedbackDraft({required this.comment, required this.audio});

  final String comment;
  final DeveloperFeedbackAudioClip? audio;
}

class _CapturedFeedbackScreenshot {
  const _CapturedFeedbackScreenshot({
    required this.pngBase64,
    required this.width,
    required this.height,
    required this.pixelRatio,
  });

  factory _CapturedFeedbackScreenshot.transparent() {
    return const _CapturedFeedbackScreenshot(
      pngBase64: _transparentPngBase64,
      width: 1,
      height: 1,
      pixelRatio: 1,
    );
  }

  final String pngBase64;
  final int width;
  final int height;
  final double pixelRatio;
}

class _GuidedTraceRecording {
  _GuidedTraceRecording({
    required this.id,
    required this.startedAt,
    required this.recorder,
    required this.audioStarted,
  });

  final String id;
  final DateTime startedAt;
  final DeveloperFeedbackAudioRecorder? recorder;
  final bool audioStarted;
  final List<DeveloperFeedbackTraceEvent> events =
      <DeveloperFeedbackTraceEvent>[];
  final List<DeveloperFeedbackTraceFrame> frames =
      <DeveloperFeedbackTraceFrame>[];
  final List<Map<String, Object?>> contextSnapshots = <Map<String, Object?>>[];
  DateTime? lastFrameAt;
  var truncated = false;
  var droppedFrameCount = 0;
  var droppedEventCount = 0;
  var _eventCount = 0;
  var _frameCount = 0;
  var _contextSnapshotCount = 0;

  int get elapsedMs =>
      DateTime.now().toUtc().difference(startedAt).inMilliseconds;

  String nextEventId() => 'event-${++_eventCount}';

  String nextFrameId() => 'frame-${++_frameCount}';

  String nextContextSnapshotId() => 'ctx-${++_contextSnapshotCount}';
}

enum _GuidedTracePreviewAction { attach, discard, rerecord }

class _GuidedTracePreviewResult {
  const _GuidedTracePreviewResult.attach({required this.comment})
    : action = _GuidedTracePreviewAction.attach;

  const _GuidedTracePreviewResult.discard()
    : action = _GuidedTracePreviewAction.discard,
      comment = '';

  const _GuidedTracePreviewResult.rerecord()
    : action = _GuidedTracePreviewAction.rerecord,
      comment = '';

  final _GuidedTracePreviewAction action;
  final String comment;
}

class DeveloperFeedbackBatch {
  const DeveloperFeedbackBatch({
    required this.batchId,
    required this.sourceApp,
    required this.sourceDisplayName,
    required this.workflowPresetId,
    required this.releaseWhenComplete,
    this.quickAskId,
    required this.items,
  });

  final String batchId;
  final String sourceApp;
  final String sourceDisplayName;
  final String workflowPresetId;
  final bool releaseWhenComplete;
  final String? quickAskId;
  final List<DeveloperFeedbackItem> items;

  Map<String, Object?> toBridgeJson() {
    return <String, Object?>{
      'kind': 'codex.developerFeedbackBatch',
      'version': 3,
      'batchId': batchId,
      'sourceApp': sourceApp,
      if (sourceDisplayName.trim().isNotEmpty)
        'sourceDisplayName': sourceDisplayName,
      'workflowPresetId': workflowPresetId,
      'releaseWhenComplete': releaseWhenComplete,
      if ((quickAskId ?? '').trim().isNotEmpty) 'quickAskId': quickAskId,
      'items': items.map((item) => item.toBridgeJson()).toList(),
    };
  }
}

class _DeveloperFeedbackWorkflowPreset {
  const _DeveloperFeedbackWorkflowPreset({
    required this.id,
    required this.name,
  });

  final String id;
  final String name;

  factory _DeveloperFeedbackWorkflowPreset.fromJson(Map<String, Object?> json) {
    return _DeveloperFeedbackWorkflowPreset(
      id: (json['id'] as String?) ?? 'generator_only',
      name: (json['name'] as String?) ?? 'Generator only',
    );
  }
}

class _DeveloperFeedbackWorkflowPresets {
  const _DeveloperFeedbackWorkflowPresets({
    required this.defaultPresetId,
    required this.presets,
  });

  final String defaultPresetId;
  final List<_DeveloperFeedbackWorkflowPreset> presets;

  factory _DeveloperFeedbackWorkflowPresets.fromJson(
    Map<String, Object?> json,
  ) {
    final rawPresets = json['presets'];
    final presets = rawPresets is List
        ? rawPresets
              .whereType<Map>()
              .map(
                (raw) => _DeveloperFeedbackWorkflowPreset.fromJson(
                  raw.cast<String, Object?>(),
                ),
              )
              .toList()
        : <_DeveloperFeedbackWorkflowPreset>[];
    if (presets.isEmpty) return _DeveloperFeedbackWorkflowPresets.fallback();
    final defaultPresetId =
        (json['default_preset_id'] as String?) ??
        (json['defaultPresetId'] as String?) ??
        presets.first.id;
    return _DeveloperFeedbackWorkflowPresets(
      defaultPresetId: defaultPresetId,
      presets: presets,
    );
  }

  factory _DeveloperFeedbackWorkflowPresets.fallback() {
    return const _DeveloperFeedbackWorkflowPresets(
      defaultPresetId: 'generator_only',
      presets: <_DeveloperFeedbackWorkflowPreset>[
        _DeveloperFeedbackWorkflowPreset(
          id: 'generator_only',
          name: 'Generator only',
        ),
        _DeveloperFeedbackWorkflowPreset(
          id: 'generator_reviewer',
          name: 'Generator + Reviewer',
        ),
      ],
    );
  }
}

class DeveloperFeedbackScreenSnapshot {
  const DeveloperFeedbackScreenSnapshot({
    this.route,
    this.name,
    this.title,
    this.metadata = const <String, Object?>{},
  });

  final String? route;
  final String? name;
  final String? title;
  final Map<String, Object?> metadata;

  Map<String, Object?> toJson() => <String, Object?>{
    if ((route ?? '').trim().isNotEmpty) 'route': route,
    if ((name ?? '').trim().isNotEmpty) 'name': name,
    if ((title ?? '').trim().isNotEmpty) 'title': title,
    ..._jsonSafeMetadata(metadata),
  };
}

class DeveloperFeedbackAttachmentSnapshot {
  const DeveloperFeedbackAttachmentSnapshot({
    required this.attachmentId,
    required this.mimeType,
    this.width,
    this.height,
    this.pixelRatio,
    this.sha256,
  });

  final String attachmentId;
  final String mimeType;
  final int? width;
  final int? height;
  final double? pixelRatio;
  final String? sha256;

  Map<String, Object?> toJson() => <String, Object?>{
    'attachmentId': attachmentId,
    'mimeType': mimeType,
    if (width != null) 'width': width,
    if (height != null) 'height': height,
    if (pixelRatio != null) 'pixelRatio': pixelRatio,
    if ((sha256 ?? '').trim().isNotEmpty) 'sha256': sha256,
  };
}

class DeveloperFeedbackAnnotationSnapshot {
  const DeveloperFeedbackAnnotationSnapshot({
    required this.id,
    required this.type,
    required this.bounds,
    this.label,
  });

  final String id;
  final String type;
  final Map<String, double> bounds;
  final String? label;

  Map<String, Object?> toJson() => <String, Object?>{
    'id': id,
    'type': type,
    if ((label ?? '').trim().isNotEmpty) 'label': label,
    'bounds': bounds,
  };
}

class DeveloperFeedbackUiElementSnapshot {
  const DeveloperFeedbackUiElementSnapshot({
    required this.id,
    required this.type,
    required this.bounds,
    this.label,
    this.state = const <String, Object?>{},
    this.metadata = const <String, Object?>{},
  });

  final String id;
  final String type;
  final String? label;
  final Map<String, double> bounds;
  final Map<String, Object?> state;
  final Map<String, Object?> metadata;

  Map<String, Object?> toJson() => <String, Object?>{
    'id': id,
    'type': type,
    if ((label ?? '').trim().isNotEmpty) 'label': label,
    'bounds': bounds,
    if (state.isNotEmpty) 'state': _jsonSafeMetadata(state),
    ..._jsonSafeMetadata(metadata),
  };
}

class DeveloperFeedbackUiMapSnapshot {
  const DeveloperFeedbackUiMapSnapshot({this.elements = const []});

  final List<DeveloperFeedbackUiElementSnapshot> elements;

  Map<String, Object?> toJson() => <String, Object?>{
    'elements': elements.map((element) => element.toJson()).toList(),
  };
}

class DeveloperFeedbackImageCapture {
  const DeveloperFeedbackImageCapture({
    required this.screenshot,
    this.annotations = const [],
    this.comment,
    this.screen,
    this.contextSnapshot = const <String, Object?>{},
    this.uiMap,
  });

  final DeveloperFeedbackAttachmentSnapshot screenshot;
  final List<DeveloperFeedbackAnnotationSnapshot> annotations;
  final String? comment;
  final DeveloperFeedbackScreenSnapshot? screen;
  final Map<String, Object?> contextSnapshot;
  final DeveloperFeedbackUiMapSnapshot? uiMap;

  Map<String, Object?> toJson() => <String, Object?>{
    'kind': developerFeedbackImageCaptureKind,
    'version': 1,
    'type': 'single_image',
    'screenshot': screenshot.toJson(),
    if (annotations.isNotEmpty)
      'annotations': annotations
          .map((annotation) => annotation.toJson())
          .toList(),
    if ((comment ?? '').trim().isNotEmpty) 'comment': comment,
    if (screen != null && screen!.toJson().isNotEmpty)
      'screen': screen!.toJson(),
    if (contextSnapshot.isNotEmpty)
      'contextSnapshot': _jsonSafeMetadata(contextSnapshot),
    if (uiMap != null) 'uiMap': uiMap!.toJson(),
  };
}

class DeveloperFeedbackTraceAudio {
  const DeveloperFeedbackTraceAudio({
    required this.attachmentId,
    required this.mimeType,
    required this.durationMs,
    this.transcriptAvailable = false,
  });

  final String attachmentId;
  final String mimeType;
  final int durationMs;
  final bool transcriptAvailable;

  Map<String, Object?> toJson() => <String, Object?>{
    'attachmentId': attachmentId,
    'mimeType': mimeType,
    'durationMs': durationMs,
    'transcriptAvailable': transcriptAvailable,
  };
}

class DeveloperFeedbackTraceFrame {
  const DeveloperFeedbackTraceFrame({
    required this.id,
    required this.attachmentId,
    required this.atMs,
    this.width,
    this.height,
    this.pixelRatio,
    this.sha256,
    this.screen,
    this.screenshotMimeType,
    this.screenshotPngBase64,
  });

  final String id;
  final String attachmentId;
  final int atMs;
  final int? width;
  final int? height;
  final double? pixelRatio;
  final String? sha256;
  final DeveloperFeedbackScreenSnapshot? screen;
  final String? screenshotMimeType;
  final String? screenshotPngBase64;

  Map<String, Object?> toJson() => <String, Object?>{
    'id': id,
    'attachmentId': attachmentId,
    'atMs': atMs,
    if (width != null) 'width': width,
    if (height != null) 'height': height,
    if (pixelRatio != null) 'pixelRatio': pixelRatio,
    if ((sha256 ?? '').trim().isNotEmpty) 'sha256': sha256,
    if (screen != null && screen!.toJson().isNotEmpty)
      'screen': screen!.toJson(),
    if ((screenshotMimeType ?? '').trim().isNotEmpty)
      'screenshotMimeType': screenshotMimeType,
    if ((screenshotPngBase64 ?? '').trim().isNotEmpty)
      'screenshotPngBase64': screenshotPngBase64,
  };
}

class DeveloperFeedbackTraceEvent {
  const DeveloperFeedbackTraceEvent({
    required this.id,
    required this.type,
    required this.atMs,
    this.frameId,
    this.contextSnapshotId,
    this.data = const <String, Object?>{},
  });

  final String id;
  final String type;
  final int atMs;
  final String? frameId;
  final String? contextSnapshotId;
  final Map<String, Object?> data;

  Map<String, Object?> toJson() => <String, Object?>{
    'id': id,
    'type': type,
    'atMs': atMs,
    if ((frameId ?? '').trim().isNotEmpty) 'frameId': frameId,
    if ((contextSnapshotId ?? '').trim().isNotEmpty)
      'contextSnapshotId': contextSnapshotId,
    ..._jsonSafeMetadata(data),
  };
}

class DeveloperFeedbackGuidedTrace {
  const DeveloperFeedbackGuidedTrace({
    required this.id,
    required this.startedAt,
    this.endedAt,
    this.durationMs,
    this.mode = 'screen_trace_with_audio',
    this.frameStrategy = 'route_change_interaction_and_interval',
    this.audio,
    this.timeline = const [],
    this.frames = const [],
    this.contextSnapshots = const <Map<String, Object?>>[],
    this.truncated = false,
    this.droppedFrameCount = 0,
    this.droppedEventCount = 0,
    this.maxFrames,
    this.maxEvents,
  });

  final String id;
  final DateTime startedAt;
  final DateTime? endedAt;
  final int? durationMs;
  final String mode;
  final String frameStrategy;
  final DeveloperFeedbackTraceAudio? audio;
  final List<DeveloperFeedbackTraceEvent> timeline;
  final List<DeveloperFeedbackTraceFrame> frames;
  final List<Map<String, Object?>> contextSnapshots;
  final bool truncated;
  final int droppedFrameCount;
  final int droppedEventCount;
  final int? maxFrames;
  final int? maxEvents;

  Map<String, Object?> toJson() => <String, Object?>{
    'kind': developerFeedbackGuidedTraceKind,
    'version': 1,
    'id': id,
    'startedAt': startedAt.toUtc().toIso8601String(),
    if (endedAt != null) 'endedAt': endedAt!.toUtc().toIso8601String(),
    'recording': <String, Object?>{
      'mode': mode,
      if (durationMs != null) 'durationMs': durationMs,
      'frameStrategy': frameStrategy,
      if (maxFrames != null) 'maxFrames': maxFrames,
      if (maxEvents != null) 'maxEvents': maxEvents,
      if (truncated) 'truncated': true,
      if (droppedFrameCount > 0) 'droppedFrameCount': droppedFrameCount,
      if (droppedEventCount > 0) 'droppedEventCount': droppedEventCount,
      if (audio != null) 'audio': audio!.toJson(),
    },
    'timeline': timeline.map((event) => event.toJson()).toList(),
    'frames': frames.map((frame) => frame.toJson()).toList(),
    if (contextSnapshots.isNotEmpty)
      'contextSnapshots': contextSnapshots.map(_jsonSafeMetadata).toList(),
  };
}

class DeveloperFeedbackItem {
  const DeveloperFeedbackItem({
    required this.id,
    required this.createdAt,
    this.sourceApp = 'unknown',
    this.sourceDisplayName = '',
    required this.comment,
    required this.screenshotPngBase64,
    required this.selectionPoints,
    required this.audio,
    this.contextMetadata = const <String, Object?>{},
    this.screen,
    this.uiMap,
    this.imageCapture,
    this.guidedTrace,
  });

  final String id;
  final DateTime createdAt;
  final String sourceApp;
  final String sourceDisplayName;
  final String comment;
  final String screenshotPngBase64;
  final List<Offset> selectionPoints;
  final DeveloperFeedbackAudioClip? audio;
  final Map<String, Object?> contextMetadata;
  final DeveloperFeedbackScreenSnapshot? screen;
  final DeveloperFeedbackUiMapSnapshot? uiMap;
  final DeveloperFeedbackImageCapture? imageCapture;
  final DeveloperFeedbackGuidedTrace? guidedTrace;

  Map<String, double> get selectionBounds => _selectionBounds(selectionPoints);

  String get feedbackKind => guidedTrace == null
      ? developerFeedbackImageCaptureKind
      : developerFeedbackGuidedTraceKind;

  DeveloperFeedbackItem copyWith({
    String? comment,
    Map<String, Object?>? contextMetadata,
    DeveloperFeedbackScreenSnapshot? screen,
    DeveloperFeedbackUiMapSnapshot? uiMap,
    DeveloperFeedbackImageCapture? imageCapture,
    DeveloperFeedbackGuidedTrace? guidedTrace,
  }) {
    return DeveloperFeedbackItem(
      id: id,
      createdAt: createdAt,
      sourceApp: sourceApp,
      sourceDisplayName: sourceDisplayName,
      comment: comment ?? this.comment,
      screenshotPngBase64: screenshotPngBase64,
      selectionPoints: selectionPoints,
      audio: audio,
      contextMetadata: contextMetadata ?? this.contextMetadata,
      screen: screen ?? this.screen,
      uiMap: uiMap ?? this.uiMap,
      imageCapture: imageCapture ?? this.imageCapture,
      guidedTrace: guidedTrace ?? this.guidedTrace,
    );
  }

  Map<String, Object?> toJson() {
    final bounds = _selectionBounds(selectionPoints);
    final hasAudioBytes = audio != null && audio!.bytes.isNotEmpty;
    return <String, Object?>{
      'kind': 'codex.developerFeedback',
      'version': 3,
      'id': id,
      'sourceApp': sourceApp,
      if (sourceDisplayName.trim().isNotEmpty)
        'sourceDisplayName': sourceDisplayName,
      'createdAt': createdAt.toIso8601String(),
      'queue': 'codexCli',
      'status': 'pending',
      'comment': comment,
      'screenshotMimeType': 'image/png',
      'screenshotPngBase64': screenshotPngBase64,
      'selectionPoints': selectionPoints
          .map((point) => <String, double>{'x': point.dx, 'y': point.dy})
          .toList(),
      'selectionBounds': bounds,
      if (contextMetadata.isNotEmpty) 'contextMetadata': contextMetadata,
      'feedbackKind': feedbackKind,
      'imageCapture': _imageCaptureJson(),
      if (guidedTrace != null) 'guidedTrace': guidedTrace!.toJson(),
      'hasAudio': hasAudioBytes,
      if (audio != null) 'audioMimeType': audio!.mimeType,
      if (audio != null) 'audioDurationMs': audio!.durationMs,
      if (audio != null) 'audioByteLength': audio!.bytes.length,
      if (hasAudioBytes) 'audioBase64': base64Encode(audio!.bytes),
    };
  }

  Map<String, Object?> toBridgeJson() {
    final hasAudioBytes = audio != null && audio!.bytes.isNotEmpty;
    return <String, Object?>{
      'kind': 'codex.developerFeedback',
      'version': 3,
      'id': id,
      'sourceApp': sourceApp,
      if (sourceDisplayName.trim().isNotEmpty)
        'sourceDisplayName': sourceDisplayName,
      'queue': 'codexCli',
      'status': 'pending',
      'comment': comment,
      'createdAt': createdAt.toIso8601String(),
      'screenshotMimeType': 'image/png',
      'screenshotPngBase64': screenshotPngBase64,
      'selectionPoints': selectionPoints
          .map((point) => <String, double>{'x': point.dx, 'y': point.dy})
          .toList(),
      'selectionBounds': selectionBounds,
      if (contextMetadata.isNotEmpty) 'contextMetadata': contextMetadata,
      'feedbackKind': feedbackKind,
      'imageCapture': _imageCaptureJson(),
      if (guidedTrace != null) 'guidedTrace': guidedTrace!.toJson(),
      'hasAudio': hasAudioBytes,
      if (audio != null) 'audioMimeType': audio!.mimeType,
      if (audio != null) 'audioDurationMs': audio!.durationMs,
      if (audio != null) 'audioByteLength': audio!.bytes.length,
      if (hasAudioBytes) 'audioBase64': base64Encode(audio!.bytes),
    };
  }

  Map<String, Object?> _imageCaptureJson() {
    final explicit = imageCapture;
    if (explicit != null) return explicit.toJson();
    final contextSnapshot = <String, Object?>{
      'observedAt': createdAt.toUtc().toIso8601String(),
      ...contextMetadata,
    };
    final bounds = selectionBounds;
    return DeveloperFeedbackImageCapture(
      screenshot: DeveloperFeedbackAttachmentSnapshot(
        attachmentId: '${id}_screenshot',
        mimeType: 'image/png',
      ),
      annotations: selectionPoints.isEmpty
          ? const <DeveloperFeedbackAnnotationSnapshot>[]
          : <DeveloperFeedbackAnnotationSnapshot>[
              DeveloperFeedbackAnnotationSnapshot(
                id: '${id}_selection',
                type: 'bounds',
                label: comment.trim().isEmpty ? null : comment.trim(),
                bounds: bounds,
              ),
            ],
      comment: comment,
      screen: screen,
      contextSnapshot: contextSnapshot,
      uiMap: uiMap,
    ).toJson();
  }

  Map<String, double> _selectionBounds(List<Offset> points) {
    if (points.isEmpty) {
      return <String, double>{'left': 0, 'top': 0, 'width': 0, 'height': 0};
    }
    var minX = points.first.dx;
    var maxX = points.first.dx;
    var minY = points.first.dy;
    var maxY = points.first.dy;
    for (final point in points.skip(1)) {
      minX = point.dx < minX ? point.dx : minX;
      maxX = point.dx > maxX ? point.dx : maxX;
      minY = point.dy < minY ? point.dy : minY;
      maxY = point.dy > maxY ? point.dy : maxY;
    }
    return <String, double>{
      'left': minX,
      'top': minY,
      'width': maxX - minX,
      'height': maxY - minY,
    };
  }
}

String _formatSelectionBounds(Map<String, double> bounds) {
  return 'Bounds: x ${bounds['left']!.round()}, y ${bounds['top']!.round()}, '
      '${bounds['width']!.round()} x ${bounds['height']!.round()}';
}

String _feedbackPreviewComment(DeveloperFeedbackItem item) {
  final comment = item.comment.trim();
  if (comment.isNotEmpty) return comment;
  if (item.guidedTrace != null) return 'Recorrido guiado sin texto';
  if (item.audio != null) return 'Comentario de audio sin texto';
  return 'Feedback sin texto';
}

BoxConstraints _dialogContentConstraints(
  BuildContext context, {
  double maxWidth = 560,
  double maxHeightFactor = 0.66,
}) {
  final size = MediaQuery.sizeOf(context);
  return BoxConstraints(
    maxWidth: math.min(maxWidth, math.max(0.0, size.width - 48)),
    maxHeight: math.max(160.0, size.height * maxHeightFactor),
  );
}

Map<String, double> _selectionBoundsFromPoints(List<Offset> points) {
  if (points.isEmpty) {
    return <String, double>{'left': 0, 'top': 0, 'width': 0, 'height': 0};
  }
  var minX = points.first.dx;
  var maxX = points.first.dx;
  var minY = points.first.dy;
  var maxY = points.first.dy;
  for (final point in points.skip(1)) {
    minX = math.min(minX, point.dx);
    maxX = math.max(maxX, point.dx);
    minY = math.min(minY, point.dy);
    maxY = math.max(maxY, point.dy);
  }
  return <String, double>{
    'left': minX,
    'top': minY,
    'width': maxX - minX,
    'height': maxY - minY,
  };
}

bool _selectionBoundsIsEmpty(Map<String, double> bounds) {
  return (bounds['left'] ?? 0) == 0 &&
      (bounds['top'] ?? 0) == 0 &&
      (bounds['width'] ?? 0) == 0 &&
      (bounds['height'] ?? 0) == 0;
}

List<_QuickAskRecord> _sortQuickAskRecords(Iterable<_QuickAskRecord> records) {
  return List<_QuickAskRecord>.of(records)..sort((a, b) {
    final aTime = DateTime.tryParse(a.createdAt);
    final bTime = DateTime.tryParse(b.createdAt);
    if (aTime != null && bTime != null) return bTime.compareTo(aTime);
    if (aTime != null) return -1;
    if (bTime != null) return 1;
    return b.quickAskId.compareTo(a.quickAskId);
  });
}

String _formatIsoDateTime(String value) {
  final parsed = DateTime.tryParse(value);
  if (parsed == null) return value;
  final local = parsed.toLocal();
  String twoDigits(int number) => number.toString().padLeft(2, '0');
  return '${local.year}-${twoDigits(local.month)}-${twoDigits(local.day)} '
      '${twoDigits(local.hour)}:${twoDigits(local.minute)}';
}

List<Offset> _pointsFromBounds(Map<String, double> bounds) {
  final left = bounds['left'] ?? 0;
  final top = bounds['top'] ?? 0;
  final width = bounds['width'] ?? 0;
  final height = bounds['height'] ?? 0;
  return <Offset>[
    Offset(left, top),
    Offset(left + width, top),
    Offset(left + width, top + height),
    Offset(left, top + height),
  ];
}

String _formatAudioSummary(DeveloperFeedbackAudioClip? audio) {
  if (audio == null) return 'Audio: sin adjunto';
  return 'Audio: ${audio.durationMs} ms, ${audio.bytes.length} bytes, '
      '${audio.mimeType}';
}

Map<String, Object?> _jsonSafeMetadata(Map<String, Object?> metadata) {
  final result = <String, Object?>{};
  for (final entry in metadata.entries) {
    final key = entry.key.trim();
    if (key.isEmpty) continue;
    final value = _jsonSafeValue(entry.value);
    if (value != null) result[key] = value;
  }
  return result;
}

Object? _jsonSafeValue(Object? value) {
  if (value == null || value is String || value is num || value is bool) {
    return value;
  }
  if (value is DateTime) return value.toIso8601String();
  if (value is Iterable) {
    return value
        .map(_jsonSafeValue)
        .where((item) => item != null)
        .toList(growable: false);
  }
  if (value is Map) {
    final result = <String, Object?>{};
    for (final entry in value.entries) {
      final key = entry.key?.toString().trim() ?? '';
      if (key.isEmpty) continue;
      final safeValue = _jsonSafeValue(entry.value);
      if (safeValue != null) result[key] = safeValue;
    }
    return result;
  }
  return value.toString();
}

class DeveloperFeedbackExport {
  const DeveloperFeedbackExport({required this.items});

  final List<DeveloperFeedbackItem> items;

  String toJsonText() {
    return const JsonEncoder.withIndent('  ').convert(<String, Object?>{
      'kind': 'codex.developerFeedbackExport',
      'version': 3,
      'generatedAt': DateTime.now().toUtc().toIso8601String(),
      'items': items.map((item) => item.toJson()).toList(),
    });
  }
}
