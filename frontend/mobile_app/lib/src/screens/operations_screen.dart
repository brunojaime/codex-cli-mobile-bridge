import 'dart:async';

import 'package:flutter/material.dart';

import '../models/control_status.dart';
import '../services/control_agent_client.dart';
import '../services/control_agent_store.dart';

class OperationsScreen extends StatefulWidget {
  const OperationsScreen({super.key, required this.bridgeBaseUrl});

  final String bridgeBaseUrl;

  @override
  State<OperationsScreen> createState() => _OperationsScreenState();
}

class _OperationsScreenState extends State<OperationsScreen> {
  final ControlAgentStore _store = ControlAgentStore();
  ControlAgentConfiguration? _configuration;
  ControlAgentClient? _client;
  Timer? _refreshTimer;
  ControlSnapshot? _snapshot;
  final Map<String, ControlRestartAction> _actions =
      <String, ControlRestartAction>{};
  bool _loading = true;
  bool _refreshing = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    unawaited(_initialize());
    _refreshTimer = Timer.periodic(
      const Duration(seconds: 5),
      (_) => unawaited(_refresh(silent: true)),
    );
  }

  @override
  void dispose() {
    _refreshTimer?.cancel();
    _client?.close();
    super.dispose();
  }

  Future<void> _initialize() async {
    final configuration = await _store.load();
    if (!mounted) {
      return;
    }
    setState(() {
      _configuration = configuration;
      _client = configuration == null
          ? null
          : ControlAgentClient(
              baseUrl: configuration.baseUrl,
              token: configuration.token,
            );
      _loading = false;
    });
    if (configuration != null) {
      await _refresh();
    }
  }

  Future<void> _refresh({bool silent = false}) async {
    final client = _client;
    if (client == null || !mounted || _refreshing) {
      return;
    }
    _refreshing = true;
    if (!silent) {
      setState(() {
        _loading = true;
        _error = null;
      });
    }
    try {
      final snapshot = await client.getSnapshot();
      final updatedActions = Map<String, ControlRestartAction>.from(_actions);
      for (final entry in _actions.entries) {
        if (entry.value.isTerminal) {
          continue;
        }
        updatedActions[entry.key] = await client.getAction(entry.value.id);
      }
      if (!mounted) {
        return;
      }
      setState(() {
        _snapshot = snapshot;
        _actions
          ..clear()
          ..addAll(updatedActions);
        _loading = false;
        _error = null;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _loading = false;
        _error = '$error';
      });
    } finally {
      _refreshing = false;
    }
  }

  Future<void> _configure() async {
    final urlController = TextEditingController(
      text:
          _configuration?.baseUrl ??
          deriveControlAgentUrl(widget.bridgeBaseUrl),
    );
    final tokenController = TextEditingController(
      text: _configuration?.token ?? '',
    );
    final configuration = await showDialog<ControlAgentConfiguration>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Control Agent connection'),
        content: SizedBox(
          width: 480,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              TextField(
                controller: urlController,
                decoration: const InputDecoration(labelText: 'Control URL'),
                keyboardType: TextInputType.url,
              ),
              const SizedBox(height: 12),
              TextField(
                controller: tokenController,
                decoration: const InputDecoration(labelText: 'Control token'),
                obscureText: true,
                autocorrect: false,
                enableSuggestions: false,
              ),
            ],
          ),
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              final url = urlController.text.trim().replaceFirst(
                RegExp(r'/$'),
                '',
              );
              final token = tokenController.text.trim();
              if (!url.startsWith('http') || token.isEmpty) {
                return;
              }
              Navigator.of(
                context,
              ).pop(ControlAgentConfiguration(baseUrl: url, token: token));
            },
            child: const Text('Save'),
          ),
        ],
      ),
    );
    urlController.dispose();
    tokenController.dispose();
    if (configuration == null || !mounted) {
      return;
    }
    await _store.save(configuration);
    _client?.close();
    setState(() {
      _configuration = configuration;
      _client = ControlAgentClient(
        baseUrl: configuration.baseUrl,
        token: configuration.token,
      );
    });
    await _refresh();
  }

  Future<void> _restart(
    ControlEnvironmentStatus environment, {
    required bool force,
  }) async {
    final activeJobs = environment.activeJobCount ?? 0;
    final confirmed =
        await showDialog<bool>(
          context: context,
          builder: (context) => AlertDialog(
            title: Text(force ? 'Force restart?' : 'Restart safely?'),
            content: Text(
              force
                  ? 'This skips drain and may interrupt $activeJobs active run(s). Use it only when the backend cannot recover normally.'
                  : 'New runs will be blocked and the restart will wait for $activeJobs active run(s) to finish.',
            ),
            actions: <Widget>[
              TextButton(
                onPressed: () => Navigator.of(context).pop(false),
                child: const Text('Cancel'),
              ),
              FilledButton(
                style: force
                    ? FilledButton.styleFrom(
                        backgroundColor: const Color(0xFFE45B6A),
                      )
                    : null,
                onPressed: () => Navigator.of(context).pop(true),
                child: Text(force ? 'Force restart' : 'Restart safely'),
              ),
            ],
          ),
        ) ??
        false;
    if (!confirmed || !mounted) {
      return;
    }
    try {
      final action = await _client!.restart(environment.name, force: force);
      if (!mounted) {
        return;
      }
      setState(() {
        _actions[environment.name] = action;
      });
      await _refresh(silent: true);
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('Restart failed: $error')));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Operations'),
        actions: <Widget>[
          IconButton(
            onPressed: _configure,
            icon: const Icon(Icons.settings_outlined),
            tooltip: 'Configure Control Agent',
          ),
          IconButton(
            onPressed: _configuration == null ? null : () => _refresh(),
            icon: const Icon(Icons.refresh),
            tooltip: 'Refresh',
          ),
        ],
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_configuration == null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              const Icon(Icons.admin_panel_settings_outlined, size: 64),
              const SizedBox(height: 16),
              const Text(
                'Connect the independent Control Agent to inspect and recover DEV and PROD even when the main backend is down.',
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 20),
              FilledButton.icon(
                onPressed: _configure,
                icon: const Icon(Icons.link),
                label: const Text('Configure connection'),
              ),
            ],
          ),
        ),
      );
    }
    if (_loading && _snapshot == null) {
      return const Center(child: CircularProgressIndicator());
    }
    return RefreshIndicator(
      onRefresh: _refresh,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: <Widget>[
          if (_error != null) _ErrorCard(message: _error!),
          if (_snapshot != null) ...<Widget>[
            _CodexStatusCard(status: _snapshot!.codex),
            const SizedBox(height: 12),
            ..._snapshot!.environments.map(
              (environment) => Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: _EnvironmentCard(
                  environment: environment,
                  action:
                      _actions[environment.name] ?? environment.activeAction,
                  onRestart: () => _restart(environment, force: false),
                  onForceRestart: () => _restart(environment, force: true),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _CodexStatusCard extends StatelessWidget {
  const _CodexStatusCard({required this.status});

  final CodexControlStatus status;

  @override
  Widget build(BuildContext context) {
    final healthy = status.available && status.authenticated;
    return Card(
      child: ListTile(
        leading: Icon(
          healthy ? Icons.check_circle : Icons.error_outline,
          color: healthy ? const Color(0xFF55D6BE) : const Color(0xFFE45B6A),
        ),
        title: const Text('Codex CLI'),
        subtitle: Text(
          <String>[
            status.version ?? 'CLI unavailable',
            status.authenticated
                ? 'Authenticated'
                : 'Authentication unavailable',
            if (status.detail?.isNotEmpty == true) status.detail!,
          ].join(' • '),
        ),
      ),
    );
  }
}

class _EnvironmentCard extends StatelessWidget {
  const _EnvironmentCard({
    required this.environment,
    required this.action,
    required this.onRestart,
    required this.onForceRestart,
  });

  final ControlEnvironmentStatus environment;
  final ControlRestartAction? action;
  final VoidCallback onRestart;
  final VoidCallback onForceRestart;

  @override
  Widget build(BuildContext context) {
    final actionActive = action != null && !action!.isTerminal;
    final color = environment.isHealthy
        ? const Color(0xFF55D6BE)
        : const Color(0xFFE45B6A);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(
              children: <Widget>[
                Icon(Icons.circle, size: 14, color: color),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    environment.displayName,
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                ),
                PopupMenuButton<String>(
                  enabled: !actionActive,
                  tooltip: 'More recovery actions',
                  onSelected: (value) {
                    if (value == 'force') {
                      onForceRestart();
                    }
                  },
                  itemBuilder: (context) => const <PopupMenuEntry<String>>[
                    PopupMenuItem<String>(
                      value: 'force',
                      child: Text('Force restart'),
                    ),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 12),
            _StatusRow(
              label: 'Service',
              value: environment.service.loaded
                  ? '${environment.service.activeState} / ${environment.service.subState}'
                  : 'unit not installed',
            ),
            _StatusRow(
              label: 'Backend',
              value: environment.backendReachable ? 'reachable' : 'unreachable',
            ),
            _StatusRow(
              label: 'Active runs',
              value: environment.activeJobCount?.toString() ?? 'unknown',
            ),
            _StatusRow(
              label: 'Run sessions',
              value: environment.activeSessionCount?.toString() ?? 'unknown',
            ),
            _StatusRow(
              label: 'Submitting',
              value: environment.inFlightMessageCount?.toString() ?? 'unknown',
            ),
            for (final job in environment.activeJobs)
              Padding(
                padding: const EdgeInsets.only(left: 100, bottom: 4),
                child: Text(
                  '${job['phase'] ?? job['status'] ?? 'running'} • ${job['job_id'] ?? 'unknown job'}',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: Color(0xFFFFC857)),
                ),
              ),
            _StatusRow(label: 'URL', value: environment.backendUrl),
            if (action != null) ...<Widget>[
              const SizedBox(height: 12),
              LinearProgressIndicator(value: actionActive ? null : 1),
              const SizedBox(height: 8),
              Text('${action!.stage}: ${action!.detail}'),
            ],
            if (!environment.backendReachable &&
                environment.backendError?.isNotEmpty == true) ...<Widget>[
              const SizedBox(height: 8),
              Text(
                environment.backendError!,
                style: const TextStyle(color: Color(0xFFE8A8B0)),
              ),
            ],
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: actionActive ? null : onRestart,
                icon: const Icon(Icons.restart_alt),
                label: Text(
                  actionActive ? 'Restart in progress' : 'Restart safely',
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _StatusRow extends StatelessWidget {
  const _StatusRow({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          SizedBox(
            width: 100,
            child: Text(
              label,
              style: const TextStyle(color: Color(0xFF8B97B5)),
            ),
          ),
          Expanded(child: Text(value)),
        ],
      ),
    );
  }
}

class _ErrorCard extends StatelessWidget {
  const _ErrorCard({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Card(
      color: const Color(0xFF3B1521),
      child: Padding(padding: const EdgeInsets.all(16), child: Text(message)),
    );
  }
}
