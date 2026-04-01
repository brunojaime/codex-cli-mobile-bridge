import 'dart:async';
import 'dart:math' as math;

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
import '../models/server_capabilities.dart';
import '../models/server_health.dart';
import '../models/server_profile.dart';
import '../models/session_detail.dart';
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
import '../widgets/reviewer_status_banner.dart';

const String _defaultAutoReviewerPrompt =
    'You are receiving the latest answer from a generator Codex. '
    'Write the next prompt that should be sent back to that generator so it '
    'improves the implementation with more code, tighter validation, missing '
    'tests, edge cases, cleanup, or follow-up work. Reply only with that next '
    'prompt.';
const Key kChatScreenBodyScrollViewKey =
    ValueKey<String>('chat-screen-body-scroll-view');

enum _AppBarOverflowAction {
  conversationContext,
  summaryView,
  saveCurrentAgent,
  replyMode,
  servers,
  newChat,
}

enum _PinnedWorkspaceAction {
  newChat,
  remove,
}

enum _ChatBodyView {
  conversation,
  agentSummaries,
  turnSummaries,
}

class ChatScreen extends StatefulWidget {
  const ChatScreen({
    super.key,
    required this.initialApiBaseUrl,
    required this.notificationService,
    this.controllerOverride,
    this.replyPlaybackServiceOverride,
    this.enableServerBootstrap = true,
    this.initialSidebarWorkspaces = const <Workspace>[],
  });

  final String initialApiBaseUrl;
  final ChatNotificationService notificationService;
  final ChatController? controllerOverride;
  final ReplyPlaybackService? replyPlaybackServiceOverride;
  final bool enableServerBootstrap;
  final List<Workspace> initialSidebarWorkspaces;

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
  ServerProfile? _activeServer;
  ServerHealth? _activeServerHealth;
  ServerCapabilities? _activeServerCapabilities;
  String? _serverErrorText;
  bool _sidebarExpanded = false;
  bool _showArchivedChatsInSidebar = false;
  bool _stickToBottom = true;
  bool _audioRepliesEnabled = false;
  bool _isOpeningWorkspacePicker = false;
  String? _lastObservedSessionId;
  final Map<String, _ComposerDraft> _sessionDrafts = <String, _ComposerDraft>{};
  final Map<String, Set<String>> _collapsedMessageIdsBySession =
      <String, Set<String>>{};
  bool _isUpdatingFilteredMessagesView = false;
  String? _filteredMessagesViewErrorText;
  _ChatBodyView _chatBodyView = _ChatBodyView.conversation;
  static const double _compactAppBarBreakpoint = 640;

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
      _sidebarWorkspaces =
          List<Workspace>.from(widget.initialSidebarWorkspaces);
    }
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
                    child: _sidebarWorkspaces.isEmpty
                        ? const Center(
                            child: Text(
                              'No projects pinned yet',
                              style: TextStyle(color: Color(0xFF8B97B5)),
                            ),
                          )
                        : sessionGroups.isEmpty
                            ? Center(
                                child: Text(
                                  _showArchivedChatsInSidebar
                                      ? 'No archived chats yet'
                                      : 'No chats yet',
                                  style: const TextStyle(
                                    color: Color(0xFF8B97B5),
                                  ),
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
                              child: CustomScrollView(
                                key: kChatScreenBodyScrollViewKey,
                                controller: _scrollController,
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
                                          borderRadius:
                                              BorderRadius.circular(14),
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
                                          borderRadius:
                                              BorderRadius.circular(14),
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
                                      (summaryMessageCount > 0 ||
                                          turnSummaryCount > 0 ||
                                          currentSession.turnSummariesEnabled ||
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
                                              label:
                                                  const Text('Conversation'),
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
                                              selectedColor:
                                                  const Color(0xFF55D6BE),
                                              backgroundColor:
                                                  const Color(0xFF16213C),
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
                                            ChoiceChip(
                                              label: Text(
                                                summaryMessageCount == 1
                                                    ? 'Agent summary'
                                                    : 'Agent summaries ($summaryMessageCount)',
                                              ),
                                              selected: isShowingAgentSummaries,
                                              onSelected: summaryMessageCount <=
                                                      0
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
                                              selectedColor:
                                                  const Color(0xFF8CA8FF),
                                              backgroundColor:
                                                  const Color(0xFF16213C),
                                              labelStyle: TextStyle(
                                                color: isShowingAgentSummaries
                                                    ? const Color(0xFF07131D)
                                                    : const Color(0xFFDCE5FF),
                                                fontWeight: FontWeight.w700,
                                              ),
                                              side: const BorderSide(
                                                color: Color(0xFF23304F),
                                              ),
                                            ),
                                            ChoiceChip(
                                              label: Text(
                                                turnSummaryCount == 1
                                                    ? 'Turn summary'
                                                    : 'Turn summaries ($turnSummaryCount)',
                                              ),
                                              selected: isShowingTurnSummaries,
                                              onSelected: (turnSummaryCount <= 0 &&
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
                                              selectedColor:
                                                  const Color(0xFFFFC857),
                                              backgroundColor:
                                                  const Color(0xFF16213C),
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
                                          enabled:
                                              currentSession.turnSummariesEnabled,
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
                                          childCount:
                                              currentSession.turnSummaries.length,
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
                                            final entry =
                                                timelineEntries[index];
                                            if (entry.separatorDate != null) {
                                              final separatorDate =
                                                  entry.separatorDate!;
                                              return _ChatDaySeparator(
                                                key: ValueKey<String>(
                                                  'chat-day-separator-${separatorDate.year}-${separatorDate.month}-${separatorDate.day}',
                                                ),
                                                label: formatChatDaySeparatorLabel(
                                                  context,
                                                  separatorDate,
                                                ),
                                              );
                                            }
                                            final message = entry.message!;
                                            final nextEntry =
                                                index + 1 < timelineEntries.length
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
                                                  onCancelJob:
                                                      (_activeServerCapabilities
                                                                      ?.supportsJobCancellation ??
                                                                  false) &&
                                                              message.jobId !=
                                                                  null
                                                          ? () =>
                                                              _handleCancelJob(
                                                                message.jobId!,
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
                                                                message.jobId!,
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
                                          childCount: timelineEntries.length,
                                        ),
                                      ),
                                    ),
                                ],
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
                                      child: const Icon(
                                        Icons.south_rounded,
                                      ),
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
    final sessionIdBeforeSend = _chatController.selectedSessionId;
    final workspacePathBeforeSend =
        _chatController.currentSession?.workspacePath;
    final didSend = await _chatController.sendMessage(
      _textController.text,
      sessionIdOverride: sessionIdBeforeSend,
      workspacePathOverride: workspacePathBeforeSend,
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

  Future<bool> _handleSendAudio(XFile audioFile) async {
    final sessionIdBeforeSend = _chatController.selectedSessionId;
    final workspacePathBeforeSend =
        _chatController.currentSession?.workspacePath;
    final didSend = await _chatController.sendAudioMessage(
      audioFile,
      sessionIdOverride: sessionIdBeforeSend,
      workspacePathOverride: workspacePathBeforeSend,
    );
    if (didSend &&
        (sessionIdBeforeSend == null ||
            _chatController.selectedSessionId == sessionIdBeforeSend)) {
      _updateStickToBottom(true);
      _scrollToBottom();
    }
    return didSend;
  }

  Future<bool> _handleSendAttachments(
    List<_PendingAttachmentDraft> attachments, {
    String? prompt,
  }) async {
    final sessionIdBeforeSend = _chatController.selectedSessionId;
    final workspacePathBeforeSend =
        _chatController.currentSession?.workspacePath;
    final didSend = await _chatController.sendAttachmentsMessage(
      attachments.map((attachment) => attachment.file).toList(),
      message: prompt,
      sessionIdOverride: sessionIdBeforeSend,
      workspacePathOverride: workspacePathBeforeSend,
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
        content: Text(
          didRetry ? 'Retry queued.' : 'Could not retry the job.',
        ),
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
      final launched = await launchUrl(
        uri,
        mode: _launchModeForUri(uri),
      );
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

  Future<void> _copyLinkTarget(
    String target, {
    required String message,
  }) async {
    await Clipboard.setData(ClipboardData(text: target));
    if (!mounted) {
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        duration: const Duration(seconds: 2),
      ),
    );
  }

  List<ChatMessage> _visibleMessagesForCurrentSession() {
    final currentSession = _chatController.currentSession;
    if (currentSession == null) {
      return const <ChatMessage>[];
    }
    if (_chatBodyView == _ChatBodyView.agentSummaries) {
      return currentSession.messages
          .where((message) => message.agentId == AgentId.summary)
          .toList(growable: false);
    }
    return filterVisibleMessages(
      currentSession.messages,
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
              constraints: const BoxConstraints(
                maxWidth: 720,
                maxHeight: 760,
              ),
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
      SnackBar(
        content: Text('Saved ${profile.name} for future chats.'),
      ),
    );
  }

  Future<void> _pinWorkspaceToSidebar(Workspace workspace) async {
    final alreadyPinned = _sidebarWorkspaces.any(
      (item) => item.path == workspace.path,
    );
    if (alreadyPinned) {
      return;
    }

    final updatedWorkspaces = <Workspace>[
      ..._sidebarWorkspaces,
      workspace,
    ];
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
    });

    final didConnect =
        await _switchToServer(resolvedActiveProfile, initialize: true);
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
    nextController.addListener(_handleChatControllerChanged);

    final previousController = _chatController;
    await _replyPlaybackService.setServer(client);
    setState(() {
      _chatController = nextController;
      _activeServer = profile;
      _activeServerHealth = null;
      _activeServerCapabilities = null;
      _sidebarWorkspaces = sidebarWorkspaces;
      _sessionReadMarkers = sessionReadMarkers;
      _serverErrorText = null;
      _audioRepliesEnabled = audioRepliesEnabled;
    });
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
      if (mounted) {
        setState(() {
          _activeServerHealth = health;
          _activeServerCapabilities = capabilities;
        });
      }
      _replyPlaybackService.setCapabilities(capabilities);
      didConnect = true;
    } catch (error) {
      _replyPlaybackService.setCapabilities(null);
      setState(() {
        _activeServerHealth = null;
        _activeServerCapabilities = null;
        _serverErrorText = 'Failed to connect to ${profile.name}.\n$error';
      });
    }

    if (!identical(previousController, nextController)) {
      previousController
        ..removeListener(_handleChatControllerChanged)
        ..dispose();
    }
    return didConnect;
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
        return _AgentStudioSheet(
          session: currentSession,
        );
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
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(errorText),
      ),
    );
  }

  Future<void> _openReplyModePicker() async {
    final nextValue = await showModalBottomSheet<bool>(
      context: context,
      backgroundColor: const Color(0xFF101931),
      builder: (context) {
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
                  _audioRepliesEnabled
                      ? Icons.radio_button_unchecked_rounded
                      : Icons.radio_button_checked_rounded,
                ),
                title: const Text('Text replies'),
                subtitle: const Text('Keep assistant responses silent'),
                onTap: () => Navigator.of(context).pop(false),
              ),
              ListTile(
                leading: Icon(
                  _audioRepliesEnabled
                      ? Icons.radio_button_checked_rounded
                      : Icons.radio_button_unchecked_rounded,
                ),
                title: const Text('Audio replies'),
                subtitle: const Text('Speak assistant responses automatically'),
                onTap: () => Navigator.of(context).pop(true),
              ),
            ],
          ),
        );
      },
    );

    if (nextValue == null || nextValue == _audioRepliesEnabled) {
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
        tooltip: showingSummaryView
            ? 'Show full chat'
            : 'Show summary tabs',
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
              action: _AppBarOverflowAction.conversationContext,
              icon: Icons.topic_outlined,
              label: 'What are we doing?',
            ),
            _buildAppBarOverflowMenuItem(
              action: _AppBarOverflowAction.summaryView,
              icon: showingSummaryView
                  ? Icons.chat_bubble_outline_rounded
                  : Icons.summarize_outlined,
              label: showingSummaryView
                  ? 'Show full chat'
                  : 'Show summary tabs',
              enabled: showingSummaryView ||
                  (_chatController.currentSession != null && canShowAnySummary),
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
                  ? 'Audio replies enabled'
                  : 'Text replies enabled',
            ),
            _buildAppBarOverflowMenuItem(
              action: _AppBarOverflowAction.servers,
              icon: Icons.computer,
              label: 'Servers',
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
            ? 'Audio replies enabled'
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
          Expanded(
            child: Text(
              label,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _handleAppBarOverflowAction(_AppBarOverflowAction action) async {
    switch (action) {
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
      case _AppBarOverflowAction.saveCurrentAgent:
        await _openSaveCurrentAgentProfile();
        return;
      case _AppBarOverflowAction.replyMode:
        await _openReplyModePicker();
        return;
      case _AppBarOverflowAction.servers:
        await _openServerManager();
        return;
      case _AppBarOverflowAction.newChat:
        await _openWorkspacePicker();
        return;
    }
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
                  style: const TextStyle(
                    color: Colors.white,
                    height: 1.35,
                  ),
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
        _sameDraftAttachments(
            previous?.attachments ?? const <_PendingAttachmentDraft>[],
            draft.attachments);
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

  List<Widget> _buildSessionGroups({required bool archivedOnly}) {
    final groupedSessions = <String, List<ChatSessionSummary>>{};
    final sessionGroups = <Widget>[];

    for (final session in _chatController.sessions) {
      groupedSessions
          .putIfAbsent(session.workspacePath, () => <ChatSessionSummary>[])
          .add(session);
    }

    for (final workspace in _sidebarWorkspaces) {
      final sessions =
          groupedSessions[workspace.path] ?? <ChatSessionSummary>[];
      final visibleSessions = sessions
          .where(
            (session) =>
                archivedOnly ? session.isArchived : !session.isArchived,
          )
          .toList(growable: false);
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

      sessionGroups.add(Container(
        margin: const EdgeInsets.fromLTRB(10, 6, 10, 6),
        decoration: BoxDecoration(
          color: projectCardColor,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: projectBorderColor),
        ),
        child: Theme(
          data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
          child: ExpansionTile(
            key: PageStorageKey<String>('workspace-${workspace.path}'),
            initiallyExpanded: hasSelected,
            tilePadding:
                const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
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
                    ...visibleSessions.map(
                      (session) => Padding(
                        padding: const EdgeInsets.only(left: 10, right: 10),
                        child: _SessionTile(
                          activeJobSummary:
                              _chatController.activeJobSummaryForSession(
                            session.id,
                          ),
                          outgoingUploadSummary: _chatController
                              .outgoingUploadSummaryForSession(session.id),
                          session: session,
                          unreadCount: _unreadCountForSession(session),
                          selected:
                              session.id == _chatController.selectedSessionId,
                          onTap: () async {
                            Navigator.of(context).pop();
                            await _chatController.selectSession(session.id);
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
                  ],
          ),
        ),
      ));
    }

    return sessionGroups;
  }

  void _handleChatControllerChanged() {
    _markCurrentSessionAsRead();
    final currentSessionId = _chatController.selectedSessionId;
    final sessionChanged = currentSessionId != _lastObservedSessionId;
    if (sessionChanged) {
      _lastObservedSessionId = currentSessionId;
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
    }

    if (_stickToBottom) {
      _scrollToBottom(jumpToBottom: sessionChanged);
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
        .where((workspace) =>
            _activeOperationCountForWorkspace(workspace.path) > 0)
        .length;
  }

  int _totalActivePinnedJobsCount() {
    return _sidebarWorkspaces.fold(
        0,
        (total, workspace) =>
            total + _activeOperationCountForWorkspace(workspace.path));
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
    }
    return false;
  }

  bool _isNearBottom(ScrollMetrics metrics) {
    return metrics.extentAfter < 72;
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
    required this.onArchiveToggle,
  });

  final SessionActiveJobSummary? activeJobSummary;
  final SessionOutgoingUploadSummary? outgoingUploadSummary;
  final ChatSessionSummary session;
  final int unreadCount;
  final bool selected;
  final VoidCallback onTap;
  final VoidCallback onArchiveToggle;

  @override
  Widget build(BuildContext context) {
    final activeJobPresentation =
        _buildSessionActiveJobPresentation(activeJobSummary);
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
    final previewColor = isActive || isUploading
        ? const Color(0xFFA8C7C0)
        : const Color(0xFF8B97B5);
    final conversationProduct = session.conversationProduct;
    final subtitleText = conversationProduct != null &&
            conversationProduct.description.trim().isNotEmpty
        ? conversationProduct.description
        : session.lastMessagePreview?.isNotEmpty == true
            ? session.lastMessagePreview!
            : 'No messages yet';

    return AnimatedContainer(
      duration: const Duration(milliseconds: 180),
      margin: const EdgeInsets.symmetric(vertical: 2),
      decoration: BoxDecoration(
        color: tileBackgroundColor,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: tileBorderColor),
      ),
      child: ListTile(
        selected: selected,
        selectedTileColor: Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
        ),
        title: Text(
          session.title,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            color: session.isArchived ? const Color(0xFFB8C8EA) : titleColor,
            fontWeight: isActive ? FontWeight.w600 : null,
          ),
        ),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            if (conversationProduct?.statusLine.trim().isNotEmpty == true) ...<Widget>[
              Text(
                conversationProduct!.statusLine,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: session.isArchived
                      ? const Color(0xFF9FB3D6)
                      : const Color(0xFF55D6BE),
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 4),
            ],
            Text(
              subtitleText,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color:
                    session.isArchived ? const Color(0xFF7F8EAF) : previewColor,
              ),
            ),
            if (session.isArchived) ...<Widget>[
              const SizedBox(height: 6),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: const Color(0xFF1B2745),
                  borderRadius: BorderRadius.circular(999),
                ),
                child: const Text(
                  'Archived',
                  style: TextStyle(
                    color: Color(0xFF9FB3D6),
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ],
            if (activeJobPresentation != null) ...<Widget>[
              const SizedBox(height: 6),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: activeJobPresentation.backgroundColor,
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    Container(
                      width: 8,
                      height: 8,
                      decoration: BoxDecoration(
                        color: activeJobPresentation.foregroundColor,
                        shape: BoxShape.circle,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Flexible(
                      child: Text(
                        activeJobPresentation.label,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          color: activeJobPresentation.foregroundColor,
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
            if (isUploading) ...<Widget>[
              const SizedBox(height: 6),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: const Color(0xFF15265A),
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text(
                  _formatOutgoingUploadLabel(outgoingUploadSummary!),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: Color(0xFFB8CCFF),
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ],
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
              tooltip: session.isArchived ? 'Unarchive chat' : 'Archive chat',
              onSelected: (value) {
                if (value == 'toggle-archive') {
                  onArchiveToggle();
                }
              },
              itemBuilder: (context) => <PopupMenuEntry<String>>[
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
                      Text(session.isArchived
                          ? 'Unarchive chat'
                          : 'Archive chat'),
                    ],
                  ),
                ),
              ],
            ),
          ],
        ),
        onTap: onTap,
      ),
    );
  }
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

String _formatOutgoingUploadLabel(SessionOutgoingUploadSummary summary) {
  if (summary.totalCount == 1) {
    if (summary.audioCount == 1) {
      return 'Sending audio';
    }
    if (summary.imageCount == 1) {
      return 'Uploading image';
    }
    if (summary.fileCount == 1) {
      return 'Uploading file';
    }
    return 'Uploading attachments';
  }

  if (summary.audioCount == summary.totalCount) {
    return 'Sending ${summary.totalCount} audios';
  }
  if (summary.imageCount == summary.totalCount) {
    return 'Uploading ${summary.totalCount} images';
  }
  if (summary.fileCount == summary.totalCount) {
    return 'Uploading ${summary.totalCount} files';
  }
  return 'Uploading ${summary.totalCount} items';
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

class _SessionActiveJobPresentation {
  const _SessionActiveJobPresentation({
    required this.label,
    required this.backgroundColor,
    required this.foregroundColor,
  });

  final String label;
  final Color backgroundColor;
  final Color foregroundColor;
}

_SessionActiveJobPresentation? _buildSessionActiveJobPresentation(
  SessionActiveJobSummary? summary,
) {
  if (summary == null) {
    return null;
  }

  final elapsedLabel = _formatElapsed(summary.maxElapsedSeconds);
  if (elapsedLabel == null) {
    return null;
  }

  final accentColor = _agentAccentColor(
    summary.primaryAgentId,
    seed: summary.primaryAgentSeed,
  );
  final agentLabel = summary.primaryAgentLabel.trim();
  final label = summary.activeJobCount == 1
      ? '$agentLabel running • $elapsedLabel'
      : '$agentLabel +${summary.activeJobCount - 1} running • $elapsedLabel';

  return _SessionActiveJobPresentation(
    label: label,
    backgroundColor: accentColor.withValues(alpha: 0.18),
    foregroundColor: accentColor,
  );
}

String? _formatElapsed(int? seconds) {
  if (seconds == null) {
    return null;
  }
  if (seconds < 60) {
    return '${seconds}s';
  }
  final minutes = seconds ~/ 60;
  final remainingSeconds = seconds % 60;
  return '${minutes}m ${remainingSeconds}s';
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
  const _ProjectStatusPill({
    required this.active,
    required this.label,
  });

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
                        hintText: 'http://192.168.1.10:8000',
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
                style: const TextStyle(
                  color: Color(0xFF8B97B5),
                  height: 1.5,
                ),
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
                style: TextStyle(
                  color: Color(0xFFB8C8EA),
                  height: 1.5,
                ),
              ),
              if (errorText != null) ...<Widget>[
                const SizedBox(height: 12),
                Text(
                  errorText!,
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    color: Color(0xFFFFB4B4),
                    height: 1.4,
                  ),
                ),
              ],
            ],
          ),
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
          const Icon(
            Icons.summarize_outlined,
            color: Color(0xFFAED3FF),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              '$label. Tap a summary to inspect what was completed at that point in the run.',
              style: const TextStyle(
                color: Colors.white,
                height: 1.35,
              ),
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
  const _SummaryMessagesPlaceholder({
    required this.onShowFullChat,
  });

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
                style: TextStyle(
                  color: Color(0xFF8B97B5),
                  height: 1.5,
                ),
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
        ? 'Showing 1 turn summary'
        : 'Showing $summaryCount turn summaries';
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
          const Icon(
            Icons.history_edu_outlined,
            color: Color(0xFFFFE08A),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              '$label. $suffix Each entry includes the source messages it was built from.',
              style: const TextStyle(
                color: Colors.white,
                height: 1.35,
              ),
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
        ? 'The summarizer is enabled, but it has not created a turn summary yet.'
        : 'The summarizer is disabled for this chat. Enable it from Agents to start collecting turn summaries.';
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 24),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 460),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              const Text(
                'No turn summaries yet',
                style: TextStyle(fontSize: 24, fontWeight: FontWeight.w600),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 12),
              Text(
                message,
                textAlign: TextAlign.center,
                style: const TextStyle(
                  color: Color(0xFF8B97B5),
                  height: 1.5,
                ),
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
  const _TurnSummaryCard({
    required this.summary,
  });

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
              const Icon(
                Icons.article_outlined,
                color: Color(0xFFFFC857),
              ),
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
                style: const TextStyle(
                  color: Color(0xFF9FB0D4),
                  fontSize: 12,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            summary.content,
            style: const TextStyle(
              color: Colors.white,
              height: 1.45,
            ),
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
              style: TextStyle(
                color: Color(0xFFB8C8EA),
                height: 1.4,
              ),
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
    required this.isBusy,
    required this.voiceEnabled,
    required this.imageAttachmentsEnabled,
    required this.fileAttachmentsEnabled,
    required this.voiceStatusText,
  });

  final String? sessionId;
  final TextEditingController controller;
  final _ComposerDraft draft;
  final ValueChanged<_ComposerDraft> onDraftChanged;
  final Future<bool> Function() onSend;
  final Future<bool> Function(XFile audioFile) onSendAudio;
  final Future<bool> Function(
    List<_PendingAttachmentDraft> attachments, {
    String? prompt,
  }) onSendAttachments;
  final Future<void> Function() onBeginRecording;
  final bool isBusy;
  final bool voiceEnabled;
  final bool imageAttachmentsEnabled;
  final bool fileAttachmentsEnabled;
  final String voiceStatusText;

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
  final List<_PendingAttachmentDraft> _pendingAttachments =
      <_PendingAttachmentDraft>[];

  @override
  void initState() {
    super.initState();
    _audioRecorder = AudioNoteRecorder();
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
    final isDisabled = widget.isBusy;
    final showAttachmentActions = !_isRecording;

    return SafeArea(
      top: false,
      child: Container(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
        decoration: const BoxDecoration(
          color: Color(0xFF0D1427),
          border: Border(
            top: BorderSide(color: Color(0xFF1F2945)),
          ),
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
                            backgroundColor: const Color(0xFF31405F),
                            foregroundColor: const Color(0xFFE8ECF8),
                          ),
                          icon: const Icon(Icons.close_rounded),
                          label: const Text('Cancel'),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: FilledButton.icon(
                          onPressed: _stopRecordingAndSend,
                          style: _actionButtonStyle(
                            backgroundColor: const Color(0xFFFF7A7A),
                            foregroundColor: const Color(0xFF2C0710),
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
                      if (showAttachmentActions) ...<Widget>[
                        FilledButton(
                          onPressed: isDisabled ? null : _openAttachmentPicker,
                          style: _actionButtonStyle(
                            backgroundColor: const Color(0xFF1F4D45),
                            foregroundColor: const Color(0xFFB6F4E4),
                          ),
                          child: const Icon(Icons.attach_file_rounded),
                        ),
                        const SizedBox(width: 10),
                      ],
                      Expanded(
                        child: FilledButton.icon(
                          onPressed: isDisabled ? null : _handlePrimaryAction,
                          style: _actionButtonStyle(
                            backgroundColor: const Color(0xFF55D6BE),
                            foregroundColor: const Color(0xFF07131D),
                          ),
                          icon: const Icon(Icons.arrow_upward_rounded),
                          label: const Text('Send'),
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
                if (showAttachmentActions) ...<Widget>[
                  FilledButton(
                    onPressed: isDisabled ? null : _openAttachmentPicker,
                    style: _actionButtonStyle(
                      backgroundColor: hasPendingAttachment
                          ? const Color(0xFF1F4D45)
                          : const Color(0xFF31405F),
                      foregroundColor: hasPendingAttachment
                          ? const Color(0xFFB6F4E4)
                          : const Color(0xFFE8ECF8),
                    ),
                    child: const Icon(Icons.attach_file_rounded),
                  ),
                  const SizedBox(width: 12),
                ],
                Expanded(
                  child: _buildComposerBody(),
                ),
                const SizedBox(width: 12),
                if (_isRecording)
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: <Widget>[
                      FilledButton(
                        onPressed: _confirmCancelRecording,
                        style: _actionButtonStyle(
                          backgroundColor: const Color(0xFF31405F),
                          foregroundColor: const Color(0xFFE8ECF8),
                          minimumSize: const Size(52, 52),
                        ),
                        child: const Icon(Icons.close_rounded),
                      ),
                      const SizedBox(width: 6),
                      FilledButton(
                        onPressed: _stopRecordingAndSend,
                        style: _actionButtonStyle(
                          backgroundColor: const Color(0xFFFF7A7A),
                          foregroundColor: const Color(0xFF2C0710),
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
                      backgroundColor: const Color(0xFF31405F),
                      foregroundColor: const Color(0xFF9EABC9),
                    ),
                    child: const Icon(Icons.mic_off_rounded),
                  )
                else if (showMicAction)
                  FilledButton(
                    onPressed: isDisabled ? null : _toggleRecording,
                    style: _actionButtonStyle(
                      backgroundColor: const Color(0xFF3F5EF7),
                      foregroundColor: Colors.white,
                    ),
                    child: const Icon(Icons.mic_rounded),
                  )
                else
                  FilledButton(
                    onPressed: isDisabled ? null : _handlePrimaryAction,
                    style: _actionButtonStyle(
                      backgroundColor: const Color(0xFF55D6BE),
                      foregroundColor: const Color(0xFF07131D),
                    ),
                    child: const Icon(Icons.arrow_upward_rounded),
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
        subtitle: 'Send to upload or cancel to discard',
        color: const Color(0xFFFF7A7A),
        trailing: _StatusPill(
          label: _formatDuration(),
          backgroundColor: const Color(0xFF3B1521),
          foregroundColor: const Color(0xFFFFB3B3),
        ),
        titleMaxLines: 1,
        subtitleMaxLines: 1,
      );
    }

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        if (_pendingAttachments.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: _PendingAttachmentTray(
              attachments: _pendingAttachments,
              busy: widget.isBusy,
              onRemove: _removePendingAttachment,
              onClearAll: _clearPendingAttachments,
            ),
          ),
        TextField(
          controller: widget.controller,
          focusNode: _composerFocusNode,
          minLines: 1,
          maxLines: 6,
          enabled: !widget.isBusy,
          textInputAction: TextInputAction.send,
          onSubmitted: (_) async {
            await _handlePrimaryAction();
          },
          decoration: InputDecoration(
            hintText: _composerHintText(),
          ),
        ),
      ],
    );
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
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(18),
      ),
    );
  }

  void _handleTextChanged() {
    final hasText = widget.controller.text.trim().isNotEmpty;
    if (_hasText != hasText) {
      setState(() {
        _hasText = hasText;
      });
    }
    _emitDraftChanged();
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
                  onTap: () => Navigator.of(context).pop(
                    _AttachmentSourceAction.image,
                  ),
                ),
              if (supportsFiles)
                ListTile(
                  leading: const Icon(Icons.insert_drive_file_outlined),
                  title: const Text('Browse files'),
                  subtitle: const Text(
                    'Attach documents, code, text files, or images',
                  ),
                  onTap: () => Navigator.of(context).pop(
                    _AttachmentSourceAction.file,
                  ),
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
      final pickedImages = await _imagePicker.pickMultiImage(
        imageQuality: 90,
      );
      if (pickedImages.isEmpty || !mounted) {
        return;
      }
      final attachments = <_PendingAttachmentDraft>[];
      for (final picked in pickedImages) {
        final previewBytes = await picked.readAsBytes();
        attachments.add(
          _PendingAttachmentDraft(
            file: picked,
            name: picked.name,
            kind: _AttachmentDraftKind.image,
            sizeBytes: await picked.length(),
            previewBytes: previewBytes,
          ),
        );
      }
      _appendPendingAttachments(attachments);
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('$error')),
      );
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
        if (kind == _AttachmentDraftKind.image && !widget.imageAttachmentsEnabled) {
          skippedImageCount += 1;
          continue;
        }
        attachments.add(
          _PendingAttachmentDraft(
            file: xFile,
            name: file.name,
            kind: kind,
            sizeBytes: file.size > 0 ? file.size : await xFile.length(),
            previewBytes: kind == _AttachmentDraftKind.image
                ? (file.bytes ?? await xFile.readAsBytes())
                : null,
          ),
        );
      }
      if (attachments.isEmpty) {
        if (skippedImageCount > 0) {
          _showImageAttachmentsDisabledSnackBar();
          return;
        }
        throw Exception('The selected files are not accessible on this device.');
      }
      _appendPendingAttachments(attachments);
      if (skippedImageCount > 0) {
        _showImageAttachmentsDisabledSnackBar();
      }
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('$error')),
      );
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
    if (_isRecording || widget.isBusy) {
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
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('$error')),
      );
    }
  }

  Future<void> _stopRecordingAndSend() async {
    if (!_isRecording) {
      return;
    }

    final recorder = _audioRecorder;
    _audioRecorder = AudioNoteRecorder();
    _recordingTicker?.cancel();
    _recordingStopwatch?.stop();
    final audioFile = await recorder.stop();
    _recordingStopwatch = null;

    setState(() {
      _isRecording = false;
    });

    if (audioFile == null) {
      return;
    }

    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Voice note sending in the background.'),
          duration: Duration(seconds: 1),
        ),
      );
    }

    _sendAudioInBackground(recorder, audioFile);
  }

  Future<void> _handlePrimaryAction() async {
    if (_pendingAttachments.isNotEmpty) {
      final attachments =
          List<_PendingAttachmentDraft>.from(_pendingAttachments);
      final prompt = widget.controller.text.trim();
      widget.controller.clear();
      if (mounted) {
        setState(() {
          _pendingAttachments.clear();
        });
      } else {
        _pendingAttachments.clear();
      }
      _emitDraftChanged();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              attachments.length == 1
                  ? 'Attachment sending in the background.'
                  : '${attachments.length} attachments sending in the background.',
            ),
            duration: const Duration(seconds: 1),
          ),
        );
      }
      _sendAttachmentsInBackground(
        attachments,
        prompt: prompt.isEmpty ? null : prompt,
      );
      return;
    }

    await widget.onSend();
  }

  Future<void> _discardRecording() async {
    if (!_isRecording) {
      return;
    }

    final recorder = _audioRecorder;
    _audioRecorder = AudioNoteRecorder();
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

  void _clearPendingAttachments() {
    if (_pendingAttachments.isEmpty) {
      return;
    }
    setState(() {
      _pendingAttachments.clear();
    });
    _emitDraftChanged();
  }

  void _appendPendingAttachments(List<_PendingAttachmentDraft> attachments) {
    if (attachments.isEmpty || !mounted) {
      return;
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
      return;
    }

    setState(() {
      _pendingAttachments.addAll(uniqueAttachments);
    });
    _emitDraftChanged();
  }

  bool _canAcceptPastedImages() {
    return mounted &&
        _composerFocusNode.hasFocus &&
        widget.imageAttachmentsEnabled &&
        !widget.isBusy &&
        !_isRecording;
  }

  void _sendAudioInBackground(AudioNoteRecorder recorder, XFile audioFile) {
    unawaited(() async {
      try {
        await widget.onSendAudio(audioFile);
      } finally {
        await recorder.cleanup(audioFile);
        await recorder.dispose();
      }
    }());
  }

  void _sendAttachmentsInBackground(
    List<_PendingAttachmentDraft> attachments, {
    String? prompt,
  }) {
    unawaited(() async {
      final sanitizedAttachments = _filterDisallowedImageAttachments(attachments);
      if (sanitizedAttachments.isEmpty) {
        if (mounted) {
          _showImageAttachmentsDisabledSnackBar();
        }
        return;
      }
      final didSend = await widget.onSendAttachments(
        sanitizedAttachments,
        prompt: prompt,
      );
      if (!mounted) {
        return;
      }
      if (!didSend) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Background attachment send failed.'),
            duration: Duration(seconds: 2),
          ),
        );
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Attachment job accepted.'),
          duration: Duration(seconds: 1),
        ),
      );
    }());
  }

  void _resetRecorderForSessionChange() {
    if (_isRecording) {
      unawaited(_audioRecorder.cancel());
    }
    _recordingTicker?.cancel();
    _recordingTicker = null;
    _recordingStopwatch = null;
    _audioRecorder.dispose();
    _audioRecorder = AudioNoteRecorder();
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

    final nextAttachments = _filterDisallowedImageAttachments(draft.attachments);
    if (mounted) {
      setState(() {
        _hasText = nextText.trim().isNotEmpty;
        _pendingAttachments
          ..clear()
          ..addAll(nextAttachments);
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

    final attachments = images
        .map(
          (image) => _PendingAttachmentDraft(
            file: XFile.fromData(
              image.bytes,
              name: image.fileName,
              mimeType: image.mimeType,
            ),
            name: image.fileName,
            kind: _AttachmentDraftKind.image,
            sizeBytes: image.bytes.length,
            previewBytes: image.bytes,
          ),
        )
        .toList();

    if (attachments.isEmpty) {
      return;
    }

    _appendPendingAttachments(attachments);
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
      return 'Send a command to your local Codex CLI';
    }
    if (_pendingAttachments.length == 1 && _pendingAttachments.first.isImage) {
      return 'Add optional instructions for the image';
    }
    return 'Tell Codex what to do with these attachments';
  }

  _AttachmentDraftKind _resolveAttachmentKind({
    required String fileName,
    String? mimeType,
  }) {
    if (mimeType != null && mimeType.toLowerCase().startsWith('image/')) {
      return _AttachmentDraftKind.image;
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
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(widget.voiceStatusText)),
    );
  }
}

enum _AttachmentDraftKind { image, file }

enum _AttachmentSourceAction { image, file }

class _PendingAttachmentDraft {
  const _PendingAttachmentDraft({
    required this.file,
    required this.name,
    required this.kind,
    this.sizeBytes,
    this.previewBytes,
  });

  final XFile file;
  final String name;
  final _AttachmentDraftKind kind;
  final int? sizeBytes;
  final Uint8List? previewBytes;

  bool get isImage => kind == _AttachmentDraftKind.image;

  String get badgeLabel => isImage ? 'Image' : 'File';

  String get identityKey => '${kind.name}:$name:${sizeBytes ?? 0}';
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

Color _agentAccentColor(
  AgentId agentId, {
  required String seed,
}) {
  switch (agentId) {
    case AgentId.generator:
      return const Color(0xFF55D6BE);
    case AgentId.reviewer:
      return const Color(0xFFFFC857);
    case AgentId.summary:
      return const Color(0xFFAED3FF);
    case AgentId.supervisor:
      return const Color(0xFF8FEAFF);
    case AgentId.qa:
      return const Color(0xFF7EE081);
    case AgentId.ux:
      return const Color(0xFFFF9AC6);
    case AgentId.seniorEngineer:
      return const Color(0xFFFFA15C);
    case AgentId.scraper:
      return const Color(0xFF55C5B8);
    case AgentId.user:
      return _hashedAccentColor(seed);
  }
}

Color _hashedAccentColor(String seed) {
  var hash = 0;
  for (final codeUnit in seed.codeUnits) {
    hash = (hash * 31 + codeUnit) & 0x7fffffff;
  }
  final hue = (hash % 360).toDouble();
  return HSLColor.fromAHSL(1, hue, 0.68, 0.66).toColor();
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
  const _AgentProfilePill({
    required this.label,
    required this.color,
  });

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
            decoration: BoxDecoration(
              color: color,
              shape: BoxShape.circle,
            ),
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
                  title: const Text('Enable summarizer'),
                  subtitle: const Text(
                    'Create turn summaries with provenance for this chat.',
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
                    children: widget.workspaces.map(
                      (workspace) {
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
                      },
                    ).toList(),
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
  const _AgentStudioSheet({
    required this.session,
  });

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
      _labelControllers[agent.agentId] =
          TextEditingController(text: agent.label);
      _modelControllers[agent.agentId] = TextEditingController(
        text: agent.model ?? '',
      );
      _promptControllers[agent.agentId] =
          TextEditingController(text: agent.prompt);
      _turnsControllers[agent.agentId] =
          TextEditingController(text: agent.maxTurns.toString());
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
                title: const Text('Chat summarizer'),
                subtitle: const Text(
                  'Generate hidden turn summaries with provenance for this session.',
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
                  decoration:
                      const InputDecoration(labelText: 'Turn budget mode'),
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
            SwitchListTile(
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
            )
          else
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(title),
              subtitle: Text(
                usesRegistrySelection
                    ? '$enabledSubtitle Selection is controlled by the supervisor registry above.'
                    : enabledSubtitle,
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
            style: TextStyle(
              color: Colors.white,
              fontWeight: FontWeight.w700,
            ),
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
            return CheckboxListTile(
              contentPadding: EdgeInsets.zero,
              value: _supervisorMemberIds.contains(agentId),
              title: Text(label),
              subtitle: Text(
                switch (agentId) {
                  AgentId.qa =>
                    'Validation, tests, regressions, and release risk.',
                  AgentId.ux =>
                    'Usability, accessibility, flow, and interface quality.',
                  AgentId.seniorEngineer =>
                    'Architecture, implementation strategy, and delivery risk.',
                  AgentId.scraper =>
                    'Web extraction, parsing strategy, and source constraints.',
                  _ => '',
                },
              ),
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

int _normalizeAgentTurns(
  String rawValue, {
  required int fallback,
}) {
  final parsed = int.tryParse(rawValue.trim());
  if (parsed == null) {
    return fallback;
  }
  return parsed < 0 ? 0 : parsed;
}

class _ComposerDraft {
  const _ComposerDraft({
    this.text = '',
    this.attachments = const <_PendingAttachmentDraft>[],
  });

  final String text;
  final List<_PendingAttachmentDraft> attachments;

  bool get isEmpty => text.trim().isEmpty && attachments.isEmpty;
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
    required this.onRemove,
    required this.onClearAll,
  });

  final List<_PendingAttachmentDraft> attachments;
  final bool busy;
  final ValueChanged<_PendingAttachmentDraft> onRemove;
  final VoidCallback onClearAll;

  @override
  Widget build(BuildContext context) {
    final imageCount =
        attachments.where((attachment) => attachment.isImage).length;
    final fileCount = attachments.length - imageCount;

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
                fileCount: fileCount,
              ),
              style: const TextStyle(
                color: Color(0xFF8B97B5),
                height: 1.4,
              ),
            ),
          ),
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
                  onRemove: () => onRemove(attachment),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _PendingAttachmentRow extends StatelessWidget {
  const _PendingAttachmentRow({
    required this.attachment,
    required this.busy,
    required this.onRemove,
  });

  final _PendingAttachmentDraft attachment;
  final bool busy;
  final VoidCallback onRemove;

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
                        : const Color(0xFF1E2944),
                    foregroundColor: attachment.isImage
                        ? const Color(0xFF9FF0DC)
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
                style: const TextStyle(
                  fontWeight: FontWeight.w700,
                ),
              ),
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

class _AttachmentPreview extends StatelessWidget {
  const _AttachmentPreview({
    required this.attachment,
  });

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

    return const _AttachmentFallbackIcon(
      icon: Icons.insert_drive_file_outlined,
    );
  }
}

class _AttachmentFallbackIcon extends StatelessWidget {
  const _AttachmentFallbackIcon({
    required this.icon,
  });

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
  required int fileCount,
}) {
  if (totalCount == 1 && imageCount == 1) {
    return 'One image is ready. Add optional instructions or send it as-is.';
  }
  if (totalCount == 1 && fileCount == 1) {
    return 'One file is ready. Tell Codex what you want from it.';
  }

  final parts = <String>[];
  if (imageCount > 0) {
    parts.add('$imageCount image${imageCount == 1 ? '' : 's'}');
  }
  if (fileCount > 0) {
    parts.add('$fileCount file${fileCount == 1 ? '' : 's'}');
  }
  return '${parts.join(' and ')} queued. They will be sent together in one Codex turn.';
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

class _ChatTimelineEntry {
  const _ChatTimelineEntry.separator(this.separatorDate) : message = null;

  const _ChatTimelineEntry.message(this.message) : separatorDate = null;

  final DateTime? separatorDate;
  final ChatMessage? message;
}

class _ChatDaySeparator extends StatelessWidget {
  const _ChatDaySeparator({
    super.key,
    required this.label,
  });

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
