import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';

import '../models/chat_session_summary.dart';
import '../models/server_health.dart';
import '../models/server_profile.dart';
import '../models/workspace.dart';
import '../services/api_client.dart';
import '../services/audio_note_recorder.dart';
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
  ServerProfile? _activeServer;
  ServerHealth? _activeServerHealth;
  String? _serverErrorText;
  bool _stickToBottom = true;
  String? _lastObservedSessionId;

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
        return Scaffold(
          resizeToAvoidBottomInset: false,
          appBar: AppBar(
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
                              '  •  ${_activeServerHealth!.audioTranscriptionReady ? 'Voice ready' : 'Voice unavailable'}',
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
            backgroundColor: const Color(0xFF101931),
            child: SafeArea(
              child: Column(
                children: <Widget>[
                  ListTile(
                    title: const Text('Projects'),
                    subtitle: const Text('Choose a project or open a chat'),
                    trailing: IconButton(
                      onPressed: () async {
                        await _openWorkspacePicker();
                        if (context.mounted) {
                          Navigator.of(context).pop();
                        }
                      },
                      icon: const Icon(Icons.add),
                      tooltip: 'Choose project for new chat',
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
                                      return Align(
                                        alignment: message.isUser
                                            ? Alignment.centerRight
                                            : Alignment.centerLeft,
                                        child: ChatBubble(
                                          message: message,
                                          onOptionSelected:
                                              _handleSuggestedReply,
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
                  controller: _textController,
                  onSend: _handleSend,
                  onSendAudio: _handleSendAudio,
                  isBusy: _chatController.isLoading ||
                      _chatController.isSendingAudio,
                  voiceEnabled:
                      _activeServerHealth?.audioTranscriptionReady ?? true,
                  voiceStatusText: _resolveVoiceStatusText(),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Future<void> _handleSend() async {
    final text = _textController.text;
    _textController.clear();
    _updateStickToBottom(true);
    _scrollToBottom();
    await _chatController.sendMessage(text);
  }

  Future<void> _handleSendAudio(String audioPath) async {
    _updateStickToBottom(true);
    _scrollToBottom();
    await _chatController.sendAudioMessage(audioPath);
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
    final resolvedActiveProfile = profiles.firstWhere(
      (profile) => profile.id == activeProfileId,
      orElse: () => profiles.first,
    );

    setState(() {
      _serverProfiles = profiles;
      _activeServer = resolvedActiveProfile;
      _activeServerHealth = null;
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
    nextController.addListener(_handleChatControllerChanged);

    final previousController = _chatController;
    setState(() {
      _chatController = nextController;
      _activeServer = profile;
      _activeServerHealth = null;
      _sidebarWorkspaces = sidebarWorkspaces;
      _serverErrorText = null;
    });
    _lastObservedSessionId = null;
    _updateStickToBottom(true);
    await _serverProfileStore.saveActiveProfileId(profile.id);

    try {
      final health = await client.getHealth();
      if (mounted) {
        setState(() {
          _activeServerHealth = health;
        });
      }
      await _chatController.initialize();
    } catch (error) {
      setState(() {
        _activeServerHealth = null;
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
    final health = _activeServerHealth;
    if (health == null) {
      return 'Voice status unavailable.';
    }

    if (health.audioTranscriptionReady) {
      return 'Voice input ready via ${health.audioTranscriptionResolvedBackend}.';
    }

    return health.audioTranscriptionDetail ??
        'Voice input is not available on this server.';
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

      return Theme(
        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          key: PageStorageKey<String>('workspace-${workspace.path}'),
          initiallyExpanded: hasSelected,
          tilePadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 2),
          childrenPadding: EdgeInsets.zero,
          iconColor: const Color(0xFF8B97B5),
          collapsedIconColor: const Color(0xFF8B97B5),
          title: Row(
            children: <Widget>[
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      workspace.name,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
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
                  ],
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
                      padding: const EdgeInsets.only(left: 10),
                      child: _SessionTile(
                        session: session,
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
      );
    }).toList();
  }

  void _handleChatControllerChanged() {
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
    required this.session,
    required this.selected,
    required this.onTap,
  });

  final ChatSessionSummary session;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      selected: selected,
      selectedTileColor: const Color(0xFF1C2745),
      title: Text(
        session.title,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
      ),
      subtitle: Text(
        session.lastMessagePreview?.isNotEmpty == true
            ? session.lastMessagePreview!
            : 'No messages yet',
        maxLines: 2,
        overflow: TextOverflow.ellipsis,
        style: const TextStyle(color: Color(0xFF8B97B5)),
      ),
      trailing: session.hasPendingMessages
          ? const SizedBox(
              width: 18,
              height: 18,
              child: CircularProgressIndicator(strokeWidth: 2),
            )
          : null,
      onTap: onTap,
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
        padding: const EdgeInsets.symmetric(horizontal: 28),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: <Widget>[
            const Text(
              'Start a new Codex session',
              style: TextStyle(fontSize: 24, fontWeight: FontWeight.w600),
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
    );
  }
}

class _Composer extends StatefulWidget {
  const _Composer({
    required this.controller,
    required this.onSend,
    required this.onSendAudio,
    required this.isBusy,
    required this.voiceEnabled,
    required this.voiceStatusText,
  });

  final TextEditingController controller;
  final Future<void> Function() onSend;
  final Future<void> Function(String audioPath) onSendAudio;
  final bool isBusy;
  final bool voiceEnabled;
  final String voiceStatusText;

  @override
  State<_Composer> createState() => _ComposerState();
}

class _ComposerState extends State<_Composer> {
  final AudioNoteRecorder _audioRecorder = AudioNoteRecorder();
  Stopwatch? _recordingStopwatch;
  Timer? _recordingTicker;
  bool _hasText = false;
  bool _isRecording = false;
  bool _isUploadingVoiceNote = false;
  String? _pendingRecordingPath;

  @override
  void initState() {
    super.initState();
    _hasText = widget.controller.text.trim().isNotEmpty;
    widget.controller.addListener(_handleTextChanged);
  }

  @override
  void didUpdateWidget(covariant _Composer oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.controller != widget.controller) {
      oldWidget.controller.removeListener(_handleTextChanged);
      _hasText = widget.controller.text.trim().isNotEmpty;
      widget.controller.addListener(_handleTextChanged);
    }
  }

  @override
  void dispose() {
    widget.controller.removeListener(_handleTextChanged);
    _recordingTicker?.cancel();
    if (_pendingRecordingPath != null) {
      _deleteRecordedFile(_pendingRecordingPath!);
    }
    _audioRecorder.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final showMicAction = !_hasText && !_isRecording;
    final isDisabled = widget.isBusy || _isUploadingVoiceNote;
    final viewInsetsBottom = MediaQuery.of(context).viewInsets.bottom;

    return AnimatedPadding(
      duration: const Duration(milliseconds: 180),
      curve: Curves.easeOut,
      padding: EdgeInsets.only(bottom: viewInsetsBottom),
      child: SafeArea(
        top: false,
        child: Container(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
          decoration: const BoxDecoration(
            color: Color(0xFF0D1427),
            border: Border(
              top: BorderSide(color: Color(0xFF1F2945)),
            ),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: <Widget>[
              Expanded(
                child: _buildComposerBody(),
              ),
              const SizedBox(width: 12),
              if (_isRecording)
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    FilledButton(
                      onPressed: _isUploadingVoiceNote
                          ? null
                          : _confirmCancelRecording,
                      style: _actionButtonStyle(
                        backgroundColor: const Color(0xFF31405F),
                        foregroundColor: const Color(0xFFE8ECF8),
                      ),
                      child: const Icon(Icons.close_rounded),
                    ),
                    const SizedBox(width: 8),
                    FilledButton(
                      onPressed:
                          _isUploadingVoiceNote ? null : _stopRecordingAndSend,
                      style: _actionButtonStyle(
                        backgroundColor: const Color(0xFFFF7A7A),
                        foregroundColor: const Color(0xFF2C0710),
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
                  onPressed: isDisabled ? null : () async => widget.onSend(),
                  style: _actionButtonStyle(
                    backgroundColor: const Color(0xFF55D6BE),
                    foregroundColor: const Color(0xFF07131D),
                  ),
                  child: const Icon(Icons.arrow_upward_rounded),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildComposerBody() {
    if (_isRecording) {
      return _VoiceStatusCard(
        icon: Icons.mic_rounded,
        title: 'Recording voice note',
        subtitle:
            'Tap send to upload or cancel to discard • ${_formatDuration()}',
        color: const Color(0xFFFF7A7A),
      );
    }

    if (_isUploadingVoiceNote) {
      return const _VoiceStatusCard(
        icon: Icons.cloud_upload_rounded,
        title: 'Sending voice note',
        subtitle: 'Uploading audio and transcribing it on the backend',
        color: Color(0xFF55D6BE),
        showSpinner: true,
      );
    }

    return TextField(
      controller: widget.controller,
      minLines: 1,
      maxLines: 6,
      enabled: !widget.isBusy,
      textInputAction: TextInputAction.send,
      onSubmitted: (_) async {
        await widget.onSend();
      },
      decoration: const InputDecoration(
        hintText: 'Send a command to your local Codex CLI',
      ),
    );
  }

  ButtonStyle _actionButtonStyle({
    required Color backgroundColor,
    required Color foregroundColor,
  }) {
    return FilledButton.styleFrom(
      backgroundColor: backgroundColor,
      foregroundColor: foregroundColor,
      minimumSize: const Size(56, 56),
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
  }

  Future<void> _toggleRecording() async {
    if (_isRecording) {
      await _stopRecordingAndSend();
      return;
    }
    await _startRecording();
  }

  Future<void> _confirmCancelRecording() async {
    if (!_isRecording || _isUploadingVoiceNote) {
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
    if (_isRecording || widget.isBusy || _isUploadingVoiceNote) {
      return;
    }

    try {
      final path = await _audioRecorder.start();
      _recordingStopwatch = Stopwatch()..start();
      _recordingTicker?.cancel();
      _recordingTicker = Timer.periodic(const Duration(seconds: 1), (_) {
        if (mounted) {
          setState(() {});
        }
      });
      setState(() {
        _pendingRecordingPath = path;
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

    _recordingTicker?.cancel();
    _recordingStopwatch?.stop();
    final audioPath = await _audioRecorder.stop();

    setState(() {
      _isRecording = false;
      _isUploadingVoiceNote = true;
    });

    try {
      if (audioPath != null) {
        await widget.onSendAudio(audioPath);
      }
    } finally {
      if (audioPath != null) {
        _deleteRecordedFile(audioPath);
      }
      _recordingStopwatch = null;
      if (mounted) {
        setState(() {
          _pendingRecordingPath = null;
          _isUploadingVoiceNote = false;
        });
      } else {
        _pendingRecordingPath = null;
      }
    }
  }

  Future<void> _discardRecording() async {
    if (!_isRecording) {
      return;
    }

    _recordingTicker?.cancel();
    _recordingStopwatch?.stop();
    final audioPath = await _audioRecorder.stop();
    final pathToDelete = audioPath ?? _pendingRecordingPath;
    if (pathToDelete != null) {
      _deleteRecordedFile(pathToDelete);
    }

    _recordingStopwatch = null;
    if (mounted) {
      setState(() {
        _isRecording = false;
        _pendingRecordingPath = null;
      });
    } else {
      _pendingRecordingPath = null;
    }
  }

  void _deleteRecordedFile(String path) {
    final file = File(path);
    if (file.existsSync()) {
      file.deleteSync();
    }

    final parent = file.parent;
    if (parent.existsSync()) {
      parent.deleteSync(recursive: true);
    }
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

class _VoiceStatusCard extends StatelessWidget {
  const _VoiceStatusCard({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.color,
    this.showSpinner = false,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final Color color;
  final bool showSpinner;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
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
                  style: const TextStyle(fontWeight: FontWeight.w600),
                ),
                const SizedBox(height: 2),
                Text(
                  subtitle,
                  style: const TextStyle(color: Color(0xFF8B97B5)),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
