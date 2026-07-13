import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/chat_session_summary.dart';
import '../models/chat_message.dart';
import '../models/chat_turn_summary.dart';
import '../models/agent_configuration.dart';
import '../models/agent_profile.dart';
import '../models/codex_tooling.dart';
import '../models/project_factory.dart';
import '../models/server_capabilities.dart';
import '../models/server_health.dart';
import '../models/server_profile.dart';
import '../models/session_detail.dart';
import '../models/slash_command.dart';
import '../models/workspace.dart';
import '../services/api_client.dart';
import '../services/audio_note_recorder.dart';
import '../services/chat_notification_service.dart';
import '../services/clipboard_image_paste_listener_stub.dart'
    if (dart.library.js_interop) '../services/clipboard_image_paste_listener_web.dart';
import '../services/reply_playback_service.dart';
import '../services/server_profile_store.dart';
import '../state/chat_controller.dart';
import '../utils/chat_timestamp_formatter.dart';
import '../utils/chat_message_visibility.dart';
import '../widgets/agent_studio_status_button.dart';
import '../widgets/chat_bubble.dart';
import '../widgets/current_run_timeline_card.dart';
import '../widgets/installable_apps_sheet.dart';
import '../widgets/reviewer_status_banner.dart';

const String _defaultAutoReviewerPrompt =
    'You are receiving the latest answer from a generator Codex. '
    'Write the next prompt that should be sent back to that generator so it '
    'improves the implementation with more code, tighter validation, missing '
    'tests, edge cases, cleanup, or follow-up work. Reply only with that next '
    'prompt.';
const String _projectFactoryGeneratorPrompt =
    'You are the New Project Factory Codex inside Codex Mobile Bridge. '
    'Guide the user through creating a new app as a normal chat, infer missing '
    'project details from the conversation, ask concise questions, use any '
    'attached images as visual references, produce a preview before generation, '
    'and only create files after explicit confirmation. When confirmed, use the '
    'bridge Project Factory workflow. The default first release is an Initial '
    'Preview Release: real Cloudflare Preview API, persistent D1 data, '
    'https://preview.nienfos.com/<slug> and /api, android-preview-v* APK, '
    'Codex Mobile Apps Bridge registration, production not ready, and no '
    'mock/demo data unless the user explicitly asks for a mock/demo APK. Ask '
    'for initial admin emails before build-ready confirmation, include invite '
    'delivery assumptions, default expiration, and manual-link fallback. Keep '
    'specs, plan, tasks, reference assets, Flutter, FastAPI, auth, RBAC, admin, '
    'notifications, validation, and workspace handoff consistent.';
const String _projectFactoryReviewerPrompt =
    'You are reviewing the New Project Factory generator. Check that the '
    'project brief, defaults, visual references, roles, auth, admin, '
    'notifications, generated files, tests, and validation are complete. '
    'Return only the next concrete prompt that should improve or verify the '
    'generator output.';
const String kProjectFactoryReadyForBuildMarker =
    'PROJECT_FACTORY_READY_FOR_BUILD';

AgentConfiguration buildProjectFactoryIntakeConfiguration(
  AgentConfiguration current, {
  int generatorRuns = 1,
}) {
  return current.copyWith(
    preset: AgentPreset.solo,
    displayMode: AgentDisplayMode.showAll,
    turnBudgetMode: TurnBudgetMode.eachAgent,
    agents: current.agents.map((agent) {
      switch (agent.agentId) {
        case AgentId.generator:
          return agent.copyWith(
            enabled: true,
            label: 'Project Factory',
            prompt: _projectFactoryGeneratorPrompt,
            visibility: AgentVisibilityMode.visible,
            maxTurns: generatorRuns,
          );
        case AgentId.reviewer:
          return agent.copyWith(
            enabled: false,
            label: 'Project Reviewer',
            prompt: _projectFactoryReviewerPrompt,
            visibility: AgentVisibilityMode.collapsed,
            maxTurns: 0,
          );
        case AgentId.summary:
          return agent.copyWith(enabled: false, maxTurns: 0);
        case AgentId.user:
        case AgentId.supervisor:
        case AgentId.qa:
        case AgentId.ux:
        case AgentId.seniorEngineer:
        case AgentId.scraper:
          return agent.copyWith(enabled: false, maxTurns: 0);
      }
    }).toList(growable: false),
  );
}

AgentConfiguration buildProjectFactoryBuildConfiguration(
  AgentConfiguration current, {
  int generatorRuns = 20,
  int reviewerRuns = 20,
}) {
  return current.copyWith(
    preset: AgentPreset.review,
    displayMode: AgentDisplayMode.showAll,
    turnBudgetMode: TurnBudgetMode.eachAgent,
    agents: current.agents.map((agent) {
      switch (agent.agentId) {
        case AgentId.generator:
          return agent.copyWith(
            enabled: true,
            label: 'Project Factory',
            prompt: _projectFactoryGeneratorPrompt,
            visibility: AgentVisibilityMode.visible,
            maxTurns: generatorRuns,
          );
        case AgentId.reviewer:
          return agent.copyWith(
            enabled: true,
            label: 'Project Reviewer',
            prompt: _projectFactoryReviewerPrompt,
            visibility: AgentVisibilityMode.collapsed,
            maxTurns: reviewerRuns,
          );
        case AgentId.summary:
          return agent.copyWith(enabled: false, maxTurns: 0);
        case AgentId.user:
        case AgentId.supervisor:
        case AgentId.qa:
        case AgentId.ux:
        case AgentId.seniorEngineer:
        case AgentId.scraper:
          return agent.copyWith(enabled: false, maxTurns: 0);
      }
    }).toList(growable: false),
  );
}

bool isProjectFactoryIntakeConfiguration(AgentConfiguration? configuration) {
  if (configuration == null) {
    return false;
  }
  final generator = configuration.byId(AgentId.generator);
  final reviewer = configuration.byId(AgentId.reviewer);
  return generator?.label == 'Project Factory' &&
      generator?.enabled == true &&
      reviewer?.label == 'Project Reviewer' &&
      reviewer?.enabled == false;
}

bool isDomainFactoryConfiguration(AgentConfiguration? configuration) {
  if (configuration == null) {
    return false;
  }
  final generator = configuration.byId(AgentId.generator);
  final reviewer = configuration.byId(AgentId.reviewer);
  return generator?.label == 'Domain Factory' &&
      generator?.enabled == true &&
      reviewer?.label == 'Domain Reviewer' &&
      reviewer?.enabled == true;
}

bool projectFactoryHasBuildReadyMarker(Iterable<ChatMessage> messages) {
  return messages.any(
    (message) =>
        !message.isUser &&
        message.agentId == AgentId.generator &&
        message.status == ChatMessageStatus.completed &&
        message.text.contains(kProjectFactoryReadyForBuildMarker),
  );
}

bool isProjectFactoryBuildConfirmation(String? rawText) {
  final text = _normalizeProjectFactoryConfirmationText(rawText);
  if (text.isEmpty) {
    return false;
  }
  const blockers = <String>[
    'no comencemos',
    'no empecemos',
    'no arranquemos',
    'no arranques',
    'no empieces',
    'todavia no',
    'todavía no',
    'espera',
    'esperá',
  ];
  if (blockers.any(text.contains)) {
    return false;
  }
  const confirmations = <String>[
    'ok dale para adelante',
    'dale para adelante',
    'ok comencemos',
    'comencemos',
    'empecemos',
    'arranquemos',
    'arranca',
    'arrancá',
    'empeza',
    'empezá',
    'dale arrancá',
    'dale arranca',
    'go ahead',
    'start build',
    'start building',
  ];
  return confirmations.any(text.contains);
}

String _normalizeProjectFactoryConfirmationText(String? rawText) {
  return (rawText ?? '')
      .toLowerCase()
      .replaceAll(RegExp(r'[^\p{L}\p{N}]+', unicode: true), ' ')
      .replaceAll(RegExp(r'\s+'), ' ')
      .trim();
}

const List<double> _audioReplyPlaybackSpeeds = <double>[
  1.0,
  1.25,
  1.5,
  1.75,
  2.0,
];
const Key kChatScreenBodyScrollViewKey = ValueKey<String>(
  'chat-screen-body-scroll-view',
);

enum _AppBarOverflowAction {
  apps,
  conversationContext,
  summaryView,
  codexTools,
  saveCurrentAgent,
  replyMode,
  servers,
  newProject,
  domainFactory,
  projectHistory,
  newChat,
}

enum _PinnedWorkspaceAction { newChat, remove }

enum _RenameChatMode { manual, generated }

enum _ChatBodyView { conversation, agentSummaries, turnSummaries }

class ChatScreen extends StatefulWidget {
  const ChatScreen({
    super.key,
    required this.initialApiBaseUrl,
    required this.notificationService,
    this.controllerOverride,
    this.replyPlaybackServiceOverride,
    this.enableServerBootstrap = true,
    this.initialSidebarWorkspaces = const <Workspace>[],
    this.initialCodexTooling,
    this.codexMcpAppInstallerOverride,
    this.onActiveServerBaseUrlChanged,
    this.audioRecorderFactoryOverride,
    this.projectFactoryClientOverride,
  });

  final String initialApiBaseUrl;
  final ChatNotificationService notificationService;
  final ChatController? controllerOverride;
  final ReplyPlaybackService? replyPlaybackServiceOverride;
  final bool enableServerBootstrap;
  final List<Workspace> initialSidebarWorkspaces;
  final CodexToolingSnapshot? initialCodexTooling;
  final Future<CodexToolingSnapshot?> Function(CodexMcpApp app)?
      codexMcpAppInstallerOverride;
  final ValueChanged<String>? onActiveServerBaseUrlChanged;
  @visibleForTesting
  final AudioNoteRecorder Function()? audioRecorderFactoryOverride;
  @visibleForTesting
  final ApiClient? projectFactoryClientOverride;
  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> with WidgetsBindingObserver {
  final ServerProfileStore _serverProfileStore = ServerProfileStore();
  final TextEditingController _textController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  late final ReplyPlaybackService _replyPlaybackService;
  late ChatController _chatController;
  List<ServerProfile> _serverProfiles = <ServerProfile>[];
  List<Workspace> _sidebarWorkspaces = <Workspace>[];
  Map<String, DateTime> _sessionReadMarkers = <String, DateTime>{};
  final Map<String, int> _visibleSessionLimitsByGroup = <String, int>{};
  ServerProfile? _activeServer;
  ServerHealth? _activeServerHealth;
  ServerCapabilities? _activeServerCapabilities;
  CodexToolingSnapshot? _activeCodexTooling;
  String? _serverErrorText;
  String? _codexToolingErrorText;
  bool _sidebarExpanded = false;
  bool _showArchivedChatsInSidebar = false;
  bool _stickToBottom = true;
  bool _audioRepliesEnabled = false;
  double _audioReplyPlaybackSpeed = 1.0;
  bool _isLoadingCodexTooling = false;
  bool _isOpeningWorkspacePicker = false;
  String? _lastObservedSessionId;
  String? _lastObservedNewestMessageId;
  final Map<String, _ComposerDraft> _sessionDrafts = <String, _ComposerDraft>{};
  final Map<String, String> _projectFactoryDraftIdBySession =
      <String, String>{};
  final Map<String, ProjectFactoryGuidedIntake>
      _projectFactoryGuidedIntakeBySession =
      <String, ProjectFactoryGuidedIntake>{};
  final Set<String> _loadingProjectFactoryIntakeSessions = <String>{};
  String? _projectFactoryGuidedIntakeErrorText;
  final Map<String, ProjectFactoryInitJob> _projectFactoryInitBySession =
      <String, ProjectFactoryInitJob>{};
  final Set<String> _loadingProjectFactoryInitSessions = <String>{};
  String? _projectFactoryInitErrorText;
  final Map<String, Set<String>> _collapsedMessageIdsBySession =
      <String, Set<String>>{};
  bool _isUpdatingFilteredMessagesView = false;
  String? _filteredMessagesViewErrorText;
  _ChatBodyView _chatBodyView = _ChatBodyView.conversation;
  static const double _compactAppBarBreakpoint = 640;
  static const int _sessionGroupPageSize = 5;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _replyPlaybackService =
        widget.replyPlaybackServiceOverride ?? ReplyPlaybackService();
    unawaited(
      _replyPlaybackService.setServer(
        ApiClient(baseUrl: widget.initialApiBaseUrl),
      ),
    );
    _chatController =
        widget.controllerOverride ?? _buildController(widget.initialApiBaseUrl);
    if (widget.initialSidebarWorkspaces.isNotEmpty) {
      _sidebarWorkspaces = List<Workspace>.from(
        widget.initialSidebarWorkspaces,
      );
    }
    _activeCodexTooling = widget.initialCodexTooling;
    _chatController.addListener(_handleChatControllerChanged);
    if (widget.enableServerBootstrap && widget.controllerOverride == null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _initializeServerProfiles();
      });
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    unawaited(_replyPlaybackService.dispose());
    _chatController.removeListener(_handleChatControllerChanged);
    if (widget.controllerOverride == null) {
      _chatController.dispose();
    }
    _textController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _chatController.handleAppResumed();
    }
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _chatController,
      builder: (context, _) {
        final currentSession = _chatController.currentSession;
        final messages = _visibleMessagesForCurrentSession();
        final timelineEntries = _buildTimelineEntries(messages);
        final summaryMessageCount = _summaryMessageCountForCurrentSession();
        final turnSummaryCount = _turnSummaryCountForCurrentSession();
        final isShowingAgentSummaries =
            _chatBodyView == _ChatBodyView.agentSummaries;
        final isShowingTurnSummaries =
            _chatBodyView == _ChatBodyView.turnSummaries;
        final showFilteredMessagesPlaceholder = currentSession != null &&
            currentSession.messages.isNotEmpty &&
            messages.isEmpty;
        final screenWidth = MediaQuery.sizeOf(context).width;
        final isCompactAppBar = screenWidth < _compactAppBarBreakpoint;
        final drawerWidth = math.min(
          screenWidth - 24,
          _sidebarExpanded ? 440.0 : 340.0,
        );
        final sessionGroups = _buildSessionGroups(
          archivedOnly: _showArchivedChatsInSidebar,
        );
        final totalUnreadChatsCount = _totalUnreadChatsCount();
        final totalActivePinnedProjectsCount =
            _totalActivePinnedProjectsCount();
        final totalActivePinnedJobsCount = _totalActivePinnedJobsCount();
        return Scaffold(
          appBar: AppBar(
            titleSpacing: isCompactAppBar ? 4 : null,
            leading: Builder(
              builder: (context) {
                return IconButton(
                  onPressed: () => Scaffold.of(context).openDrawer(),
                  tooltip: 'Projects',
                  icon: Stack(
                    clipBehavior: Clip.none,
                    children: <Widget>[
                      Icon(
                        Icons.menu,
                        color: totalActivePinnedProjectsCount > 0
                            ? const Color(0xFFFFC857)
                            : null,
                      ),
                      if (totalActivePinnedProjectsCount > 0)
                        Positioned(
                          left: -10,
                          top: -6,
                          child: _MenuStatusBadge(
                            label: totalActivePinnedJobsCount.toString(),
                            backgroundColor: const Color(0xFFFFC857),
                            foregroundColor: const Color(0xFF2A1600),
                          ),
                        ),
                      if (totalUnreadChatsCount > 0)
                        Positioned(
                          right: -8,
                          top: -6,
                          child: _MenuStatusBadge(
                            label: totalUnreadChatsCount.toString(),
                            backgroundColor: const Color(0xFF55D6BE),
                            foregroundColor: const Color(0xFF07131D),
                          ),
                        ),
                    ],
                  ),
                );
              },
            ),
            title: _buildAppBarTitle(isCompactAppBar: isCompactAppBar),
            actions: _buildAppBarActions(isCompactAppBar: isCompactAppBar),
          ),
          drawer: Drawer(
            width: drawerWidth,
            backgroundColor: const Color(0xFF101931),
            child: SafeArea(
              child: Column(
                children: <Widget>[
                  ListTile(
                    title: const Text('Projects'),
                    subtitle: Text(
                      _showArchivedChatsInSidebar
                          ? 'Archived chats across your pinned projects'
                          : _sidebarExpanded
                              ? 'Expanded sidebar: more room for projects and chats'
                              : 'Choose a project or open a chat',
                    ),
                    trailing: Wrap(
                      spacing: 4,
                      children: <Widget>[
                        IconButton(
                          onPressed: () async {
                            await _toggleSidebarExpanded();
                          },
                          icon: Icon(
                            _sidebarExpanded
                                ? Icons.close_fullscreen_rounded
                                : Icons.open_in_full_rounded,
                          ),
                          tooltip: _sidebarExpanded
                              ? 'Use compact sidebar'
                              : 'Expand sidebar',
                        ),
                        IconButton(
                          onPressed: () async {
                            await _openWorkspacePicker();
                            if (context.mounted) {
                              Navigator.of(context).pop();
                            }
                          },
                          icon: const Icon(Icons.add),
                          tooltip: 'Choose project for new chat',
                        ),
                      ],
                    ),
                  ),
                  const Divider(height: 1),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
                    child: Row(
                      children: <Widget>[
                        Expanded(
                          child: ChoiceChip(
                            label: const Text('Active'),
                            selected: !_showArchivedChatsInSidebar,
                            onSelected: (selected) {
                              if (!selected || !_showArchivedChatsInSidebar) {
                                return;
                              }
                              setState(() {
                                _showArchivedChatsInSidebar = false;
                              });
                            },
                            selectedColor: const Color(0xFF55D6BE),
                            backgroundColor: const Color(0xFF16213C),
                            labelStyle: TextStyle(
                              color: !_showArchivedChatsInSidebar
                                  ? const Color(0xFF07131D)
                                  : const Color(0xFFDCE5FF),
                              fontWeight: FontWeight.w700,
                            ),
                            side: const BorderSide(color: Color(0xFF23304F)),
                          ),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: ChoiceChip(
                            label: const Text('Archived'),
                            selected: _showArchivedChatsInSidebar,
                            onSelected: (selected) {
                              if (!selected || _showArchivedChatsInSidebar) {
                                return;
                              }
                              setState(() {
                                _showArchivedChatsInSidebar = true;
                              });
                            },
                            selectedColor: const Color(0xFF8CA8FF),
                            backgroundColor: const Color(0xFF16213C),
                            labelStyle: TextStyle(
                              color: _showArchivedChatsInSidebar
                                  ? const Color(0xFF07131D)
                                  : const Color(0xFFDCE5FF),
                              fontWeight: FontWeight.w700,
                            ),
                            side: const BorderSide(color: Color(0xFF23304F)),
                          ),
                        ),
                      ],
                    ),
                  ),
                  Expanded(
                    child: sessionGroups.isEmpty
                        ? Center(
                            child: Text(
                              _sidebarWorkspaces.isEmpty
                                  ? 'No projects pinned yet'
                                  : _showArchivedChatsInSidebar
                                      ? 'No archived chats yet'
                                      : 'No chats yet',
                              style: const TextStyle(color: Color(0xFF8B97B5)),
                            ),
                          )
                        : ListView(children: sessionGroups),
                  ),
                ],
              ),
            ),
          ),
          body: SafeArea(
            bottom: false,
            child: Column(
              children: <Widget>[
                Expanded(
                  child: _chatController.isLoading &&
                          _chatController.currentSession == null
                      ? const Center(child: CircularProgressIndicator())
                      : Stack(
                          children: <Widget>[
                            NotificationListener<ScrollNotification>(
                              onNotification: _handleScrollNotification,
                              child: RefreshIndicator(
                                onRefresh: () =>
                                    _chatController.refreshAppState(
                                  failurePrefix:
                                      'Failed to refresh chats from the backend.',
                                ),
                                child: CustomScrollView(
                                  key: kChatScreenBodyScrollViewKey,
                                  controller: _scrollController,
                                  physics:
                                      const AlwaysScrollableScrollPhysics(),
                                  slivers: <Widget>[
                                    if (_chatController.errorText != null)
                                      SliverToBoxAdapter(
                                        child: Container(
                                          width: double.infinity,
                                          margin: const EdgeInsets.fromLTRB(
                                            16,
                                            8,
                                            16,
                                            0,
                                          ),
                                          padding: const EdgeInsets.all(12),
                                          decoration: BoxDecoration(
                                            color: const Color(0xFF3B1521),
                                            borderRadius: BorderRadius.circular(
                                              14,
                                            ),
                                          ),
                                          child: Text(
                                            _chatController.errorText!,
                                            style: const TextStyle(
                                              color: Colors.white,
                                            ),
                                          ),
                                        ),
                                      ),
                                    if (_serverErrorText != null)
                                      SliverToBoxAdapter(
                                        child: Container(
                                          width: double.infinity,
                                          margin: const EdgeInsets.fromLTRB(
                                            16,
                                            8,
                                            16,
                                            0,
                                          ),
                                          padding: const EdgeInsets.all(12),
                                          decoration: BoxDecoration(
                                            color: const Color(0xFF362411),
                                            borderRadius: BorderRadius.circular(
                                              14,
                                            ),
                                          ),
                                          child: Text(
                                            _serverErrorText!,
                                            style: const TextStyle(
                                              color: Colors.white,
                                            ),
                                          ),
                                        ),
                                      ),
                                    if (currentSession != null)
                                      SliverToBoxAdapter(
                                        child: ReviewerStatusBanner(
                                          session: currentSession,
                                        ),
                                      ),
                                    if (currentSession != null)
                                      SliverPadding(
                                        padding: const EdgeInsets.fromLTRB(
                                          16,
                                          8,
                                          16,
                                          0,
                                        ),
                                        sliver: SliverToBoxAdapter(
                                          child: CurrentRunTimelineCard(
                                            session: currentSession,
                                          ),
                                        ),
                                      ),
                                    if (currentSession != null &&
                                        isProjectFactoryIntakeConfiguration(
                                          currentSession.agentConfiguration,
                                        ))
                                      SliverPadding(
                                        padding: const EdgeInsets.fromLTRB(
                                          16,
                                          8,
                                          16,
                                          0,
                                        ),
                                        sliver: SliverToBoxAdapter(
                                          child: _buildProjectFactoryIntakeCard(
                                            currentSession,
                                          ),
                                        ),
                                      ),
                                    if (currentSession != null &&
                                        (summaryMessageCount > 0 ||
                                            turnSummaryCount > 0 ||
                                            currentSession
                                                .turnSummariesEnabled ||
                                            _chatBodyView !=
                                                _ChatBodyView.conversation))
                                      SliverToBoxAdapter(
                                        child: Padding(
                                          padding: const EdgeInsets.fromLTRB(
                                            16,
                                            10,
                                            16,
                                            0,
                                          ),
                                          child: Wrap(
                                            spacing: 10,
                                            children: <Widget>[
                                              ChoiceChip(
                                                label: const Text(
                                                  'Conversation',
                                                ),
                                                selected: _chatBodyView ==
                                                    _ChatBodyView.conversation,
                                                onSelected: (selected) {
                                                  if (!selected) {
                                                    return;
                                                  }
                                                  _setChatBodyView(
                                                    _ChatBodyView.conversation,
                                                  );
                                                },
                                                selectedColor: const Color(
                                                  0xFF55D6BE,
                                                ),
                                                backgroundColor: const Color(
                                                  0xFF16213C,
                                                ),
                                                labelStyle: TextStyle(
                                                  color: _chatBodyView ==
                                                          _ChatBodyView
                                                              .conversation
                                                      ? const Color(0xFF07131D)
                                                      : const Color(0xFFDCE5FF),
                                                  fontWeight: FontWeight.w700,
                                                ),
                                                side: const BorderSide(
                                                  color: Color(0xFF23304F),
                                                ),
                                              ),
                                              Tooltip(
                                                message: 'View summary',
                                                child: ChoiceChip(
                                                  label: Text(
                                                    summaryMessageCount == 1
                                                        ? 'Run summary'
                                                        : 'Run summaries ($summaryMessageCount)',
                                                  ),
                                                  selected:
                                                      isShowingAgentSummaries,
                                                  onSelected:
                                                      summaryMessageCount <= 0
                                                          ? null
                                                          : (selected) {
                                                              if (!selected) {
                                                                return;
                                                              }
                                                              _setChatBodyView(
                                                                _ChatBodyView
                                                                    .agentSummaries,
                                                              );
                                                            },
                                                  selectedColor: const Color(
                                                    0xFF8CA8FF,
                                                  ),
                                                  backgroundColor: const Color(
                                                    0xFF16213C,
                                                  ),
                                                  labelStyle: TextStyle(
                                                    color:
                                                        isShowingAgentSummaries
                                                            ? const Color(
                                                                0xFF07131D,
                                                              )
                                                            : const Color(
                                                                0xFFDCE5FF,
                                                              ),
                                                    fontWeight: FontWeight.w700,
                                                  ),
                                                  side: const BorderSide(
                                                    color: Color(0xFF23304F),
                                                  ),
                                                ),
                                              ),
                                              ChoiceChip(
                                                label: Text(
                                                  turnSummaryCount == 1
                                                      ? 'Chat summary'
                                                      : 'Chat summaries ($turnSummaryCount)',
                                                ),
                                                selected:
                                                    isShowingTurnSummaries,
                                                onSelected: (turnSummaryCount <=
                                                            0 &&
                                                        !currentSession
                                                            .turnSummariesEnabled)
                                                    ? null
                                                    : (selected) {
                                                        if (!selected) {
                                                          return;
                                                        }
                                                        _setChatBodyView(
                                                          _ChatBodyView
                                                              .turnSummaries,
                                                        );
                                                      },
                                                selectedColor: const Color(
                                                  0xFFFFC857,
                                                ),
                                                backgroundColor: const Color(
                                                  0xFF16213C,
                                                ),
                                                labelStyle: TextStyle(
                                                  color: isShowingTurnSummaries
                                                      ? const Color(0xFF2A1600)
                                                      : const Color(0xFFDCE5FF),
                                                  fontWeight: FontWeight.w700,
                                                ),
                                                side: const BorderSide(
                                                  color: Color(0xFF23304F),
                                                ),
                                              ),
                                            ],
                                          ),
                                        ),
                                      ),
                                    if (isShowingAgentSummaries &&
                                        currentSession != null)
                                      SliverToBoxAdapter(
                                        child: Padding(
                                          padding: const EdgeInsets.fromLTRB(
                                            16,
                                            10,
                                            16,
                                            0,
                                          ),
                                          child: _SummaryViewBanner(
                                            summaryCount: summaryMessageCount,
                                            onShowFullChat: () {
                                              _setChatBodyView(
                                                _ChatBodyView.conversation,
                                              );
                                            },
                                          ),
                                        ),
                                      ),
                                    if (isShowingTurnSummaries &&
                                        currentSession != null)
                                      SliverToBoxAdapter(
                                        child: Padding(
                                          padding: const EdgeInsets.fromLTRB(
                                            16,
                                            10,
                                            16,
                                            0,
                                          ),
                                          child: _TurnSummaryBanner(
                                            summaryCount: turnSummaryCount,
                                            enabled: currentSession
                                                .turnSummariesEnabled,
                                            onShowFullChat: () {
                                              _setChatBodyView(
                                                _ChatBodyView.conversation,
                                              );
                                            },
                                          ),
                                        ),
                                      ),
                                    if (isShowingTurnSummaries &&
                                        currentSession != null &&
                                        turnSummaryCount > 0)
                                      SliverPadding(
                                        padding: const EdgeInsets.fromLTRB(
                                          16,
                                          12,
                                          16,
                                          16,
                                        ),
                                        sliver: SliverList(
                                          delegate: SliverChildBuilderDelegate(
                                            (context, index) {
                                              final summary = currentSession
                                                  .turnSummaries[index];
                                              return Padding(
                                                padding: EdgeInsets.only(
                                                  bottom: index ==
                                                          currentSession
                                                                  .turnSummaries
                                                                  .length -
                                                              1
                                                      ? 0
                                                      : 12,
                                                ),
                                                child: _TurnSummaryCard(
                                                  summary: summary,
                                                ),
                                              );
                                            },
                                            childCount: currentSession
                                                .turnSummaries.length,
                                          ),
                                        ),
                                      )
                                    else if (messages.isEmpty)
                                      SliverFillRemaining(
                                        hasScrollBody: false,
                                        child: isShowingAgentSummaries &&
                                                currentSession != null
                                            ? _SummaryMessagesPlaceholder(
                                                onShowFullChat: () {
                                                  _setChatBodyView(
                                                    _ChatBodyView.conversation,
                                                  );
                                                },
                                              )
                                            : isShowingTurnSummaries &&
                                                    currentSession != null
                                                ? _TurnSummariesPlaceholder(
                                                    enabled: currentSession
                                                        .turnSummariesEnabled,
                                                    onShowFullChat: () {
                                                      _setChatBodyView(
                                                        _ChatBodyView
                                                            .conversation,
                                                      );
                                                    },
                                                  )
                                                : showFilteredMessagesPlaceholder
                                                    ? _FilteredMessagesPlaceholder(
                                                        displayMode: currentSession
                                                            .agentConfiguration
                                                            .displayMode,
                                                        isUpdating:
                                                            _isUpdatingFilteredMessagesView,
                                                        errorText:
                                                            _filteredMessagesViewErrorText,
                                                        onShowAllMessages:
                                                            _handleShowAllMessages,
                                                      )
                                                    : _EmptyState(
                                                        onCreateChat:
                                                            _openWorkspacePicker,
                                                      ),
                                      )
                                    else
                                      SliverPadding(
                                        padding: const EdgeInsets.fromLTRB(
                                          16,
                                          12,
                                          16,
                                          16,
                                        ),
                                        sliver: SliverList(
                                          delegate: SliverChildBuilderDelegate(
                                            (context, index) {
                                              if (index == 0 &&
                                                  _shouldShowOlderMessagesRow) {
                                                return _OlderMessagesRow(
                                                  isLoading: _chatController
                                                      .isLoadingOlderMessages,
                                                  errorText: _chatController
                                                      .olderMessagesError,
                                                  onRetry:
                                                      _loadOlderMessagesFromTop,
                                                );
                                              }
                                              final timelineIndex =
                                                  _shouldShowOlderMessagesRow
                                                      ? index - 1
                                                      : index;
                                              final entry = timelineEntries[
                                                  timelineIndex];
                                              if (entry.separatorDate != null) {
                                                final separatorDate =
                                                    entry.separatorDate!;
                                                return _ChatDaySeparator(
                                                  key: ValueKey<String>(
                                                    'chat-day-separator-${separatorDate.year}-${separatorDate.month}-${separatorDate.day}',
                                                  ),
                                                  label:
                                                      formatChatDaySeparatorLabel(
                                                    context,
                                                    separatorDate,
                                                  ),
                                                );
                                              }
                                              final message = entry.message!;
                                              final nextEntry = index + 1 <
                                                      timelineEntries.length
                                                  ? timelineEntries[index + 1]
                                                  : null;
                                              final nextMessage =
                                                  nextEntry?.message;
                                              final extraBottomSpacing =
                                                  nextMessage != null &&
                                                          nextMessage.isUser !=
                                                              message.isUser
                                                      ? 10.0
                                                      : 0.0;
                                              return Align(
                                                alignment: message.isUser
                                                    ? Alignment.centerRight
                                                    : Alignment.centerLeft,
                                                child: Padding(
                                                  padding: EdgeInsets.only(
                                                    bottom: extraBottomSpacing,
                                                  ),
                                                  child: ChatBubble(
                                                    key: ValueKey<String>(
                                                      'chat-bubble-${message.id}',
                                                    ),
                                                    message: message,
                                                    isCollapsed:
                                                        _isMessageCollapsed(
                                                      message,
                                                    ),
                                                    onToggleCollapsed: () =>
                                                        _toggleMessageCollapsed(
                                                      message,
                                                    ),
                                                    generatorColor: _chatController
                                                                .currentSession !=
                                                            null
                                                        ? _colorFromHex(
                                                            _chatController
                                                                .currentSession!
                                                                .agentProfileColor,
                                                          )
                                                        : null,
                                                    onOptionSelected:
                                                        _handleSuggestedReply,
                                                    onLinkTap:
                                                        _handleMessageLinkTap,
                                                    attachmentBaseUrl:
                                                        _activeServer
                                                                ?.baseUrl ??
                                                            widget
                                                                .initialApiBaseUrl,
                                                    onCancelJob:
                                                        (_activeServerCapabilities
                                                                        ?.supportsJobCancellation ??
                                                                    false) &&
                                                                message.jobId !=
                                                                    null
                                                            ? () =>
                                                                _handleCancelJob(
                                                                  message
                                                                      .jobId!,
                                                                )
                                                            : null,
                                                    onRetryJob:
                                                        (_activeServerCapabilities
                                                                        ?.supportsJobRetry ??
                                                                    false) &&
                                                                message.jobId !=
                                                                    null
                                                            ? () =>
                                                                _handleRetryJob(
                                                                  message
                                                                      .jobId!,
                                                                )
                                                            : null,
                                                    onRecoverUnknownSubmission: message
                                                                .status ==
                                                            ChatMessageStatus
                                                                .submissionUnknown
                                                        ? () =>
                                                            _handleRecoverUnknownSubmission(
                                                              message.id,
                                                            )
                                                        : null,
                                                    onCancelUnknownSubmission: message
                                                                .status ==
                                                            ChatMessageStatus
                                                                .submissionUnknown
                                                        ? () =>
                                                            _handleCancelUnknownSubmission(
                                                              message.id,
                                                            )
                                                        : null,
                                                  ),
                                                ),
                                              );
                                            },
                                            childCount: timelineEntries.length +
                                                (_shouldShowOlderMessagesRow
                                                    ? 1
                                                    : 0),
                                          ),
                                        ),
                                      ),
                                  ],
                                ),
                              ),
                            ),
                            Positioned(
                              right: 16,
                              bottom: 12,
                              child: IgnorePointer(
                                ignoring: _stickToBottom,
                                child: AnimatedSlide(
                                  duration: const Duration(milliseconds: 180),
                                  curve: Curves.easeOut,
                                  offset: _stickToBottom
                                      ? const Offset(0, 0.35)
                                      : Offset.zero,
                                  child: AnimatedOpacity(
                                    duration: const Duration(milliseconds: 180),
                                    opacity: _stickToBottom ? 0 : 1,
                                    child: FloatingActionButton.small(
                                      heroTag: 'scroll-to-latest',
                                      onPressed: () {
                                        _updateStickToBottom(true);
                                        _scrollToBottom();
                                      },
                                      backgroundColor: const Color(0xFF1C2745),
                                      foregroundColor: const Color(0xFF55D6BE),
                                      child: const Icon(Icons.south_rounded),
                                    ),
                                  ),
                                ),
                              ),
                            ),
                          ],
                        ),
                ),
                _Composer(
                  sessionId: _chatController.selectedSessionId,
                  controller: _textController,
                  draft: _currentComposerDraft(),
                  onDraftChanged: _updateCurrentComposerDraft,
                  onSend: _handleSend,
                  onSendAudio: _handleSendAudio,
                  onSendAttachments: _handleSendAttachments,
                  onBeginRecording: _handleBeginRecording,
                  onSlashCommand: _handleSlashCommand,
                  slashCommandContext: SlashCommandContext(
                    isProjectFactoryIntake: isProjectFactoryIntakeConfiguration(
                      _chatController.currentSession?.agentConfiguration,
                    ),
                    hasActiveBackend: _activeServer != null,
                    workbenchAvailable: _activeServer != null,
                    appsAvailable: _activeServer != null,
                  ),
                  isProjectFactoryIntake: isProjectFactoryIntakeConfiguration(
                    _chatController.currentSession?.agentConfiguration,
                  ),
                  audioRecorderFactory: widget.audioRecorderFactoryOverride ??
                      AudioNoteRecorder.new,
                  isBusy: _chatController.isLoading &&
                      _chatController.currentSession == null,
                  voiceEnabled: _resolvedAudioInputEnabled(),
                  imageAttachmentsEnabled:
                      _activeServerCapabilities?.supportsImageInput ?? true,
                  fileAttachmentsEnabled: _resolvedFileAttachmentsEnabled(),
                  voiceStatusText: _resolveVoiceStatusText(),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Future<bool> _handleSend() async {
    if (await _maybeHandleOpenMcpAppCommand(_textController.text)) {
      return true;
    }
    if (!await _maybeActivateProjectFactoryBuildMode(_textController.text)) {
      return false;
    }
    final sessionIdBeforeSend = _chatController.selectedSessionId;
    final workspacePathBeforeSend =
        _chatController.currentSession?.workspacePath;
    final codexRunOptions = _currentComposerDraft().codexRunOptions;
    final didSend = await _chatController.sendMessage(
      _textController.text,
      sessionIdOverride: sessionIdBeforeSend,
      workspacePathOverride: workspacePathBeforeSend,
      codexRunOptions: codexRunOptions.isEmpty ? null : codexRunOptions,
    );
    if (didSend &&
        (sessionIdBeforeSend == null ||
            _chatController.selectedSessionId == sessionIdBeforeSend)) {
      _textController.clear();
      _updateStickToBottom(true);
      _scrollToBottom();
    }
    return didSend;
  }

  Future<bool> _handleSlashCommand(String commandId, String payload) async {
    switch (commandId) {
      case 'new-project':
        await _openNewProjectFactory();
        return true;
      case 'status':
      case 'review':
      case 'compact':
      case 'diff':
        _textController.text = payload;
        _textController.selection = TextSelection.collapsed(
          offset: _textController.text.length,
        );
        return _handleSend();
      case 'feedback':
        _textController.text = payload;
        _textController.selection = TextSelection.collapsed(
          offset: _textController.text.length,
        );
        return true;
      case 'apps':
        await _openInstallableAppsSheet();
        return true;
      case 'workbench':
        await _openCodexToolsSheet();
        return true;
      default:
        return false;
    }
  }

  Widget _buildProjectFactoryIntakeCard(SessionDetail currentSession) {
    final draftId = _projectFactoryDraftIdBySession[currentSession.id];
    final intake = _projectFactoryGuidedIntakeBySession[currentSession.id];
    final initJob = _projectFactoryInitBySession[currentSession.id];
    final isInitLoading =
        _loadingProjectFactoryInitSessions.contains(currentSession.id);
    final isLoading =
        _loadingProjectFactoryIntakeSessions.contains(currentSession.id);
    final showLegacyGuidedIntake = initJob == null && !isInitLoading;
    if (intake != null && draftId != null) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          ProjectFactoryInitCard(
            initJob: initJob,
            isLoading: isInitLoading,
            errorText: _projectFactoryInitErrorText,
          ),
          if (showLegacyGuidedIntake) ...<Widget>[
            const SizedBox(height: 10),
            ProjectFactoryGuidedIntakeCard(
              intake: intake,
              onAnswer: (questionId, value) =>
                  _answerProjectFactoryGuidedIntake(
                currentSession.id,
                questionId,
                value,
              ),
              onPreview: () => _previewProjectFactoryGuidedIntake(
                currentSession.id,
              ),
            ),
          ],
          if (isLoading) ...<Widget>[
            const SizedBox(height: 8),
            const LinearProgressIndicator(minHeight: 2),
          ],
          if (_projectFactoryGuidedIntakeErrorText != null) ...<Widget>[
            const SizedBox(height: 8),
            Text(
              _projectFactoryGuidedIntakeErrorText!,
              style: const TextStyle(color: Color(0xFFFFB4B4)),
            ),
          ],
        ],
      );
    }
    return _GuidedProjectIntakeCard(
      readyForBuild: projectFactoryHasBuildReadyMarker(
            currentSession.messages,
          ) ||
          _projectFactoryGuidedIntakeAllowsBuild(currentSession.id),
      isLoading: isLoading,
      errorText: _projectFactoryGuidedIntakeErrorText,
      onShowContract: () {
        _textController.text =
            'Show the current New Project contract preview with decisions, assumptions, assets, release plan, Workbench/SDD, web preview, Android plan, blockers, risks, and validation.';
        _textController.selection = TextSelection.collapsed(
          offset: _textController.text.length,
        );
      },
    );
  }

  Future<bool> _handleSendAttachments(
    List<_PendingAttachmentDraft> attachments, {
    String? prompt,
  }) async {
    if (!await _maybeActivateProjectFactoryBuildMode(prompt)) {
      return false;
    }
    final sessionIdBeforeSend = _chatController.selectedSessionId;
    final workspacePathBeforeSend =
        _chatController.currentSession?.workspacePath;
    final codexRunOptions = _currentComposerDraft().codexRunOptions;
    final enrichedPrompt = await _promptWithPromotedProjectAssets(
      attachments,
      prompt,
    );
    if (enrichedPrompt == null) {
      return false;
    }
    final didSend = await _chatController.sendAttachmentsMessage(
      attachments.map((attachment) => attachment.file).toList(),
      message: enrichedPrompt,
      sessionIdOverride: sessionIdBeforeSend,
      workspacePathOverride: workspacePathBeforeSend,
      codexRunOptions: codexRunOptions.isEmpty ? null : codexRunOptions,
    );
    if (didSend &&
        (sessionIdBeforeSend == null ||
            _chatController.selectedSessionId == sessionIdBeforeSend)) {
      _updateStickToBottom(true);
      _scrollToBottom();
    }
    return didSend;
  }

  Future<String?> _promptWithPromotedProjectAssets(
    List<_PendingAttachmentDraft> attachments,
    String? prompt,
  ) async {
    if (!isProjectFactoryIntakeConfiguration(
      _chatController.currentSession?.agentConfiguration,
    )) {
      return prompt;
    }
    final promoted = attachments
        .where((attachment) => attachment.projectAssetRole != null)
        .toList(growable: false);
    if (promoted.isEmpty) {
      return prompt;
    }
    final baseUrl = (_activeServer?.baseUrl ?? widget.initialApiBaseUrl)
        .trim()
        .replaceAll(RegExp(r'/$'), '');
    final client = ApiClient(baseUrl: baseUrl);
    final lines = <String>[];
    try {
      for (final attachment in promoted) {
        final role = attachment.projectAssetRole!;
        final asset = await client.uploadAssetDepotAsset(
          attachment.file,
          source: 'chat_upload',
        );
        lines.add(
          '- asset_id: ${asset.assetId}; role: ${role.apiValue}; '
          'filename: ${asset.originalFilename}; sha256: ${asset.sha256}',
        );
      }
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not promote attachment asset. $error')),
        );
      }
      return null;
    }
    final trimmedPrompt = prompt?.trim() ?? '';
    final assetBlock = '''
Asset Depot uploads for this New Project:
${lines.join('\n')}

When you create the Project Factory draft, link each asset with POST /project-factory/drafts/{draft_id}/assets using the listed role. Preserve exact bytes for exact_asset, logo, and app_icon.
''';
    if (trimmedPrompt.isEmpty) {
      return assetBlock.trim();
    }
    return '$trimmedPrompt\n\n${assetBlock.trim()}';
  }

  Future<bool> _handleSendAudio(XFile audioFile, {String? message}) async {
    if (!await _maybeActivateProjectFactoryBuildMode(message)) {
      return false;
    }
    final sessionIdBeforeSend = _chatController.selectedSessionId;
    final workspacePathBeforeSend =
        _chatController.currentSession?.workspacePath;
    final codexRunOptions = _currentComposerDraft().codexRunOptions;
    final didSend = await _chatController.sendAudioMessage(
      audioFile,
      message: message,
      sessionIdOverride: sessionIdBeforeSend,
      workspacePathOverride: workspacePathBeforeSend,
      codexRunOptions: codexRunOptions.isEmpty ? null : codexRunOptions,
    );
    if (didSend &&
        (sessionIdBeforeSend == null ||
            _chatController.selectedSessionId == sessionIdBeforeSend)) {
      _updateStickToBottom(true);
      _scrollToBottom();
    }
    return didSend;
  }

  Future<void> _handleCancelJob(String jobId) async {
    final didCancel = await _chatController.cancelJob(jobId);
    if (!mounted) {
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          didCancel ? 'Job cancelled.' : 'Could not cancel the job.',
        ),
        duration: const Duration(seconds: 2),
      ),
    );
  }

  Future<void> _handleRetryJob(String jobId) async {
    final didRetry = await _chatController.retryJob(jobId);
    if (!mounted) {
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(didRetry ? 'Retry queued.' : 'Could not retry the job.'),
        duration: const Duration(seconds: 2),
      ),
    );
  }

  Future<void> _handleRecoverUnknownSubmission(String messageId) async {
    final didRecover = await _chatController.recoverMessage(
      messageId,
      action: MessageRecoveryAction.retry,
    );
    if (!mounted) {
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          didRecover
              ? 'Follow-up retry queued.'
              : 'Could not retry the uncertain follow-up.',
        ),
        duration: const Duration(seconds: 2),
      ),
    );
  }

  Future<void> _handleCancelUnknownSubmission(String messageId) async {
    final didCancel = await _chatController.recoverMessage(
      messageId,
      action: MessageRecoveryAction.cancel,
    );
    if (!mounted) {
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          didCancel
              ? 'Uncertain follow-up dismissed.'
              : 'Could not dismiss the uncertain follow-up.',
        ),
        duration: const Duration(seconds: 2),
      ),
    );
  }

  void _handleSuggestedReply(String value) {
    _textController
      ..text = value
      ..selection = TextSelection.collapsed(offset: value.length);
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Suggestion inserted into the composer.'),
        duration: Duration(seconds: 1),
      ),
    );
  }

  Future<void> _handleMessageLinkTap(String target) async {
    final trimmedTarget = target.trim();
    final uri = _parseMessageTarget(trimmedTarget);

    if (uri == null) {
      await _copyLinkTarget(
        trimmedTarget,
        message: 'Invalid link target. Copied instead.',
      );
      return;
    }

    try {
      final launched = await launchUrl(uri, mode: _launchModeForUri(uri));
      if (launched) {
        return;
      }
    } catch (_) {
      // Fall back to copying the target if the platform cannot open it.
    }

    await _copyLinkTarget(
      trimmedTarget,
      message: 'Could not open link here. Copied target instead.',
    );
  }

  Uri? _parseMessageTarget(String target) {
    if (target.isEmpty) {
      return null;
    }

    final parsed = Uri.tryParse(target);
    if (parsed != null && parsed.hasScheme) {
      return parsed;
    }

    if (target.startsWith('/')) {
      return Uri.file(target);
    }

    if (RegExp(r'^[A-Za-z]:[\\/]').hasMatch(target)) {
      return Uri.file(target);
    }

    return parsed;
  }

  LaunchMode _launchModeForUri(Uri uri) {
    return switch (uri.scheme) {
      'http' || 'https' => LaunchMode.externalApplication,
      _ => LaunchMode.platformDefault,
    };
  }

  Future<void> _copyLinkTarget(String target, {required String message}) async {
    await Clipboard.setData(ClipboardData(text: target));
    if (!mounted) {
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), duration: const Duration(seconds: 2)),
    );
  }

  List<ChatMessage> _visibleMessagesForCurrentSession() {
    final currentSession = _chatController.currentSession;
    if (currentSession == null) {
      return const <ChatMessage>[];
    }
    if (_chatBodyView == _ChatBodyView.agentSummaries) {
      return _chatController.messages
          .where((message) => message.agentId == AgentId.summary)
          .toList(growable: false);
    }
    return filterVisibleMessages(
      _chatController.messages,
      displayMode: currentSession.agentConfiguration.displayMode,
    );
  }

  List<_ChatTimelineEntry> _buildTimelineEntries(List<ChatMessage> messages) {
    final entries = <_ChatTimelineEntry>[];
    DateTime? previousMessageDate;

    for (final message in messages) {
      final messageDate = message.createdAt.toLocal();
      if (previousMessageDate == null ||
          !isSameChatCalendarDay(previousMessageDate, messageDate)) {
        entries.add(_ChatTimelineEntry.separator(messageDate));
      }
      entries.add(_ChatTimelineEntry.message(message));
      previousMessageDate = messageDate;
    }

    return entries;
  }

  int _summaryMessageCountForCurrentSession() {
    final currentSession = _chatController.currentSession;
    if (currentSession == null) {
      return 0;
    }
    return currentSession.messages
        .where((message) => message.agentId == AgentId.summary)
        .length;
  }

  int _turnSummaryCountForCurrentSession() {
    final currentSession = _chatController.currentSession;
    if (currentSession == null) {
      return 0;
    }
    return currentSession.turnSummaries.length;
  }

  _ChatBodyView _preferredSummaryView() {
    final currentSession = _chatController.currentSession;
    if (currentSession == null) {
      return _ChatBodyView.conversation;
    }
    if (currentSession.turnSummariesEnabled ||
        currentSession.turnSummaries.isNotEmpty) {
      return _ChatBodyView.turnSummaries;
    }
    if (_summaryMessageCountForCurrentSession() > 0) {
      return _ChatBodyView.agentSummaries;
    }
    return _ChatBodyView.conversation;
  }

  void _setChatBodyView(_ChatBodyView nextView) {
    if (_chatBodyView == nextView) {
      return;
    }
    setState(() {
      _chatBodyView = nextView;
    });
  }

  bool _isMessageCollapsed(ChatMessage message) {
    final sessionId = _chatController.currentSession?.id;
    if (sessionId == null) {
      return false;
    }
    return _collapsedMessageIdsBySession[sessionId]?.contains(message.id) ??
        false;
  }

  void _toggleMessageCollapsed(ChatMessage message) {
    final sessionId = _chatController.currentSession?.id;
    if (sessionId == null) {
      return;
    }
    setState(() {
      final collapsedIds = _collapsedMessageIdsBySession.putIfAbsent(
        sessionId,
        () => <String>{},
      );
      if (!collapsedIds.remove(message.id)) {
        collapsedIds.add(message.id);
      }
      if (collapsedIds.isEmpty) {
        _collapsedMessageIdsBySession.remove(sessionId);
      }
    });
  }

  Future<void> _handleShowAllMessages() async {
    final currentSession = _chatController.currentSession;
    if (currentSession == null || _isUpdatingFilteredMessagesView) {
      return;
    }

    setState(() {
      _isUpdatingFilteredMessagesView = true;
      _filteredMessagesViewErrorText = null;
    });

    final didUpdate = await _chatController.updateAgentConfiguration(
      currentSession.agentConfiguration.copyWith(
        displayMode: AgentDisplayMode.showAll,
      ),
    );

    if (!mounted) {
      return;
    }

    setState(() {
      _isUpdatingFilteredMessagesView = false;
      _filteredMessagesViewErrorText = didUpdate
          ? null
          : _chatController.errorText ?? 'Could not show all messages.';
    });
  }

  Future<void> _openNewProjectFactory() async {
    final client = _projectFactoryClient();
    final capabilities = _activeServerCapabilities;
    if (capabilities != null && !capabilities.supportsProjectFactory) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'New project needs an updated bridge backend. Restart or update the backend, then try again.',
          ),
        ),
      );
      return;
    }
    ProjectFactoryOptions options;
    try {
      options = await client.getProjectFactoryOptions();
    } on ProjectFactoryUnavailableException catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(error.message)));
      return;
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Could not load new project options.\n$error')),
      );
      return;
    }
    if (!mounted) {
      return;
    }

    final projectBasics = await _promptNewProjectBasics();
    if (projectBasics == null || !mounted) {
      return;
    }

    final draft = await _findOrCreateProjectFactoryGuidedDraft(
      client,
      options,
      projectTitle: projectBasics.title,
      initialAdminEmails: projectBasics.adminEmails,
    );
    if (draft == null || !mounted) {
      return;
    }
    await _startNewProjectFactoryChat(
      options,
      draft: draft,
      projectTitle: projectBasics.title,
    );
  }

  Future<void> _openDomainFactoryMode() async {
    final currentSession = _chatController.currentSession;
    if (currentSession == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Open a project chat before starting Domain Factory.'),
        ),
      );
      return;
    }
    final capabilities = _activeServerCapabilities;
    if (capabilities != null && !capabilities.supportsDomainFactory) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Domain Factory needs an updated bridge backend. Restart or update the backend, then try again.',
          ),
        ),
      );
      return;
    }

    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Starting Domain Factory mode...')),
    );
    final started = await _chatController.startDomainFactoryMode();
    if (!mounted) {
      return;
    }
    _updateStickToBottom(true);
    _scrollToBottom();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          started
              ? 'Domain Factory mode is ready for the business brief.'
              : _chatController.errorText ??
                  'Domain Factory is blocked. Check the chat message for details.',
        ),
      ),
    );
  }

  Future<_NewProjectBasics?> _promptNewProjectBasics() async {
    return showDialog<_NewProjectBasics>(
      context: context,
      builder: (context) => const _NewProjectBasicsDialog(),
    );
  }

  Future<void> _startNewProjectFactoryChat(
    ProjectFactoryOptions options, {
    required ProjectFactoryDraft draft,
    required String projectTitle,
  }) async {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Starting a New project chat...')),
    );
    await _chatController.createNewSession(title: projectTitle);
    if (!mounted) {
      return;
    }
    final session = _chatController.currentSession;
    if (session == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            _chatController.errorText ?? 'Could not start New project chat.',
          ),
        ),
      );
      return;
    }

    final didConfigure = await _chatController.updateAgentConfiguration(
      buildProjectFactoryIntakeConfiguration(session.agentConfiguration),
    );
    if (!mounted) {
      return;
    }
    if (!didConfigure) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            _chatController.errorText ??
                'Could not configure New project agents.',
          ),
        ),
      );
      return;
    }

    _projectFactoryDraftIdBySession[session.id] = draft.draftId;
    _projectFactoryGuidedIntakeBySession[session.id] = draft.guidedIntake;
    setState(() {
      _projectFactoryGuidedIntakeErrorText = null;
    });

    final initJob = await _startOrResumeProjectFactoryInit(
      client: _projectFactoryClient(),
      draft: draft,
      session: session,
    );
    if (!mounted) {
      return;
    }
    if (initJob == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            _projectFactoryInitErrorText ??
                'Could not start deterministic project init.',
          ),
        ),
      );
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('New Project baseline init started.'),
      ),
    );
  }

  ApiClient _projectFactoryClient() {
    return widget.projectFactoryClientOverride ??
        ApiClient(baseUrl: _activeServer?.baseUrl ?? widget.initialApiBaseUrl);
  }

  Future<ProjectFactoryDraft?> _findOrCreateProjectFactoryGuidedDraft(
    ApiClient client,
    ProjectFactoryOptions options, {
    required String projectTitle,
    required List<String> initialAdminEmails,
  }) async {
    try {
      return await client.createProjectFactoryDraft(
        ProjectFactoryDraftRequest(
          name: projectTitle,
          businessType: options.businessTypes.isNotEmpty
              ? options.businessTypes.first
              : 'general',
          primaryGoal: 'Build a new application',
          platforms: options.defaultPlatforms.isNotEmpty
              ? options.defaultPlatforms
              : const <String>['ios', 'android', 'web'],
          backend: options.defaultBackend,
          frontendStrategy: options.defaultFrontendStrategy,
          guidedIntakeEnabled: true,
          initialAdminEmails: initialAdminEmails,
        ),
      );
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
              content: Text('Could not create guided intake draft.\n$error')),
        );
      }
      return null;
    }
  }

  Future<ProjectFactoryInitJob?> _startOrResumeProjectFactoryInit({
    required ApiClient client,
    required ProjectFactoryDraft draft,
    required SessionDetail session,
  }) {
    return _startOrResumeProjectFactoryInitForDraft(
      client: client,
      draftId: draft.draftId,
      sessionId: session.id,
    );
  }

  Future<ProjectFactoryInitJob?> _startOrResumeProjectFactoryInitForDraft({
    required ApiClient client,
    required String draftId,
    required String sessionId,
  }) async {
    setState(() {
      _loadingProjectFactoryInitSessions.add(sessionId);
      _projectFactoryInitErrorText = null;
    });
    try {
      final initJob = await client.startProjectFactoryInit(
        draftId: draftId,
        chatSessionId: sessionId,
      );
      if (!mounted) {
        return initJob;
      }
      setState(() {
        _projectFactoryInitBySession[sessionId] = initJob;
        _loadingProjectFactoryInitSessions.remove(sessionId);
      });
      return initJob;
    } catch (error) {
      if (!mounted) {
        return null;
      }
      setState(() {
        _loadingProjectFactoryInitSessions.remove(sessionId);
        _projectFactoryInitErrorText =
            'Could not start deterministic init. $error';
      });
      return null;
    }
  }

  Future<void> _answerProjectFactoryGuidedIntake(
    String sessionId,
    String questionId,
    Object? value,
  ) async {
    final draftId = _projectFactoryDraftIdBySession[sessionId];
    if (draftId == null) {
      return;
    }
    setState(() {
      _loadingProjectFactoryIntakeSessions.add(sessionId);
      _projectFactoryGuidedIntakeErrorText = null;
    });
    try {
      var intake =
          await _projectFactoryClient().answerProjectFactoryGuidedIntake(
        draftId: draftId,
        questionId: questionId,
        value: value,
      );
      if (intake.readyForConfirmation) {
        intake =
            await _projectFactoryClient().previewProjectFactoryGuidedIntake(
          draftId,
        );
      }
      if (!mounted) {
        return;
      }
      setState(() {
        _projectFactoryGuidedIntakeBySession[sessionId] = intake;
        _loadingProjectFactoryIntakeSessions.remove(sessionId);
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _loadingProjectFactoryIntakeSessions.remove(sessionId);
        _projectFactoryGuidedIntakeErrorText =
            'Could not save guided intake answer. $error';
      });
    }
  }

  Future<void> _previewProjectFactoryGuidedIntake(String sessionId) async {
    final draftId = _projectFactoryDraftIdBySession[sessionId];
    if (draftId == null) {
      return;
    }
    setState(() {
      _loadingProjectFactoryIntakeSessions.add(sessionId);
      _projectFactoryGuidedIntakeErrorText = null;
    });
    try {
      final intake =
          await _projectFactoryClient().previewProjectFactoryGuidedIntake(
        draftId,
      );
      if (!mounted) {
        return;
      }
      setState(() {
        _projectFactoryGuidedIntakeBySession[sessionId] = intake;
        _loadingProjectFactoryIntakeSessions.remove(sessionId);
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _loadingProjectFactoryIntakeSessions.remove(sessionId);
        _projectFactoryGuidedIntakeErrorText =
            'Could not preview guided intake contract. $error';
      });
    }
  }

  bool _projectFactoryGuidedIntakeAllowsBuild(String sessionId) {
    return _projectFactoryGuidedIntakeBySession[sessionId]?.buildAllowed ==
        true;
  }

  Future<void> _openProjectFactoryHistory() async {
    final activeBaseUrl = _activeServer?.baseUrl ?? widget.initialApiBaseUrl;
    final client = ApiClient(baseUrl: activeBaseUrl);
    await showDialog<void>(
      context: context,
      builder: (context) => ProjectFactoryHistoryDialog(
        listJobs: () => client.listProjectFactoryJobs(),
        getJob: client.getProjectFactoryJob,
        onOpenProjectPath: (path) async {
          await _openProjectFactoryTargetPath(path);
        },
        listWebPreviews: () => client.listWebPreviews(),
        listWebPreviewInvites: client.listWebPreviewInvites,
        createWebPreviewInvite: client.createWebPreviewInvite,
        resendWebPreviewInvite: client.resendWebPreviewInvite,
        expireWebPreviewInvite: client.expireWebPreviewInvite,
        revokeWebPreviewInvite: client.revokeWebPreviewInvite,
        syncWebPreviewInvite: client.syncWebPreviewInvite,
        disableWebPreview: ({required previewId, ttlSeconds, reason}) =>
            client.disableWebPreview(previewId: previewId, reason: reason),
        expireWebPreview: ({required previewId, ttlSeconds, reason}) =>
            client.expireWebPreview(previewId: previewId, reason: reason),
        extendWebPreview: ({required previewId, ttlSeconds, reason}) =>
            client.extendWebPreview(
          previewId: previewId,
          ttlSeconds: ttlSeconds,
          reason: reason,
        ),
      ),
    );
  }

  Future<bool> _maybeActivateProjectFactoryBuildMode(String? message) async {
    if (!isProjectFactoryBuildConfirmation(message)) {
      return true;
    }
    final session = _chatController.currentSession;
    if (!isProjectFactoryIntakeConfiguration(session?.agentConfiguration)) {
      return true;
    }
    if (!projectFactoryHasBuildReadyMarker(session!.messages) &&
        !_projectFactoryGuidedIntakeAllowsBuild(session.id)) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'New project is still collecting specs and diagram details.',
          ),
        ),
      );
      return true;
    }

    final didConfigure = await _chatController.updateAgentConfiguration(
      buildProjectFactoryBuildConfiguration(session.agentConfiguration),
    );
    if (!mounted) {
      return didConfigure;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          didConfigure
              ? 'New project build mode enabled: reviewer will run after each generator pass.'
              : _chatController.errorText ??
                  'Could not enable New project build mode.',
        ),
      ),
    );
    return didConfigure;
  }

  // Legacy kickoff prompt kept until Plan 7 replaces it with init context packs.
  // ignore: unused_element
  String _projectFactoryKickoffPrompt(ProjectFactoryOptions options) {
    final workflow = options.creationWorkflow;
    final generatorRuns = workflow['generator_runs'] ?? 20;
    final reviewerRuns = workflow['reviewer_runs'] ?? 20;
    final platforms = options.defaultPlatforms.join(', ');
    final businessTypes = options.businessTypes.join(', ');
    final frontendStrategies = options.frontendStrategies
        .map((strategy) => strategy['id'] as String? ?? '')
        .where((id) => id.isNotEmpty)
        .join(', ');
    return '''
Estamos en modo New Project Factory dentro de un chat normal.

Primero respondeme al usuario, no generes archivos todavia. Tu primera respuesta debe explicar: "vamos a hacer un nuevo proyecto" y pedir lo minimo necesario para inferir o confirmar:
- nombre del proyecto;
- business type/rubro;
- primary goal;
- plataformas;
- backend;
- logo/icono;
- colores, estilo visual y referencias de look and feel;
- roles/permisos especiales si aplican;
- emails iniciales de administradores para enviar invites de Web Preview;
- entidades principales del dominio para DER/ERD;
- actores y permisos principales para diagrama de clases/componentes;
- integraciones externas esperadas para componentes/deployment;
- si hay imagenes adjuntas en este chat, usalas como referencia visual nativa.

Defaults si el usuario no modifica nada:
- plataformas: $platforms;
- backend: ${options.defaultBackend};
- frontendStrategy: ${options.defaultFrontendStrategy};
- frontend strategies soportadas: ${frontendStrategies.isEmpty ? 'flutter, svelte' : frontendStrategies};
- logo: generate;
- roles base: owner, admin, manager, staff, customer, guest;
- auth: login/registro + Google pending credentials;
- admin/domain management: incluido;
- notificaciones: incluido;
- workflow al confirmar: $generatorRuns generator passes y $reviewerRuns reviewer passes; cada generator pass va seguido inmediatamente por su reviewer pass antes del siguiente generator.
- business types sugeridos si necesita elegir: $businessTypes.
- first release default: Initial Preview Release, no produccion.
- admin emails iniciales: requeridos antes del marker build-ready; si faltan, preguntalos y no avances.
- flutter soporta APK preview, Workbench en APK y registro Bridge.
- svelte es web-first sobre Cloudflare Worker/D1; no prometas APK ni Bridge installable si no hay wrapper explicito.

Si el usuario no sabe el nombre, rubro o titulo, proponelo a partir de lo que cuente. Para colores y look and feel no inventes como definitivo: preguntale o propone 2-3 direcciones y espera confirmacion. Antes de crear nada, devolve un preview corto del proyecto que vas a armar y pedi confirmacion explicita tipo "ok, dale para adelante".

Contrato semi-obligatorio antes del build:
- Trabaja como intake guiado con estados: collecting, ready_for_review, changes_requested, confirmed, build_started o blocked.
- Si falta informacion para armar spec, plan, tasks, release, assets o diagramas baseline, hace una o pocas preguntas concretas.
- Cada pregunta debe traer 2-4 respuestas sugeridas, marcar recomendada cuando aplique y permitir una opcion tipo "lo inferis vos".
- Para cada respuesta, deja claro si es user, inferred, default, asset, prior_context o system y si la confianza es low, medium o high.
- Los diagramas baseline a validar son: componentes, clases, DER/ERD y deployment. Agrega otros si el dominio lo pide.
- El preview previo al build debe incluir: brief normalizado, slug, business type, objetivo, plataformas, backend, entidades del dominio, roles/permisos, admin emails iniciales, assets/logo/icono, Workbench/SDD, defaults asumidos, blockers externos, riesgos, validacion y que hara generator/reviewer.
- En release/runtime profile, describi el Initial Preview Release por defecto: URL `https://preview.nienfos.com/<slug>`, API real `https://preview.nienfos.com/<slug>/api`, runtime profile `preview`, API runtime `cloudflare_preview`, persistencia Cloudflare D1, invite emails/admin links, expiracion/default TTL, delivery provider o manual-link fallback, APK `android-preview-v*`, Bridge registration en Codex Mobile Apps, checks de health/smoke/APK/Bridge, produccion pendiente/no solicitada y mock/demo solamente si el usuario lo pide explicitamente.
- Persisti el contrato en la conversacion: cuando cambie algo, muestra una version resumida del contrato y los pendientes.
- No incluyas la linea $kProjectFactoryReadyForBuildMarker hasta que el contrato este ready_for_review y el usuario haya validado explicitamente ese preview.
- Si el usuario pide construir antes de readiness, responde solo con las preguntas o blockers minimos que faltan.
- Cuando ya este validado y solo falte que el usuario confirme el arranque, termina tu respuesta con una linea exacta: $kProjectFactoryReadyForBuildMarker

Durante intake el reviewer esta apagado a proposito. Cuando el usuario confirme despues de ese marker, recien ahi ejecuta la creacion real usando Project Factory del bridge y el repo actual: draft/manifest, reference assets desde imagenes adjuntas del chat cuando existan, specs/plan/tasks, diagramas baseline, backend FastAPI, Flutter, auth/RBAC/admin/notificaciones, validacion y apertura del workspace. Mantene la conversacion practica y anda trabajando con el reviewer durante el build.
''';
  }

  // Kept for the Project Factory history/fallback dialog.
  // ignore: unused_element
  Future<Workspace> _openProjectFactoryTargetPath(String targetPath) async {
    await _chatController.refreshWorkspaces();
    final workspace = _chatController.workspaces.firstWhere(
      (item) => item.path == targetPath,
      orElse: () =>
          Workspace(name: _fallbackWorkspaceName(targetPath), path: targetPath),
    );
    await _pinWorkspaceToSidebar(workspace);
    await _createNewChatForWorkspace(workspace);
    return workspace;
  }

  Future<void> _openWorkspacePicker() async {
    if (_isOpeningWorkspacePicker) {
      return;
    }

    setState(() {
      _isOpeningWorkspacePicker = true;
    });

    Object? agentProfilesError;
    try {
      if (_chatController.workspaces.isEmpty) {
        await _chatController.refreshWorkspaces();
      }
      if (_chatController.agentProfiles.isEmpty) {
        try {
          await _chatController.refreshAgentProfiles();
        } catch (error) {
          agentProfilesError = error;
        }
      }
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Could not load projects for a new chat.\n$error'),
        ),
      );
      return;
    } finally {
      if (mounted) {
        setState(() {
          _isOpeningWorkspacePicker = false;
        });
      }
    }
    if (!mounted) {
      return;
    }

    if (_chatController.workspaces.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'No projects were found on this server. Add folders under PROJECTS_ROOT first.',
          ),
        ),
      );
      return;
    }

    if (agentProfilesError != null && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'Agent profiles are unavailable. Using the built-in Generator profile for this new chat.\n$agentProfilesError',
          ),
        ),
      );
    }

    final draft = await _showNewChatPicker();

    if (draft != null) {
      await _pinWorkspaceToSidebar(draft.workspace);
      await _createNewChatForWorkspace(
        draft.workspace,
        agentProfileId: draft.agentProfile.id,
        turnSummariesEnabled: draft.turnSummariesEnabled,
      );
    }
  }

  Future<_NewChatDraft?> _showNewChatPicker() {
    final availableProfiles = _chatController.agentProfiles.isNotEmpty
        ? _chatController.agentProfiles
        : <AgentProfile>[_fallbackAgentProfile()];
    final sheet = _NewChatSheet(
      workspaces: _chatController.workspaces,
      agentProfiles: availableProfiles,
      pinnedWorkspacePaths:
          _sidebarWorkspaces.map((workspace) => workspace.path).toSet(),
    );

    final prefersDialog = kIsWeb || MediaQuery.sizeOf(context).width >= 900;
    if (prefersDialog) {
      return showDialog<_NewChatDraft>(
        context: context,
        builder: (context) {
          return Dialog(
            backgroundColor: const Color(0xFF101931),
            insetPadding: const EdgeInsets.symmetric(
              horizontal: 24,
              vertical: 24,
            ),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 720, maxHeight: 760),
              child: sheet,
            ),
          );
        },
      );
    }

    return showModalBottomSheet<_NewChatDraft>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      backgroundColor: const Color(0xFF101931),
      constraints: BoxConstraints(
        maxWidth: 720,
        maxHeight: MediaQuery.sizeOf(context).height * 0.82,
      ),
      builder: (context) => sheet,
    );
  }

  Future<void> _createNewChatForWorkspace(
    Workspace workspace, {
    String? agentProfileId,
    bool turnSummariesEnabled = false,
  }) async {
    await _chatController.createNewSessionWithProfile(
      workspacePath: workspace.path,
      agentProfileId: agentProfileId,
      turnSummariesEnabled: turnSummariesEnabled,
    );
    if (!mounted) {
      return;
    }

    final errorText = _chatController.errorText;
    if (errorText != null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'Could not start a chat for ${workspace.name}.\n$errorText',
          ),
          duration: const Duration(seconds: 4),
        ),
      );
    }
  }

  Future<void> _openRenameChatSheet(ChatSessionSummary session) async {
    final draft = await showModalBottomSheet<_RenameChatDraft>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      backgroundColor: const Color(0xFF101931),
      constraints: BoxConstraints(
        maxWidth: 640,
        maxHeight: MediaQuery.sizeOf(context).height * 0.86,
      ),
      builder: (context) => _RenameChatSheet(
        initialTitle: session.title,
        voiceEnabled: _resolvedAudioInputEnabled(),
        voiceStatusText: _resolveVoiceStatusText(),
        audioRecorderFactory:
            widget.audioRecorderFactoryOverride ?? AudioNoteRecorder.new,
        onBeginRecording: _handleBeginRecording,
      ),
    );

    if (!mounted || draft == null) {
      return;
    }

    var didUpdate = false;
    try {
      switch (draft.kind) {
        case _RenameChatDraftKind.manual:
          didUpdate = await _chatController.renameSession(
            session.id,
            title: draft.title!,
          );
          break;
        case _RenameChatDraftKind.generatedText:
          didUpdate = await _chatController.generateSessionTitle(
            session.id,
            instructions: draft.instructions,
          );
          break;
        case _RenameChatDraftKind.generatedAudio:
          didUpdate = await _chatController.generateSessionTitleFromAudio(
            session.id,
            draft.audioFile!,
            instructions: draft.instructions,
          );
          break;
      }
    } finally {
      final audioFile = draft.audioFile;
      if (audioFile != null) {
        final recorder =
            widget.audioRecorderFactoryOverride?.call() ?? AudioNoteRecorder();
        await recorder.cleanup(audioFile);
        await recorder.dispose();
      }
    }

    if (!mounted) {
      return;
    }
    final errorText = _chatController.errorText;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          didUpdate
              ? 'Chat renamed.'
              : 'Could not rename chat.${errorText == null ? '' : '\n$errorText'}',
        ),
        duration: const Duration(seconds: 3),
      ),
    );
  }

  Future<void> _openSaveCurrentAgentProfile() async {
    final currentSession = _chatController.currentSession;
    if (currentSession == null) {
      return;
    }

    final generator = currentSession.agentConfiguration.byId(AgentId.generator);
    if (generator == null) {
      return;
    }

    final draft = await showModalBottomSheet<_SaveAgentProfileDraft>(
      context: context,
      isScrollControlled: true,
      backgroundColor: const Color(0xFF101931),
      builder: (context) => _SaveAgentProfileSheet(
        initialName: generator.label,
        initialColorHex: currentSession.agentProfileColor,
      ),
    );

    if (draft == null) {
      return;
    }

    final profile = await _chatController.createAgentProfile(
      name: draft.name,
      description: draft.description,
      colorHex: draft.colorHex,
      configuration: currentSession.agentConfiguration,
    );
    if (!mounted || profile == null) {
      return;
    }

    await _chatController.applyAgentProfile(profile.id);
    if (!mounted) {
      return;
    }

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('Saved ${profile.name} for future chats.')),
    );
  }

  Future<void> _pinWorkspaceToSidebar(Workspace workspace) async {
    final alreadyPinned = _sidebarWorkspaces.any(
      (item) => item.path == workspace.path,
    );
    if (alreadyPinned) {
      return;
    }

    final updatedWorkspaces = <Workspace>[..._sidebarWorkspaces, workspace];
    setState(() {
      _sidebarWorkspaces = updatedWorkspaces;
    });

    final activeBaseUrl = _activeServer?.baseUrl ?? widget.initialApiBaseUrl;
    await _serverProfileStore.saveSidebarWorkspaces(
      activeBaseUrl,
      updatedWorkspaces,
    );
  }

  Future<void> _removeWorkspaceFromSidebar(Workspace workspace) async {
    final updatedWorkspaces = _sidebarWorkspaces
        .where((item) => item.path != workspace.path)
        .toList(growable: false);
    if (updatedWorkspaces.length == _sidebarWorkspaces.length) {
      return;
    }

    setState(() {
      _sidebarWorkspaces = updatedWorkspaces;
    });

    final activeBaseUrl = _activeServer?.baseUrl ?? widget.initialApiBaseUrl;
    await _serverProfileStore.saveSidebarWorkspaces(
      activeBaseUrl,
      updatedWorkspaces,
    );
  }

  Future<void> _initializeServerProfiles() async {
    final profiles = await _serverProfileStore.loadProfiles(
      defaultBaseUrl: widget.initialApiBaseUrl,
    );
    final activeProfileId = await _serverProfileStore.loadActiveProfileId();
    final sidebarExpanded = await _serverProfileStore.loadSidebarExpanded();
    final audioRepliesEnabled = await _serverProfileStore
        .loadAudioRepliesEnabled(widget.initialApiBaseUrl);
    final audioReplyPlaybackSpeed = await _serverProfileStore
        .loadAudioReplyPlaybackSpeed(widget.initialApiBaseUrl);
    final resolvedActiveProfile = profiles.firstWhere(
      (profile) => profile.id == activeProfileId,
      orElse: () => profiles.first,
    );

    setState(() {
      _serverProfiles = profiles;
      _activeServer = resolvedActiveProfile;
      _activeServerHealth = null;
      _sidebarExpanded = sidebarExpanded;
      _audioRepliesEnabled = audioRepliesEnabled;
      _audioReplyPlaybackSpeed = audioReplyPlaybackSpeed;
    });
    await _replyPlaybackService.setPlaybackSpeed(audioReplyPlaybackSpeed);

    final didConnect = await _switchToServer(
      resolvedActiveProfile,
      initialize: true,
    );
    if (didConnect) {
      return;
    }

    final localProfile = profiles.firstWhere(
      (profile) => profile.id == 'default-server',
      orElse: () => ServerProfile(
        id: 'default-server',
        name: 'Local',
        baseUrl: widget.initialApiBaseUrl,
      ),
    );
    if (localProfile.baseUrl == resolvedActiveProfile.baseUrl) {
      return;
    }

    await _switchToServer(localProfile, initialize: true);
  }

  Future<bool> _switchToServer(
    ServerProfile profile, {
    bool initialize = false,
  }) async {
    final client = ApiClient(baseUrl: profile.baseUrl);
    final nextController = ChatController(
      apiClient: client,
      notificationService: widget.notificationService,
    );
    final sidebarWorkspaces = await _serverProfileStore.loadSidebarWorkspaces(
      profile.baseUrl,
    );
    final sessionReadMarkers = await _serverProfileStore.loadSessionReadMarkers(
      profile.baseUrl,
    );
    final audioRepliesEnabled =
        await _serverProfileStore.loadAudioRepliesEnabled(profile.baseUrl);
    final audioReplyPlaybackSpeed =
        await _serverProfileStore.loadAudioReplyPlaybackSpeed(profile.baseUrl);
    nextController.addListener(_handleChatControllerChanged);

    final previousController = _chatController;
    await _replyPlaybackService.setServer(client);
    await _replyPlaybackService.setPlaybackSpeed(audioReplyPlaybackSpeed);
    setState(() {
      _chatController = nextController;
      _activeServer = profile;
      _activeServerHealth = null;
      _activeServerCapabilities = null;
      _activeCodexTooling = null;
      _sidebarWorkspaces = sidebarWorkspaces;
      _visibleSessionLimitsByGroup.clear();
      _sessionReadMarkers = sessionReadMarkers;
      _serverErrorText = null;
      _codexToolingErrorText = null;
      _audioRepliesEnabled = audioRepliesEnabled;
      _audioReplyPlaybackSpeed = audioReplyPlaybackSpeed;
      _isLoadingCodexTooling = true;
    });
    widget.onActiveServerBaseUrlChanged?.call(profile.baseUrl);
    _lastObservedSessionId = null;
    _updateStickToBottom(true);
    await _serverProfileStore.saveActiveProfileId(profile.id);

    var didConnect = false;
    try {
      final healthFuture = client.getHealth();
      final capabilitiesFuture = client.getCapabilities();
      final initializeFuture = _chatController.initialize();
      final health = await healthFuture;
      final capabilities = await capabilitiesFuture;
      await initializeFuture;
      CodexToolingSnapshot? codexTooling;
      String? codexToolingErrorText;
      try {
        codexTooling = await client.getCodexTooling(
          workspacePath: _chatController.currentSession?.workspacePath,
        );
      } catch (error) {
        codexToolingErrorText =
            'Codex tooling is unavailable on this backend.\n$error';
      }
      if (mounted) {
        setState(() {
          _activeServerHealth = health;
          _activeServerCapabilities = capabilities;
          _activeCodexTooling = codexTooling;
          _codexToolingErrorText = codexToolingErrorText;
          _isLoadingCodexTooling = false;
        });
      }
      _replyPlaybackService.setCapabilities(capabilities);
      didConnect = true;
    } catch (error) {
      _replyPlaybackService.setCapabilities(null);
      setState(() {
        _activeServerHealth = null;
        _activeServerCapabilities = null;
        _activeCodexTooling = null;
        _serverErrorText = 'Failed to connect to ${profile.name}.\n$error';
        _codexToolingErrorText = null;
        _isLoadingCodexTooling = false;
      });
    }

    if (!identical(previousController, nextController)) {
      previousController
        ..removeListener(_handleChatControllerChanged)
        ..dispose();
    }
    return didConnect;
  }

  Future<void> _refreshCodexTooling({bool showLoading = false}) async {
    final activeServer = _activeServer;
    if (activeServer == null) {
      return;
    }

    if (showLoading && mounted) {
      setState(() {
        _isLoadingCodexTooling = true;
        _codexToolingErrorText = null;
      });
    }

    try {
      final snapshot =
          await ApiClient(baseUrl: activeServer.baseUrl).getCodexTooling(
        workspacePath: _chatController.currentSession?.workspacePath,
      );
      if (!mounted) {
        return;
      }
      setState(() {
        _activeCodexTooling = snapshot;
        _codexToolingErrorText = null;
        _isLoadingCodexTooling = false;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _activeCodexTooling = null;
        _codexToolingErrorText =
            'Codex tooling is unavailable on this backend.\n$error';
        _isLoadingCodexTooling = false;
      });
    }
  }

  Future<void> _openInstallableAppsSheet() async {
    final activeServer = _activeServer;
    if (activeServer == null) {
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('No active bridge server.')));
      return;
    }
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (context) => FractionallySizedBox(
        heightFactor: 0.82,
        child: InstallableAppsSheet(
          apiClient: ApiClient(baseUrl: activeServer.baseUrl),
        ),
      ),
    );
  }

  Future<CodexToolingSnapshot?> _installCodexMcpApp(CodexMcpApp app) async {
    if (widget.codexMcpAppInstallerOverride != null) {
      final snapshot = await widget.codexMcpAppInstallerOverride!(app);
      if (mounted) {
        setState(() {
          _activeCodexTooling = snapshot;
          _codexToolingErrorText = null;
        });
      }
      return snapshot;
    }
    final activeServer = _activeServer;
    if (activeServer == null) {
      return _activeCodexTooling;
    }

    final client = ApiClient(baseUrl: activeServer.baseUrl);
    await client.installCodexMcpApp(app.appId);
    final snapshot = await client.getCodexTooling(
      workspacePath: _chatController.currentSession?.workspacePath,
    );
    if (mounted) {
      setState(() {
        _activeCodexTooling = snapshot;
        _codexToolingErrorText = null;
      });
    }
    return snapshot;
  }

  Future<void> _openMcpAppHost(CodexMcpApp app, {String? focusHint}) async {
    if (!mounted) {
      return;
    }
    final apps = _activeCodexTooling?.mcpApps ?? <CodexMcpApp>[app];
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        fullscreenDialog: true,
        builder: (context) => _McpAppHostScreen(
          apps: apps,
          initialAppId: app.appId,
          focusHint: focusHint,
        ),
      ),
    );
  }

  Future<bool> _maybeHandleOpenMcpAppCommand(String rawMessage) async {
    if ((_activeCodexTooling?.mcpApps.isEmpty ?? true) &&
        _activeServer != null) {
      await _refreshCodexTooling(showLoading: false);
    }
    final request = _matchMcpAppOpenCommand(rawMessage, _activeCodexTooling);
    if (request == null) {
      return false;
    }
    await _openMcpAppHost(request.app, focusHint: request.focusHint);
    if (!mounted) {
      return true;
    }
    _textController.clear();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Opened ${request.app.name}.'),
        duration: const Duration(seconds: 1),
      ),
    );
    return true;
  }

  AgentProfile _fallbackAgentProfile() {
    return const AgentProfile(
      id: 'default',
      name: 'Generator',
      description: 'Default implementation agent for general coding work.',
      colorHex: '#55D6BE',
      prompt:
          'You are the primary implementation Codex. Continue the task directly, produce concrete progress, and keep the output practical.',
      configuration: kDefaultAgentConfiguration,
      isBuiltin: true,
    );
  }

  Future<void> _openAgentStudio() async {
    final currentSession = _chatController.currentSession;
    if (currentSession == null) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Open or create a chat before configuring agents.'),
        ),
      );
      return;
    }

    final draft = await showModalBottomSheet<_AgentStudioDraft>(
      context: context,
      isScrollControlled: true,
      backgroundColor: const Color(0xFF101931),
      builder: (context) {
        return _AgentStudioSheet(session: currentSession);
      },
    );

    if (draft == null) {
      return;
    }

    final didUpdate = await _chatController.updateAgentStudioSettings(
      configuration: draft.configuration,
      turnSummariesEnabled: draft.turnSummariesEnabled,
    );
    if (!mounted || didUpdate) {
      return;
    }

    final errorText =
        _chatController.errorText ?? 'Failed to save agent settings.';
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(errorText)));
  }

  Future<void> _openReplyModePicker() async {
    await showModalBottomSheet<void>(
      context: context,
      backgroundColor: const Color(0xFF101931),
      builder: (context) {
        var sheetAudioRepliesEnabled = _audioRepliesEnabled;
        var sheetPlaybackSpeed = _audioReplyPlaybackSpeed;
        return StatefulBuilder(
          builder: (context, setSheetState) {
            return SafeArea(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  const ListTile(
                    title: Text('Reply mode'),
                    subtitle: Text(
                      'Choose whether assistant replies stay as text or are spoken aloud',
                    ),
                  ),
                  ListTile(
                    leading: Icon(
                      sheetAudioRepliesEnabled
                          ? Icons.radio_button_unchecked_rounded
                          : Icons.radio_button_checked_rounded,
                    ),
                    title: const Text('Text replies'),
                    subtitle: const Text('Keep assistant responses silent'),
                    onTap: () async {
                      await _setAudioRepliesEnabled(false);
                      setSheetState(() {
                        sheetAudioRepliesEnabled = false;
                      });
                    },
                  ),
                  ListTile(
                    leading: Icon(
                      sheetAudioRepliesEnabled
                          ? Icons.radio_button_checked_rounded
                          : Icons.radio_button_unchecked_rounded,
                    ),
                    title: const Text('Audio replies'),
                    subtitle: Text(
                      'Speak assistant responses at ${_formatPlaybackSpeed(sheetPlaybackSpeed)}',
                    ),
                    onTap: () async {
                      await _setAudioRepliesEnabled(true);
                      setSheetState(() {
                        sheetAudioRepliesEnabled = true;
                      });
                    },
                  ),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 4, 16, 20),
                    child: Align(
                      alignment: Alignment.centerLeft,
                      child: Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: _audioReplyPlaybackSpeeds.map((speed) {
                          final selected =
                              (sheetPlaybackSpeed - speed).abs() < 0.01;
                          return ChoiceChip(
                            label: Text(_formatPlaybackSpeed(speed)),
                            selected: selected,
                            onSelected: (_) async {
                              await _setAudioReplyPlaybackSpeed(speed);
                              setSheetState(() {
                                sheetPlaybackSpeed = speed;
                              });
                            },
                          );
                        }).toList(),
                      ),
                    ),
                  ),
                ],
              ),
            );
          },
        );
      },
    );
  }

  Future<void> _setAudioRepliesEnabled(bool nextValue) async {
    if (nextValue == _audioRepliesEnabled) {
      return;
    }

    final activeBaseUrl = _activeServer?.baseUrl ?? widget.initialApiBaseUrl;
    await _serverProfileStore.saveAudioRepliesEnabled(activeBaseUrl, nextValue);
    if (!mounted) {
      return;
    }

    if (nextValue) {
      final currentSession = _chatController.currentSession;
      if (currentSession != null) {
        _replyPlaybackService.seedSession(currentSession);
      }
    } else {
      await _replyPlaybackService.stop();
    }

    setState(() {
      _audioRepliesEnabled = nextValue;
    });
  }

  Future<void> _setAudioReplyPlaybackSpeed(double speed) async {
    final normalizedSpeed = _normalizeAudioReplyPlaybackSpeed(speed);
    if ((normalizedSpeed - _audioReplyPlaybackSpeed).abs() < 0.01) {
      return;
    }

    final activeBaseUrl = _activeServer?.baseUrl ?? widget.initialApiBaseUrl;
    await _serverProfileStore.saveAudioReplyPlaybackSpeed(
      activeBaseUrl,
      normalizedSpeed,
    );
    await _replyPlaybackService.setPlaybackSpeed(normalizedSpeed);
    if (!mounted) {
      return;
    }

    setState(() {
      _audioReplyPlaybackSpeed = normalizedSpeed;
    });
  }

  double _normalizeAudioReplyPlaybackSpeed(double speed) {
    return _audioReplyPlaybackSpeeds.reduce((closest, candidate) {
      final closestDistance = (closest - speed).abs();
      final candidateDistance = (candidate - speed).abs();
      return candidateDistance < closestDistance ? candidate : closest;
    });
  }

  String _formatPlaybackSpeed(double speed) {
    if (speed == speed.roundToDouble()) {
      return '${speed.toInt()}x';
    }
    return '${speed.toStringAsFixed(2).replaceFirst(RegExp(r'0$'), '')}x';
  }

  Future<void> _handleBeginRecording() async {
    await _replyPlaybackService.handleBeginRecording();
  }

  Future<void> _openServerManager() async {
    final result = await showModalBottomSheet<ServerProfile>(
      context: context,
      backgroundColor: const Color(0xFF101931),
      isScrollControlled: true,
      builder: (context) => _ServerManagerSheet(
        profiles: _serverProfiles,
        activeProfileId: _activeServer?.id,
        onAddServer: _addServerProfile,
      ),
    );

    if (result != null &&
        (_activeServer == null || result.id != _activeServer!.id)) {
      await _switchToServer(result);
    }
  }

  Future<void> _toggleSidebarExpanded() async {
    final nextValue = !_sidebarExpanded;
    setState(() {
      _sidebarExpanded = nextValue;
    });
    await _serverProfileStore.saveSidebarExpanded(nextValue);
  }

  Future<ServerProfile?> _addServerProfile(String name, String baseUrl) async {
    final normalizedBaseUrl = baseUrl.trim().replaceAll(RegExp(r'/$'), '');
    final client = ApiClient(baseUrl: normalizedBaseUrl);
    final health = await client.getHealth();
    final profile = ServerProfile(
      id: DateTime.now().microsecondsSinceEpoch.toString(),
      name: name.trim().isNotEmpty ? name.trim() : health.serverName,
      baseUrl: normalizedBaseUrl,
    );

    final existingIndex = _serverProfiles.indexWhere(
      (server) => server.baseUrl == normalizedBaseUrl,
    );
    final updatedProfiles = List<ServerProfile>.from(_serverProfiles);
    if (existingIndex >= 0) {
      updatedProfiles[existingIndex] = profile;
    } else {
      updatedProfiles.add(profile);
    }

    await _serverProfileStore.saveProfiles(updatedProfiles);
    setState(() {
      _serverProfiles = updatedProfiles;
    });

    return profile;
  }

  Widget _buildAppBarTitle({required bool isCompactAppBar}) {
    final currentSession = _chatController.currentSession;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Text(
          currentSession?.title ?? 'Codex Remote',
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
        const SizedBox(height: 2),
        Text(
          _buildAppBarSubtitle(isCompactAppBar: isCompactAppBar),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(fontSize: 12, color: Color(0xFF8B97B5)),
        ),
        if (!isCompactAppBar && currentSession != null) ...[
          const SizedBox(height: 6),
          _AgentProfilePill(
            label: currentSession.agentProfileName,
            color: _colorFromHex(currentSession.agentProfileColor),
          ),
        ],
      ],
    );
  }

  String _buildAppBarSubtitle({required bool isCompactAppBar}) {
    final segments = <String>[
      _activeServer != null
          ? 'Server: ${_activeServer!.name}'
          : 'Commands execute on your local machine',
    ];
    final currentSession = _chatController.currentSession;
    if (currentSession != null) {
      segments.add(currentSession.workspaceName);
      final statusLine = currentSession.conversationProduct?.statusLine.trim();
      if (statusLine != null && statusLine.isNotEmpty) {
        segments.add(statusLine);
      }
    }
    final usageLabel = _activeCodexTooling?.status.usageLabel?.trim();
    if (usageLabel != null && usageLabel.isNotEmpty) {
      segments.add(usageLabel);
    }
    if (!isCompactAppBar) {
      segments.add(_activeServer?.baseUrl ?? widget.initialApiBaseUrl);
      if (_activeServerHealth != null) {
        segments.add(
          _activeServerHealth!.audioTranscriptionReady
              ? 'Audio ready'
              : 'Audio unavailable',
        );
      }
    }
    return segments.join('  •  ');
  }

  List<Widget> _buildAppBarActions({required bool isCompactAppBar}) {
    final hasSummaryMessages = _summaryMessageCountForCurrentSession() > 0;
    final hasTurnSummaries = _turnSummaryCountForCurrentSession() > 0;
    final canShowAnySummary = hasSummaryMessages ||
        hasTurnSummaries ||
        (_chatController.currentSession?.turnSummariesEnabled ?? false);
    final showingSummaryView = _chatBodyView != _ChatBodyView.conversation;
    final primaryActions = <Widget>[
      AgentStudioStatusButton(
        session: _chatController.currentSession,
        onPressed: () async {
          await _openAgentStudio();
        },
      ),
      IconButton(
        onPressed: !showingSummaryView && !canShowAnySummary
            ? null
            : () {
                if (showingSummaryView) {
                  _setChatBodyView(_ChatBodyView.conversation);
                  return;
                }
                _setChatBodyView(_preferredSummaryView());
              },
        icon: Icon(
          showingSummaryView
              ? Icons.chat_bubble_outline_rounded
              : Icons.summarize_outlined,
        ),
        tooltip: showingSummaryView ? 'Show full chat' : 'View summary',
      ),
    ];
    if (isCompactAppBar) {
      primaryActions.add(
        PopupMenuButton<_AppBarOverflowAction>(
          tooltip: 'More actions',
          icon: const Icon(Icons.more_vert),
          onSelected: (action) {
            unawaited(_handleAppBarOverflowAction(action));
          },
          itemBuilder: (context) => <PopupMenuEntry<_AppBarOverflowAction>>[
            _buildAppBarOverflowMenuItem(
              action: _AppBarOverflowAction.apps,
              icon: Icons.apps_rounded,
              label: 'Apps',
            ),
            _buildAppBarOverflowMenuItem(
              action: _AppBarOverflowAction.conversationContext,
              icon: Icons.topic_outlined,
              label: 'What are we doing?',
            ),
            _buildAppBarOverflowMenuItem(
              action: _AppBarOverflowAction.summaryView,
              icon: showingSummaryView
                  ? Icons.chat_bubble_outline_rounded
                  : Icons.summarize_outlined,
              label: showingSummaryView ? 'Show full chat' : 'View summary',
              enabled: showingSummaryView ||
                  (_chatController.currentSession != null && canShowAnySummary),
            ),
            _buildAppBarOverflowMenuItem(
              action: _AppBarOverflowAction.codexTools,
              icon: Icons.tune_rounded,
              label: 'Codex tools',
            ),
            _buildAppBarOverflowMenuItem(
              action: _AppBarOverflowAction.saveCurrentAgent,
              icon: Icons.bookmark_add_outlined,
              label: 'Save current agent',
            ),
            _buildAppBarOverflowMenuItem(
              action: _AppBarOverflowAction.replyMode,
              icon: _audioRepliesEnabled
                  ? Icons.volume_up_rounded
                  : Icons.volume_mute_rounded,
              label: _audioRepliesEnabled
                  ? 'Audio replies ${_formatPlaybackSpeed(_audioReplyPlaybackSpeed)}'
                  : 'Text replies enabled',
            ),
            _buildAppBarOverflowMenuItem(
              action: _AppBarOverflowAction.servers,
              icon: Icons.computer,
              label: 'Servers',
            ),
            _buildAppBarOverflowMenuItem(
              action: _AppBarOverflowAction.newProject,
              icon: Icons.create_new_folder_outlined,
              label: 'New project',
            ),
            _buildAppBarOverflowMenuItem(
              action: _AppBarOverflowAction.domainFactory,
              icon: Icons.domain_add_outlined,
              label: 'Domain factory',
              enabled: _chatController.currentSession != null,
            ),
            _buildAppBarOverflowMenuItem(
              action: _AppBarOverflowAction.projectHistory,
              icon: Icons.history,
              label: 'Project history',
            ),
            _buildAppBarOverflowMenuItem(
              action: _AppBarOverflowAction.newChat,
              icon: Icons.add,
              label: 'Choose project for new chat',
            ),
          ],
        ),
      );
      return primaryActions;
    }
    return <Widget>[
      ...primaryActions,
      IconButton(
        onPressed: () async {
          await _openInstallableAppsSheet();
        },
        icon: const Icon(Icons.apps_rounded),
        tooltip: 'Apps',
      ),
      IconButton(
        onPressed: _chatController.currentSession == null
            ? null
            : () async {
                await _openConversationContextSheet();
              },
        icon: const Icon(Icons.topic_outlined),
        tooltip: 'What are we doing?',
      ),
      IconButton(
        onPressed: () async {
          await _openCodexToolsSheet();
        },
        icon: Stack(
          clipBehavior: Clip.none,
          children: <Widget>[
            const Icon(Icons.tune_rounded),
            if (_currentComposerDraft().codexRunOptions.skillIds.isNotEmpty ||
                _currentComposerDraft()
                    .codexRunOptions
                    .mcpServerIds
                    .isNotEmpty ||
                _currentComposerDraft().codexRunOptions.searchEnabled ||
                (_currentComposerDraft().codexRunOptions.profile?.isNotEmpty ??
                    false))
              Positioned(
                right: -6,
                top: -6,
                child: _MenuStatusBadge(
                  label: _codexSelectionCount(
                    _currentComposerDraft().codexRunOptions,
                  ).toString(),
                  backgroundColor: const Color(0xFF55D6BE),
                  foregroundColor: const Color(0xFF07131D),
                ),
              ),
          ],
        ),
        tooltip: 'Codex tools',
      ),
      IconButton(
        onPressed: () async {
          await _openSaveCurrentAgentProfile();
        },
        icon: const Icon(Icons.bookmark_add_outlined),
        tooltip: 'Save current agent',
      ),
      IconButton(
        onPressed: () async {
          await _openReplyModePicker();
        },
        icon: Icon(
          _audioRepliesEnabled
              ? Icons.volume_up_rounded
              : Icons.volume_mute_rounded,
        ),
        tooltip: _audioRepliesEnabled
            ? 'Audio replies enabled at ${_formatPlaybackSpeed(_audioReplyPlaybackSpeed)}'
            : 'Text replies enabled',
      ),
      IconButton(
        onPressed: () async {
          await _openServerManager();
        },
        icon: const Icon(Icons.computer),
        tooltip: 'Servers',
      ),
      IconButton(
        onPressed: () async {
          await _openNewProjectFactory();
        },
        icon: const Icon(Icons.create_new_folder_outlined),
        tooltip: 'New project',
      ),
      IconButton(
        onPressed: _chatController.currentSession == null
            ? null
            : () async {
                await _openDomainFactoryMode();
              },
        icon: const Icon(Icons.domain_add_outlined),
        tooltip: 'Domain factory',
      ),
      IconButton(
        onPressed: () async {
          await _openProjectFactoryHistory();
        },
        icon: const Icon(Icons.history),
        tooltip: 'Project history',
      ),
      IconButton(
        onPressed: () async {
          await _openWorkspacePicker();
        },
        icon: const Icon(Icons.add),
        tooltip: 'Choose project for new chat',
      ),
    ];
  }

  PopupMenuItem<_AppBarOverflowAction> _buildAppBarOverflowMenuItem({
    required _AppBarOverflowAction action,
    required IconData icon,
    required String label,
    bool enabled = true,
  }) {
    return PopupMenuItem<_AppBarOverflowAction>(
      value: action,
      enabled: enabled,
      child: Row(
        children: <Widget>[
          Icon(icon, size: 18),
          const SizedBox(width: 12),
          Expanded(child: Text(label, overflow: TextOverflow.ellipsis)),
        ],
      ),
    );
  }

  Future<void> _handleAppBarOverflowAction(_AppBarOverflowAction action) async {
    switch (action) {
      case _AppBarOverflowAction.apps:
        await _openInstallableAppsSheet();
        return;
      case _AppBarOverflowAction.conversationContext:
        await _openConversationContextSheet();
        return;
      case _AppBarOverflowAction.summaryView:
        if (_chatBodyView != _ChatBodyView.conversation) {
          _setChatBodyView(_ChatBodyView.conversation);
          return;
        }
        final currentSession = _chatController.currentSession;
        if (currentSession == null) {
          return;
        }
        final hasSummaryMessages = _summaryMessageCountForCurrentSession() > 0;
        final hasTurnSummaries = _turnSummaryCountForCurrentSession() > 0;
        if (!hasSummaryMessages &&
            !hasTurnSummaries &&
            !currentSession.turnSummariesEnabled) {
          return;
        }
        _setChatBodyView(_preferredSummaryView());
        return;
      case _AppBarOverflowAction.codexTools:
        await _openCodexToolsSheet();
        return;
      case _AppBarOverflowAction.saveCurrentAgent:
        await _openSaveCurrentAgentProfile();
        return;
      case _AppBarOverflowAction.replyMode:
        await _openReplyModePicker();
        return;
      case _AppBarOverflowAction.servers:
        await _openServerManager();
        return;
      case _AppBarOverflowAction.newProject:
        await _openNewProjectFactory();
        return;
      case _AppBarOverflowAction.domainFactory:
        await _openDomainFactoryMode();
        return;
      case _AppBarOverflowAction.projectHistory:
        await _openProjectFactoryHistory();
        return;
      case _AppBarOverflowAction.newChat:
        await _openWorkspacePicker();
        return;
    }
  }

  int _codexSelectionCount(CodexRunOptions options) {
    var count = 0;
    if (options.profile?.trim().isNotEmpty ?? false) {
      count += 1;
    }
    if (options.searchEnabled) {
      count += 1;
    }
    count += options.skillIds.length;
    count += options.mcpServerIds.length;
    if (options.configOverrides.isNotEmpty) {
      count += 1;
    }
    return count;
  }

  Future<void> _openCodexToolsSheet() async {
    await _refreshCodexTooling(showLoading: true);
    if (!mounted) {
      return;
    }

    final currentDraft = _currentComposerDraft();
    final currentSession = _chatController.currentSession;
    final result = await showModalBottomSheet<CodexRunOptions>(
      context: context,
      isScrollControlled: true,
      backgroundColor: const Color(0xFF101931),
      builder: (context) => _CodexToolsSheet(
        initialOptions: currentDraft.codexRunOptions,
        tooling: _activeCodexTooling,
        errorText: _codexToolingErrorText,
        loading: _isLoadingCodexTooling,
        agentProfileId: currentSession?.agentProfileId,
        agentProfileName: currentSession?.agentProfileName,
        onInstallApp: _installCodexMcpApp,
        onOpenApp: _openMcpAppHost,
      ),
    );
    if (result == null) {
      return;
    }

    _updateCurrentComposerDraft(
      _ComposerDraft(
        text: currentDraft.text,
        attachments: currentDraft.attachments,
        codexRunOptions: result,
      ),
    );
  }

  Future<void> _openConversationContextSheet() async {
    final session = _chatController.currentSession;
    final product = session?.conversationProduct;
    if (session == null || product == null) {
      return;
    }
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (context) {
        final maxSheetHeight = MediaQuery.sizeOf(context).height * 0.72;

        Widget buildSection(String label, String? value) {
          final trimmed = value?.trim();
          if (trimmed == null || trimmed.isEmpty) {
            return const SizedBox.shrink();
          }
          return Padding(
            padding: const EdgeInsets.only(bottom: 14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  label,
                  style: Theme.of(context).textTheme.labelLarge?.copyWith(
                        color: const Color(0xFF8B97B5),
                        fontWeight: FontWeight.w700,
                      ),
                ),
                const SizedBox(height: 4),
                Text(
                  trimmed,
                  style: const TextStyle(color: Colors.white, height: 1.35),
                ),
              ],
            ),
          );
        }

        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 8, 20, 20),
            child: ConstrainedBox(
              constraints: BoxConstraints(maxHeight: maxSheetHeight),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    session.title,
                    style: Theme.of(context).textTheme.titleLarge?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    product.statusLine,
                    style: const TextStyle(
                      color: Color(0xFF55D6BE),
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 16),
                  Flexible(
                    child: SingleChildScrollView(
                      key: const ValueKey<String>(
                        'conversation-context-scroll-view',
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          buildSection('Summary', product.description),
                          buildSection('Latest update', product.latestUpdate),
                          buildSection('Current focus', product.currentFocus),
                          buildSection('Next step', product.nextStep),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  ChatController _buildController(String baseUrl) {
    return ChatController(
      apiClient: ApiClient(baseUrl: baseUrl),
      notificationService: widget.notificationService,
    );
  }

  String _resolveVoiceStatusText() {
    if (!(_activeServerCapabilities?.supportsAudioInput ?? true)) {
      return 'This server does not currently accept audio input.';
    }

    final health = _activeServerHealth;
    if (health == null) {
      return 'Audio status unavailable.';
    }

    if (health.audioTranscriptionReady) {
      return 'Audio transcription ready via ${health.audioTranscriptionResolvedBackend}.';
    }

    return health.audioTranscriptionDetail ??
        'Audio transcription is not available on this server.';
  }

  bool _resolvedAudioInputEnabled() {
    final capabilities = _activeServerCapabilities;
    if (capabilities != null && !capabilities.supportsAudioInput) {
      return false;
    }
    return _activeServerHealth?.audioTranscriptionReady ?? true;
  }

  bool _resolvedFileAttachmentsEnabled() {
    final capabilities = _activeServerCapabilities;
    if (capabilities == null) {
      return true;
    }
    return capabilities.supportsAttachmentBatch ||
        capabilities.supportsDocumentInput;
  }

  _ComposerDraft _currentComposerDraft() {
    return _sessionDrafts[_draftKeyForSelectedSession()] ??
        const _ComposerDraft();
  }

  void _updateCurrentComposerDraft(_ComposerDraft draft) {
    final key = _draftKeyForSelectedSession();
    final previous = _sessionDrafts[key];
    final isUnchanged = previous?.text == draft.text &&
        _sameCodexRunOptions(
          previous?.codexRunOptions ?? const CodexRunOptions(),
          draft.codexRunOptions,
        ) &&
        _sameDraftAttachments(
          previous?.attachments ?? const <_PendingAttachmentDraft>[],
          draft.attachments,
        );
    if (isUnchanged) {
      return;
    }
    setState(() {
      if (draft.isEmpty) {
        _sessionDrafts.remove(key);
      } else {
        _sessionDrafts[key] = draft;
      }
    });
  }

  String _draftKeyForSelectedSession() {
    final sessionId = _chatController.selectedSessionId;
    if (sessionId != null && sessionId.isNotEmpty) {
      return 'session::$sessionId';
    }
    final serverBaseUrl = _activeServer?.baseUrl ?? widget.initialApiBaseUrl;
    final workspacePath = _chatController.currentSession?.workspacePath ?? '';
    return 'draft::$serverBaseUrl::$workspacePath';
  }

  bool _sameDraftAttachments(
    List<_PendingAttachmentDraft> left,
    List<_PendingAttachmentDraft> right,
  ) {
    if (identical(left, right)) {
      return true;
    }
    if (left.length != right.length) {
      return false;
    }
    for (var index = 0; index < left.length; index += 1) {
      if (left[index].identityKey != right[index].identityKey) {
        return false;
      }
    }
    return true;
  }

  bool _sameCodexRunOptions(CodexRunOptions left, CodexRunOptions right) {
    if (left.profile != right.profile ||
        left.searchEnabled != right.searchEnabled ||
        left.skillIds.length != right.skillIds.length ||
        left.mcpServerIds.length != right.mcpServerIds.length ||
        left.configOverrides.length != right.configOverrides.length) {
      return false;
    }
    for (var index = 0; index < left.skillIds.length; index += 1) {
      if (left.skillIds[index] != right.skillIds[index]) {
        return false;
      }
    }
    for (var index = 0; index < left.mcpServerIds.length; index += 1) {
      if (left.mcpServerIds[index] != right.mcpServerIds[index]) {
        return false;
      }
    }
    for (var index = 0; index < left.configOverrides.length; index += 1) {
      if (left.configOverrides[index] != right.configOverrides[index]) {
        return false;
      }
    }
    return true;
  }

  List<Widget> _buildSessionGroups({required bool archivedOnly}) {
    final groupedSessions = <String, List<ChatSessionSummary>>{};
    final sessionGroups = <Widget>[];

    for (final session in _chatController.sessions) {
      groupedSessions
          .putIfAbsent(session.workspacePath, () => <ChatSessionSummary>[])
          .add(session);
    }

    final visibleWorkspaces = <Workspace>[..._sidebarWorkspaces];
    final visibleWorkspacePaths =
        visibleWorkspaces.map((workspace) => workspace.path).toSet();
    final knownWorkspacePaths =
        _chatController.workspaces.map((workspace) => workspace.path).toSet();
    if (knownWorkspacePaths.isNotEmpty) {
      for (final workspacePath in groupedSessions.keys) {
        if (visibleWorkspacePaths.contains(workspacePath) ||
            knownWorkspacePaths.contains(workspacePath)) {
          continue;
        }
        visibleWorkspacePaths.add(workspacePath);
        visibleWorkspaces.add(
          Workspace(
            name: _fallbackWorkspaceName(workspacePath),
            path: workspacePath,
          ),
        );
      }
    }

    for (final workspace in visibleWorkspaces) {
      final sessions =
          groupedSessions[workspace.path] ?? <ChatSessionSummary>[];
      final visibleSessions = sessions
          .where(
            (session) =>
                archivedOnly ? session.isArchived : !session.isArchived,
          )
          .toList(growable: false)
        ..sort(_compareSessionSummariesByRecentActivity);
      final displayedSessionCount = _visibleSessionCountForGroup(
        workspace.path,
        archivedOnly: archivedOnly,
        sessions: visibleSessions,
      );
      final displayedSessions =
          visibleSessions.take(displayedSessionCount).toList(growable: false);
      final hiddenSessionCount = math.max(
        0,
        visibleSessions.length - displayedSessions.length,
      );
      if (archivedOnly && visibleSessions.isEmpty) {
        continue;
      }
      final hasSelected = visibleSessions.any(
        (session) => session.id == _chatController.selectedSessionId,
      );
      final activeJobCount = visibleSessions.fold(
        0,
        (total, session) =>
            total + _chatController.activeJobCountForSession(session.id),
      );
      final activeChatCount = visibleSessions
          .where(
            (session) =>
                _chatController.activeJobCountForSession(session.id) > 0,
          )
          .length;
      final outgoingUploadCount = visibleSessions.fold(
        0,
        (total, session) =>
            total +
            (_chatController
                    .outgoingUploadSummaryForSession(session.id)
                    ?.totalCount ??
                0),
      );
      final outgoingChatCount = visibleSessions
          .where(
            (session) =>
                _chatController.outgoingUploadSummaryForSession(session.id) !=
                null,
          )
          .length;
      final hasBackgroundActivity =
          activeJobCount > 0 || outgoingUploadCount > 0;
      final unreadChatsCount = visibleSessions
          .where((session) => _unreadCountForSession(session) > 0)
          .length;
      final projectCardColor =
          hasSelected ? const Color(0xFF16213C) : const Color(0xFF121A31);
      final projectBorderColor = activeJobCount > 0
          ? const Color(0x44FFC857)
          : outgoingUploadCount > 0
              ? const Color(0x333F5EF7)
              : unreadChatsCount > 0
                  ? const Color(0x3355D6BE)
                  : const Color(0xFF23304F);

      sessionGroups.add(
        Container(
          margin: const EdgeInsets.fromLTRB(10, 6, 10, 6),
          decoration: BoxDecoration(
            color: projectCardColor,
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: projectBorderColor),
          ),
          child: Material(
            type: MaterialType.transparency,
            child: Theme(
              data: Theme.of(
                context,
              ).copyWith(dividerColor: Colors.transparent),
              child: ExpansionTile(
                key: PageStorageKey<String>('workspace-${workspace.path}'),
                initiallyExpanded: hasSelected,
                tilePadding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 6,
                ),
                childrenPadding: const EdgeInsets.only(bottom: 10),
                iconColor: const Color(0xFF9AA8C8),
                collapsedIconColor: const Color(0xFF9AA8C8),
                title: Row(
                  children: <Widget>[
                    Container(
                      width: 38,
                      height: 38,
                      decoration: BoxDecoration(
                        color: activeJobCount > 0
                            ? const Color(0x33FFC857)
                            : outgoingUploadCount > 0
                                ? const Color(0x223F5EF7)
                                : const Color(0xFF1B2745),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      alignment: Alignment.center,
                      child: Icon(
                        Icons.folder_rounded,
                        color: activeJobCount > 0
                            ? const Color(0xFFFFC857)
                            : outgoingUploadCount > 0
                                ? const Color(0xFF8CA8FF)
                                : unreadChatsCount > 0
                                    ? const Color(0xFF55D6BE)
                                    : const Color(0xFF9AA8C8),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          Text(
                            workspace.name,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              color: activeJobCount > 0
                                  ? const Color(0xFFFFC857)
                                  : outgoingUploadCount > 0
                                      ? const Color(0xFFDCE5FF)
                                      : unreadChatsCount > 0
                                          ? const Color(0xFF55D6BE)
                                          : const Color(0xFFE7EEF9),
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            archivedOnly
                                ? '${workspace.path} • ${visibleSessions.length} archived chat${visibleSessions.length == 1 ? '' : 's'}'
                                : '${workspace.path} • ${visibleSessions.length} chat${visibleSessions.length == 1 ? '' : 's'}',
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              color: Color(0xFF8B97B5),
                              fontSize: 12,
                            ),
                          ),
                          const SizedBox(height: 6),
                          _ProjectStatusPill(
                            active: hasBackgroundActivity,
                            label: _formatProjectActivityLabel(
                              activeJobCount: activeJobCount,
                              activeChatCount: activeChatCount,
                              outgoingUploadCount: outgoingUploadCount,
                              outgoingChatCount: outgoingChatCount,
                            ),
                          ),
                        ],
                      ),
                    ),
                    if (hasBackgroundActivity)
                      Padding(
                        padding: const EdgeInsets.only(right: 8),
                        child: Text(
                          (activeJobCount + outgoingUploadCount).toString(),
                          style: TextStyle(
                            color: activeJobCount > 0
                                ? const Color(0xFFFFC857)
                                : const Color(0xFF8CA8FF),
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                    if (unreadChatsCount > 0)
                      Container(
                        margin: const EdgeInsets.only(right: 8),
                        padding: const EdgeInsets.symmetric(
                          horizontal: 8,
                          vertical: 4,
                        ),
                        decoration: BoxDecoration(
                          color: const Color(0xFF55D6BE),
                          borderRadius: BorderRadius.circular(999),
                        ),
                        child: Text(
                          unreadChatsCount.toString(),
                          style: const TextStyle(
                            color: Color(0xFF07131D),
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                    PopupMenuButton<_PinnedWorkspaceAction>(
                      tooltip: 'Project actions for ${workspace.name}',
                      icon: const Icon(Icons.more_horiz_rounded),
                      onSelected: (_PinnedWorkspaceAction action) async {
                        switch (action) {
                          case _PinnedWorkspaceAction.newChat:
                            Navigator.of(context).pop();
                            await _createNewChatForWorkspace(workspace);
                            return;
                          case _PinnedWorkspaceAction.remove:
                            await _removeWorkspaceFromSidebar(workspace);
                            return;
                        }
                      },
                      itemBuilder: (context) =>
                          <PopupMenuEntry<_PinnedWorkspaceAction>>[
                        PopupMenuItem<_PinnedWorkspaceAction>(
                          value: _PinnedWorkspaceAction.newChat,
                          child: Text('New chat in ${workspace.name}'),
                        ),
                        const PopupMenuItem<_PinnedWorkspaceAction>(
                          value: _PinnedWorkspaceAction.remove,
                          child: Text('Remove project'),
                        ),
                      ],
                    ),
                  ],
                ),
                children: visibleSessions.isEmpty
                    ? <Widget>[
                        Padding(
                          padding: EdgeInsets.fromLTRB(24, 0, 24, 16),
                          child: Align(
                            alignment: Alignment.centerLeft,
                            child: Text(
                              archivedOnly
                                  ? 'No archived chats in this project'
                                  : 'No active chats in this project',
                              style: const TextStyle(color: Color(0xFF8B97B5)),
                            ),
                          ),
                        ),
                      ]
                    : <Widget>[
                        ...displayedSessions.map(
                          (session) => Padding(
                            padding: const EdgeInsets.only(left: 10, right: 10),
                            child: _SessionTile(
                              activeJobSummary: _chatController
                                  .activeJobSummaryForSession(session.id),
                              outgoingUploadSummary: _chatController
                                  .outgoingUploadSummaryForSession(session.id),
                              session: session,
                              unreadCount: _unreadCountForSession(session),
                              selected: session.id ==
                                  _chatController.selectedSessionId,
                              onTap: () async {
                                Navigator.of(context).pop();
                                await _chatController.selectSession(session.id);
                              },
                              onRename: () async {
                                Navigator.of(context).pop();
                                await _openRenameChatSheet(session);
                              },
                              onArchiveToggle: () async {
                                await _chatController.setSessionArchived(
                                  session.id,
                                  archived: !archivedOnly,
                                );
                              },
                            ),
                          ),
                        ),
                        if (hiddenSessionCount > 0)
                          Padding(
                            padding: const EdgeInsets.fromLTRB(10, 8, 10, 0),
                            child: OutlinedButton.icon(
                              onPressed: () {
                                _showMoreSessionsForGroup(
                                  workspace.path,
                                  archivedOnly: archivedOnly,
                                );
                              },
                              icon: const Icon(Icons.expand_more_rounded),
                              label: Text(
                                'Show ${math.min(_sessionGroupPageSize, hiddenSessionCount)} more',
                              ),
                            ),
                          ),
                      ],
              ),
            ),
          ),
        ),
      );
    }

    return sessionGroups;
  }

  int _visibleSessionCountForGroup(
    String workspacePath, {
    required bool archivedOnly,
    required List<ChatSessionSummary> sessions,
  }) {
    final groupKey = _sessionGroupKey(
      workspacePath,
      archivedOnly: archivedOnly,
    );
    var limit = _visibleSessionLimitsByGroup[groupKey] ?? _sessionGroupPageSize;
    final selectedSessionId = _chatController.selectedSessionId;
    if (selectedSessionId != null) {
      final selectedIndex = sessions.indexWhere(
        (session) => session.id == selectedSessionId,
      );
      if (selectedIndex >= limit) {
        limit = selectedIndex + 1;
      }
    }
    return math.min(limit, sessions.length);
  }

  void _showMoreSessionsForGroup(
    String workspacePath, {
    required bool archivedOnly,
  }) {
    final groupKey = _sessionGroupKey(
      workspacePath,
      archivedOnly: archivedOnly,
    );
    final currentLimit =
        _visibleSessionLimitsByGroup[groupKey] ?? _sessionGroupPageSize;
    setState(() {
      _visibleSessionLimitsByGroup[groupKey] =
          currentLimit + _sessionGroupPageSize;
    });
  }

  String _sessionGroupKey(String workspacePath, {required bool archivedOnly}) {
    return '${archivedOnly ? 'archived' : 'active'}::$workspacePath';
  }

  int _compareSessionSummariesByRecentActivity(
    ChatSessionSummary left,
    ChatSessionSummary right,
  ) {
    final latestComparison = right.latestActivityAt.compareTo(
      left.latestActivityAt,
    );
    if (latestComparison != 0) {
      return latestComparison;
    }
    final createdComparison = right.createdAt.compareTo(left.createdAt);
    if (createdComparison != 0) {
      return createdComparison;
    }
    return right.id.compareTo(left.id);
  }

  String _fallbackWorkspaceName(String workspacePath) {
    final trimmed = workspacePath.trim();
    if (trimmed.isEmpty) {
      return 'Unknown project';
    }
    final parts = trimmed.split('/').where((part) => part.isNotEmpty).toList();
    if (parts.isEmpty) {
      return trimmed;
    }
    return parts.last;
  }

  void _handleChatControllerChanged() {
    _markCurrentSessionAsRead();
    final currentSessionId = _chatController.selectedSessionId;
    final currentMessages = _chatController.currentSession?.messages;
    final newestMessageId = currentMessages == null || currentMessages.isEmpty
        ? null
        : currentMessages.last.id;
    final sessionChanged = currentSessionId != _lastObservedSessionId;
    final firstRealMessageLoad = !sessionChanged &&
        currentSessionId != null &&
        newestMessageId != null &&
        _lastObservedNewestMessageId == null;
    if (sessionChanged) {
      _lastObservedSessionId = currentSessionId;
      _lastObservedNewestMessageId = newestMessageId;
      final currentSession = _chatController.currentSession;
      if (currentSession != null) {
        _replyPlaybackService.seedSession(currentSession);
      }
      if (_isUpdatingFilteredMessagesView ||
          _filteredMessagesViewErrorText != null) {
        setState(() {
          _isUpdatingFilteredMessagesView = false;
          _filteredMessagesViewErrorText = null;
          _chatBodyView = _ChatBodyView.conversation;
        });
      } else if (_chatBodyView != _ChatBodyView.conversation) {
        setState(() {
          _chatBodyView = _ChatBodyView.conversation;
        });
      }
      _updateStickToBottom(true);
    } else if (newestMessageId != _lastObservedNewestMessageId) {
      _lastObservedNewestMessageId = newestMessageId;
    }

    if (_stickToBottom) {
      _scrollToBottom(jumpToBottom: sessionChanged || firstRealMessageLoad);
    }

    unawaited(
      _replyPlaybackService.maybeSpeakLatestAssistantReply(
        enabled: _audioRepliesEnabled,
        session: _chatController.currentSession,
      ),
    );
  }

  int _unreadCountForSession(ChatSessionSummary session) {
    if (session.id == _chatController.selectedSessionId ||
        session.hasPendingMessages) {
      return 0;
    }

    final lastReadAt = _sessionReadMarkers[session.id];
    if (lastReadAt == null) {
      return 0;
    }

    return session.updatedAt.isAfter(lastReadAt) ? 1 : 0;
  }

  int _totalUnreadChatsCount() {
    final sidebarPaths =
        _sidebarWorkspaces.map((workspace) => workspace.path).toSet();
    return _chatController.sessions
        .where((session) => sidebarPaths.contains(session.workspacePath))
        .where((session) => _unreadCountForSession(session) > 0)
        .length;
  }

  int _totalActivePinnedProjectsCount() {
    return _sidebarWorkspaces
        .where(
          (workspace) => _activeOperationCountForWorkspace(workspace.path) > 0,
        )
        .length;
  }

  int _totalActivePinnedJobsCount() {
    return _sidebarWorkspaces.fold(
      0,
      (total, workspace) =>
          total + _activeOperationCountForWorkspace(workspace.path),
    );
  }

  int _activeOperationCountForWorkspace(String workspacePath) {
    return _chatController.sessions
        .where((session) => session.workspacePath == workspacePath)
        .fold(
          0,
          (total, session) =>
              total +
              _chatController.activeJobCountForSession(session.id) +
              (_chatController
                      .outgoingUploadSummaryForSession(session.id)
                      ?.totalCount ??
                  0),
        );
  }

  Future<void> _markCurrentSessionAsRead() async {
    final currentSession = _chatController.currentSession;
    if (currentSession == null) {
      return;
    }

    final lastReadAt = _sessionReadMarkers[currentSession.id];
    if (lastReadAt != null && !currentSession.updatedAt.isAfter(lastReadAt)) {
      return;
    }

    final updatedMarkers = <String, DateTime>{
      ..._sessionReadMarkers,
      currentSession.id: currentSession.updatedAt,
    };
    setState(() {
      _sessionReadMarkers = updatedMarkers;
    });

    final activeBaseUrl = _activeServer?.baseUrl ?? widget.initialApiBaseUrl;
    await _serverProfileStore.saveSessionReadMarkers(
      activeBaseUrl,
      updatedMarkers,
    );
  }

  bool _handleScrollNotification(ScrollNotification notification) {
    if (notification.metrics.axis != Axis.vertical) {
      return false;
    }
    if (notification is ScrollUpdateNotification ||
        notification is ScrollEndNotification ||
        notification is UserScrollNotification) {
      _updateStickToBottom(_isNearBottom(notification.metrics));
      if (_isNearTop(notification.metrics)) {
        unawaited(_loadOlderMessagesFromTop());
      }
    }
    return false;
  }

  bool _isNearBottom(ScrollMetrics metrics) {
    return metrics.extentAfter < 72;
  }

  bool _isNearTop(ScrollMetrics metrics) {
    return metrics.extentBefore < 96;
  }

  bool get _shouldShowOlderMessagesRow {
    return _chatBodyView == _ChatBodyView.conversation &&
        (_chatController.hasOlderMessages ||
            _chatController.isLoadingOlderMessages ||
            _chatController.olderMessagesError != null);
  }

  Future<void> _loadOlderMessagesFromTop() async {
    if (!_shouldShowOlderMessagesRow ||
        _chatController.isLoadingOlderMessages ||
        !_scrollController.hasClients) {
      return;
    }
    final beforeMaxExtent = _scrollController.position.maxScrollExtent;
    final beforeOffset = _scrollController.offset;
    final loaded = await _chatController.loadOlderMessages();
    if (!loaded || !mounted) {
      return;
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scrollController.hasClients) {
        return;
      }
      final delta =
          _scrollController.position.maxScrollExtent - beforeMaxExtent;
      _scrollController.jumpTo(beforeOffset + delta);
    });
  }

  void _updateStickToBottom(bool value) {
    if (_stickToBottom == value) {
      return;
    }
    setState(() {
      _stickToBottom = value;
    });
  }

  void _scrollToBottom({bool jumpToBottom = false}) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scrollController.hasClients) {
        return;
      }

      final maxScrollExtent = _scrollController.position.maxScrollExtent;
      if (jumpToBottom || maxScrollExtent == 0) {
        _scrollController.jumpTo(maxScrollExtent);
        return;
      }

      _scrollController.animateTo(
        maxScrollExtent,
        duration: const Duration(milliseconds: 250),
        curve: Curves.easeOut,
      );
    });
  }
}

class _SessionTile extends StatelessWidget {
  const _SessionTile({
    required this.activeJobSummary,
    required this.outgoingUploadSummary,
    required this.session,
    required this.unreadCount,
    required this.selected,
    required this.onTap,
    required this.onRename,
    required this.onArchiveToggle,
  });

  final SessionActiveJobSummary? activeJobSummary;
  final SessionOutgoingUploadSummary? outgoingUploadSummary;
  final ChatSessionSummary session;
  final int unreadCount;
  final bool selected;
  final VoidCallback onTap;
  final VoidCallback onRename;
  final VoidCallback onArchiveToggle;

  @override
  Widget build(BuildContext context) {
    final isActive = activeJobSummary != null;
    final isUploading = outgoingUploadSummary != null;
    final tileBackgroundColor = selected
        ? const Color(0xFF1C2745)
        : isActive
            ? const Color(0x1455D6BE)
            : isUploading
                ? const Color(0x123F5EF7)
                : Colors.transparent;
    final tileBorderColor = selected
        ? const Color(0xFF2F3F68)
        : isActive
            ? const Color(0x2855D6BE)
            : isUploading
                ? const Color(0x283F5EF7)
                : Colors.transparent;
    final titleColor = selected
        ? Colors.white
        : isActive
            ? const Color(0xFFE3FBF5)
            : isUploading
                ? const Color(0xFFEAF0FF)
                : null;
    final timelineColor = isActive || isUploading
        ? const Color(0xFFA8C7C0)
        : const Color(0xFF8B97B5);
    final displayTitle = _sessionDisplayTitle(session);

    return AnimatedContainer(
      duration: const Duration(milliseconds: 180),
      margin: const EdgeInsets.symmetric(vertical: 2),
      decoration: BoxDecoration(
        color: tileBackgroundColor,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: tileBorderColor),
      ),
      child: Material(
        type: MaterialType.transparency,
        child: ListTile(
          selected: selected,
          selectedTileColor: Colors.transparent,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
          title: Text(
            displayTitle,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              color: session.isArchived ? const Color(0xFFB8C8EA) : titleColor,
              fontSize: 15,
              fontWeight: isActive ? FontWeight.w700 : FontWeight.w600,
            ),
          ),
          subtitle: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              const SizedBox(height: 6),
              _SessionMomentLine(
                icon: Icons.schedule_rounded,
                label: 'Latest',
                value: _formatSessionMoment(context, session.latestActivityAt),
                color: session.isArchived
                    ? const Color(0xFF7F8EAF)
                    : timelineColor,
              ),
              const SizedBox(height: 3),
              _SessionMomentLine(
                icon: Icons.flag_outlined,
                label: 'Started',
                value: _formatSessionMoment(context, session.createdAt),
                color: session.isArchived
                    ? const Color(0xFF7F8EAF)
                    : const Color(0xFF8B97B5),
              ),
            ],
          ),
          trailing: Row(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              if (session.hasPendingMessages)
                const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              else if (isUploading)
                Icon(
                  _outgoingUploadIcon(outgoingUploadSummary!),
                  color: const Color(0xFF8CA8FF),
                )
              else if (unreadCount > 0)
                const Icon(
                  Icons.mark_chat_unread_rounded,
                  color: Color(0xFF55D6BE),
                ),
              PopupMenuButton<String>(
                padding: EdgeInsets.zero,
                tooltip: 'Chat actions',
                onSelected: (value) {
                  if (value == 'rename') {
                    onRename();
                    return;
                  }
                  if (value == 'toggle-archive') {
                    onArchiveToggle();
                  }
                },
                itemBuilder: (context) => <PopupMenuEntry<String>>[
                  const PopupMenuItem<String>(
                    value: 'rename',
                    child: Row(
                      children: <Widget>[
                        Icon(Icons.edit_outlined, size: 18),
                        SizedBox(width: 12),
                        Text('Rename chat'),
                      ],
                    ),
                  ),
                  PopupMenuItem<String>(
                    value: 'toggle-archive',
                    child: Row(
                      children: <Widget>[
                        Icon(
                          session.isArchived
                              ? Icons.unarchive_outlined
                              : Icons.archive_outlined,
                          size: 18,
                        ),
                        const SizedBox(width: 12),
                        Text(
                          session.isArchived
                              ? 'Unarchive chat'
                              : 'Archive chat',
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ],
          ),
          onTap: onTap,
        ),
      ),
    );
  }
}

class _SessionMomentLine extends StatelessWidget {
  const _SessionMomentLine({
    required this.icon,
    required this.label,
    required this.value,
    required this.color,
  });

  final IconData icon;
  final String label;
  final String value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: <Widget>[
        Icon(icon, size: 13, color: color),
        const SizedBox(width: 6),
        Text(
          label,
          style: TextStyle(
            color: color,
            fontSize: 11,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(width: 6),
        Expanded(
          child: Text(
            value,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(color: color, fontSize: 12),
          ),
        ),
      ],
    );
  }
}

String _sessionDisplayTitle(ChatSessionSummary session) {
  final title = session.title.trim();
  if (title.isEmpty || title.toLowerCase() == 'new chat') {
    return 'Untitled chat';
  }
  return title;
}

String _formatSessionMoment(BuildContext context, DateTime timestamp) {
  final localTimestamp = timestamp.toLocal();
  final dayLabel = formatChatDaySeparatorLabel(context, localTimestamp);
  final timeLabel = formatChatMessageTime(context, localTimestamp);
  return '$dayLabel, $timeLabel';
}

String _formatProjectActivityLabel({
  required int activeJobCount,
  required int activeChatCount,
  required int outgoingUploadCount,
  required int outgoingChatCount,
}) {
  final segments = <String>[];
  if (activeJobCount > 0) {
    segments.add(
      '$activeJobCount active job${activeJobCount == 1 ? '' : 's'} in $activeChatCount chat${activeChatCount == 1 ? '' : 's'}',
    );
  }
  if (outgoingUploadCount > 0) {
    segments.add(
      '$outgoingUploadCount upload${outgoingUploadCount == 1 ? '' : 's'} in $outgoingChatCount chat${outgoingChatCount == 1 ? '' : 's'}',
    );
  }
  if (segments.isEmpty) {
    return 'No active jobs';
  }
  return segments.join(' • ');
}

IconData _outgoingUploadIcon(SessionOutgoingUploadSummary summary) {
  if (summary.audioCount == summary.totalCount) {
    return Icons.graphic_eq_rounded;
  }
  if (summary.imageCount == summary.totalCount) {
    return Icons.image_rounded;
  }
  return Icons.cloud_upload_rounded;
}

class _MenuStatusBadge extends StatelessWidget {
  const _MenuStatusBadge({
    required this.label,
    required this.backgroundColor,
    required this.foregroundColor,
  });

  final String label;
  final Color backgroundColor;
  final Color foregroundColor;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: backgroundColor,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: foregroundColor,
          fontSize: 11,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }
}

class _ProjectStatusPill extends StatelessWidget {
  const _ProjectStatusPill({required this.active, required this.label});

  final bool active;
  final String label;

  @override
  Widget build(BuildContext context) {
    final backgroundColor =
        active ? const Color(0xFF3D2D08) : const Color(0xFF18223D);
    final foregroundColor =
        active ? const Color(0xFFFFC857) : const Color(0xFF8B97B5);

    return SizedBox(
      width: double.infinity,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        decoration: BoxDecoration(
          color: backgroundColor,
          borderRadius: BorderRadius.circular(999),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.max,
          children: <Widget>[
            Container(
              width: 8,
              height: 8,
              decoration: BoxDecoration(
                color: foregroundColor,
                shape: BoxShape.circle,
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: foregroundColor,
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ServerManagerSheet extends StatefulWidget {
  const _ServerManagerSheet({
    required this.profiles,
    required this.activeProfileId,
    required this.onAddServer,
  });

  final List<ServerProfile> profiles;
  final String? activeProfileId;
  final Future<ServerProfile?> Function(String name, String baseUrl)
      onAddServer;

  @override
  State<_ServerManagerSheet> createState() => _ServerManagerSheetState();
}

class _ServerManagerSheetState extends State<_ServerManagerSheet> {
  final TextEditingController _nameController = TextEditingController();
  final TextEditingController _urlController = TextEditingController();
  String? _errorText;
  bool _saving = false;

  @override
  void dispose() {
    _nameController.dispose();
    _urlController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.only(
          bottom: MediaQuery.of(context).viewInsets.bottom,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            const ListTile(
              title: Text('Servers'),
              subtitle: Text('Choose which computer to control'),
            ),
            Flexible(
              child: ListView(
                shrinkWrap: true,
                children: <Widget>[
                  ...widget.profiles.map(
                    (profile) => ListTile(
                      leading: Icon(
                        profile.id == widget.activeProfileId
                            ? Icons.radio_button_checked
                            : Icons.radio_button_off,
                      ),
                      title: Text(profile.name),
                      subtitle: Text(profile.baseUrl),
                      onTap: () => Navigator.of(context).pop(profile),
                    ),
                  ),
                  const Divider(),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                    child: TextField(
                      controller: _nameController,
                      decoration: const InputDecoration(
                        labelText: 'Server name',
                        hintText: 'Personal laptop',
                      ),
                    ),
                  ),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
                    child: TextField(
                      controller: _urlController,
                      decoration: const InputDecoration(
                        labelText: 'Base URL',
                        hintText:
                            'http://batata-default-string.tail0302c4.ts.net',
                      ),
                    ),
                  ),
                  if (_errorText != null)
                    Padding(
                      padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
                      child: Text(
                        _errorText!,
                        style: const TextStyle(color: Color(0xFFFFB4A8)),
                      ),
                    ),
                  Padding(
                    padding: const EdgeInsets.all(16),
                    child: SizedBox(
                      width: double.infinity,
                      child: FilledButton(
                        onPressed: _saving ? null : _handleAddServer,
                        child: Text(_saving ? 'Connecting...' : 'Add Server'),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _handleAddServer() async {
    setState(() {
      _saving = true;
      _errorText = null;
    });

    try {
      final profile = await widget.onAddServer(
        _nameController.text,
        _urlController.text,
      );
      if (profile != null && mounted) {
        Navigator.of(context).pop(profile);
      }
    } catch (error) {
      setState(() {
        _errorText = '$error';
      });
    } finally {
      if (mounted) {
        setState(() {
          _saving = false;
        });
      }
    }
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState({required this.onCreateChat});

  final Future<void> Function() onCreateChat;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 24),
        child: SingleChildScrollView(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                const Text(
                  'Start a new Codex session',
                  style: TextStyle(fontSize: 24, fontWeight: FontWeight.w600),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 12),
                const Text(
                  'Each chat maps to a real Codex CLI session and follow-up messages continue that session.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Color(0xFF8B97B5), height: 1.5),
                ),
                const SizedBox(height: 20),
                FilledButton.icon(
                  onPressed: () async {
                    await onCreateChat();
                  },
                  icon: const Icon(Icons.add_comment_outlined),
                  label: const Text('New Chat'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _FilteredMessagesPlaceholder extends StatelessWidget {
  const _FilteredMessagesPlaceholder({
    required this.displayMode,
    required this.isUpdating,
    required this.errorText,
    required this.onShowAllMessages,
  });

  final AgentDisplayMode displayMode;
  final bool isUpdating;
  final String? errorText;
  final Future<void> Function() onShowAllMessages;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 24),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 460),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              const Text(
                'Messages hidden in this view',
                style: TextStyle(fontSize: 24, fontWeight: FontWeight.w600),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 12),
              Text(
                _filteredMessagesPlaceholderText(displayMode),
                textAlign: TextAlign.center,
                style: const TextStyle(color: Color(0xFF8B97B5), height: 1.5),
              ),
              const SizedBox(height: 20),
              FilledButton.icon(
                onPressed: isUpdating
                    ? null
                    : () async {
                        await onShowAllMessages();
                      },
                icon: isUpdating
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.visibility_rounded),
                label: Text(
                  isUpdating ? 'Updating view...' : 'Show all messages',
                ),
              ),
              const SizedBox(height: 12),
              const Text(
                'Run history above still updates live, and you can keep chatting below.',
                textAlign: TextAlign.center,
                style: TextStyle(color: Color(0xFFB8C8EA), height: 1.5),
              ),
              if (errorText != null) ...<Widget>[
                const SizedBox(height: 12),
                Text(
                  errorText!,
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: Color(0xFFFFB4B4), height: 1.4),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _OlderMessagesRow extends StatelessWidget {
  const _OlderMessagesRow({
    required this.isLoading,
    required this.errorText,
    required this.onRetry,
  });

  final bool isLoading;
  final String? errorText;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final hasError = errorText != null;
    if (!hasError) {
      return Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: Center(
          child: SizedBox(
            width: 36,
            height: 36,
            child: Center(
              child: isLoading
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
            ),
          ),
        ),
      );
    }
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 420),
          child: DecoratedBox(
            decoration: BoxDecoration(
              color: const Color(0xFF10182B),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: const Color(0xFF24304E)),
            ),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  if (isLoading)
                    const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  else
                    const Icon(
                      Icons.error_outline_rounded,
                      size: 18,
                      color: Color(0xFFFFB4A8),
                    ),
                  const SizedBox(width: 10),
                  const Flexible(
                    child: Text(
                      'Older messages failed to load.',
                      style: TextStyle(color: Color(0xFFDCE5FF)),
                    ),
                  ),
                  const SizedBox(width: 8),
                  TextButton(onPressed: onRetry, child: const Text('Retry')),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _GuidedProjectIntakeCard extends StatelessWidget {
  const _GuidedProjectIntakeCard({
    required this.readyForBuild,
    required this.onShowContract,
    this.isLoading = false,
    this.errorText,
  });

  final bool readyForBuild;
  final VoidCallback onShowContract;
  final bool isLoading;
  final String? errorText;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: const Color(0xFF111B2D),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(0xFF273A60)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(
              children: <Widget>[
                const Icon(Icons.fact_check_rounded, color: Color(0xFF55D6BE)),
                const SizedBox(width: 10),
                const Expanded(
                  child: Text(
                    'New Project contract',
                    style: TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
                _StatusPill(
                  label: readyForBuild ? 'Ready' : 'Collecting',
                  backgroundColor: readyForBuild
                      ? const Color(0xFF0B3D25)
                      : const Color(0xFF2A2440),
                  foregroundColor: readyForBuild
                      ? const Color(0xFFB7F5CF)
                      : const Color(0xFFD9CCFF),
                ),
              ],
            ),
            const SizedBox(height: 10),
            const Text(
              'Name, goal, platforms, backend, roles, entities, assets, release, Workbench/SDD, web preview, Android plan, blockers, risks.',
              style: TextStyle(color: Color(0xFFB8C8EA), height: 1.35),
            ),
            if (isLoading) ...<Widget>[
              const SizedBox(height: 10),
              const LinearProgressIndicator(minHeight: 2),
            ],
            if (errorText != null) ...<Widget>[
              const SizedBox(height: 10),
              Text(
                errorText!,
                style: const TextStyle(color: Color(0xFFFFB4B4), height: 1.35),
              ),
            ],
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: <Widget>[
                OutlinedButton.icon(
                  onPressed: onShowContract,
                  icon: const Icon(Icons.article_outlined),
                  label: const Text('Preview'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class ProjectFactoryInitCard extends StatelessWidget {
  const ProjectFactoryInitCard({
    super.key,
    required this.initJob,
    required this.isLoading,
    this.errorText,
  });

  final ProjectFactoryInitJob? initJob;
  final bool isLoading;
  final String? errorText;

  @override
  Widget build(BuildContext context) {
    final job = initJob;
    final status = job?.status ?? (isLoading ? 'running' : 'queued');
    final currentPhase = job?.currentPhase ?? 'init_preflight';
    final blockers = job?.blockers ?? const <Map<String, dynamic>>[];
    return DecoratedBox(
      decoration: BoxDecoration(
        color: const Color(0xFF0E1A22),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(0xFF214557)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(
              children: <Widget>[
                const Icon(Icons.account_tree_rounded,
                    color: Color(0xFF65D6FF)),
                const SizedBox(width: 10),
                const Expanded(
                  child: Text(
                    'Deterministic baseline init',
                    style: TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
                _StatusPill(
                  label: _initStatusLabel(status),
                  backgroundColor: _initStatusBackground(status),
                  foregroundColor: _initStatusForeground(status),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Text(
              'Current phase: ${_humanizeInitPhase(currentPhase)}',
              style: const TextStyle(color: Color(0xFFB8C8EA), height: 1.35),
            ),
            const SizedBox(height: 6),
            const Text(
              'Preparing repo, preview infrastructure, runtime profile, Workbench, feedback, release wiring, and first-chat context before business work starts.',
              style: TextStyle(color: Color(0xFF8EA6C7), height: 1.35),
            ),
            if (isLoading) ...<Widget>[
              const SizedBox(height: 10),
              const LinearProgressIndicator(minHeight: 2),
            ],
            if (blockers.isNotEmpty) ...<Widget>[
              const SizedBox(height: 10),
              ...blockers.take(2).map(
                    (blocker) => Text(
                      blocker['message'] as String? ?? 'Init blocker',
                      style: const TextStyle(
                        color: Color(0xFFFFD7A8),
                        height: 1.35,
                      ),
                    ),
                  ),
            ],
            if (errorText != null) ...<Widget>[
              const SizedBox(height: 10),
              Text(
                errorText!,
                style: const TextStyle(color: Color(0xFFFFB4B4), height: 1.35),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _SummaryViewBanner extends StatelessWidget {
  const _SummaryViewBanner({
    required this.summaryCount,
    required this.onShowFullChat,
  });

  final int summaryCount;
  final VoidCallback onShowFullChat;

  @override
  Widget build(BuildContext context) {
    final label = summaryCount == 1
        ? 'Showing 1 summary update'
        : 'Showing $summaryCount summary updates';
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF173255),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: const Color(0xFF66A8FF), width: 1.2),
      ),
      child: Row(
        children: <Widget>[
          const Icon(Icons.summarize_outlined, color: Color(0xFFAED3FF)),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              '$label. Tap a summary to inspect what was completed at that point in the run.',
              style: const TextStyle(color: Colors.white, height: 1.35),
            ),
          ),
          const SizedBox(width: 12),
          TextButton(
            onPressed: onShowFullChat,
            child: const Text('Show full chat'),
          ),
        ],
      ),
    );
  }
}

class _SummaryMessagesPlaceholder extends StatelessWidget {
  const _SummaryMessagesPlaceholder({required this.onShowFullChat});

  final VoidCallback onShowFullChat;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 24),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 460),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              const Text(
                'No summaries yet',
                style: TextStyle(fontSize: 24, fontWeight: FontWeight.w600),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 12),
              const Text(
                'Summary view is enabled for this chat, but the summarizer has not produced an update yet.',
                textAlign: TextAlign.center,
                style: TextStyle(color: Color(0xFF8B97B5), height: 1.5),
              ),
              const SizedBox(height: 20),
              FilledButton.icon(
                onPressed: onShowFullChat,
                icon: const Icon(Icons.chat_bubble_outline_rounded),
                label: const Text('Show full chat'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _TurnSummaryBanner extends StatelessWidget {
  const _TurnSummaryBanner({
    required this.summaryCount,
    required this.enabled,
    required this.onShowFullChat,
  });

  final int summaryCount;
  final bool enabled;
  final VoidCallback onShowFullChat;

  @override
  Widget build(BuildContext context) {
    final label = summaryCount == 1
        ? 'Showing 1 chat summary'
        : 'Showing $summaryCount chat summaries';
    final suffix = enabled
        ? 'New summaries are generated automatically for this chat.'
        : 'Automatic generation is off for this chat.';
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF3B2A10),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: const Color(0xFFFFC857), width: 1.2),
      ),
      child: Row(
        children: <Widget>[
          const Icon(Icons.history_edu_outlined, color: Color(0xFFFFE08A)),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              '$label. $suffix Each entry includes the source messages it was built from.',
              style: const TextStyle(color: Colors.white, height: 1.35),
            ),
          ),
          const SizedBox(width: 12),
          TextButton(
            onPressed: onShowFullChat,
            child: const Text('Show full chat'),
          ),
        ],
      ),
    );
  }
}

class _TurnSummariesPlaceholder extends StatelessWidget {
  const _TurnSummariesPlaceholder({
    required this.enabled,
    required this.onShowFullChat,
  });

  final bool enabled;
  final VoidCallback onShowFullChat;

  @override
  Widget build(BuildContext context) {
    final message = enabled
        ? 'The chat summary is enabled, but the first summary has not been created yet.'
        : 'The chat summary is disabled for this chat. Enable it from Agents to start collecting summaries.';
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 24),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 460),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              const Text(
                'No chat summaries yet',
                style: TextStyle(fontSize: 24, fontWeight: FontWeight.w600),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 12),
              Text(
                message,
                textAlign: TextAlign.center,
                style: const TextStyle(color: Color(0xFF8B97B5), height: 1.5),
              ),
              const SizedBox(height: 20),
              FilledButton.icon(
                onPressed: onShowFullChat,
                icon: const Icon(Icons.chat_bubble_outline_rounded),
                label: const Text('Show full chat'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _TurnSummaryCard extends StatelessWidget {
  const _TurnSummaryCard({required this.summary});

  final ChatTurnSummary summary;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF181F33),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: const Color(0xFF33405D)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Icon(Icons.article_outlined, color: Color(0xFFFFC857)),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  formatChatMessageTime(context, summary.createdAt),
                  style: const TextStyle(
                    color: Color(0xFFFFE08A),
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              Text(
                summary.sourceMessages.length == 1
                    ? '1 source'
                    : '${summary.sourceMessages.length} sources',
                style: const TextStyle(color: Color(0xFF9FB0D4), fontSize: 12),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            summary.content,
            style: const TextStyle(color: Colors.white, height: 1.45),
          ),
          const SizedBox(height: 14),
          const Text(
            'Provenance',
            style: TextStyle(
              color: Color(0xFF9FB0D4),
              fontSize: 12,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 8),
          if (summary.sourceMessages.isEmpty)
            const Text(
              'Source message metadata is unavailable for this summary.',
              style: TextStyle(color: Color(0xFFB8C8EA), height: 1.4),
            )
          else
            Column(
              children: summary.sourceMessages.map((message) {
                final agentLabel = (message.agentLabel ?? '').trim();
                final label = agentLabel.isNotEmpty
                    ? agentLabel
                    : message.isUser
                        ? 'User'
                        : message.agentId.name;
                final excerpt = (message.content ?? '').trim();
                final excerptText = excerpt.isNotEmpty
                    ? excerpt.length <= 140
                        ? excerpt
                        : '${excerpt.substring(0, 137)}...'
                    : 'Message text unavailable for this older summary.';
                return Container(
                  width: double.infinity,
                  margin: const EdgeInsets.only(bottom: 8),
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: const Color(0xFF121A2C),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: const Color(0xFF27324F)),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(
                        '$label • ${formatChatMessageTime(context, message.createdAt)}',
                        style: const TextStyle(
                          color: Color(0xFFDCE5FF),
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        excerptText,
                        style: const TextStyle(
                          color: Color(0xFFB8C8EA),
                          height: 1.35,
                        ),
                      ),
                    ],
                  ),
                );
              }).toList(growable: false),
            ),
        ],
      ),
    );
  }
}

String _filteredMessagesPlaceholderText(AgentDisplayMode displayMode) {
  return switch (displayMode) {
    AgentDisplayMode.showAll =>
      'This chat has messages, but none are visible right now.',
    AgentDisplayMode.collapseSpecialists =>
      'This chat already has messages, but the current "Collapse specialists" view is hiding them. Switch chat rendering to "Show all" to inspect the full conversation.',
    AgentDisplayMode.summaryOnly =>
      'This chat already has generator or reviewer messages, but "Summary only" hides them until a summary message exists. Switch chat rendering to "Show all" to inspect the full conversation.',
  };
}

class _SlashCommandPalette extends StatelessWidget {
  const _SlashCommandPalette({
    required this.commands,
    required this.selectedIndex,
    required this.errorText,
    required this.onSelected,
    required this.onHighlightChanged,
  });

  final List<SlashCommand> commands;
  final int selectedIndex;
  final String? errorText;
  final ValueChanged<SlashCommand> onSelected;
  final ValueChanged<int> onHighlightChanged;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: const Color(0xFF10182B),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(0xFF263455)),
      ),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxHeight: 280),
        child: commands.isEmpty
            ? const Padding(
                padding: EdgeInsets.all(14),
                child: Row(
                  children: <Widget>[
                    Icon(Icons.search_off_rounded, color: Color(0xFF8B97B5)),
                    SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        'No matching commands',
                        style: TextStyle(color: Color(0xFFDCE5FF)),
                      ),
                    ),
                  ],
                ),
              )
            : ListView.builder(
                shrinkWrap: true,
                itemCount: commands.length + (errorText == null ? 0 : 1),
                itemBuilder: (context, index) {
                  if (errorText != null && index == commands.length) {
                    return Padding(
                      padding: const EdgeInsets.fromLTRB(12, 6, 12, 12),
                      child: Text(
                        errorText!,
                        style: const TextStyle(color: Color(0xFFFFB4A8)),
                      ),
                    );
                  }
                  final command = commands[index];
                  final selected = index == selectedIndex;
                  final enabled = command.isEnabled;
                  return Material(
                    color:
                        selected ? const Color(0xFF1B2745) : Colors.transparent,
                    child: InkWell(
                      onTap: () => onSelected(command),
                      onHover: (_) => onHighlightChanged(index),
                      child: Padding(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 12,
                          vertical: 10,
                        ),
                        child: Row(
                          children: <Widget>[
                            Icon(
                              enabled
                                  ? Icons.keyboard_command_key_rounded
                                  : Icons.block_rounded,
                              color: enabled
                                  ? const Color(0xFF55D6BE)
                                  : const Color(0xFF8B97B5),
                              size: 18,
                            ),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: <Widget>[
                                  Text(
                                    '${command.slash}  ${command.title}',
                                    style: TextStyle(
                                      color: enabled
                                          ? Colors.white
                                          : const Color(0xFF8B97B5),
                                      fontWeight: FontWeight.w700,
                                    ),
                                  ),
                                  const SizedBox(height: 2),
                                  Text(
                                    command.disabledReason ??
                                        command.description,
                                    style: const TextStyle(
                                      color: Color(0xFFB8C8EA),
                                      fontSize: 12,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            Text(
                              command.scope,
                              style: const TextStyle(
                                color: Color(0xFF8B97B5),
                                fontSize: 11,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  );
                },
              ),
      ),
    );
  }
}

class _Composer extends StatefulWidget {
  const _Composer({
    required this.sessionId,
    required this.controller,
    required this.draft,
    required this.onDraftChanged,
    required this.onSend,
    required this.onSendAudio,
    required this.onSendAttachments,
    required this.onBeginRecording,
    required this.onSlashCommand,
    required this.slashCommandContext,
    required this.audioRecorderFactory,
    required this.isBusy,
    required this.voiceEnabled,
    required this.imageAttachmentsEnabled,
    required this.fileAttachmentsEnabled,
    required this.voiceStatusText,
    required this.isProjectFactoryIntake,
  });

  final String? sessionId;
  final TextEditingController controller;
  final _ComposerDraft draft;
  final ValueChanged<_ComposerDraft> onDraftChanged;
  final Future<bool> Function() onSend;
  final Future<bool> Function(XFile audioFile, {String? message}) onSendAudio;
  final Future<bool> Function(
    List<_PendingAttachmentDraft> attachments, {
    String? prompt,
  }) onSendAttachments;
  final Future<void> Function() onBeginRecording;
  final Future<bool> Function(String commandId, String payload) onSlashCommand;
  final SlashCommandContext slashCommandContext;
  final AudioNoteRecorder Function() audioRecorderFactory;
  final bool isBusy;
  final bool voiceEnabled;
  final bool imageAttachmentsEnabled;
  final bool fileAttachmentsEnabled;
  final String voiceStatusText;
  final bool isProjectFactoryIntake;

  @override
  State<_Composer> createState() => _ComposerState();
}

class _ComposerState extends State<_Composer> {
  late AudioNoteRecorder _audioRecorder;
  final FocusNode _composerFocusNode = FocusNode();
  final ImagePicker _imagePicker = ImagePicker();
  late final ClipboardImagePasteListener _clipboardImagePasteListener;
  Stopwatch? _recordingStopwatch;
  Timer? _recordingTicker;
  bool _hasText = false;
  bool _isRecording = false;
  bool _isSubmittingAttachments = false;
  bool _attachmentsExpanded = true;
  bool _didStartRecordingFromPrimaryDrag = false;
  double _primaryActionDragDy = 0;
  int _selectedSlashCommandIndex = 0;
  String? _slashCommandErrorText;
  final List<_PendingAttachmentDraft> _pendingAttachments =
      <_PendingAttachmentDraft>[];

  @override
  void initState() {
    super.initState();
    _audioRecorder = widget.audioRecorderFactory();
    _applyDraft(widget.draft, notifyParent: false);
    _hasText = widget.controller.text.trim().isNotEmpty;
    widget.controller.addListener(_handleTextChanged);
    _clipboardImagePasteListener = attachClipboardImagePasteListener(
      canHandlePaste: _canAcceptPastedImages,
      onImagesPasted: _handlePastedImages,
    );
  }

  @override
  void didUpdateWidget(covariant _Composer oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.controller != widget.controller) {
      oldWidget.controller.removeListener(_handleTextChanged);
      _hasText = widget.controller.text.trim().isNotEmpty;
      widget.controller.addListener(_handleTextChanged);
    }
    if (oldWidget.sessionId != widget.sessionId) {
      _resetRecorderForSessionChange();
    }
    final draftChanged = oldWidget.draft.text != widget.draft.text ||
        oldWidget.draft.codexRunOptions.toJson().toString() !=
            widget.draft.codexRunOptions.toJson().toString() ||
        !_sameDraftAttachments(
          oldWidget.draft.attachments,
          widget.draft.attachments,
        );
    if (oldWidget.sessionId != widget.sessionId || draftChanged) {
      _applyDraft(widget.draft, notifyParent: false);
    }
  }

  @override
  void dispose() {
    _clipboardImagePasteListener.dispose();
    _composerFocusNode.dispose();
    widget.controller.removeListener(_handleTextChanged);
    _recordingTicker?.cancel();
    if (_isRecording) {
      _audioRecorder.cancel();
    }
    _audioRecorder.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final hasPendingAttachment = _pendingAttachments.isNotEmpty;
    final showMicAction = !_hasText && !_isRecording && !hasPendingAttachment;
    final showAddVoiceAction =
        !_isRecording && !showMicAction && widget.voiceEnabled;
    final isDisabled = widget.isBusy || _isSubmittingAttachments;

    return SafeArea(
      top: false,
      child: Container(
        padding: const EdgeInsets.fromLTRB(10, 8, 10, 10),
        decoration: const BoxDecoration(
          color: Color(0xFF0B141A),
          border: Border(top: BorderSide(color: Color(0xFF17232B))),
        ),
        child: LayoutBuilder(
          builder: (context, constraints) {
            final useCompactRecordingLayout =
                _isRecording && constraints.maxWidth < 380;
            final useCompactAttachmentLayout = !_isRecording &&
                hasPendingAttachment &&
                constraints.maxWidth < 430;

            if (useCompactRecordingLayout) {
              return Column(
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  _buildComposerBody(),
                  const SizedBox(height: 10),
                  Row(
                    children: <Widget>[
                      Expanded(
                        child: FilledButton.icon(
                          onPressed: _confirmCancelRecording,
                          style: _actionButtonStyle(
                            backgroundColor: const Color(0xFF1F2C34),
                            foregroundColor: const Color(0xFFE9EDEF),
                          ),
                          icon: const Icon(Icons.close_rounded),
                          label: const Text('Cancel'),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: FilledButton.icon(
                          onPressed: isDisabled ? null : _stopRecordingAndSend,
                          style: _actionButtonStyle(
                            backgroundColor: const Color(0xFF25D366),
                            foregroundColor: const Color(0xFF0B141A),
                          ),
                          icon: const Icon(Icons.send_rounded),
                          label: const Text('Send'),
                        ),
                      ),
                    ],
                  ),
                ],
              );
            }

            if (useCompactAttachmentLayout) {
              return Column(
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  _buildComposerBody(),
                  const SizedBox(height: 10),
                  Row(
                    children: <Widget>[
                      if (showAddVoiceAction) ...<Widget>[
                        FilledButton(
                          onPressed: isDisabled ? null : _toggleRecording,
                          style: _actionButtonStyle(
                            backgroundColor: const Color(0xFF1F2C34),
                            foregroundColor: const Color(0xFF8696A0),
                          ),
                          child: const Icon(Icons.mic_rounded),
                        ),
                        const SizedBox(width: 10),
                      ],
                      Expanded(
                        child: _buildPrimaryActionButton(
                          isDisabled: isDisabled,
                          includeLabel: true,
                        ),
                      ),
                    ],
                  ),
                ],
              );
            }

            return Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: <Widget>[
                Expanded(child: _buildComposerBody()),
                const SizedBox(width: 8),
                if (_isRecording)
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: <Widget>[
                      FilledButton(
                        onPressed: _confirmCancelRecording,
                        style: _actionButtonStyle(
                          backgroundColor: const Color(0xFF1F2C34),
                          foregroundColor: const Color(0xFFE9EDEF),
                          minimumSize: const Size(52, 52),
                        ),
                        child: const Icon(Icons.close_rounded),
                      ),
                      const SizedBox(width: 6),
                      FilledButton(
                        onPressed: isDisabled ? null : _stopRecordingAndSend,
                        style: _actionButtonStyle(
                          backgroundColor: const Color(0xFF25D366),
                          foregroundColor: const Color(0xFF0B141A),
                          minimumSize: const Size(52, 52),
                        ),
                        child: const Icon(Icons.send_rounded),
                      ),
                    ],
                  )
                else if (showMicAction && !widget.voiceEnabled)
                  FilledButton(
                    onPressed: _showVoiceUnavailableMessage,
                    style: _actionButtonStyle(
                      backgroundColor: const Color(0xFF25D366),
                      foregroundColor: const Color(0xFF0B141A),
                    ),
                    child: const Icon(Icons.mic_off_rounded),
                  )
                else if (showMicAction)
                  FilledButton(
                    onPressed: isDisabled ? null : _toggleRecording,
                    style: _actionButtonStyle(
                      backgroundColor: const Color(0xFF25D366),
                      foregroundColor: const Color(0xFF0B141A),
                    ),
                    child: const Icon(Icons.mic_rounded),
                  )
                else
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: <Widget>[
                      if (showAddVoiceAction) ...<Widget>[
                        FilledButton(
                          onPressed: isDisabled ? null : _toggleRecording,
                          style: _actionButtonStyle(
                            backgroundColor: const Color(0xFF1F2C34),
                            foregroundColor: const Color(0xFF8696A0),
                            minimumSize: const Size(52, 52),
                          ),
                          child: const Icon(Icons.mic_rounded),
                        ),
                        const SizedBox(width: 6),
                      ],
                      _buildPrimaryActionButton(
                        isDisabled: isDisabled,
                        minimumSize: const Size(52, 52),
                      ),
                    ],
                  ),
              ],
            );
          },
        ),
      ),
    );
  }

  Widget _buildComposerBody() {
    if (_isRecording) {
      return _VoiceStatusCard(
        icon: Icons.mic_rounded,
        title: 'Recording',
        subtitle: 'Send now or cancel to discard',
        color: const Color(0xFF25D366),
        trailing: _StatusPill(
          label: _formatDuration(),
          backgroundColor: const Color(0xFF0B3D25),
          foregroundColor: const Color(0xFFB7F5CF),
        ),
        titleMaxLines: 1,
        subtitleMaxLines: 1,
      );
    }

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        if (!widget.draft.codexRunOptions.isEmpty)
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: _CodexOptionTray(options: widget.draft.codexRunOptions),
          ),
        if (_pendingAttachments.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: _PendingAttachmentTray(
              attachments: _pendingAttachments,
              busy: widget.isBusy,
              isProjectFactoryIntake: widget.isProjectFactoryIntake,
              onRemove: _removePendingAttachment,
              onRoleChanged: _setPendingAttachmentRole,
              onClearAll: _clearPendingAttachments,
              expanded: _attachmentsExpanded,
              onToggleExpanded: _toggleAttachmentsExpanded,
            ),
          ),
        if (_slashQuery != null)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: _SlashCommandPalette(
              commands: _filteredSlashCommands(_slashQuery!),
              selectedIndex: _selectedSlashCommandIndex,
              errorText: _slashCommandErrorText,
              onSelected: _selectSlashCommand,
              onHighlightChanged: (index) {
                setState(() {
                  _selectedSlashCommandIndex = index;
                  _slashCommandErrorText = null;
                });
              },
            ),
          ),
        TextField(
          controller: widget.controller,
          focusNode: _composerFocusNode,
          minLines: 1,
          maxLines: 6,
          enabled: !widget.isBusy && !_isSubmittingAttachments,
          textInputAction: TextInputAction.send,
          onSubmitted: (_) async {
            await _handlePrimaryAction();
          },
          decoration: InputDecoration(
            filled: true,
            fillColor: const Color(0xFF1F2C34),
            hintText: _composerHintText(),
            hintStyle: const TextStyle(color: Color(0xFF8696A0)),
            contentPadding: const EdgeInsets.symmetric(
              horizontal: 14,
              vertical: 13,
            ),
            prefixIcon: IconButton(
              onPressed: _isSubmittingAttachments
                  ? null
                  : (widget.isBusy ? null : _openAttachmentPicker),
              tooltip: 'Add attachment',
              icon: const Icon(Icons.attach_file_rounded),
              color: const Color(0xFF8696A0),
            ),
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(28),
              borderSide: BorderSide.none,
            ),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(28),
              borderSide: BorderSide.none,
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(28),
              borderSide: BorderSide.none,
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildPrimaryActionButton({
    required bool isDisabled,
    bool includeLabel = false,
    Size minimumSize = const Size(56, 56),
  }) {
    final canStartVoiceFromSwipe =
        !isDisabled && widget.voiceEnabled && !_isRecording;
    final button = includeLabel
        ? FilledButton.icon(
            onPressed: isDisabled ? null : _handlePrimaryAction,
            style: _actionButtonStyle(
              backgroundColor: const Color(0xFF25D366),
              foregroundColor: const Color(0xFF0B141A),
              minimumSize: minimumSize,
            ),
            icon: const Icon(Icons.arrow_upward_rounded),
            label: const Text('Send'),
          )
        : FilledButton(
            onPressed: isDisabled ? null : _handlePrimaryAction,
            style: _actionButtonStyle(
              backgroundColor: const Color(0xFF25D366),
              foregroundColor: const Color(0xFF0B141A),
              minimumSize: minimumSize,
            ),
            child: const Icon(Icons.arrow_upward_rounded),
          );

    if (!canStartVoiceFromSwipe) {
      return button;
    }

    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onVerticalDragStart: (_) {
        _didStartRecordingFromPrimaryDrag = false;
        _primaryActionDragDy = 0;
      },
      onVerticalDragUpdate: (details) {
        _primaryActionDragDy += details.delta.dy;
        if (!_didStartRecordingFromPrimaryDrag && _primaryActionDragDy <= -44) {
          _didStartRecordingFromPrimaryDrag = true;
          unawaited(_startRecording());
        }
      },
      onVerticalDragCancel: _resetPrimaryActionDrag,
      onVerticalDragEnd: (_) {
        _resetPrimaryActionDrag();
      },
      child: button,
    );
  }

  void _resetPrimaryActionDrag() {
    _didStartRecordingFromPrimaryDrag = false;
    _primaryActionDragDy = 0;
  }

  ButtonStyle _actionButtonStyle({
    required Color backgroundColor,
    required Color foregroundColor,
    Size minimumSize = const Size(56, 56),
  }) {
    return FilledButton.styleFrom(
      backgroundColor: backgroundColor,
      foregroundColor: foregroundColor,
      minimumSize: minimumSize,
      padding: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(minimumSize.height / 2),
      ),
    );
  }

  void _handleTextChanged() {
    final hasText = widget.controller.text.trim().isNotEmpty;
    final slashQuery = _slashQuery;
    if (_hasText != hasText ||
        slashQuery != null ||
        _slashCommandErrorText != null) {
      setState(() {
        _hasText = hasText;
        if (slashQuery != null) {
          final commands = _filteredSlashCommands(slashQuery);
          if (_selectedSlashCommandIndex >= commands.length) {
            _selectedSlashCommandIndex = 0;
          }
        } else {
          _selectedSlashCommandIndex = 0;
          _slashCommandErrorText = null;
        }
      });
    }
    _emitDraftChanged();
  }

  String? get _slashQuery {
    final text = widget.controller.text;
    final selection = widget.controller.selection;
    if (!selection.isValid || !selection.isCollapsed) {
      return null;
    }
    if (!text.startsWith('/')) {
      return null;
    }
    if (text.contains(RegExp(r'\s'))) {
      return null;
    }
    return slashQueryForComposerText(text, selectionValid: true);
  }

  List<SlashCommand> get _slashCommands {
    return buildSlashCommands(widget.slashCommandContext);
  }

  List<SlashCommand> _filteredSlashCommands(String query) {
    return filterSlashCommands(_slashCommands, query);
  }

  Future<void> _selectHighlightedSlashCommand() async {
    final query = _slashQuery;
    if (query == null) {
      return;
    }
    final commands = _filteredSlashCommands(query);
    if (commands.isEmpty) {
      setState(() {
        _slashCommandErrorText = 'Unknown slash command.';
      });
      return;
    }
    final index = _selectedSlashCommandIndex.clamp(0, commands.length - 1);
    await _selectSlashCommand(commands[index]);
  }

  Future<void> _selectSlashCommand(SlashCommand command) async {
    if (!command.isEnabled) {
      setState(() {
        _slashCommandErrorText = command.disabledReason ??
            'This command is unavailable in the current context.';
      });
      return;
    }
    setState(() {
      _slashCommandErrorText = null;
      _selectedSlashCommandIndex = 0;
    });
    switch (command.actionKind) {
      case SlashCommandActionKind.insertText:
        widget.controller.text = command.payload;
        widget.controller.selection = TextSelection.collapsed(
          offset: widget.controller.text.length,
        );
        _composerFocusNode.requestFocus();
        break;
      case SlashCommandActionKind.sendMessage:
      case SlashCommandActionKind.openPanel:
      case SlashCommandActionKind.route:
      case SlashCommandActionKind.backend:
      case SlashCommandActionKind.callback:
        widget.controller.clear();
        await widget.onSlashCommand(command.id, command.payload);
        break;
      case SlashCommandActionKind.disabled:
        break;
    }
  }

  Future<void> _toggleRecording() async {
    if (_isRecording) {
      await _stopRecordingAndSend();
      return;
    }
    await _startRecording();
  }

  Future<void> _openAttachmentPicker() async {
    final supportsImages = widget.imageAttachmentsEnabled;
    final supportsFiles = widget.fileAttachmentsEnabled;
    if (!supportsImages && !supportsFiles) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('This server does not currently accept attachments.'),
        ),
      );
      return;
    }

    final choice = await showModalBottomSheet<_AttachmentSourceAction>(
      context: context,
      backgroundColor: const Color(0xFF101931),
      builder: (context) {
        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              const ListTile(
                title: Text('Add attachment'),
                subtitle: Text('Stage it in the composer before sending'),
              ),
              if (supportsImages)
                ListTile(
                  leading: const Icon(Icons.photo_library_outlined),
                  title: const Text('Photo library'),
                  subtitle: const Text('Preview an image and add instructions'),
                  onTap: () =>
                      Navigator.of(context).pop(_AttachmentSourceAction.image),
                ),
              if (supportsFiles)
                ListTile(
                  leading: const Icon(Icons.insert_drive_file_outlined),
                  title: const Text('Browse files'),
                  subtitle: const Text(
                    'Attach documents, code, text files, or images',
                  ),
                  onTap: () =>
                      Navigator.of(context).pop(_AttachmentSourceAction.file),
                ),
            ],
          ),
        );
      },
    );

    if (!mounted || choice == null) {
      return;
    }

    switch (choice) {
      case _AttachmentSourceAction.image:
        await _pickImage();
        break;
      case _AttachmentSourceAction.file:
        await _pickDocument();
        break;
    }
  }

  Future<void> _pickImage() async {
    if (!widget.imageAttachmentsEnabled) {
      _showImageAttachmentsDisabledSnackBar();
      return;
    }
    try {
      final pickedImages = await _imagePicker.pickMultiImage(imageQuality: 90);
      if (pickedImages.isEmpty || !mounted) {
        return;
      }
      final attachments = <_PendingAttachmentDraft>[];
      for (final picked in pickedImages) {
        final attachment = await _prepareImageAttachmentDraft(
          file: picked,
          name: picked.name,
        );
        if (attachment != null) {
          attachments.add(attachment);
        }
      }
      if (attachments.isEmpty) {
        return;
      }
      _appendPendingAttachments(attachments);
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('$error')));
    }
  }

  Future<void> _pickDocument() async {
    try {
      final result = await FilePicker.platform.pickFiles(
        type: FileType.any,
        allowMultiple: true,
        withData: true,
      );
      if (result == null || !mounted) {
        return;
      }
      final attachments = <_PendingAttachmentDraft>[];
      var skippedImageCount = 0;
      for (final file in result.files) {
        final xFile = file.xFile;
        final kind = _resolveAttachmentKind(
          fileName: file.name,
          mimeType: xFile.mimeType,
        );
        if (kind == _AttachmentDraftKind.image &&
            !widget.imageAttachmentsEnabled) {
          skippedImageCount += 1;
          continue;
        }
        if (kind == _AttachmentDraftKind.image) {
          final attachment = await _prepareImageAttachmentDraft(
            file: xFile,
            name: file.name,
            initialBytes: file.bytes,
          );
          if (attachment != null) {
            attachments.add(attachment);
          }
          continue;
        }
        attachments.add(
          _PendingAttachmentDraft(
            file: xFile,
            name: file.name,
            kind: kind,
            sizeBytes: file.size > 0 ? file.size : await xFile.length(),
          ),
        );
      }
      if (attachments.isEmpty) {
        if (skippedImageCount > 0) {
          _showImageAttachmentsDisabledSnackBar();
          return;
        }
        throw Exception(
          'The selected files are not accessible on this device.',
        );
      }
      _appendPendingAttachments(attachments);
      if (skippedImageCount > 0) {
        _showImageAttachmentsDisabledSnackBar();
      }
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('$error')));
    }
  }

  Future<void> _confirmCancelRecording() async {
    if (!_isRecording) {
      return;
    }

    final shouldDiscard = await showDialog<bool>(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: const Text('Discard voice note?'),
          content: const Text(
            'This recording will be deleted and will not be sent to Codex.',
          ),
          actions: <Widget>[
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Keep recording'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('Discard'),
            ),
          ],
        );
      },
    );

    if (shouldDiscard == true) {
      await _discardRecording();
    }
  }

  Future<void> _startRecording() async {
    if (_isRecording || widget.isBusy || _isSubmittingAttachments) {
      return;
    }

    try {
      await widget.onBeginRecording();
      await _audioRecorder.start();
      _recordingStopwatch = Stopwatch()..start();
      _recordingTicker?.cancel();
      _recordingTicker = Timer.periodic(const Duration(seconds: 1), (_) {
        if (mounted) {
          setState(() {});
        }
      });
      setState(() {
        _isRecording = true;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('$error')));
    }
  }

  Future<void> _stopRecordingAndSend() async {
    if (!_isRecording) {
      return;
    }

    final stagedAttachments = List<_PendingAttachmentDraft>.from(
      _pendingAttachments,
    );
    final recorder = _audioRecorder;
    _audioRecorder = widget.audioRecorderFactory();
    _recordingTicker?.cancel();
    _recordingStopwatch?.stop();
    final audioFile = await recorder.stop();
    _recordingStopwatch = null;

    setState(() {
      _isRecording = false;
    });

    if (audioFile == null) {
      await recorder.dispose();
      return;
    }

    final prompt = widget.controller.text.trim();
    if (mounted) {
      setState(() {
        _isSubmittingAttachments = true;
      });
    }

    var didSend = false;
    var usedAttachmentsFlow = false;
    try {
      if (stagedAttachments.isNotEmpty) {
        usedAttachmentsFlow = true;
        var audioName = 'voice-note.m4a';
        try {
          final resolvedName = audioFile.name.trim();
          if (resolvedName.isNotEmpty) {
            audioName = resolvedName;
          }
        } catch (_) {
          audioName = 'voice-note.m4a';
        }
        final audioAttachment = _PendingAttachmentDraft(
          file: audioFile,
          name: audioName,
          kind: _AttachmentDraftKind.audio,
        );
        final attachments = <_PendingAttachmentDraft>[
          ...stagedAttachments,
          audioAttachment,
        ];
        didSend = await _sendPendingAttachments(
          attachments,
          prompt: prompt.isEmpty ? null : prompt,
        );
      } else {
        didSend = await widget.onSendAudio(
          audioFile,
          message: prompt.isEmpty ? null : prompt,
        );
      }
    } catch (_) {
      didSend = false;
    } finally {
      await recorder.cleanup(audioFile);
      await recorder.dispose();
    }
    if (!mounted) {
      return;
    }
    setState(() {
      _isSubmittingAttachments = false;
    });
    if (didSend) {
      setState(() {
        _pendingAttachments.clear();
        _attachmentsExpanded = true;
      });
      widget.controller.clear();
      _emitDraftChanged();
      return;
    }
    if (usedAttachmentsFlow) {
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Voice note send failed.'),
        duration: Duration(seconds: 2),
      ),
    );
  }

  Future<void> _handlePrimaryAction() async {
    if (_isSubmittingAttachments) {
      return;
    }
    if (_slashQuery != null) {
      await _selectHighlightedSlashCommand();
      return;
    }
    if (_pendingAttachments.isNotEmpty) {
      final attachments = List<_PendingAttachmentDraft>.from(
        _pendingAttachments,
      );
      final prompt = widget.controller.text.trim();
      if (mounted) {
        setState(() {
          _isSubmittingAttachments = true;
        });
      }
      final didSend = await _sendPendingAttachments(
        attachments,
        prompt: prompt.isEmpty ? null : prompt,
      );
      if (!mounted) {
        return;
      }
      if (didSend) {
        setState(() {
          _pendingAttachments.clear();
          _isSubmittingAttachments = false;
        });
        widget.controller.clear();
        _emitDraftChanged();
      } else {
        setState(() {
          _isSubmittingAttachments = false;
        });
      }
      return;
    }

    await widget.onSend();
  }

  Future<void> _discardRecording() async {
    if (!_isRecording) {
      return;
    }

    final recorder = _audioRecorder;
    _audioRecorder = widget.audioRecorderFactory();
    _recordingTicker?.cancel();
    _recordingStopwatch?.stop();
    await recorder.cancel();
    await recorder.dispose();

    _recordingStopwatch = null;
    if (mounted) {
      setState(() {
        _isRecording = false;
      });
    }
  }

  void _removePendingAttachment(_PendingAttachmentDraft attachment) {
    setState(() {
      _pendingAttachments.removeWhere(
        (item) => item.identityKey == attachment.identityKey,
      );
    });
    _emitDraftChanged();
  }

  void _setPendingAttachmentRole(
    _PendingAttachmentDraft attachment,
    ProjectAssetRole? role,
  ) {
    final index = _pendingAttachments.indexWhere(
      (item) => item.identityKey == attachment.identityKey,
    );
    if (index < 0) {
      return;
    }
    setState(() {
      _pendingAttachments[index] = _pendingAttachments[index].copyWith(
        projectAssetRole: role,
      );
    });
    _emitDraftChanged();
  }

  void _clearPendingAttachments() {
    if (_pendingAttachments.isEmpty) {
      return;
    }
    setState(() {
      _pendingAttachments.clear();
      _attachmentsExpanded = true;
    });
    _emitDraftChanged();
  }

  void _toggleAttachmentsExpanded() {
    if (_pendingAttachments.isEmpty) {
      return;
    }
    setState(() {
      _attachmentsExpanded = !_attachmentsExpanded;
    });
  }

  bool _appendPendingAttachments(List<_PendingAttachmentDraft> attachments) {
    if (attachments.isEmpty || !mounted) {
      return false;
    }

    final existingPaths =
        _pendingAttachments.map((item) => item.identityKey).toSet();
    final uniqueAttachments = attachments
        .where((attachment) => !existingPaths.contains(attachment.identityKey))
        .toList();
    if (uniqueAttachments.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Those attachments are already in the tray.'),
          duration: Duration(seconds: 1),
        ),
      );
      return false;
    }

    setState(() {
      _pendingAttachments.addAll(uniqueAttachments);
      _attachmentsExpanded = true;
    });
    _emitDraftChanged();
    return true;
  }

  Future<_PendingAttachmentDraft?> _prepareImageAttachmentDraft({
    required XFile file,
    required String name,
    Uint8List? initialBytes,
  }) async {
    final originalBytes = initialBytes ?? await file.readAsBytes();
    if (!mounted) {
      return null;
    }
    final result = await Navigator.of(context).push<_ImageEditorResult>(
      MaterialPageRoute<_ImageEditorResult>(
        fullscreenDialog: true,
        builder: (context) {
          return _ImageEditorScreen(imageBytes: originalBytes, fileName: name);
        },
      ),
    );
    if (!mounted) {
      return null;
    }
    if (result == null) {
      return null;
    }

    final selectedBytes = result.bytes ?? originalBytes;
    final selectedName = result.fileName ?? name;
    final selectedFile = result.bytes == null
        ? file
        : XFile.fromData(
            selectedBytes,
            name: selectedName,
            mimeType: 'image/png',
            path: selectedName,
          );
    return _PendingAttachmentDraft(
      file: selectedFile,
      name: selectedName,
      kind: _AttachmentDraftKind.image,
      sizeBytes: selectedBytes.length,
      previewBytes: selectedBytes,
    );
  }

  bool _canAcceptPastedImages() {
    return mounted &&
        _composerFocusNode.hasFocus &&
        widget.imageAttachmentsEnabled &&
        !widget.isBusy &&
        !_isSubmittingAttachments &&
        !_isRecording;
  }

  Future<bool> _sendPendingAttachments(
    List<_PendingAttachmentDraft> attachments, {
    String? prompt,
  }) async {
    final sanitizedAttachments = _filterDisallowedImageAttachments(attachments);
    if (sanitizedAttachments.isEmpty) {
      if (mounted) {
        _showImageAttachmentsDisabledSnackBar();
      }
      return false;
    }

    try {
      final didSend = await widget.onSendAttachments(
        sanitizedAttachments,
        prompt: prompt,
      );
      if (!mounted) {
        return didSend;
      }
      if (!didSend) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Attachment send failed. Draft kept for retry.'),
            duration: Duration(seconds: 2),
          ),
        );
        return false;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Attachment job accepted.'),
          duration: Duration(seconds: 1),
        ),
      );
      return true;
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              'Attachment send failed. Draft kept for retry. $error',
            ),
            duration: const Duration(seconds: 2),
          ),
        );
      }
      return false;
    }
  }

  void _resetRecorderForSessionChange() {
    if (_isRecording) {
      unawaited(_audioRecorder.cancel());
    }
    _recordingTicker?.cancel();
    _recordingTicker = null;
    _recordingStopwatch = null;
    _audioRecorder.dispose();
    _audioRecorder = widget.audioRecorderFactory();
    if (mounted) {
      setState(() {
        _isRecording = false;
      });
    } else {
      _isRecording = false;
    }
  }

  void _applyDraft(_ComposerDraft draft, {required bool notifyParent}) {
    final nextText = draft.text;
    if (widget.controller.text != nextText) {
      widget.controller.value = TextEditingValue(
        text: nextText,
        selection: TextSelection.collapsed(offset: nextText.length),
      );
    }

    final nextAttachments = _filterDisallowedImageAttachments(
      draft.attachments,
    );
    if (mounted) {
      setState(() {
        _hasText = nextText.trim().isNotEmpty;
        _pendingAttachments
          ..clear()
          ..addAll(nextAttachments);
        if (_pendingAttachments.isEmpty) {
          _attachmentsExpanded = true;
        }
      });
    } else {
      _hasText = nextText.trim().isNotEmpty;
      _pendingAttachments
        ..clear()
        ..addAll(nextAttachments);
    }

    if (notifyParent) {
      _emitDraftChanged();
    }
  }

  void _emitDraftChanged() {
    widget.onDraftChanged(
      _ComposerDraft(
        text: widget.controller.text,
        attachments: List<_PendingAttachmentDraft>.from(_pendingAttachments),
        codexRunOptions: widget.draft.codexRunOptions,
      ),
    );
  }

  bool _sameDraftAttachments(
    List<_PendingAttachmentDraft> left,
    List<_PendingAttachmentDraft> right,
  ) {
    if (identical(left, right)) {
      return true;
    }
    if (left.length != right.length) {
      return false;
    }
    for (var index = 0; index < left.length; index += 1) {
      if (left[index].identityKey != right[index].identityKey) {
        return false;
      }
    }
    return true;
  }

  Future<void> _handlePastedImages(
    List<ClipboardImagePastePayload> images,
  ) async {
    if (images.isEmpty || !mounted) {
      return;
    }
    if (!widget.imageAttachmentsEnabled) {
      _showImageAttachmentsDisabledSnackBar();
      return;
    }

    final attachments = <_PendingAttachmentDraft>[];
    for (final image in images) {
      final attachment = await _prepareImageAttachmentDraft(
        file: XFile.fromData(
          image.bytes,
          name: image.fileName,
          mimeType: image.mimeType,
          path: image.fileName,
        ),
        name: image.fileName,
        initialBytes: image.bytes,
      );
      if (attachment != null) {
        attachments.add(attachment);
      }
    }

    if (attachments.isEmpty) {
      return;
    }

    _appendPendingAttachments(attachments);
    if (!mounted) {
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          attachments.length == 1
              ? 'Image pasted into the attachment tray.'
              : '${attachments.length} images pasted into the attachment tray.',
        ),
        duration: const Duration(seconds: 1),
      ),
    );
  }

  List<_PendingAttachmentDraft> _filterDisallowedImageAttachments(
    List<_PendingAttachmentDraft> attachments,
  ) {
    if (widget.imageAttachmentsEnabled) {
      return List<_PendingAttachmentDraft>.from(attachments);
    }
    return attachments.where((attachment) => !attachment.isImage).toList();
  }

  void _showImageAttachmentsDisabledSnackBar() {
    if (!mounted) {
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Image attachments are disabled on this server.'),
        duration: Duration(seconds: 2),
      ),
    );
  }

  String _composerHintText() {
    if (_pendingAttachments.isEmpty) {
      return 'Message';
    }
    if (_pendingAttachments.length == 1 && _pendingAttachments.first.isAudio) {
      return 'Add text for this voice note';
    }
    if (_pendingAttachments.length == 1 && _pendingAttachments.first.isImage) {
      return 'Add text for this image';
    }
    return 'Add text for these attachments';
  }

  _AttachmentDraftKind _resolveAttachmentKind({
    required String fileName,
    String? mimeType,
  }) {
    if (mimeType != null && mimeType.toLowerCase().startsWith('image/')) {
      return _AttachmentDraftKind.image;
    }
    if (isAudioAttachmentDraftInput(fileName: fileName, mimeType: mimeType)) {
      return _AttachmentDraftKind.audio;
    }
    final normalizedName = fileName.toLowerCase();
    if (_looksLikeImagePath(normalizedName)) {
      return _AttachmentDraftKind.image;
    }
    return _AttachmentDraftKind.file;
  }

  bool _looksLikeImagePath(String value) {
    return value.endsWith('.bmp') ||
        value.endsWith('.gif') ||
        value.endsWith('.jpeg') ||
        value.endsWith('.jpg') ||
        value.endsWith('.png') ||
        value.endsWith('.tif') ||
        value.endsWith('.tiff') ||
        value.endsWith('.webp');
  }

  String _formatDuration() {
    final elapsed = _recordingStopwatch?.elapsed ?? Duration.zero;
    final minutes = elapsed.inMinutes.toString().padLeft(2, '0');
    final seconds = (elapsed.inSeconds % 60).toString().padLeft(2, '0');
    return '$minutes:$seconds';
  }

  void _showVoiceUnavailableMessage() {
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(widget.voiceStatusText)));
  }
}

enum _AttachmentDraftKind { image, audio, file }

enum _AttachmentSourceAction { image, file }

class _PendingAttachmentDraft {
  const _PendingAttachmentDraft({
    required this.file,
    required this.name,
    required this.kind,
    this.sizeBytes,
    this.previewBytes,
    this.projectAssetRole,
  });

  final XFile file;
  final String name;
  final _AttachmentDraftKind kind;
  final int? sizeBytes;
  final Uint8List? previewBytes;
  final ProjectAssetRole? projectAssetRole;

  bool get isImage => kind == _AttachmentDraftKind.image;

  bool get isAudio => kind == _AttachmentDraftKind.audio;

  String get badgeLabel {
    if (isImage) {
      return 'Image';
    }
    if (isAudio) {
      return 'Audio';
    }
    return 'File';
  }

  String get identityKey => '${kind.name}:$name:${sizeBytes ?? 0}';

  _PendingAttachmentDraft copyWith({ProjectAssetRole? projectAssetRole}) {
    return _PendingAttachmentDraft(
      file: file,
      name: name,
      kind: kind,
      sizeBytes: sizeBytes,
      previewBytes: previewBytes,
      projectAssetRole: projectAssetRole,
    );
  }
}

enum _RenameChatDraftKind { manual, generatedText, generatedAudio }

class _RenameChatDraft {
  const _RenameChatDraft._({
    required this.kind,
    this.title,
    this.instructions,
    this.audioFile,
  });

  factory _RenameChatDraft.manual(String title) {
    return _RenameChatDraft._(kind: _RenameChatDraftKind.manual, title: title);
  }

  factory _RenameChatDraft.generatedText(String? instructions) {
    return _RenameChatDraft._(
      kind: _RenameChatDraftKind.generatedText,
      instructions: instructions,
    );
  }

  factory _RenameChatDraft.generatedAudio({
    required XFile audioFile,
    String? instructions,
  }) {
    return _RenameChatDraft._(
      kind: _RenameChatDraftKind.generatedAudio,
      instructions: instructions,
      audioFile: audioFile,
    );
  }

  final _RenameChatDraftKind kind;
  final String? title;
  final String? instructions;
  final XFile? audioFile;
}

class _RenameChatSheet extends StatefulWidget {
  const _RenameChatSheet({
    required this.initialTitle,
    required this.voiceEnabled,
    required this.voiceStatusText,
    required this.audioRecorderFactory,
    required this.onBeginRecording,
  });

  final String initialTitle;
  final bool voiceEnabled;
  final String voiceStatusText;
  final AudioNoteRecorder Function() audioRecorderFactory;
  final Future<void> Function() onBeginRecording;

  @override
  State<_RenameChatSheet> createState() => _RenameChatSheetState();
}

class _RenameChatSheetState extends State<_RenameChatSheet> {
  late final TextEditingController _manualTitleController;
  late final TextEditingController _instructionsController;
  late AudioNoteRecorder _audioRecorder;
  _RenameChatMode _mode = _RenameChatMode.manual;
  XFile? _recordedAudio;
  Stopwatch? _recordingStopwatch;
  Timer? _recordingTicker;
  bool _isRecording = false;
  bool _isSubmitting = false;
  bool _audioReturnedToCaller = false;

  @override
  void initState() {
    super.initState();
    _manualTitleController = TextEditingController(text: widget.initialTitle);
    _instructionsController = TextEditingController();
    _audioRecorder = widget.audioRecorderFactory();
  }

  @override
  void dispose() {
    _recordingTicker?.cancel();
    _manualTitleController.dispose();
    _instructionsController.dispose();
    if (_isRecording) {
      unawaited(_audioRecorder.cancel());
    }
    final recordedAudio = _recordedAudio;
    if (recordedAudio != null && !_audioReturnedToCaller) {
      unawaited(_audioRecorder.cleanup(recordedAudio));
    }
    unawaited(_audioRecorder.dispose());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final bottomInset = MediaQuery.viewInsetsOf(context).bottom;
    return SafeArea(
      top: false,
      child: SingleChildScrollView(
        padding: EdgeInsets.fromLTRB(20, 8, 20, 20 + bottomInset),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Row(
              children: <Widget>[
                const Expanded(
                  child: Text(
                    'Rename chat',
                    style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
                  ),
                ),
                IconButton(
                  onPressed:
                      _isSubmitting ? null : () => Navigator.of(context).pop(),
                  icon: const Icon(Icons.close_rounded),
                  tooltip: 'Close',
                ),
              ],
            ),
            const SizedBox(height: 14),
            SegmentedButton<_RenameChatMode>(
              segments: const <ButtonSegment<_RenameChatMode>>[
                ButtonSegment<_RenameChatMode>(
                  value: _RenameChatMode.manual,
                  icon: Icon(Icons.edit_outlined),
                  label: Text('Manual'),
                ),
                ButtonSegment<_RenameChatMode>(
                  value: _RenameChatMode.generated,
                  icon: Icon(Icons.auto_awesome_outlined),
                  label: Text('Suggest'),
                ),
              ],
              selected: <_RenameChatMode>{_mode},
              onSelectionChanged: _isSubmitting
                  ? null
                  : (selection) {
                      setState(() {
                        _mode = selection.first;
                      });
                    },
            ),
            const SizedBox(height: 18),
            if (_mode == _RenameChatMode.manual)
              TextField(
                controller: _manualTitleController,
                autofocus: true,
                maxLength: 120,
                minLines: 1,
                maxLines: 2,
                textInputAction: TextInputAction.done,
                onSubmitted: (_) => _submit(),
                decoration: const InputDecoration(
                  labelText: 'Chat name',
                  border: OutlineInputBorder(),
                ),
              )
            else
              Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: <Widget>[
                  TextField(
                    controller: _instructionsController,
                    maxLength: 2000,
                    minLines: 3,
                    maxLines: 6,
                    decoration: const InputDecoration(
                      labelText: 'Title instructions',
                      hintText: 'Make it about the release plan',
                      border: OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 10),
                  _buildVoiceTitleControls(),
                ],
              ),
            const SizedBox(height: 18),
            FilledButton.icon(
              onPressed: _isSubmitting ? null : _submit,
              icon: Icon(
                _mode == _RenameChatMode.manual
                    ? Icons.check_rounded
                    : Icons.auto_awesome_rounded,
              ),
              label: Text(
                _mode == _RenameChatMode.manual ? 'Save name' : 'Generate name',
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildVoiceTitleControls() {
    final recordedAudio = _recordedAudio;
    if (_isRecording) {
      return Row(
        children: <Widget>[
          Expanded(
            child: _VoiceStatusCard(
              icon: Icons.mic_rounded,
              title: 'Recording',
              subtitle: 'Speak the title direction',
              color: const Color(0xFF25D366),
              trailing: _StatusPill(
                label: _formatRenameRecordingDuration(),
                backgroundColor: const Color(0xFF0B3D25),
                foregroundColor: const Color(0xFFB7F5CF),
              ),
              titleMaxLines: 1,
              subtitleMaxLines: 1,
            ),
          ),
          const SizedBox(width: 10),
          FilledButton(
            onPressed: _stopRecording,
            style: FilledButton.styleFrom(
              minimumSize: const Size(52, 52),
              padding: EdgeInsets.zero,
            ),
            child: const Icon(Icons.stop_rounded),
          ),
        ],
      );
    }

    if (recordedAudio != null) {
      return Row(
        children: <Widget>[
          const Expanded(
            child: _VoiceStatusCard(
              icon: Icons.graphic_eq_rounded,
              title: 'Voice instruction ready',
              subtitle: 'It will be transcribed before naming',
              color: Color(0xFF55D6BE),
              titleMaxLines: 1,
              subtitleMaxLines: 1,
            ),
          ),
          const SizedBox(width: 10),
          IconButton.filledTonal(
            onPressed: _discardRecordedAudio,
            icon: const Icon(Icons.delete_outline_rounded),
            tooltip: 'Discard voice instruction',
          ),
        ],
      );
    }

    return OutlinedButton.icon(
      onPressed: _isSubmitting ? null : _startRecording,
      icon: Icon(
        widget.voiceEnabled ? Icons.mic_rounded : Icons.mic_off_rounded,
      ),
      label: Text(
        widget.voiceEnabled
            ? 'Record title instruction'
            : widget.voiceStatusText,
        overflow: TextOverflow.ellipsis,
      ),
    );
  }

  Future<void> _startRecording() async {
    if (!widget.voiceEnabled) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(widget.voiceStatusText)));
      return;
    }
    if (_isRecording || _isSubmitting) {
      return;
    }

    try {
      await _discardRecordedAudio();
      await widget.onBeginRecording();
      await _audioRecorder.start();
      _recordingStopwatch = Stopwatch()..start();
      _recordingTicker?.cancel();
      _recordingTicker = Timer.periodic(const Duration(seconds: 1), (_) {
        if (mounted) {
          setState(() {});
        }
      });
      setState(() {
        _isRecording = true;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('$error')));
    }
  }

  Future<void> _stopRecording() async {
    if (!_isRecording) {
      return;
    }

    final audioFile = await _audioRecorder.stop();
    _recordingTicker?.cancel();
    _recordingStopwatch?.stop();
    _recordingStopwatch = null;
    if (!mounted) {
      return;
    }
    setState(() {
      _isRecording = false;
      _recordedAudio = audioFile;
    });
  }

  Future<void> _discardRecordedAudio() async {
    final audioFile = _recordedAudio;
    if (audioFile == null) {
      return;
    }
    _recordedAudio = null;
    await _audioRecorder.cleanup(audioFile);
    if (mounted) {
      setState(() {});
    }
  }

  void _submit() {
    if (_isRecording) {
      return;
    }

    setState(() {
      _isSubmitting = true;
    });

    if (_mode == _RenameChatMode.manual) {
      final title = _manualTitleController.text.trim();
      if (title.isEmpty) {
        setState(() {
          _isSubmitting = false;
        });
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('Enter a chat name.')));
        return;
      }
      Navigator.of(context).pop(_RenameChatDraft.manual(title));
      return;
    }

    final instructions = _instructionsController.text.trim();
    final audioFile = _recordedAudio;
    if (audioFile != null) {
      _audioReturnedToCaller = true;
      Navigator.of(context).pop(
        _RenameChatDraft.generatedAudio(
          audioFile: audioFile,
          instructions: instructions.isEmpty ? null : instructions,
        ),
      );
      return;
    }

    Navigator.of(context).pop(
      _RenameChatDraft.generatedText(
        instructions.isEmpty ? null : instructions,
      ),
    );
  }

  String _formatRenameRecordingDuration() {
    final elapsed = _recordingStopwatch?.elapsed ?? Duration.zero;
    final minutes = elapsed.inMinutes.remainder(60).toString().padLeft(2, '0');
    final seconds = elapsed.inSeconds.remainder(60).toString().padLeft(2, '0');
    return '$minutes:$seconds';
  }
}

Color _colorFromHex(String value) {
  final normalized = value.trim().replaceFirst('#', '');
  if (normalized.length != 6) {
    return const Color(0xFF55D6BE);
  }
  final parsed = int.tryParse(normalized, radix: 16);
  if (parsed == null) {
    return const Color(0xFF55D6BE);
  }
  return Color(0xFF000000 | parsed);
}

String _presetLabel(AgentPreset preset) {
  return switch (preset) {
    AgentPreset.solo => 'Solo',
    AgentPreset.review => 'Review',
    AgentPreset.triad => 'Triad',
    AgentPreset.supervisor => 'Supervisor',
  };
}

class _AgentProfilePill extends StatelessWidget {
  const _AgentProfilePill({required this.label, required this.color});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: Color.alphaBlend(
          color.withValues(alpha: 0.2),
          const Color(0xFF121A31),
        ),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.45)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          ),
          const SizedBox(width: 8),
          Text(
            label,
            style: const TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w600,
              color: Colors.white,
            ),
          ),
        ],
      ),
    );
  }
}

class NewProjectFactoryDraft {
  const NewProjectFactoryDraft({
    required this.name,
    required this.businessType,
    required this.primaryGoal,
    required this.platforms,
    required this.backend,
    required this.frontendStrategy,
    required this.logoMode,
    required this.visualReferencePaths,
    required this.referenceImages,
  });

  final String name;
  final String businessType;
  final String primaryGoal;
  final List<String> platforms;
  final String backend;
  final String frontendStrategy;
  final String logoMode;
  final List<String> visualReferencePaths;
  final List<XFile> referenceImages;
}

class _NewProjectBasics {
  const _NewProjectBasics({
    required this.title,
    required this.adminEmails,
  });

  final String title;
  final List<String> adminEmails;
}

class _NewProjectBasicsDialog extends StatefulWidget {
  const _NewProjectBasicsDialog();

  @override
  State<_NewProjectBasicsDialog> createState() =>
      _NewProjectBasicsDialogState();
}

class _NewProjectBasicsDialogState extends State<_NewProjectBasicsDialog> {
  final TextEditingController _titleController = TextEditingController();
  final TextEditingController _emailController = TextEditingController();
  final List<String> _adminEmails = <String>[];
  String? _errorText;

  @override
  void dispose() {
    _titleController.dispose();
    _emailController.dispose();
    super.dispose();
  }

  String _normalizedEmail(String value) => value.trim().toLowerCase();

  bool get _canSubmit =>
      _titleController.text.trim().isNotEmpty && _adminEmails.isNotEmpty;

  bool _looksLikeEmail(String value) {
    return RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(value);
  }

  void _addEmail() {
    final email = _normalizedEmail(_emailController.text);
    if (!_looksLikeEmail(email)) {
      setState(() {
        _errorText = 'Enter a valid admin email.';
      });
      return;
    }
    if (_adminEmails.contains(email)) {
      _emailController.clear();
      setState(() {
        _errorText = null;
      });
      return;
    }
    setState(() {
      _adminEmails.add(email);
      _emailController.clear();
      _errorText = null;
    });
  }

  void _submit() {
    final pendingEmail = _emailController.text.trim();
    if (pendingEmail.isNotEmpty) {
      _addEmail();
      if (_emailController.text.trim().isNotEmpty) {
        return;
      }
    }
    final title = _titleController.text.trim();
    if (title.isEmpty) {
      setState(() {
        _errorText = 'Project title is required.';
      });
      return;
    }
    if (_adminEmails.isEmpty) {
      setState(() {
        _errorText = 'Add at least one admin email.';
      });
      return;
    }
    Navigator.of(context).pop(
      _NewProjectBasics(
        title: title,
        adminEmails: List<String>.unmodifiable(_adminEmails),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('New project'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            TextField(
              controller: _titleController,
              autofocus: true,
              maxLength: 80,
              textInputAction: TextInputAction.next,
              onChanged: (_) {
                setState(() {
                  if (_errorText != null && _errorText!.contains('title')) {
                    _errorText = null;
                  }
                });
              },
              decoration: InputDecoration(
                labelText: 'Project title',
                errorText: _errorText != null && _errorText!.contains('title')
                    ? _errorText
                    : null,
              ),
            ),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Expanded(
                  child: TextField(
                    controller: _emailController,
                    keyboardType: TextInputType.emailAddress,
                    textInputAction: TextInputAction.done,
                    decoration: InputDecoration(
                      labelText: 'Admin email',
                      errorText:
                          _errorText != null && !_errorText!.contains('title')
                              ? _errorText
                              : null,
                    ),
                    onSubmitted: (_) => _addEmail(),
                  ),
                ),
                const SizedBox(width: 8),
                IconButton(
                  onPressed: _addEmail,
                  icon: const Icon(Icons.add),
                  tooltip: 'Add admin email',
                ),
              ],
            ),
            if (_adminEmails.isNotEmpty) ...<Widget>[
              const SizedBox(height: 12),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: _adminEmails.map((email) {
                  return InputChip(
                    label: Text(email),
                    onDeleted: () {
                      setState(() {
                        _adminEmails.remove(email);
                      });
                    },
                  );
                }).toList(),
              ),
            ],
          ],
        ),
      ),
      actions: <Widget>[
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: _canSubmit ? _submit : null,
          child: const Text('Start'),
        ),
      ],
    );
  }
}

class ProjectFactoryGuidedIntakeCard extends StatefulWidget {
  const ProjectFactoryGuidedIntakeCard({
    super.key,
    required this.intake,
    required this.onAnswer,
    required this.onPreview,
  });

  final ProjectFactoryGuidedIntake intake;
  final Future<void> Function(String questionId, Object? value) onAnswer;
  final Future<void> Function() onPreview;

  @override
  State<ProjectFactoryGuidedIntakeCard> createState() =>
      _ProjectFactoryGuidedIntakeCardState();
}

class _ProjectFactoryGuidedIntakeCardState
    extends State<ProjectFactoryGuidedIntakeCard> {
  final Map<String, TextEditingController> _controllers =
      <String, TextEditingController>{};

  @override
  void dispose() {
    for (final controller in _controllers.values) {
      controller.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Row(
              children: <Widget>[
                const Icon(Icons.route_outlined),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    'Guided intake',
                    style: theme.textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
                _StatusPill(
                  label: widget.intake.status.replaceAll('_', ' '),
                  backgroundColor: widget.intake.isBlocked
                      ? const Color(0xFF3A2714)
                      : const Color(0xFF143A32),
                  foregroundColor: widget.intake.isBlocked
                      ? const Color(0xFFFFD9A3)
                      : const Color(0xFF8FF5DE),
                ),
              ],
            ),
            if (widget.intake.missingFields.isNotEmpty) ...<Widget>[
              const SizedBox(height: 10),
              ...widget.intake.missingFields.map(
                (field) => Text(
                  field['message']?.toString() ?? field['field'].toString(),
                  style: const TextStyle(color: Color(0xFFFFD27D)),
                ),
              ),
            ],
            const SizedBox(height: 12),
            ...widget.intake.questions.map(_buildQuestion),
            if (widget.intake.contractPreview != null) ...<Widget>[
              const SizedBox(height: 12),
              _buildPreview(widget.intake.contractPreview!),
            ],
            if (widget.intake.blockers.isNotEmpty) ...<Widget>[
              const SizedBox(height: 12),
              Text('Blockers', style: theme.textTheme.titleSmall),
              const SizedBox(height: 6),
              ...widget.intake.blockers.map(
                (blocker) => Text(
                  '${blocker['scope']}: ${blocker['message']}',
                  style: TextStyle(
                    color: blocker['external'] == true
                        ? const Color(0xFFFFD27D)
                        : theme.colorScheme.error,
                  ),
                ),
              ),
            ],
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: <Widget>[
                OutlinedButton.icon(
                  onPressed: widget.onPreview,
                  icon: const Icon(Icons.fact_check_outlined),
                  label: const Text('Preview contract'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildQuestion(Map<String, dynamic> question) {
    final id = question['id']?.toString() ?? '';
    final options = _projectFactoryMapList(question['options']);
    final controller =
        _controllers.putIfAbsent(id, () => TextEditingController());
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Text(
            question['title']?.toString() ?? id,
            style: const TextStyle(fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 4),
          Text(question['prompt']?.toString() ?? ''),
          if (options.isNotEmpty) ...<Widget>[
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: options.map((option) {
                return ActionChip(
                  label: Text(
                    option['recommended'] == true
                        ? '${option['label']} (recommended)'
                        : option['label']?.toString() ?? '',
                  ),
                  onPressed: () => widget.onAnswer(id, option['value']),
                );
              }).toList(),
            ),
          ],
          const SizedBox(height: 8),
          TextField(
            controller: controller,
            decoration: const InputDecoration(
              labelText: 'Answer',
              prefixIcon: Icon(Icons.edit_outlined),
            ),
            onSubmitted: (value) => widget.onAnswer(id, value),
          ),
          Align(
            alignment: Alignment.centerRight,
            child: TextButton(
              onPressed: () => widget.onAnswer(id, controller.text),
              child: const Text('Save answer'),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPreview(Map<String, dynamic> preview) {
    final decisions = _projectFactoryMap(preview['decisions']);
    final defaults = _projectFactoryMap(preview['defaults']);
    return DecoratedBox(
      decoration: BoxDecoration(
        color: const Color(0xFF101931),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFF263454)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            const Text(
              'Contract preview',
              style: TextStyle(fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 8),
            Text('Name: ${decisions['name'] ?? ''}'),
            Text(
                'Platforms: ${(decisions['platforms'] as List?)?.join(', ') ?? ''}'),
            Text('Preview: ${defaults['previewUrl'] ?? ''}'),
          ],
        ),
      ),
    );
  }
}

class NewProjectFactoryDialog extends StatefulWidget {
  const NewProjectFactoryDialog({
    super.key,
    required this.options,
    this.onOpenHistory,
  });

  final ProjectFactoryOptions options;
  final Future<void> Function()? onOpenHistory;

  @override
  State<NewProjectFactoryDialog> createState() =>
      NewProjectFactoryDialogState();
}

class NewProjectFactoryDialogState extends State<NewProjectFactoryDialog> {
  final TextEditingController _nameController = TextEditingController();
  final TextEditingController _goalController = TextEditingController();
  final TextEditingController _visualReferencesController =
      TextEditingController();
  final List<XFile> _referenceImages = <XFile>[];
  late String _businessType;
  late String _backend;
  late String _frontendStrategy;
  late String _logoMode;
  late Set<String> _platforms;

  @override
  void initState() {
    super.initState();
    _businessType = widget.options.businessTypes.isNotEmpty
        ? widget.options.businessTypes.first
        : 'other';
    _backend = widget.options.defaultBackend;
    _frontendStrategy = widget.options.defaultFrontendStrategy;
    _logoMode = widget.options.logoModes.isNotEmpty
        ? widget.options.logoModes.first
        : 'generate';
    _platforms = widget.options.defaultPlatforms.toSet();
  }

  @override
  void dispose() {
    _nameController.dispose();
    _goalController.dispose();
    _visualReferencesController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final businessTypes = widget.options.businessTypes.isNotEmpty
        ? widget.options.businessTypes
        : <String>['other'];
    final backends = widget.options.backends.isNotEmpty
        ? widget.options.backends
        : <String>['fastapi'];
    final logoModes = widget.options.logoModes.isNotEmpty
        ? widget.options.logoModes
        : <String>['generate'];
    final platforms = widget.options.platforms.isNotEmpty
        ? widget.options.platforms
        : <String>['ios', 'android', 'web'];
    final frontendStrategies = widget.options.frontendStrategies.isNotEmpty
        ? widget.options.frontendStrategies
        : const <Map<String, dynamic>>[
            <String, dynamic>{
              'id': 'flutter',
              'display_name': 'Flutter',
              'project_kind': 'mobile_web',
            },
            <String, dynamic>{
              'id': 'svelte',
              'display_name': 'Svelte',
              'project_kind': 'web',
            },
          ];
    final strategyIds = frontendStrategies
        .map((strategy) => strategy['id'] as String? ?? '')
        .where((id) => id.isNotEmpty)
        .toList(growable: false);
    if (!strategyIds.contains(_frontendStrategy) && strategyIds.isNotEmpty) {
      _frontendStrategy = strategyIds.first;
    }
    final strategyBlocker = _frontendStrategy == 'svelte' &&
        (_platforms.contains('android') || _platforms.contains('ios'));
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Icon(Icons.create_new_folder_outlined),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  'New project',
                  style: theme.textTheme.titleLarge?.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              if (widget.onOpenHistory != null)
                IconButton(
                  onPressed: widget.onOpenHistory,
                  icon: const Icon(Icons.history),
                  tooltip: 'Project history',
                ),
              IconButton(
                onPressed: () => Navigator.of(context).pop(),
                icon: const Icon(Icons.close),
                tooltip: 'Close',
              ),
            ],
          ),
          const SizedBox(height: 16),
          Expanded(
            child: SingleChildScrollView(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: <Widget>[
                  TextField(
                    controller: _nameController,
                    textInputAction: TextInputAction.next,
                    decoration: const InputDecoration(
                      labelText: 'Project name',
                      prefixIcon: Icon(Icons.drive_file_rename_outline),
                    ),
                  ),
                  const SizedBox(height: 12),
                  DropdownButtonFormField<String>(
                    initialValue: _businessType,
                    decoration: const InputDecoration(
                      labelText: 'Business type',
                      prefixIcon: Icon(Icons.business_center_outlined),
                    ),
                    items: businessTypes
                        .map(
                          (type) => DropdownMenuItem<String>(
                            value: type,
                            child: Text(type),
                          ),
                        )
                        .toList(),
                    onChanged: (value) {
                      if (value == null) {
                        return;
                      }
                      setState(() => _businessType = value);
                    },
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: _goalController,
                    maxLines: 3,
                    decoration: const InputDecoration(
                      labelText: 'Primary goal',
                      prefixIcon: Icon(Icons.flag_outlined),
                    ),
                  ),
                  const SizedBox(height: 16),
                  DropdownButtonFormField<String>(
                    initialValue: _frontendStrategy,
                    decoration: const InputDecoration(
                      labelText: 'Frontend',
                      prefixIcon: Icon(Icons.dashboard_customize_outlined),
                    ),
                    items: frontendStrategies
                        .map(
                          (strategy) => DropdownMenuItem<String>(
                            value: strategy['id'] as String? ?? 'flutter',
                            child: Text(
                              strategy['display_name'] as String? ??
                                  strategy['id'] as String? ??
                                  'flutter',
                            ),
                          ),
                        )
                        .toList(),
                    onChanged: (value) {
                      if (value == null) {
                        return;
                      }
                      setState(() => _frontendStrategy = value);
                    },
                  ),
                  if (strategyBlocker) ...<Widget>[
                    const SizedBox(height: 8),
                    Text(
                      'Svelte is web-only for now. Remove Android/iOS or choose Flutter for APK and installable preview.',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.error,
                      ),
                    ),
                  ],
                  const SizedBox(height: 16),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: platforms.map((platform) {
                      return FilterChip(
                        label: Text(platform),
                        selected: _platforms.contains(platform),
                        onSelected: (selected) {
                          setState(() {
                            if (selected) {
                              _platforms.add(platform);
                            } else if (_platforms.length > 1) {
                              _platforms.remove(platform);
                            }
                          });
                        },
                      );
                    }).toList(),
                  ),
                  const SizedBox(height: 16),
                  DropdownButtonFormField<String>(
                    initialValue: _backend,
                    decoration: const InputDecoration(
                      labelText: 'Backend',
                      prefixIcon: Icon(Icons.dns_outlined),
                    ),
                    items: backends
                        .map(
                          (backend) => DropdownMenuItem<String>(
                            value: backend,
                            child: Text(backend),
                          ),
                        )
                        .toList(),
                    onChanged: (value) {
                      if (value == null) {
                        return;
                      }
                      setState(() => _backend = value);
                    },
                  ),
                  const SizedBox(height: 12),
                  DropdownButtonFormField<String>(
                    initialValue: _logoMode,
                    decoration: const InputDecoration(
                      labelText: 'Logo',
                      prefixIcon: Icon(Icons.imagesearch_roller_outlined),
                    ),
                    items: logoModes
                        .map(
                          (mode) => DropdownMenuItem<String>(
                            value: mode,
                            child: Text(mode),
                          ),
                        )
                        .toList(),
                    onChanged: (value) {
                      if (value == null) {
                        return;
                      }
                      setState(() => _logoMode = value);
                    },
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: _visualReferencesController,
                    maxLines: 2,
                    decoration: const InputDecoration(
                      labelText: 'Visual reference paths',
                      prefixIcon: Icon(Icons.image_outlined),
                    ),
                  ),
                  const SizedBox(height: 12),
                  OutlinedButton.icon(
                    onPressed: _pickReferenceImages,
                    icon: const Icon(Icons.add_photo_alternate_outlined),
                    label: const Text('Attach reference images'),
                  ),
                  if (_referenceImages.isNotEmpty) ...<Widget>[
                    const SizedBox(height: 8),
                    ..._referenceImages.map(
                      (image) => ListTile(
                        dense: true,
                        contentPadding: EdgeInsets.zero,
                        leading: const Icon(Icons.image_outlined),
                        title: Text(image.name),
                        trailing: IconButton(
                          onPressed: () {
                            setState(() {
                              _referenceImages.remove(image);
                            });
                          },
                          icon: const Icon(Icons.close),
                          tooltip: 'Remove image',
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          FilledButton.icon(
            onPressed: strategyBlocker ? null : _submit,
            icon: const Icon(Icons.play_arrow_rounded),
            label: const Text('Create'),
          ),
        ],
      ),
    );
  }

  Future<void> _pickReferenceImages() async {
    final result = await FilePicker.platform.pickFiles(
      type: FileType.image,
      allowMultiple: true,
      withData: kIsWeb,
    );
    if (result == null || result.files.isEmpty) {
      return;
    }
    final picked = <XFile>[];
    for (final file in result.files) {
      final mimeType = _mimeTypeForReferenceImage(file.name);
      if (file.path != null && file.path!.isNotEmpty) {
        picked.add(XFile(file.path!, name: file.name, mimeType: mimeType));
        continue;
      }
      final bytes = file.bytes;
      if (bytes != null) {
        picked.add(XFile.fromData(bytes, name: file.name, mimeType: mimeType));
      }
    }
    if (picked.isEmpty) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Could not read selected images.')),
      );
      return;
    }
    setState(() {
      _referenceImages.addAll(picked);
    });
  }

  void _submit() {
    final name = _nameController.text.trim();
    final goal = _goalController.text.trim();
    if (name.isEmpty || goal.isEmpty || _platforms.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Name, goal, and platform are required.')),
      );
      return;
    }
    if (_frontendStrategy == 'svelte' &&
        (_platforms.contains('android') || _platforms.contains('ios'))) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Svelte is web-only for now. Remove Android/iOS or choose Flutter.',
          ),
        ),
      );
      return;
    }
    Navigator.of(context).pop(
      NewProjectFactoryDraft(
        name: name,
        businessType: _businessType,
        primaryGoal: goal,
        platforms: _platforms.toList(growable: false),
        backend: _backend,
        frontendStrategy: _frontendStrategy,
        logoMode: _logoMode,
        visualReferencePaths: _visualReferencesController.text
            .split(',')
            .map((item) => item.trim())
            .where((item) => item.isNotEmpty)
            .toList(growable: false),
        referenceImages: List<XFile>.unmodifiable(_referenceImages),
      ),
    );
  }
}

String? _mimeTypeForReferenceImage(String filename) {
  final suffix = filename.trim().toLowerCase().split('.').last;
  return switch (suffix) {
    'png' => 'image/png',
    'jpg' || 'jpeg' => 'image/jpeg',
    'webp' => 'image/webp',
    _ => null,
  };
}

List<Map<String, dynamic>> _projectFactoryMapList(Object? value) {
  if (value is! List) {
    return const <Map<String, dynamic>>[];
  }
  return value
      .whereType<Map>()
      .map((item) => item.map((key, value) => MapEntry(key.toString(), value)))
      .toList(growable: false);
}

Map<String, dynamic> _projectFactoryMap(Object? value) {
  if (value is Map<String, dynamic>) {
    return value;
  }
  if (value is Map) {
    return value.map((key, item) => MapEntry(key.toString(), item));
  }
  return const <String, dynamic>{};
}

typedef ProjectFactoryJobPoller = Future<ProjectFactoryJob> Function(
    String jobId);
typedef ProjectFactoryJobLister = Future<List<ProjectFactoryJobSummary>>
    Function();
typedef ProjectFactoryProjectPathOpener = Future<void> Function(
    String projectPath);
typedef WebPreviewLister = Future<List<WebPreview>> Function();
typedef WebPreviewInviteLister = Future<List<WebPreviewInvite>> Function(
    String previewId);
typedef WebPreviewInviteCreator = Future<WebPreviewInvite> Function(
  String previewId, {
  int? ttlSeconds,
  bool singleUse,
  String? email,
  String role,
});
typedef WebPreviewInviteMutator = Future<WebPreviewInvite> Function({
  required String previewId,
  required String inviteId,
});
typedef WebPreviewMutator = Future<WebPreview> Function({
  required String previewId,
  int? ttlSeconds,
  String? reason,
});
typedef WebPreviewUrlOpener = Future<void> Function(String url);

class ProjectFactoryHistoryDialog extends StatefulWidget {
  const ProjectFactoryHistoryDialog({
    super.key,
    required this.listJobs,
    required this.getJob,
    required this.onOpenProjectPath,
    this.listWebPreviews,
    this.listWebPreviewInvites,
    this.createWebPreviewInvite,
    this.resendWebPreviewInvite,
    this.expireWebPreviewInvite,
    this.revokeWebPreviewInvite,
    this.syncWebPreviewInvite,
    this.disableWebPreview,
    this.expireWebPreview,
    this.extendWebPreview,
    this.onOpenWebPreviewUrl,
  });

  final ProjectFactoryJobLister listJobs;
  final ProjectFactoryJobPoller getJob;
  final ProjectFactoryProjectPathOpener onOpenProjectPath;
  final WebPreviewLister? listWebPreviews;
  final WebPreviewInviteLister? listWebPreviewInvites;
  final WebPreviewInviteCreator? createWebPreviewInvite;
  final WebPreviewInviteMutator? resendWebPreviewInvite;
  final WebPreviewInviteMutator? expireWebPreviewInvite;
  final WebPreviewInviteMutator? revokeWebPreviewInvite;
  final WebPreviewInviteMutator? syncWebPreviewInvite;
  final WebPreviewMutator? disableWebPreview;
  final WebPreviewMutator? expireWebPreview;
  final WebPreviewMutator? extendWebPreview;
  final WebPreviewUrlOpener? onOpenWebPreviewUrl;

  @override
  State<ProjectFactoryHistoryDialog> createState() =>
      _ProjectFactoryHistoryDialogState();
}

class _ProjectFactoryHistoryDialogState
    extends State<ProjectFactoryHistoryDialog> {
  bool _loading = true;
  String? _error;
  List<ProjectFactoryJobSummary> _jobs = <ProjectFactoryJobSummary>[];

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final jobs = await widget.listJobs();
      if (!mounted) {
        return;
      }
      setState(() {
        _jobs = jobs;
        _loading = false;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _error = error.toString();
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Row(
        children: <Widget>[
          const Icon(Icons.history),
          const SizedBox(width: 12),
          const Expanded(child: Text('Project history')),
          if (widget.listWebPreviews != null)
            IconButton(
              onPressed: _openWebPreviews,
              icon: const Icon(Icons.language),
              tooltip: 'Web previews',
            ),
          IconButton(
            onPressed: _load,
            icon: const Icon(Icons.refresh),
            tooltip: 'Refresh',
          ),
        ],
      ),
      content: SizedBox(width: 620, child: _buildContent(context)),
      actions: <Widget>[
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Close'),
        ),
      ],
    );
  }

  Widget _buildContent(BuildContext context) {
    if (_loading) {
      return const SizedBox(
        height: 160,
        child: Center(child: CircularProgressIndicator()),
      );
    }
    if (_error != null) {
      return SizedBox(height: 160, child: Center(child: Text(_error!)));
    }
    if (_jobs.isEmpty) {
      return const SizedBox(
        height: 160,
        child: Center(child: Text('No project factory history')),
      );
    }
    return ConstrainedBox(
      constraints: const BoxConstraints(maxHeight: 520),
      child: ListView.separated(
        shrinkWrap: true,
        itemCount: _jobs.length,
        separatorBuilder: (_, __) => const Divider(height: 1),
        itemBuilder: (context, index) => _ProjectFactoryHistoryTile(
          job: _jobs[index],
          onWatch: () => _watchJob(_jobs[index]),
          onOpen: _jobs[index].isReady && _jobs[index].projectPath != null
              ? () => _openProject(_jobs[index].projectPath!)
              : null,
          onOpenPreview: _jobs[index].initialPreviewRelease.hasPreviewUrl
              ? (url) => _openPreviewUrl(url)
              : null,
        ),
      ),
    );
  }

  Future<void> _watchJob(ProjectFactoryJobSummary summary) async {
    final detail = await widget.getJob(summary.jobId);
    if (!mounted) {
      return;
    }
    final result = await showDialog<ProjectFactoryJob>(
      context: context,
      barrierDismissible: detail.isTerminal,
      builder: (context) => ProjectFactoryProgressDialog(
        initialJob: detail,
        pollJob: widget.getJob,
      ),
    );
    final targetPath = result?.targetPath;
    if (result != null && result.isReady && targetPath != null) {
      await _openProject(targetPath);
    }
    await _load();
  }

  Future<void> _openProject(String projectPath) async {
    await widget.onOpenProjectPath(projectPath);
    if (!mounted) {
      return;
    }
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(const SnackBar(content: Text('Project workspace opened.')));
  }

  Future<void> _openPreviewUrl(String url) async {
    final callback = widget.onOpenWebPreviewUrl;
    if (callback != null) {
      await callback(url);
      return;
    }
    final uri = Uri.tryParse(url);
    if (uri == null) {
      return;
    }
    await launchUrl(uri, mode: LaunchMode.externalApplication);
  }

  Future<void> _openWebPreviews() async {
    final listWebPreviews = widget.listWebPreviews;
    if (listWebPreviews == null) {
      return;
    }
    await showDialog<void>(
      context: context,
      builder: (context) => WebPreviewPanelDialog(
        listWebPreviews: listWebPreviews,
        listInvites: widget.listWebPreviewInvites,
        createInvite: widget.createWebPreviewInvite,
        resendInvite: widget.resendWebPreviewInvite,
        expireInvite: widget.expireWebPreviewInvite,
        revokeInvite: widget.revokeWebPreviewInvite,
        syncInvite: widget.syncWebPreviewInvite,
        disablePreview: widget.disableWebPreview,
        expirePreview: widget.expireWebPreview,
        extendPreview: widget.extendWebPreview,
        onOpenUrl: widget.onOpenWebPreviewUrl,
      ),
    );
  }
}

class WebPreviewPanelDialog extends StatefulWidget {
  const WebPreviewPanelDialog({
    super.key,
    required this.listWebPreviews,
    this.listInvites,
    this.createInvite,
    this.resendInvite,
    this.expireInvite,
    this.revokeInvite,
    this.syncInvite,
    this.disablePreview,
    this.expirePreview,
    this.extendPreview,
    this.onOpenUrl,
  });

  final WebPreviewLister listWebPreviews;
  final WebPreviewInviteLister? listInvites;
  final WebPreviewInviteCreator? createInvite;
  final WebPreviewInviteMutator? resendInvite;
  final WebPreviewInviteMutator? expireInvite;
  final WebPreviewInviteMutator? revokeInvite;
  final WebPreviewInviteMutator? syncInvite;
  final WebPreviewMutator? disablePreview;
  final WebPreviewMutator? expirePreview;
  final WebPreviewMutator? extendPreview;
  final WebPreviewUrlOpener? onOpenUrl;

  @override
  State<WebPreviewPanelDialog> createState() => _WebPreviewPanelDialogState();
}

class _WebPreviewPanelDialogState extends State<WebPreviewPanelDialog> {
  bool _loading = true;
  String? _error;
  List<WebPreview> _previews = <WebPreview>[];

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final previews = await widget.listWebPreviews();
      if (!mounted) {
        return;
      }
      setState(() {
        _previews = previews;
        _loading = false;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _error = error.toString();
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Row(
        children: <Widget>[
          const Icon(Icons.language),
          const SizedBox(width: 12),
          const Expanded(child: Text('Web previews')),
          IconButton(
            onPressed: _load,
            icon: const Icon(Icons.refresh),
            tooltip: 'Refresh previews',
          ),
        ],
      ),
      content: SizedBox(width: 680, child: _buildContent(context)),
      actions: <Widget>[
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Close'),
        ),
      ],
    );
  }

  Widget _buildContent(BuildContext context) {
    if (_loading) {
      return const SizedBox(
        height: 180,
        child: Center(child: CircularProgressIndicator()),
      );
    }
    if (_error != null) {
      return SizedBox(height: 180, child: Center(child: Text(_error!)));
    }
    if (_previews.isEmpty) {
      return const SizedBox(
        height: 180,
        child: Center(child: Text('No web previews')),
      );
    }
    return ConstrainedBox(
      constraints: const BoxConstraints(maxHeight: 560),
      child: ListView.separated(
        shrinkWrap: true,
        itemCount: _previews.length,
        separatorBuilder: (_, __) => const SizedBox(height: 12),
        itemBuilder: (context, index) => _WebPreviewCard(
          preview: _previews[index],
          onOpen: _previews[index].isActive
              ? () => _openUrl(_previews[index].previewUrl)
              : null,
          onCopy: _previews[index].previewUrl.isEmpty
              ? null
              : () => unawaited(
                    _copyPreviewText(context, _previews[index].previewUrl),
                  ),
          onInvites: widget.listInvites == null
              ? null
              : () => _openInvites(_previews[index]),
          onExtend: widget.extendPreview == null
              ? null
              : () => _mutatePreview(
                    _previews[index],
                    widget.extendPreview,
                    ttlSeconds: 7 * 24 * 60 * 60,
                    reason: 'extended from mobile workbench',
                  ),
          onExpire: widget.expirePreview == null
              ? null
              : () => _mutatePreview(
                    _previews[index],
                    widget.expirePreview,
                    reason: 'expired from mobile workbench',
                  ),
          onDisable: widget.disablePreview == null
              ? null
              : () => _mutatePreview(
                    _previews[index],
                    widget.disablePreview,
                    reason: 'disabled from mobile workbench',
                  ),
        ),
      ),
    );
  }

  Future<void> _openUrl(String url) async {
    final callback = widget.onOpenUrl;
    if (callback != null) {
      await callback(url);
      return;
    }
    final uri = Uri.tryParse(url);
    if (uri == null) {
      return;
    }
    await launchUrl(uri, mode: LaunchMode.externalApplication);
  }

  Future<void> _openInvites(WebPreview preview) async {
    final listInvites = widget.listInvites;
    if (listInvites == null) {
      return;
    }
    await showDialog<void>(
      context: context,
      builder: (context) => WebPreviewInvitesDialog(
        preview: preview,
        listInvites: listInvites,
        createInvite: widget.createInvite,
        resendInvite: widget.resendInvite,
        expireInvite: widget.expireInvite,
        revokeInvite: widget.revokeInvite,
        syncInvite: widget.syncInvite,
      ),
    );
    await _load();
  }

  Future<void> _mutatePreview(
    WebPreview preview,
    WebPreviewMutator? mutator, {
    int? ttlSeconds,
    String? reason,
  }) async {
    if (mutator == null) {
      return;
    }
    try {
      await mutator(
        previewId: preview.previewId,
        ttlSeconds: ttlSeconds,
        reason: reason,
      );
      await _load();
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _error = error.toString();
      });
    }
  }
}

class _WebPreviewCard extends StatelessWidget {
  const _WebPreviewCard({
    required this.preview,
    required this.onOpen,
    required this.onCopy,
    required this.onInvites,
    required this.onExtend,
    required this.onExpire,
    required this.onDisable,
  });

  final WebPreview preview;
  final VoidCallback? onOpen;
  final VoidCallback? onCopy;
  final VoidCallback? onInvites;
  final VoidCallback? onExtend;
  final VoidCallback? onExpire;
  final VoidCallback? onDisable;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final resourceSummary = _resourceSummary(preview);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(
              children: <Widget>[
                Icon(_iconForWebPreviewStatus(preview.status)),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    preview.sourceApp.isEmpty
                        ? preview.previewId
                        : preview.sourceApp,
                    style: theme.textTheme.titleMedium,
                  ),
                ),
                Text(preview.status),
              ],
            ),
            const SizedBox(height: 8),
            if (preview.previewUrl.isNotEmpty) Text(preview.previewUrl),
            if (preview.healthUrl != null && preview.healthUrl!.isNotEmpty)
              Text('Health: ${preview.healthUrl}'),
            if (preview.expiresAt != null && preview.expiresAt!.isNotEmpty)
              Text('Expires: ${preview.expiresAt}'),
            if (preview.disabledAt != null && preview.disabledAt!.isNotEmpty)
              Text('Disabled: ${preview.disabledAt}'),
            if (preview.disabledReason != null &&
                preview.disabledReason!.isNotEmpty)
              Text('Reason: ${preview.disabledReason}'),
            if (preview.auditEvents.isNotEmpty)
              Text('Audit events: ${preview.auditEvents.length}'),
            if (resourceSummary.isNotEmpty) Text(resourceSummary),
            if (preview.inviteSyncSummary != null)
              Text(_inviteSyncSummary(preview.inviteSyncSummary!)),
            if (preview.status == 'apply_disabled')
              const Text(
                'Apply is disabled on the backend. Configure and enable web preview apply before publishing.',
              ),
            if (preview.error != null && preview.error!.isNotEmpty)
              Text(
                preview.error!,
                style: TextStyle(color: theme.colorScheme.error),
              ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              children: <Widget>[
                if (onOpen != null)
                  FilledButton.icon(
                    onPressed: onOpen,
                    icon: const Icon(Icons.open_in_browser),
                    label: const Text('Open preview'),
                  ),
                if (onCopy != null)
                  OutlinedButton.icon(
                    onPressed: onCopy,
                    icon: const Icon(Icons.copy),
                    label: const Text('Copy URL'),
                  ),
                if (onInvites != null)
                  OutlinedButton.icon(
                    onPressed: onInvites,
                    icon: const Icon(Icons.mail_outline),
                    label: const Text('Invites'),
                  ),
                if (onExtend != null)
                  OutlinedButton.icon(
                    onPressed: onExtend,
                    icon: const Icon(Icons.update),
                    label: const Text('Extend 7d'),
                  ),
                if (onExpire != null)
                  OutlinedButton.icon(
                    onPressed: onExpire,
                    icon: const Icon(Icons.timer_off_outlined),
                    label: const Text('Expire'),
                  ),
                if (onDisable != null)
                  OutlinedButton.icon(
                    onPressed: onDisable,
                    icon: const Icon(Icons.block),
                    label: const Text('Disable'),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class WebPreviewInvitesDialog extends StatefulWidget {
  const WebPreviewInvitesDialog({
    super.key,
    required this.preview,
    required this.listInvites,
    this.createInvite,
    this.resendInvite,
    this.expireInvite,
    this.revokeInvite,
    this.syncInvite,
  });

  final WebPreview preview;
  final WebPreviewInviteLister listInvites;
  final WebPreviewInviteCreator? createInvite;
  final WebPreviewInviteMutator? resendInvite;
  final WebPreviewInviteMutator? expireInvite;
  final WebPreviewInviteMutator? revokeInvite;
  final WebPreviewInviteMutator? syncInvite;

  @override
  State<WebPreviewInvitesDialog> createState() =>
      _WebPreviewInvitesDialogState();
}

class _WebPreviewInvitesDialogState extends State<WebPreviewInvitesDialog> {
  final TextEditingController _ttlController = TextEditingController(
    text: '604800',
  );
  final TextEditingController _emailController = TextEditingController();
  String _role = 'admin';
  bool _singleUse = true;
  bool _loading = true;
  bool _busy = false;
  String? _error;
  WebPreviewInvite? _createdInvite;
  List<WebPreviewInvite> _invites = <WebPreviewInvite>[];

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _ttlController.dispose();
    _emailController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final invites = await widget.listInvites(widget.preview.previewId);
      if (!mounted) {
        return;
      }
      setState(() {
        _invites = invites;
        _loading = false;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _error = error.toString();
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text('Invites - ${widget.preview.sourceApp}'),
      content: SizedBox(width: 680, child: _buildContent(context)),
      actions: <Widget>[
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Close'),
        ),
      ],
    );
  }

  Widget _buildContent(BuildContext context) {
    if (_loading) {
      return const SizedBox(
        height: 180,
        child: Center(child: CircularProgressIndicator()),
      );
    }
    if (_error != null) {
      return SizedBox(height: 180, child: Center(child: Text(_error!)));
    }
    return ConstrainedBox(
      constraints: const BoxConstraints(maxHeight: 560),
      child: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            _buildCreateInvite(context),
            if (_createdInvite?.inviteUrl != null) ...<Widget>[
              const SizedBox(height: 12),
              _InviteLinkCard(invite: _createdInvite!),
            ],
            const SizedBox(height: 16),
            if (_invites.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 32),
                child: Center(child: Text('No preview invites')),
              )
            else
              ..._invites.map(_buildInviteTile),
          ],
        ),
      ),
    );
  }

  Widget _buildCreateInvite(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Wrap(
          spacing: 12,
          runSpacing: 8,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: <Widget>[
            SizedBox(
              width: 220,
              child: TextField(
                controller: _emailController,
                keyboardType: TextInputType.emailAddress,
                decoration: const InputDecoration(labelText: 'Admin email'),
              ),
            ),
            SizedBox(
              width: 130,
              child: TextField(
                controller: _ttlController,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(labelText: 'TTL seconds'),
              ),
            ),
            DropdownButton<String>(
              value: _role,
              items: const <DropdownMenuItem<String>>[
                DropdownMenuItem(value: 'admin', child: Text('admin')),
                DropdownMenuItem(value: 'owner', child: Text('owner')),
                DropdownMenuItem(value: 'manager', child: Text('manager')),
                DropdownMenuItem(value: 'staff', child: Text('staff')),
              ],
              onChanged: _busy
                  ? null
                  : (value) => setState(() {
                        _role = value ?? 'admin';
                      }),
            ),
            SizedBox(
              width: 190,
              child: SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Single use'),
                value: _singleUse,
                onChanged: _busy
                    ? null
                    : (value) => setState(() {
                          _singleUse = value;
                        }),
              ),
            ),
            FilledButton.icon(
              onPressed: _busy || widget.createInvite == null ? null : _create,
              icon: const Icon(Icons.add_link),
              label: const Text('Create invite'),
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildInviteTile(WebPreviewInvite invite) {
    return ListTile(
      contentPadding: EdgeInsets.zero,
      leading: Icon(invite.isRevoked ? Icons.block : Icons.link),
      title: Text(invite.inviteId),
      subtitle: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text('Expires: ${invite.expiresAt}'),
          if (invite.email != null && invite.email!.isNotEmpty)
            Text('Email: ${invite.email}'),
          Text('Role: ${invite.role}'),
          Text('Delivery: ${invite.emailDeliveryStatus}'),
          if (invite.manualDeliveryRequired)
            const Text('Manual link delivery required'),
          if (invite.resendCount > 0) Text('Resends: ${invite.resendCount}'),
          Text('Sync: ${invite.syncStatus}'),
          if (invite.syncedAt != null) Text('Synced: ${invite.syncedAt}'),
          if (invite.revokedAt != null) Text('Revoked: ${invite.revokedAt}'),
          if (invite.expiredAt != null) Text('Expired: ${invite.expiredAt}'),
          if (invite.syncError != null && invite.syncError!.isNotEmpty)
            Text(invite.syncError!),
        ],
      ),
      trailing: Wrap(
        spacing: 8,
        children: <Widget>[
          if (invite.canRetrySync && widget.syncInvite != null)
            TextButton(
              onPressed: _busy ? null : () => _sync(invite),
              child: const Text('Retry sync'),
            ),
          if (!invite.isRevoked && widget.resendInvite != null)
            TextButton(
              onPressed: _busy ? null : () => _resend(invite),
              child: const Text('Resend'),
            ),
          if (!invite.isRevoked && widget.expireInvite != null)
            TextButton(
              onPressed: _busy ? null : () => _expire(invite),
              child: const Text('Expire'),
            ),
          if (!invite.isRevoked && widget.revokeInvite != null)
            TextButton(
              onPressed: _busy ? null : () => _revoke(invite),
              child: const Text('Revoke'),
            ),
        ],
      ),
    );
  }

  Future<void> _create() async {
    final createInvite = widget.createInvite;
    if (createInvite == null) {
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final ttl = int.tryParse(_ttlController.text.trim());
      final invite = await createInvite(
        widget.preview.previewId,
        ttlSeconds: ttl,
        singleUse: _singleUse,
        email: _emailController.text.trim(),
        role: _role,
      );
      if (!mounted) {
        return;
      }
      setState(() {
        _createdInvite = invite;
        _busy = false;
      });
      await _load();
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _busy = false;
        _error = error.toString();
      });
    }
  }

  Future<void> _revoke(WebPreviewInvite invite) async {
    await _mutateInvite(invite, widget.revokeInvite);
  }

  Future<void> _sync(WebPreviewInvite invite) async {
    await _mutateInvite(invite, widget.syncInvite);
  }

  Future<void> _resend(WebPreviewInvite invite) async {
    await _mutateInvite(invite, widget.resendInvite);
  }

  Future<void> _expire(WebPreviewInvite invite) async {
    await _mutateInvite(invite, widget.expireInvite);
  }

  Future<void> _mutateInvite(
    WebPreviewInvite invite,
    WebPreviewInviteMutator? mutator,
  ) async {
    if (mutator == null) {
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await mutator(
        previewId: widget.preview.previewId,
        inviteId: invite.inviteId,
      );
      if (!mounted) {
        return;
      }
      setState(() {
        _busy = false;
      });
      await _load();
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _busy = false;
        _error = error.toString();
      });
    }
  }
}

class _InviteLinkCard extends StatelessWidget {
  const _InviteLinkCard({required this.invite});

  final WebPreviewInvite invite;

  @override
  Widget build(BuildContext context) {
    final url = invite.inviteUrl ?? '';
    return Card(
      child: ListTile(
        leading: const Icon(Icons.link),
        title: const Text('Invite link created'),
        subtitle: Text(url),
        trailing: IconButton(
          onPressed: url.isEmpty
              ? null
              : () async {
                  await Clipboard.setData(ClipboardData(text: url));
                  if (context.mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('Invite link copied.')),
                    );
                  }
                },
          icon: const Icon(Icons.copy),
          tooltip: 'Copy invite link',
        ),
      ),
    );
  }
}

class _ProjectFactoryHistoryTile extends StatelessWidget {
  const _ProjectFactoryHistoryTile({
    required this.job,
    required this.onWatch,
    required this.onOpen,
    required this.onOpenPreview,
  });

  final ProjectFactoryJobSummary job;
  final VoidCallback onWatch;
  final VoidCallback? onOpen;
  final Future<void> Function(String url)? onOpenPreview;

  @override
  Widget build(BuildContext context) {
    final error = job.error;
    return ListTile(
      contentPadding: EdgeInsets.zero,
      leading: Icon(_iconForProjectFactoryStatus(job.status)),
      title: Text(job.name ?? job.slug ?? job.jobId),
      subtitle: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text('${job.status} - ${job.currentPhase} - ${job.progress}%'),
          if (job.completedAt != null) Text('Completed: ${job.completedAt}'),
          if (error != null && error.isNotEmpty)
            Text(
              error,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          if (job.manualNextStep != null && !job.isReady)
            Text(job.manualNextStep!),
          const SizedBox(height: 8),
          _InitialPreviewReleasePanel(
            release: job.initialPreviewRelease,
            compact: true,
            onOpenPreview: onOpenPreview == null
                ? null
                : (url) => unawaited(onOpenPreview!(url)),
          ),
        ],
      ),
      trailing: Wrap(
        spacing: 8,
        children: <Widget>[
          if (!job.isReady)
            TextButton(onPressed: onWatch, child: const Text('Details')),
          if (job.initialPreviewRelease.hasPreviewUrl && onOpenPreview != null)
            OutlinedButton(
              onPressed: () => unawaited(
                onOpenPreview!(job.initialPreviewRelease.previewUrl!),
              ),
              child: const Text('Open preview'),
            ),
          if (job.isReady && onOpen != null)
            FilledButton(onPressed: onOpen, child: const Text('Open')),
        ],
      ),
      onTap: job.isReady && onOpen != null ? onOpen : onWatch,
    );
  }
}

String _initStatusLabel(String status) {
  return switch (status) {
    'ready' => 'Ready',
    'blocked_with_context' => 'Blocked',
    'failed' => 'Failed',
    'cancelled' => 'Cancelled',
    'resumable' => 'Resumable',
    'running' => 'Running',
    _ => 'Queued',
  };
}

Color _initStatusBackground(String status) {
  return switch (status) {
    'ready' => const Color(0xFF0B3D25),
    'blocked_with_context' => const Color(0xFF3A2714),
    'failed' => const Color(0xFF431B27),
    'cancelled' => const Color(0xFF2B364D),
    'resumable' => const Color(0xFF2A2440),
    'running' => const Color(0xFF133954),
    _ => const Color(0xFF26324A),
  };
}

Color _initStatusForeground(String status) {
  return switch (status) {
    'ready' => const Color(0xFFB7F5CF),
    'blocked_with_context' => const Color(0xFFFFD9A3),
    'failed' => const Color(0xFFFFC4CB),
    'cancelled' => const Color(0xFFB8C3DA),
    'resumable' => const Color(0xFFD9CCFF),
    'running' => const Color(0xFFBFE8FF),
    _ => const Color(0xFFDCE5FF),
  };
}

String _humanizeInitPhase(String phase) {
  final normalized = phase.replaceAll('_', ' ').trim();
  if (normalized.isEmpty) {
    return 'Init preflight';
  }
  return normalized[0].toUpperCase() + normalized.substring(1);
}

class _InitialPreviewReleasePanel extends StatelessWidget {
  const _InitialPreviewReleasePanel({
    required this.release,
    this.compact = false,
    this.showPhases = false,
    this.onOpenPreview,
  });

  final InitialPreviewRelease release;
  final bool compact;
  final bool showPhases;
  final void Function(String url)? onOpenPreview;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final previewUrl = release.previewUrl?.trim() ?? '';
    final apiUrl = release.apiBaseUrl?.trim() ?? '';
    final blocker = release.blockerText?.trim() ?? '';
    if (previewUrl.isEmpty &&
        release.sourceApp.isEmpty &&
        release.status == 'draft' &&
        blocker.isEmpty) {
      return const SizedBox.shrink();
    }
    final commands = release.manualCommandHints
        .where((command) => command.trim().isNotEmpty)
        .toList(growable: false);
    return DecoratedBox(
      decoration: BoxDecoration(
        color:
            theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.35),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Padding(
        padding: EdgeInsets.all(compact ? 8 : 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Wrap(
              spacing: 8,
              runSpacing: 6,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: <Widget>[
                const Icon(Icons.rocket_launch_outlined, size: 18),
                Text(
                  'Initial Preview: ${release.status} / ${release.currentPhase}',
                  style: theme.textTheme.labelLarge,
                ),
                _PreviewChip(label: 'profile ${release.runtimeProfile}'),
                _PreviewChip(label: 'channel ${release.releaseChannel}'),
                _PreviewChip(label: release.releaseTagPattern),
              ],
            ),
            const SizedBox(height: 6),
            Text('Preview URL: ${previewUrl.isEmpty ? 'pending' : previewUrl}'),
            if (!compact)
              Text('API URL: ${apiUrl.isEmpty ? 'pending' : apiUrl}'),
            if (!compact) ...<Widget>[
              Text('D1 persistence: Cloudflare preview'),
              Text('Android APK: android-preview-v*'),
              Text('Bridge registration: required'),
              Text('Signing mode: preview release workflow'),
            ],
            Text(release.productionReadinessLabel),
            Text(release.mockDemoLabel),
            const Text('Production release: pending / not requested'),
            if (blocker.isNotEmpty) ...<Widget>[
              const SizedBox(height: 6),
              Text(
                blocker,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.error,
                ),
              ),
            ],
            if (showPhases && release.phaseStatuses.isNotEmpty) ...<Widget>[
              const SizedBox(height: 8),
              ...release.phaseStatuses.entries.map(
                (entry) => Text('${entry.key}: ${entry.value.status}'),
              ),
            ],
            if (previewUrl.isNotEmpty || commands.isNotEmpty) ...<Widget>[
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 6,
                children: <Widget>[
                  if (previewUrl.isNotEmpty)
                    OutlinedButton.icon(
                      onPressed: () =>
                          unawaited(_copyPreviewText(context, previewUrl)),
                      icon: const Icon(Icons.copy),
                      label: const Text('Copy preview URL'),
                    ),
                  ...commands.take(compact ? 1 : 3).map((command) {
                    return OutlinedButton.icon(
                      onPressed: () =>
                          unawaited(_copyPreviewText(context, command)),
                      icon: const Icon(Icons.copy),
                      label: Text(compact ? 'Copy command' : command),
                    );
                  }),
                ],
              ),
            ],
            if (!compact &&
                previewUrl.isNotEmpty &&
                onOpenPreview != null) ...<Widget>[
              const SizedBox(height: 8),
              FilledButton.icon(
                onPressed: () => onOpenPreview!(previewUrl),
                icon: const Icon(Icons.open_in_browser),
                label: const Text('Open preview'),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _PreviewChip extends StatelessWidget {
  const _PreviewChip({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Chip(
      label: Text(label),
      visualDensity: VisualDensity.compact,
      materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
    );
  }
}

Future<void> _copyPreviewText(BuildContext context, String value) async {
  await Clipboard.setData(ClipboardData(text: value));
  if (!context.mounted) {
    return;
  }
  ScaffoldMessenger.of(
    context,
  ).showSnackBar(const SnackBar(content: Text('Copied.')));
}

Future<void> _openPreviewUrl(BuildContext context, String url) async {
  final uri = Uri.tryParse(url);
  if (uri == null) {
    return;
  }
  await launchUrl(uri, mode: LaunchMode.externalApplication);
}

IconData _iconForProjectFactoryStatus(String status) {
  return switch (status) {
    'ready' || 'completed' => Icons.check_circle_outline,
    'failed' || 'interrupted' || 'blocked' => Icons.error_outline,
    _ => Icons.pending_actions_outlined,
  };
}

IconData _iconForWebPreviewStatus(String status) {
  return switch (status) {
    'active' => Icons.check_circle_outline,
    'failed' => Icons.error_outline,
    'applying' || 'planned' => Icons.pending_actions_outlined,
    'apply_disabled' => Icons.lock_outline,
    _ => Icons.language,
  };
}

String _resourceSummary(WebPreview preview) {
  final planned = preview.plannedResources.length;
  final applied = preview.appliedResources.length;
  if (planned == 0 && applied == 0) {
    return '';
  }
  return 'Resources: $planned planned, $applied applied';
}

String _inviteSyncSummary(Map<String, dynamic> summary) {
  final synced = summary['synced'] ?? 0;
  final failed = summary['failed'] ?? 0;
  final pending = summary['pending'] ?? 0;
  final notDeployed = summary['not_deployed'] ?? 0;
  return 'Invite sync: $synced synced, $failed failed, $pending pending, $notDeployed not deployed';
}

class ProjectFactoryProgressDialog extends StatefulWidget {
  const ProjectFactoryProgressDialog({
    super.key,
    required this.initialJob,
    required this.pollJob,
    this.pollInterval = const Duration(seconds: 1),
  });

  final ProjectFactoryJob initialJob;
  final ProjectFactoryJobPoller pollJob;
  final Duration pollInterval;

  @override
  State<ProjectFactoryProgressDialog> createState() =>
      ProjectFactoryProgressDialogState();
}

class ProjectFactoryProgressDialogState
    extends State<ProjectFactoryProgressDialog> {
  late ProjectFactoryJob _job;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _job = widget.initialJob;
    if (!_isTerminal(_job)) {
      _timer = Timer.periodic(widget.pollInterval, (_) => _poll());
      unawaited(_poll());
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final failed = _job.status == 'failed' ||
        _job.status == 'blocked' ||
        _job.status == 'interrupted';
    final ready = _job.isReady;
    return AlertDialog(
      title: const Text('New project'),
      content: SizedBox(
        width: 620,
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxHeight: 460),
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                LinearProgressIndicator(
                  value: (_job.progress.clamp(0, 100)) / 100,
                ),
                const SizedBox(height: 16),
                Text(_job.currentPhase),
                const SizedBox(height: 8),
                Text(_job.message),
                const SizedBox(height: 12),
                _InitialPreviewReleasePanel(
                  release: _job.initialPreviewRelease,
                  showPhases: true,
                  onOpenPreview: _job.initialPreviewRelease.hasPreviewUrl
                      ? (url) => unawaited(_openPreviewUrl(context, url))
                      : null,
                ),
                if (failed && _job.error != null) ...<Widget>[
                  const SizedBox(height: 8),
                  Text(_job.error!),
                ],
              ],
            ),
          ),
        ),
      ),
      actions: <Widget>[
        if (failed)
          TextButton(
            onPressed: () => Navigator.of(context).pop(_job),
            child: const Text('Close'),
          ),
        if (ready)
          FilledButton(
            onPressed: () => Navigator.of(context).pop(_job),
            child: const Text('Open project'),
          ),
      ],
    );
  }

  Future<void> _poll() async {
    try {
      final next = await widget.pollJob(_job.jobId);
      if (!mounted) {
        return;
      }
      setState(() {
        _job = next;
      });
      if (_isTerminal(next)) {
        _timer?.cancel();
      }
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _job = ProjectFactoryJob(
          jobId: _job.jobId,
          draftId: _job.draftId,
          status: 'failed',
          currentStep: 'polling',
          currentPhase: 'polling',
          progress: _job.progress,
          message: 'Could not refresh project job.',
          manifestPlan: _job.manifestPlan,
          stepLogs: _job.stepLogs,
          initialPreviewRelease: _job.initialPreviewRelease,
          error: error.toString(),
          generationResult: _job.generationResult,
        );
      });
      _timer?.cancel();
    }
  }

  bool _isTerminal(ProjectFactoryJob job) {
    return job.status == 'ready' ||
        job.status == 'failed' ||
        job.status == 'blocked' ||
        job.status == 'interrupted';
  }
}

class _NewChatDraft {
  const _NewChatDraft({
    required this.workspace,
    required this.agentProfile,
    required this.turnSummariesEnabled,
  });

  final Workspace workspace;
  final AgentProfile agentProfile;
  final bool turnSummariesEnabled;
}

class _NewChatSheet extends StatefulWidget {
  const _NewChatSheet({
    required this.workspaces,
    required this.agentProfiles,
    required this.pinnedWorkspacePaths,
  });

  final List<Workspace> workspaces;
  final List<AgentProfile> agentProfiles;
  final Set<String> pinnedWorkspacePaths;

  @override
  State<_NewChatSheet> createState() => _NewChatSheetState();
}

class _NewChatSheetState extends State<_NewChatSheet> {
  late AgentProfile _selectedProfile;
  bool _turnSummariesEnabled = true;

  @override
  void initState() {
    super.initState();
    _selectedProfile = widget.agentProfiles.first;
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: LayoutBuilder(
        builder: (context, constraints) {
          return ConstrainedBox(
            constraints: BoxConstraints(maxHeight: constraints.maxHeight),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                const ListTile(
                  title: Text('Choose Existing Project'),
                  subtitle: Text(
                    'Select a folder already visible under PROJECTS_ROOT to start a new chat.',
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
                  child: DropdownButtonFormField<AgentProfile>(
                    initialValue: _selectedProfile,
                    decoration: const InputDecoration(
                      labelText: 'Agent profile',
                    ),
                    items: widget.agentProfiles
                        .map(
                          (profile) => DropdownMenuItem<AgentProfile>(
                            value: profile,
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: <Widget>[
                                Container(
                                  width: 10,
                                  height: 10,
                                  decoration: BoxDecoration(
                                    color: _colorFromHex(profile.colorHex),
                                    shape: BoxShape.circle,
                                  ),
                                ),
                                const SizedBox(width: 10),
                                Flexible(
                                  fit: FlexFit.loose,
                                  child: Text(
                                    '${profile.name} · ${_presetLabel(profile.configuration.preset)}',
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        )
                        .toList(),
                    onChanged: (value) {
                      if (value == null) {
                        return;
                      }
                      setState(() {
                        _selectedProfile = value;
                      });
                    },
                  ),
                ),
                SwitchListTile(
                  value: _turnSummariesEnabled,
                  title: const Text('Enable chat summary'),
                  subtitle: const Text(
                    'Create short background summaries for this chat.',
                  ),
                  onChanged: (value) {
                    setState(() {
                      _turnSummariesEnabled = value;
                    });
                  },
                ),
                Flexible(
                  child: ListView(
                    shrinkWrap: true,
                    children: widget.workspaces.map((workspace) {
                      final isPinned = widget.pinnedWorkspacePaths.contains(
                        workspace.path,
                      );
                      return ListTile(
                        title: Text(workspace.name),
                        subtitle: Text(
                          workspace.path,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        trailing: isPinned
                            ? const Icon(
                                Icons.bookmark_added_rounded,
                                color: Color(0xFF55D6BE),
                              )
                            : null,
                        onTap: () => Navigator.of(context).pop(
                          _NewChatDraft(
                            workspace: workspace,
                            agentProfile: _selectedProfile,
                            turnSummariesEnabled: _turnSummariesEnabled,
                          ),
                        ),
                      );
                    }).toList(),
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}

class _SaveAgentProfileDraft {
  const _SaveAgentProfileDraft({
    required this.name,
    required this.description,
    required this.colorHex,
  });

  final String name;
  final String description;
  final String colorHex;
}

class _SaveAgentProfileSheet extends StatefulWidget {
  const _SaveAgentProfileSheet({
    required this.initialName,
    required this.initialColorHex,
  });

  final String initialName;
  final String initialColorHex;

  @override
  State<_SaveAgentProfileSheet> createState() => _SaveAgentProfileSheetState();
}

class _SaveAgentProfileSheetState extends State<_SaveAgentProfileSheet> {
  late final TextEditingController _nameController;
  late final TextEditingController _descriptionController;
  late final TextEditingController _colorController;

  @override
  void initState() {
    super.initState();
    _nameController = TextEditingController(text: widget.initialName);
    _descriptionController = TextEditingController();
    _colorController = TextEditingController(text: widget.initialColorHex);
  }

  @override
  void dispose() {
    _nameController.dispose();
    _descriptionController.dispose();
    _colorController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.only(
          left: 16,
          right: 16,
          top: 12,
          bottom: MediaQuery.of(context).viewInsets.bottom + 16,
        ),
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              const ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text('Save Agent'),
                subtitle: Text(
                  'Save the current generator as a reusable agent for future chats.',
                ),
              ),
              TextField(
                controller: _nameController,
                decoration: const InputDecoration(labelText: 'Name'),
              ),
              const SizedBox(height: 8),
              TextField(
                controller: _descriptionController,
                decoration: const InputDecoration(labelText: 'Description'),
              ),
              const SizedBox(height: 8),
              TextField(
                controller: _colorController,
                decoration: const InputDecoration(
                  labelText: 'Color',
                  helperText: 'Use a hex color like #F28C28',
                ),
              ),
              const SizedBox(height: 20),
              Row(
                children: <Widget>[
                  TextButton(
                    onPressed: () => Navigator.of(context).pop(),
                    child: const Text('Cancel'),
                  ),
                  const Spacer(),
                  FilledButton(
                    onPressed: () {
                      Navigator.of(context).pop(
                        _SaveAgentProfileDraft(
                          name: _nameController.text.trim(),
                          description: _descriptionController.text.trim(),
                          colorHex: _colorController.text.trim(),
                        ),
                      );
                    },
                    child: const Text('Save'),
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

class _AgentStudioDraft {
  const _AgentStudioDraft({
    required this.configuration,
    required this.turnSummariesEnabled,
  });

  final AgentConfiguration configuration;
  final bool turnSummariesEnabled;
}

class _AgentStudioSheet extends StatefulWidget {
  const _AgentStudioSheet({required this.session});

  final SessionDetail session;

  @override
  State<_AgentStudioSheet> createState() => _AgentStudioSheetState();
}

class _AgentStudioSheetState extends State<_AgentStudioSheet> {
  late AgentPreset _preset;
  late AgentDisplayMode _displayMode;
  late TurnBudgetMode _turnBudgetMode;
  late SummaryStrategy _summaryStrategy;
  late final Map<AgentId, TextEditingController> _labelControllers;
  late final Map<AgentId, TextEditingController> _modelControllers;
  late final Map<AgentId, TextEditingController> _promptControllers;
  late final Map<AgentId, TextEditingController> _turnsControllers;
  late final TextEditingController _summaryDeterministicController;
  late final TextEditingController _summaryWindowStartController;
  late final TextEditingController _summaryWindowEndController;
  late final Map<AgentId, bool> _enabled;
  late final Map<AgentId, AgentVisibilityMode> _visibility;
  late final Set<AgentId> _supervisorMemberIds;
  late bool _turnSummariesEnabled;

  @override
  void initState() {
    super.initState();
    final configuration = widget.session.agentConfiguration;
    _preset = configuration.preset;
    _displayMode = configuration.displayMode;
    _turnBudgetMode = configuration.turnBudgetMode;
    _summaryStrategy = configuration.summaryStrategy;
    _labelControllers = <AgentId, TextEditingController>{};
    _modelControllers = <AgentId, TextEditingController>{};
    _promptControllers = <AgentId, TextEditingController>{};
    _turnsControllers = <AgentId, TextEditingController>{};
    _summaryDeterministicController = TextEditingController(
      text: configuration.summaryStrategy.deterministicInterval.toString(),
    );
    _summaryWindowStartController = TextEditingController(
      text: configuration.summaryStrategy.supervisorWindowStart.toString(),
    );
    _summaryWindowEndController = TextEditingController(
      text: configuration.summaryStrategy.supervisorWindowEnd.toString(),
    );
    _enabled = <AgentId, bool>{};
    _visibility = <AgentId, AgentVisibilityMode>{};
    _supervisorMemberIds = configuration.supervisorMemberIds.toSet();
    _turnSummariesEnabled = widget.session.turnSummariesEnabled;

    for (final agent in configuration.agents) {
      _labelControllers[agent.agentId] = TextEditingController(
        text: agent.label,
      );
      _modelControllers[agent.agentId] = TextEditingController(
        text: agent.model ?? '',
      );
      _promptControllers[agent.agentId] = TextEditingController(
        text: agent.prompt,
      );
      _turnsControllers[agent.agentId] = TextEditingController(
        text: agent.maxTurns.toString(),
      );
      _enabled[agent.agentId] = agent.enabled;
      _visibility[agent.agentId] = agent.visibility;
    }
  }

  @override
  void dispose() {
    for (final controller in _labelControllers.values) {
      controller.dispose();
    }
    for (final controller in _modelControllers.values) {
      controller.dispose();
    }
    for (final controller in _promptControllers.values) {
      controller.dispose();
    }
    for (final controller in _turnsControllers.values) {
      controller.dispose();
    }
    _summaryDeterministicController.dispose();
    _summaryWindowStartController.dispose();
    _summaryWindowEndController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.only(
          left: 16,
          right: 16,
          top: 12,
          bottom: MediaQuery.of(context).viewInsets.bottom + 16,
        ),
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              const ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text('Agents'),
                subtitle: Text(
                  'Configure the preset, the available agents, and how runs are delegated for this chat.',
                ),
              ),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                value: _turnSummariesEnabled,
                title: const Text('Chat summary'),
                subtitle: const Text(
                  'Keep a short background summary for this session.',
                ),
                onChanged: (value) {
                  setState(() {
                    _turnSummariesEnabled = value;
                  });
                },
              ),
              const SizedBox(height: 8),
              DropdownButtonFormField<AgentPreset>(
                initialValue: _preset,
                decoration: const InputDecoration(labelText: 'Preset'),
                items: const <DropdownMenuItem<AgentPreset>>[
                  DropdownMenuItem(
                    value: AgentPreset.solo,
                    child: Text('Solo'),
                  ),
                  DropdownMenuItem(
                    value: AgentPreset.review,
                    child: Text('Generator + Reviewer'),
                  ),
                  DropdownMenuItem(
                    value: AgentPreset.triad,
                    child: Text('Generator + Reviewer + Summary'),
                  ),
                  DropdownMenuItem(
                    value: AgentPreset.supervisor,
                    child: Text('Supervisor + Specialists'),
                  ),
                ],
                onChanged: (value) {
                  if (value == null) {
                    return;
                  }
                  setState(() {
                    _preset = value;
                    _applyPreset(value);
                  });
                },
              ),
              const SizedBox(height: 8),
              CurrentRunTimelineCard(session: widget.session),
              const SizedBox(height: 4),
              DropdownButtonFormField<AgentDisplayMode>(
                initialValue: _displayMode,
                decoration: const InputDecoration(labelText: 'Chat rendering'),
                items: const <DropdownMenuItem<AgentDisplayMode>>[
                  DropdownMenuItem(
                    value: AgentDisplayMode.showAll,
                    child: Text('Show all'),
                  ),
                  DropdownMenuItem(
                    value: AgentDisplayMode.collapseSpecialists,
                    child: Text('Collapse specialists'),
                  ),
                  DropdownMenuItem(
                    value: AgentDisplayMode.summaryOnly,
                    child: Text('Summary only'),
                  ),
                ],
                onChanged: (value) {
                  if (value == null) {
                    return;
                  }
                  setState(() {
                    _displayMode = value;
                  });
                },
              ),
              if (_preset == AgentPreset.supervisor) ...<Widget>[
                const SizedBox(height: 12),
                DropdownButtonFormField<TurnBudgetMode>(
                  initialValue: _turnBudgetMode,
                  decoration: const InputDecoration(
                    labelText: 'Turn budget mode',
                  ),
                  items: const <DropdownMenuItem<TurnBudgetMode>>[
                    DropdownMenuItem(
                      value: TurnBudgetMode.eachAgent,
                      child: Text('Each agent'),
                    ),
                    DropdownMenuItem(
                      value: TurnBudgetMode.supervisorOnly,
                      child: Text('Supervisor only'),
                    ),
                  ],
                  onChanged: (value) {
                    if (value == null) {
                      return;
                    }
                    setState(() {
                      _turnBudgetMode = value;
                    });
                  },
                ),
                const SizedBox(height: 12),
                _buildSupervisorRegistryCard(),
              ],
              const SizedBox(height: 16),
              ...widget.session.agentConfiguration.agents
                  .where((agent) => agent.agentId != AgentId.user)
                  .map((agent) => _buildAgentCard(context, agent.agentId)),
              const SizedBox(height: 20),
              Row(
                children: <Widget>[
                  TextButton(
                    onPressed: () => Navigator.of(context).pop(),
                    child: const Text('Cancel'),
                  ),
                  const Spacer(),
                  FilledButton(
                    onPressed: () {
                      Navigator.of(context).pop(
                        _AgentStudioDraft(
                          configuration: _buildConfiguration(),
                          turnSummariesEnabled: _turnSummariesEnabled,
                        ),
                      );
                    },
                    child: const Text('Save'),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildAgentCard(BuildContext context, AgentId agentId) {
    final title = switch (agentId) {
      AgentId.generator => 'Generator',
      AgentId.reviewer => 'Reviewer',
      AgentId.summary => 'Summary',
      AgentId.supervisor => 'Supervisor',
      AgentId.qa => 'QA',
      AgentId.ux => 'UX',
      AgentId.seniorEngineer => 'Senior Engineer',
      AgentId.scraper => 'Scraper',
      AgentId.user => 'User',
    };
    final promptHint = switch (agentId) {
      AgentId.generator => 'Primary builder prompt',
      AgentId.reviewer => _defaultAutoReviewerPrompt,
      AgentId.summary =>
        'Summarize generator progress and reviewer feedback for the user.',
      AgentId.supervisor =>
        'Own the plan, decide who acts next, and return strict JSON.',
      AgentId.qa =>
        'Validate correctness, test coverage, regressions, and release risk.',
      AgentId.ux =>
        'Review usability, accessibility, flow, copy, and interaction quality.',
      AgentId.seniorEngineer =>
        'Review architecture, technical strategy, maintainability, and delivery risk.',
      AgentId.scraper =>
        'Inspect websites, choose extraction methods, and report scraping risks.',
      AgentId.user => '',
    };
    final enabledSubtitle = switch (agentId) {
      AgentId.generator => 'The main implementation agent for this chat.',
      AgentId.reviewer =>
        'When enabled, new runs wait for the generator and then hand off to the reviewer.',
      AgentId.summary =>
        'Adds a user-facing summary after the configured number of completed agent turns.',
      AgentId.supervisor =>
        'Owns planning, delegation, and specialist routing for supervisor mode.',
      AgentId.qa =>
        'Reports validation risk, testing gaps, and regressions back to the supervisor.',
      AgentId.ux =>
        'Reports UX, accessibility, and product quality feedback back to the supervisor.',
      AgentId.seniorEngineer =>
        'Reports senior technical guidance and implementation risk back to the supervisor.',
      AgentId.scraper =>
        'Reports extraction strategy, parser robustness, and source constraints back to the supervisor.',
      AgentId.user => '',
    };
    final visibilityHelperText = switch (agentId) {
      AgentId.reviewer =>
        'Collapsed reviewer replies stay out of the main list, but the reviewer status banner still updates.',
      AgentId.qa ||
      AgentId.ux ||
      AgentId.seniorEngineer ||
      AgentId.scraper =>
        'Specialist replies usually stay collapsed so the supervisor can summarize the run.',
      _ => null,
    };
    final usesRegistrySelection = _preset == AgentPreset.supervisor &&
        kSupervisorMemberAgentIds.contains(agentId);
    final showEnabledToggle = _preset != AgentPreset.supervisor
        ? true
        : agentId != AgentId.supervisor && !usesRegistrySelection;
    final canToggle = switch (agentId) {
      AgentId.generator => _preset != AgentPreset.supervisor,
      AgentId.supervisor => false,
      AgentId.summary => true,
      AgentId.qa ||
      AgentId.ux ||
      AgentId.seniorEngineer ||
      AgentId.scraper =>
        false,
      _ => _preset != AgentPreset.supervisor,
    };

    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFF15203B),
        borderRadius: BorderRadius.circular(18),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          if (showEnabledToggle)
            Material(
              type: MaterialType.transparency,
              child: SwitchListTile(
                contentPadding: EdgeInsets.zero,
                value: _enabled[agentId] ?? false,
                title: Text(title),
                subtitle: Text(enabledSubtitle),
                onChanged: !canToggle
                    ? null
                    : (value) {
                        setState(() {
                          _enabled[agentId] = value;
                          if (kSupervisorMemberAgentIds.contains(agentId)) {
                            if (value) {
                              _supervisorMemberIds.add(agentId);
                            } else {
                              _supervisorMemberIds.remove(agentId);
                            }
                          }
                        });
                      },
              ),
            )
          else
            Material(
              type: MaterialType.transparency,
              child: ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text(title),
                subtitle: Text(
                  usesRegistrySelection
                      ? '$enabledSubtitle Selection is controlled by the supervisor registry above.'
                      : enabledSubtitle,
                ),
              ),
            ),
          TextField(
            controller: _labelControllers[agentId],
            decoration: const InputDecoration(labelText: 'Label'),
          ),
          const SizedBox(height: 8),
          TextField(
            key: ValueKey<String>('agent-model-${agentIdToJson(agentId)}'),
            controller: _modelControllers[agentId],
            decoration: const InputDecoration(
              labelText: 'Model override',
              helperText:
                  'Optional. Leave blank to use the backend default Codex model.',
            ),
          ),
          const SizedBox(height: 8),
          DropdownButtonFormField<AgentVisibilityMode>(
            initialValue: _visibility[agentId],
            decoration: InputDecoration(
              labelText: 'Visibility',
              helperText: visibilityHelperText,
            ),
            items: const <DropdownMenuItem<AgentVisibilityMode>>[
              DropdownMenuItem(
                value: AgentVisibilityMode.visible,
                child: Text('Visible'),
              ),
              DropdownMenuItem(
                value: AgentVisibilityMode.collapsed,
                child: Text('Collapsed'),
              ),
              DropdownMenuItem(
                value: AgentVisibilityMode.hidden,
                child: Text('Hidden'),
              ),
            ],
            onChanged: (value) {
              if (value == null) {
                return;
              }
              setState(() {
                _visibility[agentId] = value;
              });
            },
          ),
          const SizedBox(height: 8),
          if (!_hideTurnBudgetField(agentId)) ...<Widget>[
            TextField(
              controller: _turnsControllers[agentId],
              keyboardType: TextInputType.number,
              decoration: InputDecoration(
                labelText: 'Turn budget',
                helperText: agentId == AgentId.supervisor
                    ? 'Any integer. Supervisor runs use at least 1.'
                    : agentId == AgentId.summary
                        ? 'Maximum number of summary calls for each run.'
                        : 'Any non-negative integer.',
              ),
            ),
            const SizedBox(height: 8),
          ],
          if (agentId == AgentId.summary) ...<Widget>[
            if (_preset == AgentPreset.supervisor) ...<Widget>[
              TextField(
                controller: _summaryWindowStartController,
                keyboardType: TextInputType.number,
                decoration: InputDecoration(
                  labelText: 'Summary window start',
                  helperText: _summaryWindowHelperText(),
                ),
              ),
              const SizedBox(height: 8),
              TextField(
                controller: _summaryWindowEndController,
                keyboardType: TextInputType.number,
                decoration: InputDecoration(
                  labelText: 'Summary window end',
                  helperText: _summaryWindowHelperText(),
                ),
              ),
              const SizedBox(height: 8),
            ] else ...<Widget>[
              TextField(
                controller: _summaryDeterministicController,
                keyboardType: TextInputType.number,
                decoration: InputDecoration(
                  labelText: 'Summary cadence',
                  helperText: _summaryCadenceHelperText(),
                ),
              ),
              const SizedBox(height: 8),
            ],
          ],
          TextField(
            controller: _promptControllers[agentId],
            minLines: 3,
            maxLines: 6,
            decoration: InputDecoration(
              labelText: 'Prompt',
              hintText: promptHint,
              alignLabelWithHint: true,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSupervisorRegistryCard() {
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFF15203B),
        borderRadius: BorderRadius.circular(18),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const Text(
            'Supervisor Registry',
            style: TextStyle(color: Colors.white, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 6),
          const Text(
            'Choose which specialist agents the supervisor can call during the run.',
            style: TextStyle(
              color: Color(0xFFB8C8EA),
              fontSize: 12,
              height: 1.3,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            _turnBudgetMode == TurnBudgetMode.supervisorOnly
                ? 'Supervisor only means selected specialists can be called whenever the supervisor chooses within the supervisor turn budget. Specialist turn budgets are preserved and become active again if you switch back to Each agent.'
                : 'Each agent means selected specialists keep their own turn budgets in addition to the supervisor budget.',
            style: const TextStyle(
              color: Color(0xFFB8C8EA),
              fontSize: 12,
              height: 1.3,
            ),
          ),
          const SizedBox(height: 12),
          ...kSupervisorMemberAgentIds.map((agentId) {
            final label = switch (agentId) {
              AgentId.qa => 'QA',
              AgentId.ux => 'UX',
              AgentId.seniorEngineer => 'Senior Engineer',
              AgentId.scraper => 'Scraper',
              _ => agentIdToJson(agentId),
            };
            return Material(
              type: MaterialType.transparency,
              child: CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                value: _supervisorMemberIds.contains(agentId),
                title: Text(label),
                subtitle: Text(switch (agentId) {
                  AgentId.qa =>
                    'Validation, tests, regressions, and release risk.',
                  AgentId.ux =>
                    'Usability, accessibility, flow, and interface quality.',
                  AgentId.seniorEngineer =>
                    'Architecture, implementation strategy, and delivery risk.',
                  AgentId.scraper =>
                    'Web extraction, parsing strategy, and source constraints.',
                  _ => '',
                }),
                onChanged: (value) {
                  setState(() {
                    if (value ?? false) {
                      _supervisorMemberIds.add(agentId);
                      _enabled[agentId] = true;
                    } else {
                      _supervisorMemberIds.remove(agentId);
                      _enabled[agentId] = false;
                    }
                  });
                },
              ),
            );
          }),
        ],
      ),
    );
  }

  void _applyPreset(AgentPreset preset) {
    for (final agentId in kConfigurableAgentIds) {
      _enabled[agentId] = agentEnabledForPreset(agentId, preset);
    }
    _summaryStrategy = _summaryStrategy.copyWith(
      mode: preset == AgentPreset.supervisor
          ? SummaryStrategyMode.supervisorWindow
          : SummaryStrategyMode.deterministic,
    );
    if (preset == AgentPreset.supervisor) {
      _enabled[AgentId.supervisor] = true;
      for (final agentId in kSupervisorMemberAgentIds) {
        _enabled[agentId] = _supervisorMemberIds.contains(agentId);
      }
    }
  }

  AgentConfiguration _buildConfiguration() {
    final previousAgents = widget.session.agentConfiguration.agents;
    final nextAgents = previousAgents.map((agent) {
      final maxTurns = _normalizeAgentTurns(
        _turnsControllers[agent.agentId]?.text ?? agent.maxTurns.toString(),
        fallback: agent.maxTurns,
      );
      final trimmedLabel = _labelControllers[agent.agentId]?.text.trim() ?? '';
      final trimmedModel = _modelControllers[agent.agentId]?.text.trim() ?? '';
      final trimmedPrompt =
          _promptControllers[agent.agentId]?.text.trim() ?? '';
      return agent.copyWith(
        enabled: _enabled[agent.agentId] ?? agent.enabled,
        label: trimmedLabel.isNotEmpty ? trimmedLabel : agent.label,
        model: trimmedModel.isNotEmpty ? trimmedModel : null,
        prompt: trimmedPrompt,
        visibility: _visibility[agent.agentId] ?? agent.visibility,
        maxTurns: maxTurns,
      );
    }).toList(growable: false);
    final summaryStrategy = _preset == AgentPreset.supervisor
        ? _summaryStrategy.copyWith(
            mode: SummaryStrategyMode.supervisorWindow,
            supervisorWindowStart: _normalizeAgentTurns(
              _summaryWindowStartController.text,
              fallback: _summaryStrategy.supervisorWindowStart,
            ),
            supervisorWindowEnd: _normalizeAgentTurns(
              _summaryWindowEndController.text,
              fallback: _summaryStrategy.supervisorWindowEnd,
            ),
          )
        : _summaryStrategy.copyWith(
            mode: SummaryStrategyMode.deterministic,
            deterministicInterval: _normalizeAgentTurns(
              _summaryDeterministicController.text,
              fallback: _summaryStrategy.deterministicInterval,
            ),
          );
    return widget.session.agentConfiguration.copyWith(
      preset: _preset,
      displayMode: _displayMode,
      turnBudgetMode: _turnBudgetMode,
      summaryStrategy: summaryStrategy,
      agents: nextAgents,
      supervisorMemberIds: _supervisorMemberIds.toList(growable: false),
    );
  }

  bool _hideTurnBudgetField(AgentId agentId) {
    if (_preset != AgentPreset.supervisor) {
      return false;
    }
    if (_turnBudgetMode != TurnBudgetMode.supervisorOnly) {
      return false;
    }
    return kSupervisorMemberAgentIds.contains(agentId);
  }

  String _summaryCadenceHelperText() {
    return 'Run the summary after this many completed generator or reviewer turns.';
  }

  String _summaryWindowHelperText() {
    return 'The supervisor can request a summary after completed agent turns inside this window. Default: turns 3 to 6.';
  }
}

int _normalizeAgentTurns(String rawValue, {required int fallback}) {
  final parsed = int.tryParse(rawValue.trim());
  if (parsed == null) {
    return fallback;
  }
  return parsed < 0 ? 0 : parsed;
}

class _ImageEditorResult {
  const _ImageEditorResult({required this.bytes, required this.fileName});

  final Uint8List? bytes;
  final String? fileName;
}

enum _ImageEditorMode { crop, draw }

enum _CropDragTarget { move, topLeft, topRight, bottomLeft, bottomRight }

class _ImageEditorScreen extends StatefulWidget {
  const _ImageEditorScreen({required this.imageBytes, required this.fileName});

  final Uint8List imageBytes;
  final String fileName;

  @override
  State<_ImageEditorScreen> createState() => _ImageEditorScreenState();
}

class _ImageEditorScreenState extends State<_ImageEditorScreen> {
  static const double _minCropSize = 0.08;
  static const List<Color> _palette = <Color>[
    Color(0xFFFF4D4F),
    Color(0xFFFFC857),
    Color(0xFF55D6BE),
    Color(0xFF66A8FF),
    Colors.white,
  ];

  ui.Image? _image;
  Object? _decodeError;
  _ImageEditorMode _mode = _ImageEditorMode.crop;
  Rect _cropRect = const Rect.fromLTWH(0, 0, 1, 1);
  Color _selectedColor = _palette.first;
  final List<_ImageAnnotationStroke> _strokes = <_ImageAnnotationStroke>[];
  _CropDragTarget? _cropDragTarget;
  Offset? _lastCropDragPoint;
  bool _isSaving = false;

  @override
  void initState() {
    super.initState();
    unawaited(_decodeImage());
  }

  Future<void> _decodeImage() async {
    try {
      final codec = await ui.instantiateImageCodec(widget.imageBytes);
      final frame = await codec.getNextFrame();
      if (!mounted) {
        return;
      }
      setState(() {
        _image = frame.image;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _decodeError = error;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final image = _image;
    return Scaffold(
      appBar: AppBar(
        title: Text(
          widget.fileName,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
        actions: <Widget>[
          TextButton(
            onPressed: _isSaving
                ? null
                : () => Navigator.of(
                      context,
                    ).pop(
                        const _ImageEditorResult(bytes: null, fileName: null)),
            child: const Text('Original'),
          ),
          TextButton(
            onPressed: _isSaving || image == null ? null : _saveEditedImage,
            child: _isSaving
                ? const SizedBox.square(
                    dimension: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Text('Done'),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: <Widget>[
            Expanded(child: Center(child: _buildImageStage(image))),
            _buildTools(),
          ],
        ),
      ),
    );
  }

  Widget _buildImageStage(ui.Image? image) {
    if (_decodeError != null) {
      return Padding(
        padding: const EdgeInsets.all(24),
        child: Text('Could not open image: $_decodeError'),
      );
    }
    if (image == null) {
      return const CircularProgressIndicator();
    }

    return LayoutBuilder(
      builder: (context, constraints) {
        final imageAspect = image.width / image.height;
        var stageWidth = constraints.maxWidth;
        var stageHeight = stageWidth / imageAspect;
        if (stageHeight > constraints.maxHeight) {
          stageHeight = constraints.maxHeight;
          stageWidth = stageHeight * imageAspect;
        }
        final stageSize = Size(stageWidth, stageHeight);
        return SizedBox(
          width: stageWidth,
          height: stageHeight,
          child: GestureDetector(
            onPanStart: (details) =>
                _handlePanStart(details.localPosition, stageSize),
            onPanUpdate: (details) => _handlePanUpdate(
              details.localPosition,
              details.delta,
              stageSize,
            ),
            onPanEnd: (_) => _handlePanEnd(),
            child: CustomPaint(
              painter: _ImageEditorPainter(
                image: image,
                cropRect: _cropRect,
                strokes: _strokes,
                mode: _mode,
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildTools() {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
      decoration: const BoxDecoration(
        color: Color(0xFF0D1427),
        border: Border(top: BorderSide(color: Color(0xFF1F2945))),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Row(
            children: <Widget>[
              Expanded(
                child: SegmentedButton<_ImageEditorMode>(
                  segments: const <ButtonSegment<_ImageEditorMode>>[
                    ButtonSegment<_ImageEditorMode>(
                      value: _ImageEditorMode.crop,
                      icon: Icon(Icons.crop_rounded),
                      label: Text('Crop'),
                    ),
                    ButtonSegment<_ImageEditorMode>(
                      value: _ImageEditorMode.draw,
                      icon: Icon(Icons.brush_rounded),
                      label: Text('Draw'),
                    ),
                  ],
                  selected: <_ImageEditorMode>{_mode},
                  onSelectionChanged: (selection) {
                    setState(() {
                      _mode = selection.first;
                    });
                  },
                ),
              ),
              const SizedBox(width: 10),
              IconButton.filledTonal(
                onPressed: _resetEdits,
                tooltip: 'Reset edits',
                icon: const Icon(Icons.restart_alt_rounded),
              ),
            ],
          ),
          if (_mode == _ImageEditorMode.draw) ...<Widget>[
            const SizedBox(height: 12),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: _palette.map((color) {
                final selected = color == _selectedColor;
                return Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 5),
                  child: InkResponse(
                    onTap: () {
                      setState(() {
                        _selectedColor = color;
                      });
                    },
                    radius: 22,
                    child: Container(
                      width: 34,
                      height: 34,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: color,
                        border: Border.all(
                          color: selected
                              ? const Color(0xFF55D6BE)
                              : const Color(0xFF53617F),
                          width: selected ? 3 : 1,
                        ),
                      ),
                    ),
                  ),
                );
              }).toList(growable: false),
            ),
          ],
        ],
      ),
    );
  }

  void _handlePanStart(Offset localPosition, Size stageSize) {
    if (_mode == _ImageEditorMode.draw) {
      setState(() {
        _strokes.add(
          _ImageAnnotationStroke(
            color: _selectedColor,
            strokeWidth: 5,
            points: <Offset>[_normalizePoint(localPosition, stageSize)],
          ),
        );
      });
      return;
    }

    _cropDragTarget = _resolveCropDragTarget(localPosition, stageSize);
    _lastCropDragPoint = localPosition;
  }

  void _handlePanUpdate(Offset localPosition, Offset delta, Size stageSize) {
    if (_mode == _ImageEditorMode.draw) {
      if (_strokes.isEmpty) {
        return;
      }
      setState(() {
        _strokes.last.points.add(_normalizePoint(localPosition, stageSize));
      });
      return;
    }

    final target = _cropDragTarget;
    final previous = _lastCropDragPoint;
    if (target == null || previous == null) {
      return;
    }
    final normalizedDelta = Offset(
      delta.dx / stageSize.width,
      delta.dy / stageSize.height,
    );
    setState(() {
      _cropRect = _updatedCropRect(target, normalizedDelta);
      _lastCropDragPoint = localPosition;
    });
  }

  void _handlePanEnd() {
    _cropDragTarget = null;
    _lastCropDragPoint = null;
  }

  _CropDragTarget _resolveCropDragTarget(Offset point, Size stageSize) {
    final crop = _cropRectForStage(stageSize);
    const handleRadius = 32.0;
    final corners = <_CropDragTarget, Offset>{
      _CropDragTarget.topLeft: crop.topLeft,
      _CropDragTarget.topRight: crop.topRight,
      _CropDragTarget.bottomLeft: crop.bottomLeft,
      _CropDragTarget.bottomRight: crop.bottomRight,
    };
    for (final entry in corners.entries) {
      if ((entry.value - point).distance <= handleRadius) {
        return entry.key;
      }
    }
    return _CropDragTarget.move;
  }

  Rect _updatedCropRect(_CropDragTarget target, Offset delta) {
    var left = _cropRect.left;
    var top = _cropRect.top;
    var right = _cropRect.right;
    var bottom = _cropRect.bottom;

    switch (target) {
      case _CropDragTarget.move:
        final width = _cropRect.width;
        final height = _cropRect.height;
        left = (left + delta.dx).clamp(0.0, 1.0 - width);
        top = (top + delta.dy).clamp(0.0, 1.0 - height);
        right = left + width;
        bottom = top + height;
        break;
      case _CropDragTarget.topLeft:
        left = (left + delta.dx).clamp(0.0, right - _minCropSize);
        top = (top + delta.dy).clamp(0.0, bottom - _minCropSize);
        break;
      case _CropDragTarget.topRight:
        right = (right + delta.dx).clamp(left + _minCropSize, 1.0);
        top = (top + delta.dy).clamp(0.0, bottom - _minCropSize);
        break;
      case _CropDragTarget.bottomLeft:
        left = (left + delta.dx).clamp(0.0, right - _minCropSize);
        bottom = (bottom + delta.dy).clamp(top + _minCropSize, 1.0);
        break;
      case _CropDragTarget.bottomRight:
        right = (right + delta.dx).clamp(left + _minCropSize, 1.0);
        bottom = (bottom + delta.dy).clamp(top + _minCropSize, 1.0);
        break;
    }

    return Rect.fromLTRB(left, top, right, bottom);
  }

  Offset _normalizePoint(Offset point, Size stageSize) {
    return Offset(
      (point.dx / stageSize.width).clamp(0.0, 1.0),
      (point.dy / stageSize.height).clamp(0.0, 1.0),
    );
  }

  Rect _cropRectForStage(Size stageSize) {
    return Rect.fromLTRB(
      _cropRect.left * stageSize.width,
      _cropRect.top * stageSize.height,
      _cropRect.right * stageSize.width,
      _cropRect.bottom * stageSize.height,
    );
  }

  void _resetEdits() {
    setState(() {
      _cropRect = const Rect.fromLTWH(0, 0, 1, 1);
      _strokes.clear();
      _mode = _ImageEditorMode.crop;
    });
  }

  Future<void> _saveEditedImage() async {
    final image = _image;
    if (image == null) {
      return;
    }
    setState(() {
      _isSaving = true;
    });
    try {
      final editedBytes = await _renderEditedImage(
        image: image,
        cropRect: _cropRect,
        strokes: _strokes,
      );
      if (!mounted) {
        return;
      }
      Navigator.of(context).pop(
        _ImageEditorResult(
          bytes: editedBytes,
          fileName: _editedImageFileName(widget.fileName),
        ),
      );
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Could not save image edit: $error')),
      );
      setState(() {
        _isSaving = false;
      });
    }
  }
}

class _ImageAnnotationStroke {
  _ImageAnnotationStroke({
    required this.color,
    required this.strokeWidth,
    required this.points,
  });

  final Color color;
  final double strokeWidth;
  final List<Offset> points;
}

class _ImageEditorPainter extends CustomPainter {
  const _ImageEditorPainter({
    required this.image,
    required this.cropRect,
    required this.strokes,
    required this.mode,
  });

  final ui.Image image;
  final Rect cropRect;
  final List<_ImageAnnotationStroke> strokes;
  final _ImageEditorMode mode;

  @override
  void paint(Canvas canvas, Size size) {
    final imagePaint = Paint()..filterQuality = FilterQuality.high;
    canvas.drawImageRect(
      image,
      Rect.fromLTWH(0, 0, image.width.toDouble(), image.height.toDouble()),
      Offset.zero & size,
      imagePaint,
    );
    for (final stroke in strokes) {
      _paintStroke(canvas, size, stroke);
    }
    _paintCropOverlay(canvas, size);
  }

  void _paintStroke(Canvas canvas, Size size, _ImageAnnotationStroke stroke) {
    if (stroke.points.isEmpty) {
      return;
    }
    final paint = Paint()
      ..color = stroke.color
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round
      ..style = PaintingStyle.stroke
      ..strokeWidth = stroke.strokeWidth;
    final path = Path()
      ..moveTo(
        stroke.points.first.dx * size.width,
        stroke.points.first.dy * size.height,
      );
    for (final point in stroke.points.skip(1)) {
      path.lineTo(point.dx * size.width, point.dy * size.height);
    }
    canvas.drawPath(path, paint);
  }

  void _paintCropOverlay(Canvas canvas, Size size) {
    final crop = Rect.fromLTRB(
      cropRect.left * size.width,
      cropRect.top * size.height,
      cropRect.right * size.width,
      cropRect.bottom * size.height,
    );
    final overlayPath = Path()
      ..addRect(Offset.zero & size)
      ..addRect(crop)
      ..fillType = PathFillType.evenOdd;
    canvas.drawPath(
      overlayPath,
      Paint()..color = Colors.black.withValues(alpha: 0.46),
    );
    final borderPaint = Paint()
      ..color =
          mode == _ImageEditorMode.crop ? const Color(0xFF55D6BE) : Colors.white
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.2;
    canvas.drawRect(crop, borderPaint);
    final handlePaint = Paint()..color = const Color(0xFF55D6BE);
    for (final corner in <Offset>[
      crop.topLeft,
      crop.topRight,
      crop.bottomLeft,
      crop.bottomRight,
    ]) {
      canvas.drawCircle(corner, 6, handlePaint);
    }
  }

  @override
  bool shouldRepaint(covariant _ImageEditorPainter oldDelegate) {
    return true;
  }
}

Future<Uint8List> _renderEditedImage({
  required ui.Image image,
  required Rect cropRect,
  required List<_ImageAnnotationStroke> strokes,
}) async {
  final imageWidth = image.width.toDouble();
  final imageHeight = image.height.toDouble();
  final sourceRect = Rect.fromLTRB(
    (cropRect.left * imageWidth).roundToDouble(),
    (cropRect.top * imageHeight).roundToDouble(),
    (cropRect.right * imageWidth).roundToDouble(),
    (cropRect.bottom * imageHeight).roundToDouble(),
  );
  final outputWidth = math.max(1, sourceRect.width.round());
  final outputHeight = math.max(1, sourceRect.height.round());
  final outputRect = Rect.fromLTWH(
    0,
    0,
    outputWidth.toDouble(),
    outputHeight.toDouble(),
  );
  final recorder = ui.PictureRecorder();
  final canvas = Canvas(recorder);
  canvas.drawImageRect(
    image,
    sourceRect,
    outputRect,
    Paint()..filterQuality = FilterQuality.high,
  );
  canvas.clipRect(outputRect);
  for (final stroke in strokes) {
    _paintEditedStroke(
      canvas: canvas,
      stroke: stroke,
      imageSize: Size(imageWidth, imageHeight),
      sourceRect: sourceRect,
    );
  }
  final picture = recorder.endRecording();
  final outputImage = await picture.toImage(outputWidth, outputHeight);
  final byteData = await outputImage.toByteData(format: ui.ImageByteFormat.png);
  if (byteData == null) {
    throw StateError('PNG encoder returned no bytes.');
  }
  return byteData.buffer.asUint8List();
}

void _paintEditedStroke({
  required Canvas canvas,
  required _ImageAnnotationStroke stroke,
  required Size imageSize,
  required Rect sourceRect,
}) {
  if (stroke.points.isEmpty) {
    return;
  }
  final paint = Paint()
    ..color = stroke.color
    ..strokeCap = StrokeCap.round
    ..strokeJoin = StrokeJoin.round
    ..style = PaintingStyle.stroke
    ..strokeWidth =
        stroke.strokeWidth * (imageSize.shortestSide / 420).clamp(1.0, 5.0);
  final first = _editedStrokePoint(stroke.points.first, imageSize, sourceRect);
  final path = Path()..moveTo(first.dx, first.dy);
  for (final point in stroke.points.skip(1)) {
    final editedPoint = _editedStrokePoint(point, imageSize, sourceRect);
    path.lineTo(editedPoint.dx, editedPoint.dy);
  }
  canvas.drawPath(path, paint);
}

Offset _editedStrokePoint(Offset point, Size imageSize, Rect sourceRect) {
  return Offset(
    point.dx * imageSize.width - sourceRect.left,
    point.dy * imageSize.height - sourceRect.top,
  );
}

String _editedImageFileName(String fileName) {
  final trimmed = fileName.trim();
  if (trimmed.isEmpty) {
    return 'edited-image.png';
  }
  final dotIndex = trimmed.lastIndexOf('.');
  if (dotIndex <= 0) {
    return '$trimmed-edited.png';
  }
  return '${trimmed.substring(0, dotIndex)}-edited.png';
}

@visibleForTesting
bool isAudioAttachmentDraftInput({required String fileName, String? mimeType}) {
  final normalizedMimeType = (mimeType ?? '').trim().toLowerCase();
  if (normalizedMimeType.startsWith('audio/')) {
    return true;
  }
  final normalizedName = fileName.trim().toLowerCase();
  return normalizedName.endsWith('.aac') ||
      normalizedName.endsWith('.aif') ||
      normalizedName.endsWith('.aiff') ||
      normalizedName.endsWith('.amr') ||
      normalizedName.endsWith('.flac') ||
      normalizedName.endsWith('.m4a') ||
      normalizedName.endsWith('.mp3') ||
      normalizedName.endsWith('.oga') ||
      normalizedName.endsWith('.ogg') ||
      normalizedName.endsWith('.opus') ||
      normalizedName.endsWith('.wav') ||
      normalizedName.endsWith('.webm');
}

@visibleForTesting
Widget buildImageEditorForTest({
  required Uint8List imageBytes,
  required String fileName,
}) {
  return _ImageEditorScreen(imageBytes: imageBytes, fileName: fileName);
}

@visibleForTesting
Widget buildComposerVoiceRecordingHarnessForTest({
  required TextEditingController controller,
  required AudioNoteRecorder Function() audioRecorderFactory,
  required Future<bool> Function(XFile audioFile, {String? message})
      onSendAudio,
  required Future<bool> Function(List<XFile> attachments, {String? prompt})
      onSendAttachments,
  Future<bool> Function()? onSend,
  String stagedText = '',
  bool stageAttachment = false,
  bool isProjectFactoryIntake = false,
  SlashCommandContext slashCommandContext = const SlashCommandContext(),
  Future<bool> Function(String commandId, String payload)? onSlashCommand,
}) {
  return _Composer(
    sessionId: 'test-session',
    controller: controller,
    draft: _ComposerDraft(
      text: stagedText,
      attachments: stageAttachment
          ? <_PendingAttachmentDraft>[
              _PendingAttachmentDraft(
                file: XFile.fromData(
                  Uint8List.fromList(const <int>[1, 2, 3]),
                  name: 'staged-note.txt',
                  mimeType: 'text/plain',
                  path: 'staged-note.txt',
                ),
                name: 'staged-note.txt',
                kind: _AttachmentDraftKind.file,
                sizeBytes: 3,
              ),
            ]
          : const <_PendingAttachmentDraft>[],
    ),
    onDraftChanged: (_) {},
    onSend: onSend ?? () async => false,
    onSendAudio: onSendAudio,
    onSendAttachments: (attachments, {prompt}) {
      return onSendAttachments(
        attachments.map((attachment) => attachment.file).toList(),
        prompt: prompt,
      );
    },
    onBeginRecording: () async {},
    onSlashCommand: onSlashCommand ?? (_, __) async => false,
    slashCommandContext: slashCommandContext,
    audioRecorderFactory: audioRecorderFactory,
    isBusy: false,
    voiceEnabled: true,
    imageAttachmentsEnabled: true,
    fileAttachmentsEnabled: true,
    voiceStatusText: 'Audio transcription ready.',
    isProjectFactoryIntake: isProjectFactoryIntake,
  );
}

class _ComposerDraft {
  const _ComposerDraft({
    this.text = '',
    this.attachments = const <_PendingAttachmentDraft>[],
    this.codexRunOptions = const CodexRunOptions(),
  });

  final String text;
  final List<_PendingAttachmentDraft> attachments;
  final CodexRunOptions codexRunOptions;

  bool get isEmpty =>
      text.trim().isEmpty && attachments.isEmpty && codexRunOptions.isEmpty;
}

class _VoiceStatusCard extends StatelessWidget {
  const _VoiceStatusCard({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.color,
    this.trailing,
    this.titleMaxLines = 1,
    this.subtitleMaxLines = 2,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final Color color;
  final Widget? trailing;
  final int titleMaxLines;
  final int subtitleMaxLines;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: const Color(0xFF15203B),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: color.withValues(alpha: 0.35)),
      ),
      child: Row(
        children: <Widget>[
          Icon(icon, color: color),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Text(
                  title,
                  maxLines: titleMaxLines,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontWeight: FontWeight.w600),
                ),
                const SizedBox(height: 2),
                Text(
                  subtitle,
                  maxLines: subtitleMaxLines,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: Color(0xFF8B97B5)),
                ),
              ],
            ),
          ),
          if (trailing != null) ...<Widget>[
            const SizedBox(width: 12),
            trailing!,
          ],
        ],
      ),
    );
  }
}

class _PendingAttachmentTray extends StatelessWidget {
  const _PendingAttachmentTray({
    required this.attachments,
    required this.busy,
    required this.isProjectFactoryIntake,
    required this.onRemove,
    required this.onRoleChanged,
    required this.onClearAll,
    required this.expanded,
    required this.onToggleExpanded,
  });

  final List<_PendingAttachmentDraft> attachments;
  final bool busy;
  final bool isProjectFactoryIntake;
  final ValueChanged<_PendingAttachmentDraft> onRemove;
  final void Function(
    _PendingAttachmentDraft attachment,
    ProjectAssetRole? role,
  ) onRoleChanged;
  final VoidCallback onClearAll;
  final bool expanded;
  final VoidCallback onToggleExpanded;

  @override
  Widget build(BuildContext context) {
    final imageCount =
        attachments.where((attachment) => attachment.isImage).length;
    final audioCount =
        attachments.where((attachment) => attachment.isAudio).length;
    final fileCount = attachments.length - imageCount - audioCount;

    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: const Color(0xFF15203B),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: const Color(0xFF2B395D)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          LayoutBuilder(
            builder: (context, constraints) {
              final useStackedHeader = constraints.maxWidth < 320;
              final statusPill = _StatusPill(
                label: '${attachments.length} selected',
                backgroundColor: const Color(0xFF1E2944),
                foregroundColor: const Color(0xFFB8C8EA),
              );

              if (useStackedHeader) {
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Row(
                      children: <Widget>[
                        const Expanded(
                          child: Text(
                            'Attachments ready',
                            style: TextStyle(fontWeight: FontWeight.w700),
                          ),
                        ),
                        const SizedBox(width: 8),
                        statusPill,
                        IconButton(
                          onPressed: onToggleExpanded,
                          tooltip: expanded
                              ? 'Collapse attachments'
                              : 'Expand attachments',
                          icon: Icon(
                            expanded
                                ? Icons.expand_less_rounded
                                : Icons.expand_more_rounded,
                          ),
                        ),
                      ],
                    ),
                    Align(
                      alignment: Alignment.centerRight,
                      child: TextButton(
                        onPressed: busy ? null : onClearAll,
                        child: const Text('Clear all'),
                      ),
                    ),
                  ],
                );
              }

              return Row(
                children: <Widget>[
                  const Expanded(
                    child: Text(
                      'Attachments ready',
                      style: TextStyle(fontWeight: FontWeight.w700),
                    ),
                  ),
                  statusPill,
                  const SizedBox(width: 8),
                  IconButton(
                    onPressed: onToggleExpanded,
                    tooltip: expanded
                        ? 'Collapse attachments'
                        : 'Expand attachments',
                    icon: Icon(
                      expanded
                          ? Icons.expand_less_rounded
                          : Icons.expand_more_rounded,
                    ),
                  ),
                  const SizedBox(width: 4),
                  TextButton(
                    onPressed: busy ? null : onClearAll,
                    child: const Text('Clear all'),
                  ),
                ],
              );
            },
          ),
          const SizedBox(height: 4),
          Align(
            alignment: Alignment.centerLeft,
            child: Text(
              _buildAttachmentTraySummary(
                totalCount: attachments.length,
                imageCount: imageCount,
                audioCount: audioCount,
                fileCount: fileCount,
              ),
              style: const TextStyle(color: Color(0xFF8B97B5), height: 1.4),
            ),
          ),
          if (expanded) ...<Widget>[
            const SizedBox(height: 10),
            ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 220),
              child: ListView.separated(
                shrinkWrap: true,
                itemCount: attachments.length,
                separatorBuilder: (context, index) => const SizedBox(height: 8),
                itemBuilder: (context, index) {
                  final attachment = attachments[index];
                  return _PendingAttachmentRow(
                    attachment: attachment,
                    busy: busy,
                    showProjectAssetRole: isProjectFactoryIntake,
                    onRemove: () => onRemove(attachment),
                    onRoleChanged: (role) => onRoleChanged(attachment, role),
                  );
                },
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _PendingAttachmentRow extends StatelessWidget {
  const _PendingAttachmentRow({
    required this.attachment,
    required this.busy,
    required this.showProjectAssetRole,
    required this.onRemove,
    required this.onRoleChanged,
  });

  final _PendingAttachmentDraft attachment;
  final bool busy;
  final bool showProjectAssetRole;
  final VoidCallback onRemove;
  final ValueChanged<ProjectAssetRole?> onRoleChanged;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        _AttachmentPreview(attachment: attachment),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Wrap(
                spacing: 8,
                runSpacing: 6,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: <Widget>[
                  _StatusPill(
                    label: attachment.badgeLabel,
                    backgroundColor: attachment.isImage
                        ? const Color(0xFF11352E)
                        : attachment.isAudio
                            ? const Color(0xFF3B1521)
                            : const Color(0xFF1E2944),
                    foregroundColor: attachment.isImage
                        ? const Color(0xFF9FF0DC)
                        : attachment.isAudio
                            ? const Color(0xFFFFB3B3)
                            : const Color(0xFFB8C8EA),
                  ),
                  if (attachment.sizeBytes != null) ...<Widget>[
                    Text(
                      _formatAttachmentSize(attachment.sizeBytes!),
                      style: const TextStyle(
                        color: Color(0xFF8B97B5),
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ],
              ),
              const SizedBox(height: 8),
              Text(
                attachment.name,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontWeight: FontWeight.w700),
              ),
              if (showProjectAssetRole) ...<Widget>[
                const SizedBox(height: 8),
                _ProjectAssetRoleSelector(
                  value: attachment.projectAssetRole,
                  enabled: !busy,
                  onChanged: onRoleChanged,
                ),
              ],
            ],
          ),
        ),
        IconButton(
          onPressed: busy ? null : onRemove,
          tooltip: 'Remove attachment',
          icon: const Icon(Icons.close_rounded),
        ),
      ],
    );
  }
}

class _ProjectAssetRoleSelector extends StatelessWidget {
  const _ProjectAssetRoleSelector({
    required this.value,
    required this.enabled,
    required this.onChanged,
  });

  final ProjectAssetRole? value;
  final bool enabled;
  final ValueChanged<ProjectAssetRole?> onChanged;

  @override
  Widget build(BuildContext context) {
    return DropdownButtonFormField<ProjectAssetRole?>(
      initialValue: value,
      isDense: true,
      decoration: const InputDecoration(
        labelText: 'New Project asset',
        contentPadding: EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      ),
      items: <DropdownMenuItem<ProjectAssetRole?>>[
        const DropdownMenuItem<ProjectAssetRole?>(
          value: null,
          child: Text('Chat context only'),
        ),
        for (final role in ProjectAssetRole.values)
          DropdownMenuItem<ProjectAssetRole?>(
            value: role,
            child: Text(role.label),
          ),
      ],
      onChanged: enabled ? onChanged : null,
    );
  }
}

class _AttachmentPreview extends StatelessWidget {
  const _AttachmentPreview({required this.attachment});

  final _PendingAttachmentDraft attachment;

  @override
  Widget build(BuildContext context) {
    final previewBytes = attachment.previewBytes;
    if (attachment.isImage && previewBytes != null) {
      return ClipRRect(
        borderRadius: BorderRadius.circular(12),
        child: Image.memory(
          previewBytes,
          width: 60,
          height: 60,
          fit: BoxFit.cover,
          errorBuilder: (context, error, stackTrace) {
            return const _AttachmentFallbackIcon(
              icon: Icons.broken_image_outlined,
            );
          },
        ),
      );
    }

    return _AttachmentFallbackIcon(
      icon: attachment.isAudio
          ? Icons.graphic_eq_rounded
          : Icons.insert_drive_file_outlined,
    );
  }
}

class _AttachmentFallbackIcon extends StatelessWidget {
  const _AttachmentFallbackIcon({required this.icon});

  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 60,
      height: 60,
      decoration: BoxDecoration(
        color: const Color(0xFF31405F),
        borderRadius: BorderRadius.circular(12),
      ),
      alignment: Alignment.center,
      child: Icon(icon, color: const Color(0xFFE8ECF8)),
    );
  }
}

String _formatAttachmentSize(int sizeBytes) {
  if (sizeBytes < 1024) {
    return '$sizeBytes B';
  }
  if (sizeBytes < 1024 * 1024) {
    return '${(sizeBytes / 1024).toStringAsFixed(1)} KB';
  }
  return '${(sizeBytes / (1024 * 1024)).toStringAsFixed(1)} MB';
}

String _buildAttachmentTraySummary({
  required int totalCount,
  required int imageCount,
  required int audioCount,
  required int fileCount,
}) {
  if (totalCount == 1 && imageCount == 1) {
    return 'One image is ready. Add optional instructions or send it as-is.';
  }
  if (totalCount == 1 && audioCount == 1) {
    return 'One voice note is ready. Add optional instructions or send it as-is.';
  }
  if (totalCount == 1 && fileCount == 1) {
    return 'One file is ready. Tell Codex what you want from it.';
  }

  final parts = <String>[];
  if (imageCount > 0) {
    parts.add('$imageCount image${imageCount == 1 ? '' : 's'}');
  }
  if (audioCount > 0) {
    parts.add('$audioCount voice note${audioCount == 1 ? '' : 's'}');
  }
  if (fileCount > 0) {
    parts.add('$fileCount file${fileCount == 1 ? '' : 's'}');
  }
  return '${parts.join(' and ')} queued. They will be sent together in one Codex turn.';
}

class _CodexOptionTray extends StatelessWidget {
  const _CodexOptionTray({required this.options});

  final CodexRunOptions options;

  @override
  Widget build(BuildContext context) {
    final pills = <Widget>[
      if (options.profile?.trim().isNotEmpty ?? false)
        _StatusPill(
          label: 'profile:${options.profile!.trim()}',
          backgroundColor: const Color(0xFF233151),
          foregroundColor: const Color(0xFFB7C8F8),
        ),
      if (options.searchEnabled)
        const _StatusPill(
          label: 'search',
          backgroundColor: Color(0xFF1F4D45),
          foregroundColor: Color(0xFFB6F4E4),
        ),
      ...options.skillIds.map(
        (skillId) => _StatusPill(
          label: skillId,
          backgroundColor: const Color(0xFF3A2714),
          foregroundColor: const Color(0xFFFFD9A3),
        ),
      ),
      ...options.mcpServerIds.map(
        (serverId) => _StatusPill(
          label: 'mcp:$serverId',
          backgroundColor: const Color(0xFF2F2146),
          foregroundColor: const Color(0xFFD9C2FF),
        ),
      ),
      if (options.configOverrides.isNotEmpty)
        const _StatusPill(
          label: 'config',
          backgroundColor: Color(0xFF2B364D),
          foregroundColor: Color(0xFFB8C3DA),
        ),
    ];

    return Align(
      alignment: Alignment.centerLeft,
      child: Wrap(spacing: 8, runSpacing: 8, children: pills),
    );
  }
}

List<String> _recommendedCodexSkillIds({
  required String? agentProfileId,
  required String? agentProfileName,
}) {
  final profileSignals = <String>[
    agentProfileId ?? '',
    agentProfileName ?? '',
  ].join(' ').toLowerCase();
  final recommended = <String>[];

  if (profileSignals.contains('agent_creator') ||
      profileSignals.contains('creator')) {
    recommended.add('skill-creator');
  }
  if (profileSignals.contains('android') ||
      profileSignals.contains('release') ||
      profileSignals.contains('deploy')) {
    recommended.add('codex-mobile-android-release');
  }
  return recommended;
}

Set<String> normalizeSelectedCodexMcpServerIds(
  CodexToolingSnapshot? tooling,
  Iterable<String> selectedIds,
) {
  if (tooling == null) {
    return <String>{};
  }
  final selectableIds = {
    for (final server in tooling.mcpServers)
      if (server.selectable) server.serverId,
  };
  return selectedIds.where(selectableIds.contains).toSet();
}

class _McpAppOpenRequest {
  const _McpAppOpenRequest({required this.app, this.focusHint});

  final CodexMcpApp app;
  final String? focusHint;
}

_McpAppOpenRequest? _matchMcpAppOpenCommand(
  String rawMessage,
  CodexToolingSnapshot? tooling,
) {
  final apps = tooling?.mcpApps ?? const <CodexMcpApp>[];
  if (apps.isEmpty) {
    return null;
  }
  final normalized = _normalizeMcpAppLookupToken(rawMessage);
  if (normalized.isEmpty) {
    return null;
  }

  String? target;
  for (final prefix in const <String>['open ', 'launch ', 'show ']) {
    if (normalized.startsWith(prefix)) {
      target = normalized.substring(prefix.length).trim();
      break;
    }
  }
  if (target == null) {
    return null;
  }

  target = target.replaceFirst(RegExp(r'^(the|this|that)\s+'), '');
  target = target.replaceFirst(RegExp(r'^(mcp\s+app|app|mcp)\s+'), '');
  target = target.trim();

  final genericMatch = RegExp(r'^(mcp\s+apps?|apps?)\b').firstMatch(target);
  if (genericMatch != null) {
    final focusHint = target.substring(genericMatch.end).trim();
    if (apps.length == 1) {
      return _McpAppOpenRequest(
        app: apps.single,
        focusHint: _normalizeFocusHint(focusHint),
      );
    }
    return null;
  }

  for (final app in apps) {
    final candidates = <String>{
      _normalizeMcpAppLookupToken(app.appId),
      _normalizeMcpAppLookupToken(app.name),
      _normalizeMcpAppLookupToken(app.recommendedServerId),
    };
    for (final candidate in candidates) {
      if (target == candidate) {
        return _McpAppOpenRequest(app: app);
      }
      if (target.startsWith('$candidate ')) {
        final trailing = target.substring(candidate.length).trim();
        return _McpAppOpenRequest(
          app: app,
          focusHint: _normalizeFocusHint(trailing),
        );
      }
    }
  }
  return null;
}

String? _normalizeFocusHint(String rawValue) {
  var normalized = rawValue.trim();
  if (normalized.isEmpty) {
    return null;
  }
  normalized = normalized.replaceFirst(RegExp(r'^(for|about|on)\s+'), '');
  normalized = normalized.replaceFirst(RegExp(r'^(the|this|that)\s+'), '');
  normalized = normalized.replaceFirst(RegExp(r'^(project|repo)\s+'), '');
  normalized = normalized.trim();
  return normalized.isEmpty ? null : normalized;
}

String _normalizeMcpAppLookupToken(String value) {
  return value.toLowerCase().replaceAll(RegExp(r'[^a-z0-9]+'), ' ').trim();
}

List<Map<String, dynamic>>? _extractMcpPreviewProjects(
  Object? previewResult, {
  int limit = 12,
}) {
  if (previewResult is! Map<String, dynamic>) {
    return null;
  }
  final projects = previewResult['projects'];
  if (projects is! List<dynamic>) {
    return null;
  }
  return projects
      .whereType<Map<String, dynamic>>()
      .take(limit)
      .toList(growable: false);
}

String _prettyMcpPreviewJson(Object? value) {
  if (value == null) {
    return 'No preview result.';
  }
  try {
    return const JsonEncoder.withIndent('  ').convert(value);
  } catch (_) {
    return value.toString();
  }
}

class _CodexToolsSheet extends StatefulWidget {
  const _CodexToolsSheet({
    required this.initialOptions,
    required this.tooling,
    required this.errorText,
    required this.loading,
    required this.onInstallApp,
    required this.onOpenApp,
    this.agentProfileId,
    this.agentProfileName,
  });

  final CodexRunOptions initialOptions;
  final CodexToolingSnapshot? tooling;
  final String? errorText;
  final bool loading;
  final Future<CodexToolingSnapshot?> Function(CodexMcpApp app) onInstallApp;
  final Future<void> Function(CodexMcpApp app) onOpenApp;
  final String? agentProfileId;
  final String? agentProfileName;

  @override
  State<_CodexToolsSheet> createState() => _CodexToolsSheetState();
}

class _CodexToolsSheetState extends State<_CodexToolsSheet> {
  late final TextEditingController _profileController;
  late final TextEditingController _configOverridesController;
  late bool _searchEnabled;
  late Set<String> _selectedSkillIds;
  late Set<String> _selectedMcpServerIds;
  CodexToolingSnapshot? _tooling;
  String? _errorText;
  bool _isInstallingApp = false;
  String? _installingAppId;

  @override
  void initState() {
    super.initState();
    _profileController = TextEditingController(
      text: widget.initialOptions.profile ?? '',
    );
    _configOverridesController = TextEditingController(
      text: widget.initialOptions.configOverrides.join('\n'),
    );
    _searchEnabled = widget.initialOptions.searchEnabled;
    _selectedSkillIds = widget.initialOptions.skillIds.toSet();
    _selectedMcpServerIds = widget.initialOptions.mcpServerIds.toSet();
    _tooling = widget.tooling;
    _selectedMcpServerIds = normalizeSelectedCodexMcpServerIds(
      _tooling,
      _selectedMcpServerIds,
    );
    _errorText = widget.errorText;
  }

  @override
  void dispose() {
    _profileController.dispose();
    _configOverridesController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final tooling = _tooling;
    final status = tooling?.status;
    final insetBottom = MediaQuery.viewInsetsOf(context).bottom;
    final recommendedSkillIds = _recommendedSkillIds();
    final orderedSkills =
        tooling == null ? const <CodexSkill>[] : _orderedSkills(tooling.skills);

    return SafeArea(
      child: Padding(
        padding: EdgeInsets.only(bottom: insetBottom),
        child: SingleChildScrollView(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                const ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: Icon(Icons.tune_rounded),
                  title: Text('Codex tools'),
                  subtitle: Text(
                    'Use real local Codex skills, MCP apps, profiles, and status.',
                  ),
                ),
                if (widget.loading || _isInstallingApp)
                  const Padding(
                    padding: EdgeInsets.only(bottom: 12),
                    child: LinearProgressIndicator(minHeight: 3),
                  ),
                if (_errorText != null)
                  Container(
                    width: double.infinity,
                    margin: const EdgeInsets.only(bottom: 12),
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: const Color(0xFF3B1521),
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(color: const Color(0xFFFF7A7A)),
                    ),
                    child: Text(
                      _errorText!,
                      style: const TextStyle(color: Color(0xFFFFD7D7)),
                    ),
                  ),
                if (status != null)
                  Container(
                    width: double.infinity,
                    margin: const EdgeInsets.only(bottom: 12),
                    padding: const EdgeInsets.all(14),
                    decoration: BoxDecoration(
                      color: const Color(0xFF15203B),
                      borderRadius: BorderRadius.circular(18),
                      border: Border.all(color: const Color(0xFF24355F)),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Row(
                          children: <Widget>[
                            Icon(
                              status.loggedIn
                                  ? Icons.verified_user_outlined
                                  : Icons.error_outline_rounded,
                              color: status.loggedIn
                                  ? const Color(0xFF55D6BE)
                                  : const Color(0xFFFF7A7A),
                            ),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Text(
                                status.statusSummary,
                                style: const TextStyle(
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 8),
                        Text(
                          'Command: ${status.command}'
                          '${status.version == null ? '' : ' · ${status.version}'}',
                          style: const TextStyle(color: Color(0xFF8B97B5)),
                        ),
                        if (status.usageSummary != null) ...<Widget>[
                          const SizedBox(height: 8),
                          Text(
                            status.usageSummary!,
                            style: const TextStyle(color: Color(0xFF8B97B5)),
                          ),
                        ],
                      ],
                    ),
                  ),
                TextField(
                  controller: _profileController,
                  decoration: InputDecoration(
                    labelText: 'Codex profile',
                    hintText: 'safe',
                    helperText: tooling == null || tooling.profiles.isEmpty
                        ? 'Optional. Enter a profile name from ~/.codex/config.toml if you use one.'
                        : 'Available profiles: ${tooling.profiles.map((profile) => profile.name).join(', ')}',
                  ),
                ),
                const SizedBox(height: 10),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  value: _searchEnabled,
                  onChanged: (value) {
                    setState(() {
                      _searchEnabled = value;
                    });
                  },
                  title: const Text('Enable web search'),
                  subtitle: const Text(
                    'Adds `--search` to the local Codex run.',
                  ),
                ),
                const SizedBox(height: 12),
                Text(
                  'Installed skills',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                if (recommendedSkillIds.isNotEmpty) ...<Widget>[
                  const SizedBox(height: 4),
                  Text(
                    'Recommended for this agent: ${recommendedSkillIds.join(', ')}',
                    style: const TextStyle(color: Color(0xFF8B97B5)),
                  ),
                ],
                const SizedBox(height: 8),
                if (tooling == null || tooling.skills.isEmpty)
                  const Text(
                    'No Codex skills were discovered for this backend user.',
                    style: TextStyle(color: Color(0xFF8B97B5)),
                  )
                else
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: orderedSkills.map((skill) {
                      final selected = _selectedSkillIds.contains(
                        skill.skillId,
                      );
                      return FilterChip(
                        selected: selected,
                        label: Text(skill.skillId),
                        tooltip:
                            '${skill.description}\nSource: ${skill.source}',
                        onSelected: (value) {
                          setState(() {
                            if (value) {
                              _selectedSkillIds.add(skill.skillId);
                            } else {
                              _selectedSkillIds.remove(skill.skillId);
                            }
                          });
                        },
                      );
                    }).toList(),
                  ),
                const SizedBox(height: 14),
                Text(
                  'Available MCP apps',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: 8),
                if (tooling == null || tooling.mcpApps.isEmpty)
                  const Text(
                    'No repo MCP apps were discovered for this backend.',
                    style: TextStyle(color: Color(0xFF8B97B5)),
                  )
                else
                  Column(
                    children: tooling.mcpApps
                        .map((app) => _buildMcpAppCard(context, app))
                        .toList(),
                  ),
                const SizedBox(height: 14),
                Text(
                  'Configured MCP servers',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: 8),
                if (tooling != null &&
                    !tooling.mcpServerInventoryComplete) ...<Widget>[
                  Container(
                    width: double.infinity,
                    margin: const EdgeInsets.only(bottom: 10),
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: const Color(0xFF3A2714),
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(color: const Color(0xFF7C5A2A)),
                    ),
                    child: Text(
                      'Codex MCP inventory is incomplete, so direct MCP server selection is temporarily unavailable.\n'
                      '${tooling.mcpError ?? "Retry `codex mcp list` when the CLI is healthy."}',
                      style: const TextStyle(color: Color(0xFFFFD9A3)),
                    ),
                  ),
                ],
                if (tooling == null || tooling.mcpServers.isEmpty)
                  Text(
                    tooling?.mcpRawOutput?.trim().isNotEmpty == true
                        ? tooling!.mcpRawOutput!
                        : 'No MCP servers were reported by `codex mcp list`.',
                    style: const TextStyle(color: Color(0xFF8B97B5)),
                  )
                else
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: tooling.mcpServers.map((server) {
                      final selected = _selectedMcpServerIds.contains(
                        server.serverId,
                      );
                      return FilterChip(
                        selected: selected,
                        label: Text(server.serverId),
                        tooltip: server.selectableReason == null
                            ? server.summary
                            : '${server.summary}\n${server.selectableReason}',
                        onSelected: server.selectable
                            ? (value) {
                                setState(() {
                                  if (value) {
                                    _selectedMcpServerIds.add(server.serverId);
                                  } else {
                                    _selectedMcpServerIds.remove(
                                      server.serverId,
                                    );
                                  }
                                });
                              }
                            : null,
                      );
                    }).toList(),
                  ),
                const SizedBox(height: 14),
                TextField(
                  controller: _configOverridesController,
                  minLines: 2,
                  maxLines: 4,
                  decoration: const InputDecoration(
                    labelText: 'Extra Codex config overrides',
                    hintText: 'One `key=value` override per line',
                  ),
                ),
                const SizedBox(height: 16),
                Row(
                  children: <Widget>[
                    TextButton(
                      onPressed: () {
                        Navigator.of(context).pop(const CodexRunOptions());
                      },
                      child: const Text('Clear'),
                    ),
                    const Spacer(),
                    FilledButton(
                      onPressed: () {
                        Navigator.of(context).pop(_buildResult());
                      },
                      child: const Text('Save'),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  List<String> _recommendedSkillIds() {
    return _recommendedCodexSkillIds(
      agentProfileId: widget.agentProfileId,
      agentProfileName: widget.agentProfileName,
    );
  }

  List<CodexSkill> _orderedSkills(List<CodexSkill> skills) {
    final recommendedSkillIds = _recommendedSkillIds().toSet();
    final ordered = skills.toList();
    ordered.sort((left, right) {
      final leftRank = _skillOrderRank(
        left,
        recommendedSkillIds: recommendedSkillIds,
      );
      final rightRank = _skillOrderRank(
        right,
        recommendedSkillIds: recommendedSkillIds,
      );
      if (leftRank != rightRank) {
        return leftRank.compareTo(rightRank);
      }
      return left.skillId.compareTo(right.skillId);
    });
    return ordered;
  }

  int _skillOrderRank(
    CodexSkill skill, {
    required Set<String> recommendedSkillIds,
  }) {
    if (_selectedSkillIds.contains(skill.skillId)) {
      return 0;
    }
    if (recommendedSkillIds.contains(skill.skillId)) {
      return 1;
    }
    return switch (skill.source) {
      'repo' => 2,
      'system' => 3,
      'user' => 4,
      'plugin' => 5,
      _ => 6,
    };
  }

  Widget _buildMcpAppCard(BuildContext context, CodexMcpApp app) {
    final theme = Theme.of(context);
    final isSelected = _selectedMcpServerIds.contains(app.recommendedServerId);
    final isInstalling = _installingAppId == app.appId;
    final validationError = app.validationError?.trim();
    final lookupError = app.lookupError?.trim();
    final protocolError = app.protocolError?.trim();
    final hasInstallBlockingError = (validationError?.isNotEmpty ?? false) ||
        (lookupError?.isNotEmpty ?? false) ||
        (protocolError?.isNotEmpty ?? false);
    final preview = app.preview;
    final previewResult = preview?.result;
    final launchSummary = app.launchSummary;
    final toolCount = app.tools.length;
    final resourceCount = app.resources.length;
    final promptCount = app.prompts.length;
    final installStateStyle = _mcpAppInstallStateStyle(app);
    final actionLabel = switch (app.installState) {
      'drifted' => 'Reconcile & enable',
      'disabled' when app.configMatches == false => 'Reconcile & enable',
      'disabled' => 'Re-enable & use',
      _ => 'Install & enable',
    };
    final installHelpText = _mcpAppInstallHelpText(
      app,
      hasInstallBlockingError: hasInstallBlockingError,
    );

    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF111C34),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: installStateStyle.$2),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      app.name,
                      style: theme.textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      app.description,
                      style: const TextStyle(color: Color(0xFFB9C5E3)),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              _StatusPill(
                label: installStateStyle.$1,
                backgroundColor: installStateStyle.$2,
                foregroundColor: installStateStyle.$3,
              ),
            ],
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: <Widget>[
              _StatusPill(
                label: 'server:${app.recommendedServerId}',
                backgroundColor: const Color(0xFF24355F),
                foregroundColor: const Color(0xFFDCE5FF),
              ),
              _StatusPill(
                label: '$toolCount tool${toolCount == 1 ? '' : 's'}',
                backgroundColor: const Color(0xFF3A2714),
                foregroundColor: const Color(0xFFFFD9A3),
              ),
              if (resourceCount > 0)
                _StatusPill(
                  label:
                      '$resourceCount resource${resourceCount == 1 ? '' : 's'}',
                  backgroundColor: const Color(0xFF1D3D52),
                  foregroundColor: const Color(0xFFBFE8FF),
                ),
              if (promptCount > 0)
                _StatusPill(
                  label: '$promptCount prompt${promptCount == 1 ? '' : 's'}',
                  backgroundColor: const Color(0xFF2F2146),
                  foregroundColor: const Color(0xFFD9C2FF),
                ),
              if (app.supportsUiExtension)
                const _StatusPill(
                  label: 'ui',
                  backgroundColor: Color(0xFF32481D),
                  foregroundColor: Color(0xFFD5F5B6),
                ),
              ...app.tags.map(
                (tag) => _StatusPill(
                  label: tag,
                  backgroundColor: const Color(0xFF2B364D),
                  foregroundColor: const Color(0xFFB8C3DA),
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            'Launch: $launchSummary',
            style: const TextStyle(color: Color(0xFF8B97B5)),
          ),
          if (validationError != null &&
              validationError.isNotEmpty) ...<Widget>[
            const SizedBox(height: 10),
            Text(
              'Spec validation failed: $validationError',
              style: const TextStyle(color: Color(0xFFFFB3B3)),
            ),
          ],
          if (lookupError != null && lookupError.isNotEmpty) ...<Widget>[
            const SizedBox(height: 10),
            Text(
              'Installed server state is unreadable: $lookupError',
              style: const TextStyle(color: Color(0xFFFFD9A3)),
            ),
          ],
          if (protocolError != null && protocolError.isNotEmpty) ...<Widget>[
            const SizedBox(height: 10),
            Text(
              'Protocol check failed: $protocolError',
              style: const TextStyle(color: Color(0xFFFFB3B3)),
            ),
          ],
          if (app.driftSummary != null &&
              app.driftSummary!.trim().isNotEmpty) ...<Widget>[
            const SizedBox(height: 10),
            Text(
              'Stored Codex config drifted: ${app.driftSummary!}',
              style: const TextStyle(color: Color(0xFFFFD9A3)),
            ),
          ],
          if (app.disabledReason != null &&
              app.disabledReason!.trim().isNotEmpty) ...<Widget>[
            const SizedBox(height: 10),
            Text(
              'Stored server is disabled: ${app.disabledReason!}',
              style: const TextStyle(color: Color(0xFFFFD9A3)),
            ),
          ],
          if (preview != null) ...<Widget>[
            const SizedBox(height: 12),
            Text(
              'Preview from `${preview.toolName}`',
              style: theme.textTheme.bodyMedium?.copyWith(
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 8),
            _buildMcpPreviewCard(previewResult),
            if (preview.isError && preview.error != null) ...<Widget>[
              const SizedBox(height: 8),
              Text(
                preview.error!,
                style: const TextStyle(color: Color(0xFFFFB3B3)),
              ),
            ],
          ],
          if (toolCount > 0) ...<Widget>[
            const SizedBox(height: 12),
            Text(
              'Tools: ${app.tools.map((tool) => tool.name).join(', ')}',
              style: const TextStyle(color: Color(0xFF8B97B5)),
            ),
          ],
          const SizedBox(height: 12),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: <Widget>[
              FilledButton.tonalIcon(
                onPressed: () => widget.onOpenApp(app),
                icon: const Icon(Icons.open_in_full_rounded),
                label: const Text('Open app'),
              ),
              if (app.installed)
                FilledButton.tonalIcon(
                  onPressed: () {
                    setState(() {
                      if (isSelected) {
                        _selectedMcpServerIds.remove(app.recommendedServerId);
                      } else {
                        _selectedMcpServerIds.add(app.recommendedServerId);
                      }
                    });
                  },
                  icon: Icon(
                    isSelected ? Icons.check_circle_outline : Icons.add_link,
                  ),
                  label: Text(
                    isSelected ? 'Enabled for run' : 'Enable for run',
                  ),
                )
              else
                FilledButton.icon(
                  onPressed: isInstalling || hasInstallBlockingError
                      ? null
                      : () => _handleInstallApp(app),
                  icon: isInstalling
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.download_for_offline_outlined),
                  label: Text(actionLabel),
                ),
              SizedBox(
                width: 360,
                child: Text(
                  installHelpText,
                  style: const TextStyle(color: Color(0xFF8B97B5)),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  (String, Color, Color) _mcpAppInstallStateStyle(CodexMcpApp app) {
    return switch (app.installState) {
      'matching' => (
          'matching',
          const Color(0xFF1F4D45),
          const Color(0xFFB6F4E4),
        ),
      'drifted' => (
          'drifted',
          const Color(0xFF5A3A16),
          const Color(0xFFFFD9A3),
        ),
      'disabled' when app.configMatches == false => (
          'disabled-drifted',
          const Color(0xFF5A3A16),
          const Color(0xFFFFD9A3),
        ),
      'disabled' => (
          'disabled',
          const Color(0xFF5A3A16),
          const Color(0xFFFFD9A3),
        ),
      'protocol-broken' => (
          'protocol-broken',
          const Color(0xFF5A1F28),
          const Color(0xFFFFC4CB),
        ),
      'unreadable' => (
          'unreadable',
          const Color(0xFF5A3A16),
          const Color(0xFFFFD9A3),
        ),
      'invalid' => (
          'invalid',
          const Color(0xFF5A1F28),
          const Color(0xFFFFC4CB),
        ),
      _ => ('missing', const Color(0xFF2B364D), const Color(0xFFB8C3DA)),
    };
  }

  String _mcpAppInstallHelpText(
    CodexMcpApp app, {
    required bool hasInstallBlockingError,
  }) {
    if (app.installed) {
      return 'Installed into Codex and ready for selection.';
    }
    if (hasInstallBlockingError) {
      return switch (app.installState) {
        'unreadable' =>
          'Codex could not read the existing stored server state safely. Fix that before installing or reconciling this app.',
        _ =>
          'Fix the app spec or server health first. Invalid apps are shown for diagnosis only.',
      };
    }
    return switch (app.installState) {
      'drifted' =>
        'The stored Codex server config no longer matches this repo app. Reconcile it and select it for this run.',
      'disabled' when app.configMatches == false =>
        'The stored Codex server is disabled and no longer matches this repo app. Reconcile it and select it for this run.',
      'disabled' =>
        'The stored Codex server exists but is disabled. Re-enable it and select it for this run.',
      _ =>
        'Registers the repo app with `codex mcp add` and selects it for this run.',
    };
  }

  Widget _buildMcpPreviewCard(Object? previewResult) {
    final projects = _extractMcpPreviewProjects(previewResult, limit: 5);
    if (projects != null && projects.isNotEmpty) {
      return Container(
        width: double.infinity,
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: const Color(0xFF0C152B),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: const Color(0xFF203154)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: projects.map((project) {
            final name = project['name']?.toString() ?? 'project';
            final languages =
                (project['detected_languages'] as List<dynamic>? ??
                        const <dynamic>[])
                    .map((item) => item.toString())
                    .where((item) => item.isNotEmpty)
                    .join(', ');
            final signatures = (project['signature_files'] as List<dynamic>? ??
                    const <dynamic>[])
                .map((item) => item.toString())
                .where((item) => item.isNotEmpty)
                .join(', ');
            return Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    name,
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                  if (languages.isNotEmpty)
                    Text(
                      languages,
                      style: const TextStyle(color: Color(0xFF8B97B5)),
                    ),
                  if (signatures.isNotEmpty)
                    Text(
                      signatures,
                      style: const TextStyle(color: Color(0xFF8B97B5)),
                    ),
                ],
              ),
            );
          }).toList(),
        ),
      );
    }

    final pretty = _prettyMcpPreviewJson(previewResult);
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFF0C152B),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFF203154)),
      ),
      child: SelectableText(
        pretty,
        style: const TextStyle(
          color: Color(0xFFDCE5FF),
          fontFamily: 'monospace',
          fontSize: 12,
        ),
      ),
    );
  }

  Future<void> _handleInstallApp(CodexMcpApp app) async {
    setState(() {
      _isInstallingApp = true;
      _installingAppId = app.appId;
      _errorText = null;
    });

    try {
      final snapshot = await widget.onInstallApp(app);
      if (!mounted) {
        return;
      }
      setState(() {
        _tooling = snapshot ?? _tooling;
        _selectedMcpServerIds = normalizeSelectedCodexMcpServerIds(
          _tooling,
          _selectedMcpServerIds,
        );
        if (_tooling?.mcpServers.any(
              (server) =>
                  server.serverId == app.recommendedServerId &&
                  server.selectable,
            ) ??
            false) {
          _selectedMcpServerIds.add(app.recommendedServerId);
        }
        _isInstallingApp = false;
        _installingAppId = null;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _isInstallingApp = false;
        _installingAppId = null;
        _errorText = 'Failed to install `${app.name}`.\n$error';
      });
    }
  }

  CodexRunOptions _buildResult() {
    final profile = _profileController.text.trim();
    final overrides = _configOverridesController.text
        .split('\n')
        .map((line) => line.trim())
        .where((line) => line.isNotEmpty)
        .toList(growable: false);
    final skillIds = _selectedSkillIds.toList()..sort();
    final normalizedMcpServerIds = normalizeSelectedCodexMcpServerIds(
      _tooling,
      _selectedMcpServerIds,
    );
    final mcpServerIds = normalizedMcpServerIds.toList()..sort();
    return CodexRunOptions(
      profile: profile.isEmpty ? null : profile,
      searchEnabled: _searchEnabled,
      skillIds: skillIds,
      mcpServerIds: mcpServerIds,
      configOverrides: overrides,
    );
  }
}

class _StatusPill extends StatelessWidget {
  const _StatusPill({
    required this.label,
    required this.backgroundColor,
    required this.foregroundColor,
  });

  final String label;
  final Color backgroundColor;
  final Color foregroundColor;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: backgroundColor,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: foregroundColor,
          fontSize: 12,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }
}

class _McpAppHostScreen extends StatefulWidget {
  const _McpAppHostScreen({
    required this.apps,
    required this.initialAppId,
    this.focusHint,
  });

  final List<CodexMcpApp> apps;
  final String initialAppId;
  final String? focusHint;

  @override
  State<_McpAppHostScreen> createState() => _McpAppHostScreenState();
}

class _McpAppHostScreenState extends State<_McpAppHostScreen> {
  late String _selectedAppId;

  @override
  void initState() {
    super.initState();
    _selectedAppId = widget.initialAppId;
  }

  @override
  Widget build(BuildContext context) {
    final app = widget.apps.firstWhere(
      (candidate) => candidate.appId == _selectedAppId,
      orElse: () => widget.apps.first,
    );
    final theme = Theme.of(context);
    final previewProjects = _extractMcpPreviewProjects(app.preview?.result);
    final preview = app.preview;
    final installState = app.installState;
    final focusProjectName = _resolvedProjectFocusName(
      previewProjects,
      widget.focusHint,
    );

    return Scaffold(
      backgroundColor: const Color(0xFF08111F),
      appBar: AppBar(
        backgroundColor: const Color(0xFF0E1730),
        foregroundColor: Colors.white,
        title: Text(app.name),
        leading: IconButton(
          tooltip: 'Close app',
          onPressed: () => Navigator.of(context).pop(),
          icon: const Icon(Icons.close_rounded),
        ),
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 20, 20, 28),
          children: <Widget>[
            if (widget.apps.length > 1) ...<Widget>[
              Text(
                'Apps',
                style: theme.textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: widget.apps.map((candidate) {
                  final selected = candidate.appId == app.appId;
                  return ChoiceChip(
                    selected: selected,
                    label: Text(candidate.name),
                    onSelected: (_) {
                      setState(() {
                        _selectedAppId = candidate.appId;
                      });
                    },
                  );
                }).toList(),
              ),
              const SizedBox(height: 18),
            ],
            Text(
              app.description,
              style: theme.textTheme.titleMedium?.copyWith(
                color: const Color(0xFFDCE5FF),
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 8),
            const Text(
              'This MCP app is open full-screen. Close it to return to chat.',
              style: TextStyle(color: Color(0xFF8B97B5)),
            ),
            const SizedBox(height: 16),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: <Widget>[
                _StatusPill(
                  label: installState,
                  backgroundColor: const Color(0xFF24355F),
                  foregroundColor: const Color(0xFFDCE5FF),
                ),
                _StatusPill(
                  label: 'server:${app.recommendedServerId}',
                  backgroundColor: const Color(0xFF1F4D45),
                  foregroundColor: const Color(0xFFB6F4E4),
                ),
                ...app.tags.map(
                  (tag) => _StatusPill(
                    label: tag,
                    backgroundColor: const Color(0xFF2B364D),
                    foregroundColor: const Color(0xFFB8C3DA),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 18),
            if (focusProjectName != null) ...<Widget>[
              _McpAppNoticeCard(
                tone: _McpAppNoticeTone.info,
                title: 'Focused from your command',
                message:
                    'Showing `${app.name}` with attention on project `$focusProjectName`.',
              ),
              const SizedBox(height: 12),
            ],
            if (app.lookupError?.trim().isNotEmpty ?? false)
              _McpAppNoticeCard(
                tone: _McpAppNoticeTone.warning,
                title: 'Stored server state needs attention',
                message: app.lookupError!.trim(),
              ),
            if (app.protocolError?.trim().isNotEmpty ?? false)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: _McpAppNoticeCard(
                  tone: _McpAppNoticeTone.error,
                  title: 'Protocol inspection failed',
                  message: app.protocolError!.trim(),
                ),
              ),
            if (app.driftSummary?.trim().isNotEmpty ?? false)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: _McpAppNoticeCard(
                  tone: _McpAppNoticeTone.warning,
                  title: 'Stored Codex config drifted',
                  message: app.driftSummary!.trim(),
                ),
              ),
            const SizedBox(height: 18),
            Text(
              preview == null ? 'App payload' : 'Live preview',
              style: theme.textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 10),
            if (previewProjects != null && previewProjects.isNotEmpty)
              ...previewProjects.map(
                (project) => Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: _McpProjectPreviewCard(
                    project: project,
                    highlighted: _projectMatchesFocus(
                      project,
                      focusProjectName,
                    ),
                  ),
                ),
              )
            else
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: const Color(0xFF0C152B),
                  borderRadius: BorderRadius.circular(18),
                  border: Border.all(color: const Color(0xFF203154)),
                ),
                child: SelectableText(
                  _prettyMcpPreviewJson(preview?.result),
                  style: const TextStyle(
                    color: Color(0xFFDCE5FF),
                    fontFamily: 'monospace',
                    fontSize: 12,
                  ),
                ),
              ),
            const SizedBox(height: 18),
            Text(
              'Capabilities',
              style: theme.textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 10),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: const Color(0xFF111C34),
                borderRadius: BorderRadius.circular(18),
                border: Border.all(color: const Color(0xFF203154)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    'Tools: ${app.tools.isEmpty ? "none" : app.tools.map((tool) => tool.name).join(", ")}',
                    style: const TextStyle(color: Color(0xFFB9C5E3)),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Resources: ${app.resources.isEmpty ? "none" : app.resources.map((resource) => resource.name).join(", ")}',
                    style: const TextStyle(color: Color(0xFFB9C5E3)),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Prompts: ${app.prompts.isEmpty ? "none" : app.prompts.map((prompt) => prompt.name).join(", ")}',
                    style: const TextStyle(color: Color(0xFFB9C5E3)),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

enum _McpAppNoticeTone { info, warning, error }

class _McpAppNoticeCard extends StatelessWidget {
  const _McpAppNoticeCard({
    required this.tone,
    required this.title,
    required this.message,
  });

  final _McpAppNoticeTone tone;
  final String title;
  final String message;

  @override
  Widget build(BuildContext context) {
    final backgroundColor = switch (tone) {
      _McpAppNoticeTone.info => const Color(0xFF1D3D52),
      _McpAppNoticeTone.warning => const Color(0xFF3A2714),
      _McpAppNoticeTone.error => const Color(0xFF431B27),
    };
    final borderColor = switch (tone) {
      _McpAppNoticeTone.info => const Color(0xFF2D6587),
      _McpAppNoticeTone.warning => const Color(0xFF7C5A2A),
      _McpAppNoticeTone.error => const Color(0xFF8B3D4D),
    };
    final foregroundColor = switch (tone) {
      _McpAppNoticeTone.info => const Color(0xFFBFE8FF),
      _McpAppNoticeTone.warning => const Color(0xFFFFD9A3),
      _McpAppNoticeTone.error => const Color(0xFFFFC4CB),
    };

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: backgroundColor,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: borderColor),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            title,
            style: TextStyle(
              color: foregroundColor,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 6),
          Text(message, style: TextStyle(color: foregroundColor)),
        ],
      ),
    );
  }
}

class _McpProjectPreviewCard extends StatelessWidget {
  const _McpProjectPreviewCard({
    required this.project,
    this.highlighted = false,
  });

  final Map<String, dynamic> project;
  final bool highlighted;

  @override
  Widget build(BuildContext context) {
    final name = project['name']?.toString() ?? 'project';
    final path = project['path']?.toString() ?? '';
    final languages =
        (project['detected_languages'] as List<dynamic>? ?? const <dynamic>[])
            .map((item) => item.toString())
            .where((item) => item.isNotEmpty)
            .join(', ');
    final signatures =
        (project['signature_files'] as List<dynamic>? ?? const <dynamic>[])
            .map((item) => item.toString())
            .where((item) => item.isNotEmpty)
            .join(', ');
    final readme = project['readme_excerpt']?.toString().trim();

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF111C34),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(
          color:
              highlighted ? const Color(0xFF55D6BE) : const Color(0xFF203154),
          width: highlighted ? 2 : 1,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          if (highlighted) ...<Widget>[
            const _StatusPill(
              label: 'focused',
              backgroundColor: Color(0xFF1F4D45),
              foregroundColor: Color(0xFFB6F4E4),
            ),
            const SizedBox(height: 10),
          ],
          Text(
            name,
            style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
          ),
          if (path.isNotEmpty) ...<Widget>[
            const SizedBox(height: 6),
            Text(path, style: const TextStyle(color: Color(0xFF8B97B5))),
          ],
          if (languages.isNotEmpty) ...<Widget>[
            const SizedBox(height: 10),
            Text(languages, style: const TextStyle(color: Color(0xFFDCE5FF))),
          ],
          if (signatures.isNotEmpty) ...<Widget>[
            const SizedBox(height: 8),
            Text(signatures, style: const TextStyle(color: Color(0xFF8B97B5))),
          ],
          if (readme != null && readme.isNotEmpty) ...<Widget>[
            const SizedBox(height: 12),
            Text(readme, style: const TextStyle(color: Color(0xFFB9C5E3))),
          ],
        ],
      ),
    );
  }
}

String? _resolvedProjectFocusName(
  List<Map<String, dynamic>>? projects,
  String? focusHint,
) {
  final normalizedHint = _normalizeFocusHint(focusHint ?? '');
  if (normalizedHint == null || normalizedHint.isEmpty) {
    return null;
  }
  if (projects == null || projects.isEmpty) {
    return normalizedHint;
  }
  for (final project in projects) {
    final name = project['name']?.toString();
    if (name == null || name.trim().isEmpty) {
      continue;
    }
    if (_normalizeMcpAppLookupToken(name) ==
        _normalizeMcpAppLookupToken(normalizedHint)) {
      return name;
    }
  }
  return normalizedHint;
}

bool _projectMatchesFocus(
  Map<String, dynamic> project,
  String? focusProjectName,
) {
  if (focusProjectName == null || focusProjectName.trim().isEmpty) {
    return false;
  }
  final projectName = project['name']?.toString();
  if (projectName == null || projectName.trim().isEmpty) {
    return false;
  }
  return _normalizeMcpAppLookupToken(projectName) ==
      _normalizeMcpAppLookupToken(focusProjectName);
}

class _ChatTimelineEntry {
  const _ChatTimelineEntry.separator(this.separatorDate) : message = null;

  const _ChatTimelineEntry.message(this.message) : separatorDate = null;

  final DateTime? separatorDate;
  final ChatMessage? message;
}

class _ChatDaySeparator extends StatelessWidget {
  const _ChatDaySeparator({super.key, required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(0, 8, 0, 14),
      child: Center(
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          decoration: BoxDecoration(
            color: const Color(0xFF16213C),
            borderRadius: BorderRadius.circular(999),
            border: Border.all(color: const Color(0xFF23304F)),
          ),
          child: Text(
            label,
            style: const TextStyle(
              color: Color(0xFFDCE5FF),
              fontSize: 12,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
      ),
    );
  }
}
