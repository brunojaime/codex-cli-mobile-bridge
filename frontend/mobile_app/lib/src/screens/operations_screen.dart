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
  DateTime? _lastUpdated;

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
        _lastUpdated = DateTime.now();
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
      text: _configuration?.baseUrl ??
          deriveControlAgentUrl(widget.bridgeBaseUrl),
    );
    final tokenController = TextEditingController(
      text: _configuration?.token ?? '',
    );
    final configuration = await showDialog<ControlAgentConfiguration>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Control Agent connection'),
        content: SingleChildScrollView(
          child: SizedBox(
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
                  decoration: const InputDecoration(
                    labelText: 'Control token',
                    helperText: 'Stored only in this device.',
                    prefixIcon: Icon(Icons.key_outlined),
                  ),
                  obscureText: true,
                  autocorrect: false,
                  enableSuggestions: false,
                ),
              ],
            ),
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
    final confirmed = await showDialog<bool>(
          context: context,
          builder: (context) => AlertDialog(
            icon: Icon(
              force ? Icons.warning_amber_rounded : Icons.restart_alt_rounded,
            ),
            title: Text(
              force
                  ? 'Force restart?'
                  : environment.isHealthy
                      ? 'Restart safely?'
                      : 'Start recovery?',
            ),
            content: Text(
              force
                  ? 'This skips drain and may interrupt $activeJobs active run(s). Use it only when the backend cannot recover normally.'
                  : environment.isHealthy
                      ? 'New runs will be blocked and the restart will wait for $activeJobs active run(s) to finish.'
                      : 'The control agent will start the service and wait until its health check passes.',
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
                child: Text(
                  force
                      ? 'Force restart'
                      : environment.isHealthy
                          ? 'Restart safely'
                          : 'Start recovery',
                ),
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
        title: const Text('Remote operations'),
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
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 520),
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Container(
                  width: 88,
                  height: 88,
                  decoration: BoxDecoration(
                    color: Theme.of(context).colorScheme.primaryContainer,
                    shape: BoxShape.circle,
                  ),
                  child: Icon(
                    Icons.power_settings_new_rounded,
                    size: 42,
                    color: Theme.of(context).colorScheme.onPrimaryContainer,
                  ),
                ),
                const SizedBox(height: 24),
                Text(
                  'Control Batata remotely',
                  style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                        fontWeight: FontWeight.w700,
                      ),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 10),
                Text(
                  'See PROD and DEV status, then recover either service without depending on the main backend.',
                  style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                        color: const Color(0xFFB7C1DD),
                        height: 1.45,
                      ),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 24),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    onPressed: _configure,
                    icon: const Icon(Icons.link_rounded),
                    label: const Text('Connect control agent'),
                  ),
                ),
              ],
            ),
          ),
        ),
      );
    }
    if (_loading && _snapshot == null) {
      return const _OperationsLoadingView();
    }
    return RefreshIndicator(
      onRefresh: _refresh,
      child: LayoutBuilder(
        builder: (context, constraints) => ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
          children: <Widget>[
            Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 720),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: <Widget>[
                    if (_snapshot != null)
                      _OperationsOverview(
                        snapshot: _snapshot!,
                        lastUpdated: _lastUpdated,
                        refreshing: _refreshing,
                      ),
                    if (_error != null) ...<Widget>[
                      const SizedBox(height: 12),
                      _ErrorCard(message: _error!, onRetry: _refresh),
                    ],
                    if (_snapshot != null) ...<Widget>[
                      const SizedBox(height: 12),
                      ..._snapshot!.environments.map(
                        (environment) => Padding(
                          padding: const EdgeInsets.only(bottom: 12),
                          child: _EnvironmentCard(
                            environment: environment,
                            action: _actions[environment.name] ??
                                environment.activeAction,
                            onRestart: () => _restart(
                              environment,
                              force: false,
                            ),
                            onForceRestart: () => _restart(
                              environment,
                              force: true,
                            ),
                          ),
                        ),
                      ),
                      _CodexStatusCard(status: _snapshot!.codex),
                    ],
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _OperationsOverview extends StatelessWidget {
  const _OperationsOverview({
    required this.snapshot,
    required this.lastUpdated,
    required this.refreshing,
  });

  final ControlSnapshot snapshot;
  final DateTime? lastUpdated;
  final bool refreshing;

  @override
  Widget build(BuildContext context) {
    final healthyCount =
        snapshot.environments.where((item) => item.isHealthy).length;
    final allHealthy = healthyCount == snapshot.environments.length;
    final color =
        allHealthy ? const Color(0xFF55D6BE) : const Color(0xFFFFC857);
    final updated = lastUpdated == null
        ? 'Waiting for status'
        : 'Updated ${TimeOfDay.fromDateTime(lastUpdated!).format(context)}';
    return Semantics(
      label: allHealthy
          ? 'All services are online'
          : '$healthyCount of ${snapshot.environments.length} services online',
      child: Container(
        padding: const EdgeInsets.all(18),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.10),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: color.withValues(alpha: 0.30)),
        ),
        child: Row(
          children: <Widget>[
            Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(
                color: color.withValues(alpha: 0.16),
                shape: BoxShape.circle,
              ),
              child: Icon(
                allHealthy
                    ? Icons.cloud_done_rounded
                    : Icons.cloud_sync_rounded,
                color: color,
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    allHealthy ? 'Batata is online' : 'Attention needed',
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    '$healthyCount of ${snapshot.environments.length} services ready  •  $updated',
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: const Color(0xFFB7C1DD),
                        ),
                  ),
                ],
              ),
            ),
            if (refreshing)
              const SizedBox.square(
                dimension: 20,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
          ],
        ),
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
      margin: EdgeInsets.zero,
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
        leading: Icon(
          healthy ? Icons.check_circle : Icons.error_outline,
          color: healthy ? const Color(0xFF55D6BE) : const Color(0xFFE45B6A),
        ),
        title: const Text('Codex CLI access'),
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
    final actionFailed = action?.status == 'failed';
    final color = environment.isHealthy
        ? const Color(0xFF55D6BE)
        : const Color(0xFFE45B6A);
    final statusLabel = actionActive
        ? 'Recovering'
        : environment.isHealthy
            ? 'Online'
            : 'Needs recovery';
    final buttonLabel = actionActive
        ? 'Recovery in progress'
        : environment.isHealthy
            ? 'Restart safely'
            : 'Start / recover';
    return Card(
      margin: EdgeInsets.zero,
      clipBehavior: Clip.antiAlias,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(18),
        side: BorderSide(color: color.withValues(alpha: 0.24)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(
              children: <Widget>[
                Container(
                  width: 42,
                  height: 42,
                  decoration: BoxDecoration(
                    color: color.withValues(alpha: 0.13),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Icon(
                    environment.isHealthy
                        ? Icons.dns_rounded
                        : Icons.power_off_rounded,
                    color: color,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(
                        environment.displayName,
                        style: Theme.of(context).textTheme.titleLarge?.copyWith(
                              fontWeight: FontWeight.w700,
                            ),
                      ),
                      const SizedBox(height: 2),
                      Row(
                        children: <Widget>[
                          Icon(Icons.circle, size: 8, color: color),
                          const SizedBox(width: 6),
                          Text(
                            statusLabel,
                            style: Theme.of(context)
                                .textTheme
                                .labelMedium
                                ?.copyWith(
                                  color: color,
                                  fontWeight: FontWeight.w700,
                                ),
                          ),
                        ],
                      ),
                    ],
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
                      child: Row(
                        children: <Widget>[
                          Icon(Icons.warning_amber_rounded),
                          SizedBox(width: 12),
                          Text('Emergency restart'),
                        ],
                      ),
                    ),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 18),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: <Widget>[
                _MetricTile(
                  icon: Icons.play_circle_outline_rounded,
                  label: 'Active runs',
                  value: environment.activeJobCount?.toString() ?? '—',
                ),
                _MetricTile(
                  icon: Icons.forum_outlined,
                  label: 'Sessions',
                  value: environment.activeSessionCount?.toString() ?? '—',
                ),
                _MetricTile(
                  icon: Icons.upload_rounded,
                  label: 'Submitting',
                  value: environment.inFlightMessageCount?.toString() ?? '—',
                ),
              ],
            ),
            for (final job in environment.activeJobs)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(
                  '${job['phase'] ?? job['status'] ?? 'running'} • ${job['job_id'] ?? 'unknown job'}',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: Color(0xFFFFC857)),
                ),
              ),
            if (action != null) ...<Widget>[
              const SizedBox(height: 16),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: (actionFailed ? const Color(0xFFE45B6A) : color)
                      .withValues(alpha: 0.09),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    if (actionActive) const LinearProgressIndicator(),
                    if (actionActive) const SizedBox(height: 10),
                    Text(
                      actionFailed
                          ? 'Recovery failed'
                          : _stageLabel(action!.stage),
                      style: const TextStyle(fontWeight: FontWeight.w700),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      action!.detail,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: const Color(0xFFB7C1DD),
                          ),
                    ),
                  ],
                ),
              ),
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
                style: FilledButton.styleFrom(
                  minimumSize: const Size.fromHeight(52),
                  backgroundColor:
                      environment.isHealthy ? null : const Color(0xFFD97706),
                ),
                icon: Icon(
                  actionActive
                      ? Icons.sync_rounded
                      : environment.isHealthy
                          ? Icons.restart_alt_rounded
                          : Icons.power_settings_new_rounded,
                ),
                label: Text(buttonLabel),
              ),
            ),
            const SizedBox(height: 10),
            ExpansionTile(
              tilePadding: EdgeInsets.zero,
              childrenPadding: EdgeInsets.zero,
              visualDensity: VisualDensity.compact,
              title: const Text('Technical details'),
              children: <Widget>[
                _StatusRow(
                  label: 'Service',
                  value: environment.service.loaded
                      ? '${environment.service.activeState} / ${environment.service.subState}'
                      : 'unit not installed',
                ),
                _StatusRow(
                  label: 'Backend',
                  value: environment.backendReachable
                      ? 'reachable'
                      : 'unreachable',
                ),
                _StatusRow(label: 'URL', value: environment.backendUrl),
              ],
            ),
          ],
        ),
      ),
    );
  }

  String _stageLabel(String stage) {
    return switch (stage) {
      'queued' => 'Recovery queued',
      'checking_backend' => 'Checking service',
      'draining' => 'Waiting for active runs',
      'restarting_service' => 'Restarting service',
      'waiting_for_health' => 'Waiting for health check',
      'healthy' => 'Service recovered',
      _ => stage.replaceAll('_', ' '),
    };
  }
}

class _MetricTile extends StatelessWidget {
  const _MetricTile({
    required this.icon,
    required this.label,
    required this.value,
  });

  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(minWidth: 116),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: const Color(0xFF0F172A),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(icon, size: 18, color: const Color(0xFF8B97B5)),
          const SizedBox(width: 8),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(
                value,
                style: const TextStyle(fontWeight: FontWeight.w700),
              ),
              Text(
                label,
                style: Theme.of(context).textTheme.labelSmall?.copyWith(
                      color: const Color(0xFF8B97B5),
                    ),
              ),
            ],
          ),
        ],
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
  const _ErrorCard({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Card(
      color: const Color(0xFF3B1521),
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            const Icon(Icons.cloud_off_rounded, color: Color(0xFFFFA6B2)),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  const Text(
                    'Control connection unavailable',
                    style: TextStyle(fontWeight: FontWeight.w700),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    message,
                    maxLines: 3,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(color: Color(0xFFFFC7CE)),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 8),
            TextButton(onPressed: onRetry, child: const Text('Retry')),
          ],
        ),
      ),
    );
  }
}

class _OperationsLoadingView extends StatelessWidget {
  const _OperationsLoadingView();

  @override
  Widget build(BuildContext context) {
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
      children: <Widget>[
        Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 720),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                Container(
                  height: 84,
                  decoration: BoxDecoration(
                    color: const Color(0xFF141C33),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: const Center(
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: <Widget>[
                        SizedBox.square(
                          dimension: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        ),
                        SizedBox(width: 12),
                        Text('Checking Batata services…'),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                for (var index = 0; index < 2; index++) ...<Widget>[
                  Container(
                    height: 238,
                    decoration: BoxDecoration(
                      color: const Color(0xFF141C33),
                      borderRadius: BorderRadius.circular(18),
                    ),
                  ),
                  const SizedBox(height: 12),
                ],
              ],
            ),
          ),
        ),
      ],
    );
  }
}
