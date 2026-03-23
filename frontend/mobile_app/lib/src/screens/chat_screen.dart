import 'dart:async';
import 'dart:math' as math;

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/chat_session_summary.dart';
import '../models/server_capabilities.dart';
import '../models/server_health.dart';
import '../models/server_profile.dart';
import '../models/workspace.dart';
import '../services/api_client.dart';
import '../services/audio_note_recorder.dart';
import '../services/clipboard_image_paste_listener_stub.dart'
    if (dart.library.js_interop) '../services/clipboard_image_paste_listener_web.dart';
import '../services/server_profile_store.dart';
import '../state/chat_controller.dart';
import '../widgets/chat_bubble.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({
    super.key,
    required this.initialApiBaseUrl,
  });

  final String initialApiBaseUrl;

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> with WidgetsBindingObserver {
  final ServerProfileStore _serverProfileStore = ServerProfileStore();
  final TextEditingController _textController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  late ChatController _chatController;
  List<ServerProfile> _serverProfiles = <ServerProfile>[];
  List<Workspace> _sidebarWorkspaces = <Workspace>[];
  Map<String, DateTime> _sessionReadMarkers = <String, DateTime>{};
  ServerProfile? _activeServer;
  ServerHealth? _activeServerHealth;
  ServerCapabilities? _activeServerCapabilities;
  String? _serverErrorText;
  bool _sidebarExpanded = false;
  bool _stickToBottom = true;
  String? _lastObservedSessionId;
  final Map<String, _ComposerDraft> _sessionDrafts = <String, _ComposerDraft>{};

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _chatController = _buildController(widget.initialApiBaseUrl);
    _chatController.addListener(_handleChatControllerChanged);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _initializeServerProfiles();
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _chatController
      ..removeListener(_handleChatControllerChanged)
      ..dispose();
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
        final messages = _chatController.messages;
        final screenWidth = MediaQuery.sizeOf(context).width;
        final drawerWidth = math.min(
          screenWidth - 24,
          _sidebarExpanded ? 440.0 : 340.0,
        );
        final totalUnreadChatsCount = _totalUnreadChatsCount();
        final totalActivePinnedProjectsCount =
            _totalActivePinnedProjectsCount();
        final totalActivePinnedJobsCount = _totalActivePinnedJobsCount();
        return Scaffold(
          appBar: AppBar(
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
            title: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(_chatController.currentSession?.title ?? 'Codex Remote'),
                const SizedBox(height: 2),
                Text.rich(
                  TextSpan(
                    text: _activeServer != null
                        ? 'Server: ${_activeServer!.name}'
                        : 'Commands execute on your local machine',
                    children: <InlineSpan>[
                      if (_chatController.currentSession != null)
                        TextSpan(
                          text:
                              '  •  ${_chatController.currentSession!.workspaceName}',
                        ),
                      TextSpan(
                        text:
                            '  •  ${_activeServer?.baseUrl ?? widget.initialApiBaseUrl}',
                      ),
                      if (_activeServerHealth != null)
                        TextSpan(
                          text:
                              '  •  ${_activeServerHealth!.audioTranscriptionReady ? 'Audio ready' : 'Audio unavailable'}',
                        ),
                    ],
                  ),
                  style:
                      const TextStyle(fontSize: 12, color: Color(0xFF8B97B5)),
                ),
              ],
            ),
            actions: <Widget>[
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
            ],
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
                      _sidebarExpanded
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
                  Expanded(
                    child: _sidebarWorkspaces.isEmpty
                        ? const Center(
                            child: Text(
                              'No projects pinned yet',
                              style: TextStyle(color: Color(0xFF8B97B5)),
                            ),
                          )
                        : ListView(
                            children: _buildSessionGroups(),
                          ),
                  ),
                ],
              ),
            ),
          ),
          body: SafeArea(
            bottom: false,
            child: Column(
              children: <Widget>[
                if (_chatController.errorText != null)
                  Container(
                    width: double.infinity,
                    margin: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: const Color(0xFF3B1521),
                      borderRadius: BorderRadius.circular(14),
                    ),
                    child: Text(
                      _chatController.errorText!,
                      style: const TextStyle(color: Colors.white),
                    ),
                  ),
                if (_serverErrorText != null)
                  Container(
                    width: double.infinity,
                    margin: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: const Color(0xFF362411),
                      borderRadius: BorderRadius.circular(14),
                    ),
                    child: Text(
                      _serverErrorText!,
                      style: const TextStyle(color: Colors.white),
                    ),
                  ),
                Expanded(
                  child: _chatController.isLoading &&
                          _chatController.currentSession == null
                      ? const Center(child: CircularProgressIndicator())
                      : messages.isEmpty
                          ? _EmptyState(onCreateChat: _openWorkspacePicker)
                          : Stack(
                              children: <Widget>[
                                NotificationListener<ScrollNotification>(
                                  onNotification: _handleScrollNotification,
                                  child: ListView.builder(
                                    controller: _scrollController,
                                    padding: const EdgeInsets.fromLTRB(
                                      16,
                                      12,
                                      16,
                                      16,
                                    ),
                                    itemCount: messages.length,
                                    itemBuilder: (context, index) {
                                      final message = messages[index];
                                      final nextMessage =
                                          index + 1 < messages.length
                                              ? messages[index + 1]
                                              : null;
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
                                            message: message,
                                            onOptionSelected:
                                                _handleSuggestedReply,
                                            onLinkTap: _handleMessageLinkTap,
                                          ),
                                        ),
                                      );
                                    },
                                  ),
                                ),
                                Positioned(
                                  right: 16,
                                  bottom: 12,
                                  child: IgnorePointer(
                                    ignoring: _stickToBottom,
                                    child: AnimatedSlide(
                                      duration:
                                          const Duration(milliseconds: 180),
                                      curve: Curves.easeOut,
                                      offset: _stickToBottom
                                          ? const Offset(0, 0.35)
                                          : Offset.zero,
                                      child: AnimatedOpacity(
                                        duration:
                                            const Duration(milliseconds: 180),
                                        opacity: _stickToBottom ? 0 : 1,
                                        child: FloatingActionButton.small(
                                          heroTag: 'scroll-to-latest',
                                          onPressed: () {
                                            _updateStickToBottom(true);
                                            _scrollToBottom();
                                          },
                                          backgroundColor:
                                              const Color(0xFF1C2745),
                                          foregroundColor:
                                              const Color(0xFF55D6BE),
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
                  isBusy: _chatController.isLoading ||
                      _chatController.isSendingDocument ||
                      _chatController.isSendingImage,
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
    final didSend = await _chatController.sendMessage(_textController.text);
    if (didSend && _chatController.selectedSessionId == sessionIdBeforeSend) {
      _textController.clear();
      _updateStickToBottom(true);
      _scrollToBottom();
    }
    return didSend;
  }

  Future<bool> _handleSendAudio(XFile audioFile) async {
    final sessionIdBeforeSend = _chatController.selectedSessionId;
    final didSend = await _chatController.sendAudioMessage(audioFile);
    if (didSend && _chatController.selectedSessionId == sessionIdBeforeSend) {
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
    final didSend = await _chatController.sendAttachmentsMessage(
      attachments.map((attachment) => attachment.file).toList(),
      message: prompt,
    );
    if (didSend && _chatController.selectedSessionId == sessionIdBeforeSend) {
      _updateStickToBottom(true);
      _scrollToBottom();
    }
    return didSend;
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

  Future<void> _openWorkspacePicker() async {
    if (_chatController.workspaces.isEmpty) {
      await _chatController.refreshWorkspaces();
    }
    if (!mounted) {
      return;
    }

    final selectedWorkspace = await showModalBottomSheet<Workspace>(
      context: context,
      backgroundColor: const Color(0xFF101931),
      builder: (context) {
        final workspaces = _chatController.workspaces;
        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              const ListTile(
                title: Text('Choose Project'),
                subtitle: Text('Add it to the sidebar and start a new chat'),
              ),
              Flexible(
                child: ListView(
                  shrinkWrap: true,
                  children: workspaces.map(
                    (workspace) {
                      final isPinned = _sidebarWorkspaces.any(
                        (item) => item.path == workspace.path,
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
                        onTap: () => Navigator.of(context).pop(workspace),
                      );
                    },
                  ).toList(),
                ),
              ),
            ],
          ),
        );
      },
    );

    if (selectedWorkspace != null) {
      await _pinWorkspaceToSidebar(selectedWorkspace);
      await _createNewChatForWorkspace(selectedWorkspace);
    }
  }

  Future<void> _createNewChatForWorkspace(Workspace workspace) async {
    await _chatController.createNewSession(workspacePath: workspace.path);
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

  Future<void> _initializeServerProfiles() async {
    final profiles = await _serverProfileStore.loadProfiles(
      defaultBaseUrl: widget.initialApiBaseUrl,
    );
    final activeProfileId = await _serverProfileStore.loadActiveProfileId();
    final sidebarExpanded = await _serverProfileStore.loadSidebarExpanded();
    final resolvedActiveProfile = profiles.firstWhere(
      (profile) => profile.id == activeProfileId,
      orElse: () => profiles.first,
    );

    setState(() {
      _serverProfiles = profiles;
      _activeServer = resolvedActiveProfile;
      _activeServerHealth = null;
      _sidebarExpanded = sidebarExpanded;
    });

    await _switchToServer(resolvedActiveProfile, initialize: true);
  }

  Future<void> _switchToServer(
    ServerProfile profile, {
    bool initialize = false,
  }) async {
    final client = ApiClient(baseUrl: profile.baseUrl);
    final nextController = ChatController(apiClient: client);
    final sidebarWorkspaces = await _serverProfileStore.loadSidebarWorkspaces(
      profile.baseUrl,
    );
    final sessionReadMarkers = await _serverProfileStore.loadSessionReadMarkers(
      profile.baseUrl,
    );
    nextController.addListener(_handleChatControllerChanged);

    final previousController = _chatController;
    setState(() {
      _chatController = nextController;
      _activeServer = profile;
      _activeServerHealth = null;
      _activeServerCapabilities = null;
      _sidebarWorkspaces = sidebarWorkspaces;
      _sessionReadMarkers = sessionReadMarkers;
      _serverErrorText = null;
    });
    _lastObservedSessionId = null;
    _updateStickToBottom(true);
    await _serverProfileStore.saveActiveProfileId(profile.id);

    try {
      final health = await client.getHealth();
      final capabilities = await client.getCapabilities();
      if (mounted) {
        setState(() {
          _activeServerHealth = health;
          _activeServerCapabilities = capabilities;
        });
      }
      await _chatController.initialize();
    } catch (error) {
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

  ChatController _buildController(String baseUrl) {
    return ChatController(apiClient: ApiClient(baseUrl: baseUrl));
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

  List<Widget> _buildSessionGroups() {
    final groupedSessions = <String, List<ChatSessionSummary>>{};

    for (final session in _chatController.sessions) {
      groupedSessions
          .putIfAbsent(session.workspacePath, () => <ChatSessionSummary>[])
          .add(session);
    }

    return _sidebarWorkspaces.map((workspace) {
      final sessions =
          groupedSessions[workspace.path] ?? <ChatSessionSummary>[];
      final hasSelected = sessions.any(
        (session) => session.id == _chatController.selectedSessionId,
      );
      final activeJobCount = sessions.fold(
        0,
        (total, session) =>
            total + _chatController.activeJobCountForSession(session.id),
      );
      final activeChatCount = sessions
          .where(
            (session) =>
                _chatController.activeJobCountForSession(session.id) > 0,
          )
          .length;
      final unreadChatsCount = sessions
          .where((session) => _unreadCountForSession(session) > 0)
          .length;
      final projectCardColor =
          hasSelected ? const Color(0xFF16213C) : const Color(0xFF121A31);
      final projectBorderColor = activeJobCount > 0
          ? const Color(0x44FFC857)
          : unreadChatsCount > 0
              ? const Color(0x3355D6BE)
              : const Color(0xFF23304F);

      return Container(
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
                        : const Color(0xFF1B2745),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  alignment: Alignment.center,
                  child: Icon(
                    Icons.folder_rounded,
                    color: activeJobCount > 0
                        ? const Color(0xFFFFC857)
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
                              : unreadChatsCount > 0
                                  ? const Color(0xFF55D6BE)
                                  : const Color(0xFFE7EEF9),
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        '${workspace.path} • ${sessions.length} chat${sessions.length == 1 ? '' : 's'}',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: Color(0xFF8B97B5),
                          fontSize: 12,
                        ),
                      ),
                      const SizedBox(height: 6),
                      _ProjectStatusPill(
                        active: activeJobCount > 0,
                        label: activeJobCount > 0
                            ? '$activeJobCount active job${activeJobCount == 1 ? '' : 's'} in $activeChatCount chat${activeChatCount == 1 ? '' : 's'}'
                            : 'No active jobs',
                      ),
                    ],
                  ),
                ),
                if (activeJobCount > 0)
                  Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: Text(
                      activeJobCount.toString(),
                      style: const TextStyle(
                        color: Color(0xFFFFC857),
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
                IconButton(
                  onPressed: () async {
                    Navigator.of(context).pop();
                    await _createNewChatForWorkspace(workspace);
                  },
                  icon: const Icon(Icons.add_circle_outline),
                  tooltip: 'New chat in ${workspace.name}',
                ),
              ],
            ),
            children: sessions.isEmpty
                ? <Widget>[
                    const Padding(
                      padding: EdgeInsets.fromLTRB(24, 0, 24, 16),
                      child: Align(
                        alignment: Alignment.centerLeft,
                        child: Text(
                          'No chats yet for this project',
                          style: TextStyle(color: Color(0xFF8B97B5)),
                        ),
                      ),
                    ),
                  ]
                : sessions
                    .map(
                      (session) => Padding(
                        padding: const EdgeInsets.only(left: 10, right: 10),
                        child: _SessionTile(
                          activeJobSummary:
                              _chatController.activeJobSummaryForSession(
                            session.id,
                          ),
                          outgoingAudioUploadCount: _chatController
                              .outgoingAudioUploadCountForSession(
                            session.id,
                          ),
                          session: session,
                          unreadCount: _unreadCountForSession(session),
                          selected:
                              session.id == _chatController.selectedSessionId,
                          onTap: () async {
                            Navigator.of(context).pop();
                            await _chatController.selectSession(session.id);
                          },
                        ),
                      ),
                    )
                    .toList(),
          ),
        ),
      );
    }).toList();
  }

  void _handleChatControllerChanged() {
    _markCurrentSessionAsRead();
    final currentSessionId = _chatController.selectedSessionId;
    final sessionChanged = currentSessionId != _lastObservedSessionId;
    if (sessionChanged) {
      _lastObservedSessionId = currentSessionId;
      _updateStickToBottom(true);
    }

    if (_stickToBottom) {
      _scrollToBottom(jumpToBottom: sessionChanged);
    }
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
        .where((workspace) => _activeJobCountForWorkspace(workspace.path) > 0)
        .length;
  }

  int _totalActivePinnedJobsCount() {
    return _sidebarWorkspaces.fold(
        0,
        (total, workspace) =>
            total + _activeJobCountForWorkspace(workspace.path));
  }

  int _activeJobCountForWorkspace(String workspacePath) {
    return _chatController.sessions
        .where((session) => session.workspacePath == workspacePath)
        .fold(
          0,
          (total, session) =>
              total + _chatController.activeJobCountForSession(session.id),
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
    required this.outgoingAudioUploadCount,
    required this.session,
    required this.unreadCount,
    required this.selected,
    required this.onTap,
  });

  final SessionActiveJobSummary? activeJobSummary;
  final int outgoingAudioUploadCount;
  final ChatSessionSummary session;
  final int unreadCount;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final activeRuntimeLabel = _formatSessionRuntime(activeJobSummary);
    final isActive = activeJobSummary != null;
    final isUploadingAudio = outgoingAudioUploadCount > 0;
    final tileBackgroundColor = selected
        ? const Color(0xFF1C2745)
        : isActive
            ? const Color(0x1455D6BE)
            : isUploadingAudio
                ? const Color(0x123F5EF7)
                : Colors.transparent;
    final tileBorderColor = selected
        ? const Color(0xFF2F3F68)
        : isActive
            ? const Color(0x2855D6BE)
            : isUploadingAudio
                ? const Color(0x283F5EF7)
                : Colors.transparent;
    final titleColor = selected
        ? Colors.white
        : isActive
            ? const Color(0xFFE3FBF5)
            : isUploadingAudio
                ? const Color(0xFFEAF0FF)
                : null;
    final previewColor = isActive || isUploadingAudio
        ? const Color(0xFFA8C7C0)
        : const Color(0xFF8B97B5);

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
            color: titleColor,
            fontWeight: isActive ? FontWeight.w600 : null,
          ),
        ),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Text(
              session.lastMessagePreview?.isNotEmpty == true
                  ? session.lastMessagePreview!
                  : 'No messages yet',
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(color: previewColor),
            ),
            if (activeRuntimeLabel != null) ...<Widget>[
              const SizedBox(height: 6),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: const Color(0xFF3D2D08),
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text(
                  activeRuntimeLabel,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: Color(0xFFFFC857),
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ],
            if (isUploadingAudio) ...<Widget>[
              const SizedBox(height: 6),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: const Color(0xFF15265A),
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text(
                  outgoingAudioUploadCount == 1
                      ? 'Sending audio'
                      : 'Sending $outgoingAudioUploadCount audios',
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
        trailing: session.hasPendingMessages
            ? const SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            : isUploadingAudio
                ? const Icon(
                    Icons.graphic_eq_rounded,
                    color: Color(0xFF8CA8FF),
                  )
                : unreadCount > 0
                    ? const Icon(
                        Icons.mark_chat_unread_rounded,
                        color: Color(0xFF55D6BE),
                      )
                    : null,
        onTap: onTap,
      ),
    );
  }
}

String? _formatSessionRuntime(SessionActiveJobSummary? summary) {
  if (summary == null) {
    return null;
  }

  final elapsedLabel = _formatElapsed(summary.maxElapsedSeconds);
  if (elapsedLabel == null) {
    return null;
  }

  if (summary.activeJobCount == 1) {
    return 'Running for $elapsedLabel';
  }

  return '${summary.activeJobCount} jobs running • $elapsedLabel';
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
    return LayoutBuilder(
      builder: (context, constraints) {
        return SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 24),
          child: ConstrainedBox(
            constraints: BoxConstraints(minHeight: constraints.maxHeight),
            child: Center(
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
        );
      },
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
  final List<_PendingAttachmentDraft> _uploadingAttachments =
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
    final isDisabled = widget.isBusy || _uploadingAttachments.isNotEmpty;
    final showAttachmentActions =
        !_isRecording && _uploadingAttachments.isEmpty;

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

    if (_uploadingAttachments.isNotEmpty) {
      final isSingleAttachment = _uploadingAttachments.length == 1;
      final primaryAttachment = _uploadingAttachments.first;
      return _VoiceStatusCard(
        icon: primaryAttachment.isImage
            ? Icons.image_rounded
            : Icons.insert_drive_file_rounded,
        title: isSingleAttachment
            ? (primaryAttachment.isImage ? 'Sending image' : 'Sending file')
            : 'Sending ${_uploadingAttachments.length} attachments',
        subtitle: isSingleAttachment
            ? (primaryAttachment.isImage
                ? 'Uploading ${primaryAttachment.name} and forwarding it to Codex'
                : 'Uploading ${primaryAttachment.name} and preparing it for Codex')
            : 'Uploading ${_uploadingAttachments.length} attachments to one Codex turn',
        color: const Color(0xFF55D6BE),
        showSpinner: true,
        trailing: _StatusPill(
          label: isSingleAttachment
              ? primaryAttachment.badgeLabel
              : '${_uploadingAttachments.length} files',
          backgroundColor: const Color(0xFF11352E),
          foregroundColor: const Color(0xFF9FF0DC),
        ),
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
      for (final file in result.files) {
        final xFile = file.xFile;
        final kind = _resolveAttachmentKind(
          fileName: file.name,
          mimeType: xFile.mimeType,
        );
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
        throw Exception(
            'The selected files are not accessible on this device.');
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

      setState(() {
        _uploadingAttachments
          ..clear()
          ..addAll(attachments);
      });

      try {
        final didSend = await widget.onSendAttachments(
          attachments,
          prompt: prompt.isEmpty ? null : prompt,
        );
        if (didSend) {
          widget.controller.clear();
          if (mounted) {
            setState(() {
              _pendingAttachments.clear();
            });
          } else {
            _pendingAttachments.clear();
          }
          _emitDraftChanged();
        }
      } finally {
        if (mounted) {
          setState(() {
            _uploadingAttachments.clear();
          });
        } else {
          _uploadingAttachments.clear();
        }
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
        !widget.isBusy &&
        !_isRecording &&
        _uploadingAttachments.isEmpty;
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

    final nextAttachments =
        List<_PendingAttachmentDraft>.from(draft.attachments);
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
    this.showSpinner = false,
    this.trailing,
    this.titleMaxLines = 1,
    this.subtitleMaxLines = 2,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final Color color;
  final bool showSpinner;
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
          if (showSpinner)
            SizedBox(
              width: 20,
              height: 20,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                valueColor: AlwaysStoppedAnimation<Color>(color),
              ),
            )
          else
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
