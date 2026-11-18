import 'dart:async';
import 'package:flutter/material.dart';
import '../models/agent_proposal.dart';
import '../services/agent_proposal_client.dart';
import '../services/chat_notification_service.dart';
import '../services/proposal_notification.dart';
import '../state/agent_proposal_controller.dart';

class AgentProposalsButton extends StatefulWidget {
  const AgentProposalsButton(
      {super.key,
      required this.baseUrl,
      required this.notificationService,
      required this.onOpenChat,
      this.clientOverride,
      this.autoStart = true});
  final String baseUrl;
  final ChatNotificationService notificationService;
  final Future<void> Function(String id) onOpenChat;
  final bool autoStart;
  final AgentProposalClient? clientOverride;
  @override
  State<AgentProposalsButton> createState() => _AgentProposalsButtonState();
}

class _AgentProposalsButtonState extends State<AgentProposalsButton>
    with WidgetsBindingObserver {
  late final AgentProposalController _controller;
  StreamSubscription<ProposalNotificationTarget>? _taps;
  bool _opening = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    final service = widget.notificationService;
    final notifications = service is ProposalNotificationService
        ? service as ProposalNotificationService
        : null;
    _controller = AgentProposalController(
        client: widget.clientOverride ??
            AgentProposalClient(baseUrl: widget.baseUrl),
        notifications: notifications);
    _controller.onNewProposal = (proposal, count) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(count == 1
            ? 'Hay una propuesta para revisar.'
            : 'Hay $count propuestas nuevas.'),
        action:
            SnackBarAction(label: 'Abrir', onPressed: () => _open(proposal.id)),
      ));
    };
    _taps = notifications?.proposalTaps.listen((target) {
      if (target.server == widget.baseUrl) {
        notifications.takePendingProposal(widget.baseUrl);
        unawaited(_open(target.id));
      }
    });
    if (widget.autoStart) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        _controller.start();
        final pending = notifications?.takePendingProposal(widget.baseUrl);
        if (pending != null) unawaited(_open(pending.id));
      });
    }
  }

  Future<void> _open(String id) async {
    if (_opening || !mounted) return;
    _opening = true;
    try {
      final proposal = await _controller.open(id);
      if (!mounted) return;
      await Navigator.of(context).push(MaterialPageRoute<void>(
          builder: (_) => AgentProposalDetail(
              controller: _controller,
              initial: proposal,
              onOpenChat: widget.onOpenChat)));
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            content: Text(
                'No se pudo abrir la propuesta. Revisá la bandeja o reintentá.')));
      }
    } finally {
      _opening = false;
    }
  }

  @override
  void didUpdateWidget(covariant AgentProposalsButton oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!oldWidget.autoStart && widget.autoStart) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        _controller.start();
        final pending =
            _controller.notifications?.takePendingProposal(widget.baseUrl);
        if (pending != null) unawaited(_open(pending.id));
      });
    }
    if (oldWidget.autoStart && !widget.autoStart) _controller.pause();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (!widget.autoStart) return;
    if (state == AppLifecycleState.resumed) {
      _controller.start();
    } else {
      _controller.pause();
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    unawaited(_taps?.cancel());
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
      listenable: _controller,
      builder: (context, _) => IconButton(
            tooltip: 'Propuestas del agente',
            icon: Badge(
                isLabelVisible: _controller.unreadCount > 0,
                label: Text('${_controller.unreadCount}'),
                child: const Icon(Icons.notifications_outlined)),
            onPressed: () {
              unawaited(_controller.refresh());
              Navigator.of(context).push(MaterialPageRoute<void>(
                  builder: (_) => AgentProposalInbox(
                      controller: _controller, onOpen: _open)));
            },
          ));
}

class AgentProposalInbox extends StatelessWidget {
  const AgentProposalInbox(
      {super.key, required this.controller, required this.onOpen});
  final AgentProposalController controller;
  final Future<void> Function(String id) onOpen;
  @override
  Widget build(BuildContext context) => ListenableBuilder(
      listenable: controller,
      builder: (context, _) => Scaffold(
            appBar:
                AppBar(title: const Text('Propuestas del agente'), actions: [
              IconButton(
                  tooltip: 'Actualizar propuestas',
                  onPressed: () => controller.refresh(),
                  icon: const Icon(Icons.refresh)),
            ]),
            body: Center(
                child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 760),
              child: RefreshIndicator(
                  onRefresh: controller.refresh,
                  child: ListView(
                      physics: const AlwaysScrollableScrollPhysics(),
                      padding: const EdgeInsets.all(20),
                      children: [
                        if (controller.loading) const LinearProgressIndicator(),
                        if (controller.error != null) ...[
                          Text(controller.error!,
                              style: TextStyle(
                                  color: Theme.of(context).colorScheme.error)),
                          TextButton(
                              onPressed: () => controller.refresh(),
                              child: const Text('Reintentar')),
                        ],
                        if (controller.notificationError != null)
                          Text(controller.notificationError!),
                        if (!controller.loading &&
                            controller.error == null &&
                            controller.items.isEmpty)
                          const Padding(
                              padding: EdgeInsets.symmetric(vertical: 70),
                              child: Column(children: [
                                Icon(Icons.notifications_none, size: 40),
                                SizedBox(height: 16),
                                Text('No hay propuestas nuevas'),
                                SizedBox(height: 8),
                                Text(
                                    'Cuando haya algo útil para revisar, lo vas a encontrar acá.',
                                    textAlign: TextAlign.center),
                              ])),
                        for (final proposal in controller.items)
                          Card(
                              child: ListTile(
                            contentPadding: const EdgeInsets.all(16),
                            title: Text(proposal.title),
                            subtitle: Padding(
                                padding: const EdgeInsets.only(top: 8),
                                child: Text(
                                    '${proposal.workspaceName} · ${proposal.statusLabel}\n${proposal.summary}')),
                            trailing: Icon(
                                proposal.unread
                                    ? Icons.circle
                                    : Icons.chevron_right,
                                size: proposal.unread ? 10 : 24,
                                color: Theme.of(context).colorScheme.primary),
                            onTap: () => onOpen(proposal.id),
                          )),
                        if (controller.hasMore)
                          TextButton(
                              onPressed: () => controller.refresh(more: true),
                              child: const Text('Ver más propuestas')),
                      ])),
            )),
          ));
}

class AgentProposalDetail extends StatefulWidget {
  const AgentProposalDetail(
      {super.key,
      required this.controller,
      required this.initial,
      required this.onOpenChat});
  final AgentProposalController controller;
  final AgentProposal initial;
  final Future<void> Function(String id) onOpenChat;
  @override
  State<AgentProposalDetail> createState() => _AgentProposalDetailState();
}

class _AgentProposalDetailState extends State<AgentProposalDetail> {
  late AgentProposal _proposal = widget.initial;
  String? _error;
  bool _busy = false;

  Future<void> _refresh() async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final updated = await widget.controller.open(_proposal.id);
      if (mounted) {
        setState(() {
          _proposal = updated;
          _error = null;
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() => _error = 'No se pudo actualizar la propuesta.');
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _respond(String action, [String observations = '']) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final updated = await widget.controller
          .decide(_proposal, action, observations: observations);
      if (!mounted) return;
      setState(() => _proposal = updated);
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(updated.statusLabel)));
    } catch (e) {
      if (mounted) {
        setState(() => _error = e is ProposalApiException
            ? e.message
            : 'No se confirmó tu respuesta. Actualizá para comprobar el estado antes de reintentar.');
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _execute() async {
    await _respond('execute');
  }

  Future<void> _observations() async {
    final value = await showDialog<String>(
        context: context,
        builder: (_) =>
            _ProposalObservationsDialog(initial: _proposal.observations));
    if (value != null && mounted) await _respond('observations', value);
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Propuesta'), actions: [
          IconButton(
              tooltip: 'Actualizar propuesta',
              onPressed: _busy ? null : _refresh,
              icon: const Icon(Icons.refresh)),
        ]),
        body: SafeArea(
            child: Center(
                child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 760),
          child: Column(children: [
            Expanded(
                child: ListView(padding: const EdgeInsets.all(20), children: [
              Text('${_proposal.workspaceName} · versión ${_proposal.revision}',
                  style:
                      TextStyle(color: Theme.of(context).colorScheme.primary)),
              const SizedBox(height: 12),
              Text(_proposal.title,
                  style: Theme.of(context).textTheme.headlineSmall),
              const SizedBox(height: 12),
              Text(_proposal.summary),
              _section('Por qué lo propongo', _proposal.rationale),
              _section('Trabajo propuesto', _proposal.kickoff),
              if (_proposal.data['generator_prompt'] != null)
                ExpansionTile(
                  title: const Text('Instrucciones de los agentes'),
                  children: [
                    _section('Generator',
                        _proposal.data['generator_prompt'] as String),
                    _section('Reviewer',
                        _proposal.data['reviewer_prompt'] as String),
                  ],
                ),
              Card(
                  child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Text(
                          'Generator + Reviewer\nHasta ${_proposal.generatorTurns} turnos de Generator '
                          'y ${_proposal.reviewerTurns} de Reviewer.\nUn ciclo acotado; puede terminar antes.'))),
              if (_proposal.evidence.isNotEmpty)
                _section('Evidencias', _proposal.evidence.join('\n\n')),
              if (_proposal.observations.isNotEmpty)
                _section('Tus observaciones', _proposal.observations),
              if (!_proposal.canRespond)
                _section('Estado', _proposal.statusLabel),
              if (_proposal.status == 'needs_revision')
                const Text(
                    'Tus observaciones quedaron guardadas. La próxima versión deberá incorporar los ajustes.'),
              if (_proposal.problem != null)
                _section('Qué pasó', _proposal.problem!),
              if (_error != null)
                Text(_error!,
                    style:
                        TextStyle(color: Theme.of(context).colorScheme.error)),
              if (_proposal.sessionId != null)
                Padding(
                    padding: const EdgeInsets.only(top: 16),
                    child: OutlinedButton.icon(
                        onPressed: () async {
                          final navigator = Navigator.of(context);
                          try {
                            await widget.onOpenChat(_proposal.sessionId!);
                            if (mounted) {
                              navigator.popUntil((route) => route.isFirst);
                            }
                          } catch (_) {
                            if (mounted) {
                              setState(() => _error =
                                  'No se pudo abrir el chat del trabajo.');
                            }
                          }
                        },
                        icon: const Icon(Icons.chat_bubble_outline),
                        label: const Text('Abrir trabajo'))),
            ])),
            if (_proposal.canRespond)
              Padding(
                  padding: const EdgeInsets.fromLTRB(20, 8, 20, 16),
                  child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        const Padding(
                          padding: EdgeInsets.only(bottom: 8),
                          child: Text(
                              'Ejecutar inicia un trabajo real. No incluye publicar ni contactar terceros.',
                              style: TextStyle(fontSize: 12)),
                        ),
                        FilledButton.icon(
                            style: FilledButton.styleFrom(
                                minimumSize: const Size(48, 48)),
                            onPressed: _busy ? null : _execute,
                            icon: const Icon(Icons.play_arrow),
                            label: Text(_busy ? 'Procesando…' : 'Ejecutar')),
                        const SizedBox(height: 8),
                        Wrap(
                            alignment: WrapAlignment.spaceBetween,
                            spacing: 8,
                            runSpacing: 8,
                            children: [
                              TextButton(
                                  onPressed:
                                      _busy ? null : () => _respond('reject'),
                                  child: const Text('Rechazar')),
                              OutlinedButton(
                                  onPressed: _busy ? null : _observations,
                                  child: const Text('Observaciones')),
                            ]),
                      ])),
          ]),
        ))),
      );

  Widget _section(String title, String text) => Padding(
      padding: const EdgeInsets.only(top: 24, bottom: 8),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(title, style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        SelectableText(text),
      ]));
}

class _ProposalObservationsDialog extends StatefulWidget {
  const _ProposalObservationsDialog({required this.initial});
  final String initial;
  @override
  State<_ProposalObservationsDialog> createState() =>
      _ProposalObservationsDialogState();
}

class _ProposalObservationsDialogState
    extends State<_ProposalObservationsDialog> {
  late final _text = TextEditingController(text: widget.initial);
  String? _error;
  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
          scrollable: true,
          title: const Text('Observaciones'),
          content: SizedBox(
              width: 480,
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                const Text(
                    'La propuesta quedará esperando una revisión antes de poder ejecutarse.'),
                const SizedBox(height: 16),
                TextField(
                    controller: _text,
                    onChanged: (_) {
                      if (_error != null) setState(() => _error = null);
                    },
                    minLines: 3,
                    maxLines: 6,
                    maxLength: 2000,
                    decoration: InputDecoration(
                        labelText: 'Tu observación', errorText: _error)),
              ])),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('Cancelar')),
            FilledButton(
                onPressed: () {
                  if (_text.text.trim().isEmpty) {
                    setState(() => _error = 'Escribí una observación.');
                    return;
                  }
                  Navigator.pop(context, _text.text.trim());
                },
                child: const Text('Enviar observaciones')),
          ]);
}
