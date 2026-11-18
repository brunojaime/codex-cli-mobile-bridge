import 'dart:async';

import 'package:flutter/material.dart';

import '../state/proactive_mock_controller.dart';

const _proposalTitle = 'Retomar una tarea desde la notificación';
const _proposalSummary =
    'Abrir una propuesta con su contexto y decidir qué hacer, '
    'sin tener que buscar la conversación del proyecto.';

class ProactiveProposalsButton extends StatefulWidget {
  const ProactiveProposalsButton({super.key});

  @override
  State<ProactiveProposalsButton> createState() =>
      _ProactiveProposalsButtonState();
}

class _ProactiveProposalsButtonState extends State<ProactiveProposalsButton> {
  final _controller = ProactiveMockController();

  @override
  void initState() {
    super.initState();
    unawaited(_controller.load());
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
        listenable: _controller,
        builder: (context, _) => IconButton(
          tooltip: _controller.unread
              ? 'Propuestas del agente: 1 nueva'
              : 'Propuestas del agente',
          icon: Badge(
            isLabelVisible: _controller.unread,
            label: const Text('1'),
            child: const Icon(Icons.notifications_outlined),
          ),
          onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(
            builder: (_) => ProactiveProposalsScreen(controller: _controller),
          )),
        ),
      );
}

class ProactiveProposalsScreen extends StatelessWidget {
  const ProactiveProposalsScreen({super.key, required this.controller});

  final ProactiveMockController controller;

  Future<void> _simulate(BuildContext context) async {
    if (!await controller.simulateArrival() || !context.mounted) return;
    final messenger = ScaffoldMessenger.of(context);
    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(SnackBar(
      behavior: SnackBarBehavior.floating,
      duration: const Duration(seconds: 8),
      content: const Text('Nueva propuesta · Codex Mobile\n$_proposalTitle'),
      action: SnackBarAction(
        label: 'Abrir',
        onPressed: () => _openProposal(context),
      ),
    ));
  }

  void _openProposal(BuildContext context) {
    ScaffoldMessenger.of(context).hideCurrentSnackBar();
    unawaited(controller.markRead());
    Navigator.of(context).push(MaterialPageRoute<void>(
      builder: (_) => ProactiveProposalDetail(controller: controller),
    ));
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
        listenable: controller,
        builder: (context, _) => Scaffold(
          appBar: AppBar(title: const Text('Propuestas del agente')),
          body: SafeArea(
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 760),
                child: ListView(
                  padding: const EdgeInsets.all(20),
                  children: [
                    const _DemoNotice(),
                    const SizedBox(height: 28),
                    Text('Una idea que merece tu atención',
                        style: Theme.of(context).textTheme.headlineSmall),
                    const SizedBox(height: 8),
                    const Text(
                      'El agente te propone. Vos decidís cómo seguir.',
                    ),
                    const SizedBox(height: 24),
                    if (controller.loading)
                      const Center(child: CircularProgressIndicator())
                    else if (controller.error != null)
                      _StorageError(controller: controller)
                    else if (!controller.hasProposal)
                      const _EmptyInbox()
                    else
                      Card(
                        margin: EdgeInsets.zero,
                        clipBehavior: Clip.antiAlias,
                        child: InkWell(
                          key: const ValueKey('proactive-proposal-card'),
                          onTap: () => _openProposal(context),
                          child: Padding(
                            padding: const EdgeInsets.all(20),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Wrap(
                                  spacing: 8,
                                  runSpacing: 8,
                                  crossAxisAlignment: WrapCrossAlignment.center,
                                  children: [
                                    const Text('Codex Mobile',
                                        style: TextStyle(
                                            fontWeight: FontWeight.w600)),
                                    _StatusLabel(label: controller.status),
                                    if (controller.unread)
                                      const _StatusLabel(label: 'Nueva'),
                                  ],
                                ),
                                const SizedBox(height: 16),
                                Text(_proposalTitle,
                                    style:
                                        Theme.of(context).textTheme.titleLarge),
                                const SizedBox(height: 10),
                                const Text(_proposalSummary),
                                const SizedBox(height: 20),
                                const Text(
                                    'Generator + Reviewer · hasta 2 tandas'),
                                const SizedBox(height: 16),
                                Row(children: [
                                  Icon(Icons.arrow_forward_rounded,
                                      color: Theme.of(context)
                                          .colorScheme
                                          .primary),
                                  const SizedBox(width: 8),
                                  const Text('Ver propuesta'),
                                ]),
                              ],
                            ),
                          ),
                        ),
                      ),
                    const SizedBox(height: 24),
                    OutlinedButton.icon(
                      style: OutlinedButton.styleFrom(
                        minimumSize: const Size(48, 48),
                      ),
                      key: const ValueKey('simulate-proactive-notification'),
                      onPressed: controller.loading || controller.saving
                          ? null
                          : () => _simulate(context),
                      icon: const Icon(Icons.notification_add_outlined),
                      label: Text(controller.hasProposal
                          ? 'Volver a simular notificación'
                          : 'Simular notificación'),
                    ),
                    const SizedBox(height: 8),
                    const Text(
                      'La simulación crea un ejemplo nuevo y reinicia su respuesta. '
                      'Sólo se muestra dentro de la app.',
                      style: TextStyle(fontSize: 12),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      );
}

class ProactiveProposalDetail extends StatelessWidget {
  const ProactiveProposalDetail({super.key, required this.controller});
  final ProactiveMockController controller;

  Future<void> _observe(BuildContext context) async {
    await showDialog<void>(
      context: context,
      builder: (_) => _ObservationsDialog(controller: controller),
    );
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
        listenable: controller,
        builder: (context, _) {
          final pending = controller.decision == MockProposalDecision.pending;
          return Scaffold(
            appBar: AppBar(title: const Text('Propuesta')),
            body: SafeArea(
              child: Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 760),
                  child: Column(children: [
                    Expanded(
                      child: ListView(
                        padding: const EdgeInsets.all(20),
                        children: [
                          const _DemoNotice(),
                          const SizedBox(height: 24),
                          Wrap(spacing: 8, runSpacing: 8, children: [
                            const _StatusLabel(label: 'Codex Mobile'),
                            _StatusLabel(label: controller.status),
                          ]),
                          const SizedBox(height: 16),
                          Text(_proposalTitle,
                              style: Theme.of(context)
                                  .textTheme
                                  .headlineSmall
                                  ?.copyWith(fontWeight: FontWeight.w600)),
                          const SizedBox(height: 12),
                          const Text(_proposalSummary),
                          const SizedBox(height: 28),
                          const _DetailSection(
                            title: 'Por qué lo propongo',
                            body:
                                'Una notificación con contexto y acciones podría '
                                'reducir los pasos entre una idea y una decisión. '
                                'Este hallazgo es un ejemplo para probar el recorrido.',
                          ),
                          const _DetailSection(
                            title: 'Qué haríamos',
                            body:
                                'Mostrar la propuesta, permitir responder desde '
                                'el teléfono y conservar la decisión al volver a abrirla.',
                          ),
                          Card(
                            margin: EdgeInsets.zero,
                            child: Padding(
                              padding: const EdgeInsets.all(16),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  const Icon(Icons.account_tree_outlined),
                                  const SizedBox(height: 12),
                                  Text('Generator + Reviewer',
                                      style: Theme.of(context)
                                          .textTheme
                                          .titleMedium),
                                  const SizedBox(height: 8),
                                  const Text(
                                      'Hasta 2 tandas. Por tanda: hasta 3 turnos '
                                      'de Generator y 2 de Reviewer.'),
                                  const SizedBox(height: 8),
                                  const Text(
                                      'La segunda tanda sólo si la revisión '
                                      'encuentra algo que corregir.'),
                                ],
                              ),
                            ),
                          ),
                          const SizedBox(height: 24),
                          if (controller.observations.isNotEmpty)
                            _DetailSection(
                              title: 'Tus observaciones',
                              body: controller.observations,
                            ),
                          if (!pending) _DecisionResult(controller: controller),
                          if (controller.error != null)
                            _StorageError(controller: controller),
                        ],
                      ),
                    ),
                    if (pending)
                      Padding(
                        padding: const EdgeInsets.fromLTRB(20, 12, 20, 16),
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            const Text(
                                'Prueba: no se iniciarán agentes reales.',
                                style: TextStyle(fontSize: 12)),
                            const SizedBox(height: 10),
                            FilledButton.icon(
                              style: FilledButton.styleFrom(
                                minimumSize: const Size(48, 48),
                              ),
                              key: const ValueKey('execute-proactive-proposal'),
                              onPressed: controller.saving
                                  ? null
                                  : () => controller
                                      .respond(MockProposalDecision.execute),
                              icon: const Icon(Icons.play_arrow_rounded),
                              label: const Text('Ejecutar'),
                            ),
                            const SizedBox(height: 8),
                            Wrap(
                              spacing: 12,
                              runSpacing: 8,
                              alignment: WrapAlignment.spaceBetween,
                              children: [
                                TextButton.icon(
                                  style: TextButton.styleFrom(
                                    minimumSize: const Size(48, 48),
                                  ),
                                  key: const ValueKey(
                                      'reject-proactive-proposal'),
                                  onPressed: controller.saving
                                      ? null
                                      : () => controller
                                          .respond(MockProposalDecision.reject),
                                  icon: const Icon(Icons.close_rounded),
                                  label: const Text('Rechazar'),
                                ),
                                OutlinedButton.icon(
                                  style: OutlinedButton.styleFrom(
                                    minimumSize: const Size(48, 48),
                                  ),
                                  onPressed: controller.saving
                                      ? null
                                      : () => _observe(context),
                                  icon: const Icon(Icons.edit_note_outlined),
                                  label: const Text('Observaciones'),
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),
                  ]),
                ),
              ),
            ),
          );
        },
      );
}

class _ObservationsDialog extends StatefulWidget {
  const _ObservationsDialog({required this.controller});
  final ProactiveMockController controller;

  @override
  State<_ObservationsDialog> createState() => _ObservationsDialogState();
}

class _ObservationsDialogState extends State<_ObservationsDialog> {
  late final _text =
      TextEditingController(text: widget.controller.observations);
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (_text.text.trim().isEmpty) {
      setState(() => _error = 'Escribí una observación antes de guardar.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    final saved = await widget.controller.saveObservations(_text.text);
    if (!mounted) return;
    if (saved) {
      Navigator.of(context).pop();
    } else {
      setState(() {
        _saving = false;
        _error = 'No se pudo guardar. Reintentá.';
      });
    }
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        scrollable: true,
        title: const Text('Observaciones'),
        content: SizedBox(
          width: 480,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('Contale al agente qué ajustarías antes de avanzar.'),
              const SizedBox(height: 16),
              TextField(
                key: const ValueKey('proactive-observations-input'),
                controller: _text,
                autofocus: true,
                minLines: 3,
                maxLines: 6,
                maxLength: 2000,
                enabled: !_saving,
                decoration: InputDecoration(
                  labelText: 'Tu observación',
                  alignLabelWithHint: true,
                  hintText: 'Por ejemplo: primero revisemos el alcance.',
                  errorText: _error,
                ),
              ),
              const SizedBox(height: 8),
              const Text('Se guarda en esta prueba; no se envía a un agente.',
                  style: TextStyle(fontSize: 12)),
            ],
          ),
        ),
        actions: [
          TextButton(
            style: TextButton.styleFrom(minimumSize: const Size(48, 48)),
            onPressed: _saving ? null : () => Navigator.of(context).pop(),
            child: const Text('Cancelar'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(minimumSize: const Size(48, 48)),
            onPressed: _saving ? null : _save,
            child: Text(_saving ? 'Guardando…' : 'Guardar observaciones'),
          ),
        ],
      );
}

class _DemoNotice extends StatelessWidget {
  const _DemoNotice();

  @override
  Widget build(BuildContext context) => Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.science_outlined,
              size: 20, color: Theme.of(context).colorScheme.primary),
          const SizedBox(width: 10),
          const Expanded(
              child: Text(
            'Vista de prueba · propuestas y ejecuciones simuladas',
            style: TextStyle(fontSize: 13),
          )),
        ],
      );
}

class _StatusLabel extends StatelessWidget {
  const _StatusLabel({required this.label});
  final String label;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(8),
        ),
        child: Text(label, style: const TextStyle(fontSize: 12)),
      );
}

class _DetailSection extends StatelessWidget {
  const _DetailSection({required this.title, required this.body});
  final String title;
  final String body;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            Text(body),
          ],
        ),
      );
}

class _EmptyInbox extends StatelessWidget {
  const _EmptyInbox();

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 36),
        child: Column(children: [
          Icon(Icons.notifications_none_rounded,
              size: 40, color: Theme.of(context).colorScheme.primary),
          const SizedBox(height: 16),
          Text('No hay propuestas nuevas',
              style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          const Text(
              'Si no hay nada útil para proponer, el agente guarda silencio.',
              textAlign: TextAlign.center),
        ]),
      );
}

class _DecisionResult extends StatelessWidget {
  const _DecisionResult({required this.controller});
  final ProactiveMockController controller;

  @override
  Widget build(BuildContext context) => Semantics(
        liveRegion: true,
        child: _DetailSection(
          title: controller.status,
          body: controller.decision == MockProposalDecision.execute
              ? 'Tu decisión quedó guardada. En el flujo real se abriría el '
                  'trabajo con Generator y Reviewer. En esta prueba no se inició ningún agente.'
              : 'La propuesta quedó rechazada en esta prueba. Podés volver '
                  'a simular una notificación desde la bandeja.',
        ),
      );
}

class _StorageError extends StatelessWidget {
  const _StorageError({required this.controller});
  final ProactiveMockController controller;

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(controller.error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error)),
          if (!controller.hasProposal)
            TextButton(
                onPressed: controller.load, child: const Text('Reintentar')),
        ],
      );
}
