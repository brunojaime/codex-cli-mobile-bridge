import 'package:flutter/material.dart';

import '../models/chat_session_summary.dart';
import '../models/server_profile.dart';
import '../models/workspace.dart';
import '../services/api_client.dart';
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

class _ChatScreenState extends State<ChatScreen> {
  final ServerProfileStore _serverProfileStore = ServerProfileStore();
  final TextEditingController _textController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  late ChatController _chatController;
  List<ServerProfile> _serverProfiles = <ServerProfile>[];
  ServerProfile? _activeServer;
  String? _serverErrorText;

  @override
  void initState() {
    super.initState();
    _chatController = _buildController(widget.initialApiBaseUrl);
    _chatController.addListener(_scrollToBottom);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _initializeServerProfiles();
    });
  }

  @override
  void dispose() {
    _chatController
      ..removeListener(_scrollToBottom)
      ..dispose();
    _textController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _chatController,
      builder: (context, _) {
        final messages = _chatController.messages;
        return Scaffold(
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
                          text: '  •  ${_chatController.currentSession!.workspaceName}',
                        ),
                      TextSpan(
                        text: '  •  ${_activeServer?.baseUrl ?? widget.initialApiBaseUrl}',
                      ),
                    ],
                  ),
                  style: const TextStyle(fontSize: 12, color: Color(0xFF8B97B5)),
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
                icon: const Icon(Icons.edit_square),
                tooltip: 'New chat',
              ),
            ],
          ),
          drawer: Drawer(
            backgroundColor: const Color(0xFF101931),
            child: SafeArea(
              child: Column(
                children: <Widget>[
                  ListTile(
                    title: const Text('Chats'),
                    subtitle: const Text('Codex session history'),
                    trailing: IconButton(
                      onPressed: () async {
                        await _openWorkspacePicker();
                        if (context.mounted) {
                          Navigator.of(context).pop();
                        }
                      },
                      icon: const Icon(Icons.add),
                    ),
                  ),
                  const Divider(height: 1),
                  Expanded(
                    child: _chatController.sessions.isEmpty
                        ? const Center(
                            child: Text(
                              'No chats yet',
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
                  child: _chatController.isLoading && _chatController.currentSession == null
                      ? const Center(child: CircularProgressIndicator())
                      : messages.isEmpty
                          ? _EmptyState(onCreateChat: _openWorkspacePicker)
                          : ListView.builder(
                              controller: _scrollController,
                              padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
                              itemCount: messages.length,
                              itemBuilder: (context, index) {
                                final message = messages[index];
                                return Align(
                                  alignment: message.isUser
                                      ? Alignment.centerRight
                                      : Alignment.centerLeft,
                                  child: ChatBubble(
                                    message: message,
                                    onOptionSelected: _handleSuggestedReply,
                                  ),
                                );
                              },
                            ),
                ),
                _Composer(
                  controller: _textController,
                  onSend: _handleSend,
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
    await _chatController.sendMessage(text);
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
                subtitle: Text('New chat will run in this workspace'),
              ),
              Flexible(
                child: ListView(
                  shrinkWrap: true,
                  children: workspaces
                      .map(
                        (workspace) => ListTile(
                          title: Text(workspace.name),
                          subtitle: Text(
                            workspace.path,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                          onTap: () => Navigator.of(context).pop(workspace),
                        ),
                      )
                      .toList(),
                ),
              ),
            ],
          ),
        );
      },
    );

    if (selectedWorkspace != null) {
      await _chatController.createNewSession(
        workspacePath: selectedWorkspace.path,
      );
    }
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
    });

    await _switchToServer(resolvedActiveProfile, initialize: true);
  }

  Future<void> _switchToServer(
    ServerProfile profile, {
    bool initialize = false,
  }) async {
    final nextController = _buildController(profile.baseUrl);
    nextController.addListener(_scrollToBottom);

    final previousController = _chatController;
    setState(() {
      _chatController = nextController;
      _activeServer = profile;
      _serverErrorText = null;
    });
    await _serverProfileStore.saveActiveProfileId(profile.id);

    try {
      await _chatController.initialize();
    } catch (error) {
      setState(() {
        _serverErrorText = 'Failed to connect to ${profile.name}.\n$error';
      });
    }

    if (!identical(previousController, nextController)) {
      previousController
        ..removeListener(_scrollToBottom)
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

    if (result != null && (_activeServer == null || result.id != _activeServer!.id)) {
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

  List<Widget> _buildSessionGroups() {
    final groupedSessions = <String, List<ChatSessionSummary>>{};
    final workspacePaths = <String, String>{};

    for (final session in _chatController.sessions) {
      groupedSessions.putIfAbsent(session.workspaceName, () => <ChatSessionSummary>[]).add(session);
      workspacePaths[session.workspaceName] = session.workspacePath;
    }

    return groupedSessions.entries.map((entry) {
      final workspaceName = entry.key;
      final sessions = entry.value;
      final hasSelected = sessions.any(
        (session) => session.id == _chatController.selectedSessionId,
      );
      final workspacePath = workspacePaths[workspaceName] ?? workspaceName;

      return Theme(
        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          key: PageStorageKey<String>('workspace-$workspaceName'),
          initiallyExpanded: hasSelected,
          tilePadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 2),
          childrenPadding: EdgeInsets.zero,
          iconColor: const Color(0xFF8B97B5),
          collapsedIconColor: const Color(0xFF8B97B5),
          title: Text(
            workspaceName,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
          subtitle: Text(
            '$workspacePath • ${sessions.length} chat${sessions.length == 1 ? '' : 's'}',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(color: Color(0xFF8B97B5)),
          ),
          children: sessions
              .map(
                (session) => Padding(
                  padding: const EdgeInsets.only(left: 10),
                  child: _SessionTile(
                    session: session,
                    selected: session.id == _chatController.selectedSessionId,
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

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scrollController.hasClients) {
        return;
      }

      _scrollController.animateTo(
        _scrollController.position.maxScrollExtent,
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
  final Future<ServerProfile?> Function(String name, String baseUrl) onAddServer;

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

class _Composer extends StatelessWidget {
  const _Composer({
    required this.controller,
    required this.onSend,
  });

  final TextEditingController controller;
  final Future<void> Function() onSend;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
      decoration: const BoxDecoration(
        color: Color(0xFF0D1427),
        border: Border(
          top: BorderSide(color: Color(0xFF1F2945)),
        ),
      ),
      child: Row(
        children: <Widget>[
          Expanded(
            child: TextField(
              controller: controller,
              minLines: 1,
              maxLines: 6,
              textInputAction: TextInputAction.send,
              onSubmitted: (_) async {
                await onSend();
              },
              decoration: const InputDecoration(
                hintText: 'Send a command to your local Codex CLI',
              ),
            ),
          ),
          const SizedBox(width: 12),
          FilledButton(
            onPressed: () async {
              await onSend();
            },
            style: FilledButton.styleFrom(
              backgroundColor: const Color(0xFF55D6BE),
              foregroundColor: const Color(0xFF07131D),
              minimumSize: const Size(56, 56),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(18),
              ),
            ),
            child: const Icon(Icons.arrow_upward_rounded),
          ),
        ],
      ),
    );
  }
}
