import 'package:flutter/material.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';

import '../models/run_overview.dart';

const _card = Color(0xFF1B2440);
const _border = Color(0xFF3A3420);
const _amber = Color(0xFFFFC857);
const _text = Color(0xFFDCE5FF);
const _muted = Color(0xFF8B97B5);
const _code = Color(0xFF0D1428);

typedef InteractionDecider = Future<bool> Function(InteractionDecision decision);

/// A request from the agent that blocks it until the user answers.
///
/// Mirrors the CLI choices: allow once / don't ask again / deny with a note
/// for tools, option picking (+ free text) for questions, and approve-with-mode
/// or keep planning for plans.
class InteractionCard extends StatefulWidget {
  const InteractionCard({
    super.key,
    required this.interaction,
    required this.onDecide,
    this.busy = false,
    this.dense = false,
  });

  final PendingInteraction interaction;
  final InteractionDecider onDecide;
  final bool busy;

  /// Compact layout for the dashboard.
  final bool dense;

  @override
  State<InteractionCard> createState() => _InteractionCardState();
}

class _InteractionCardState extends State<InteractionCard> {
  final Map<String, Set<String>> _picked = <String, Set<String>>{};
  final Map<String, TextEditingController> _other =
      <String, TextEditingController>{};
  final TextEditingController _note = TextEditingController();
  bool _writingNote = false;
  bool _sending = false;
  bool _expanded = false;

  @override
  void dispose() {
    for (final controller in _other.values) {
      controller.dispose();
    }
    _note.dispose();
    super.dispose();
  }

  bool get _busy => widget.busy || _sending;

  Future<void> _decide(InteractionDecision decision) async {
    if (_busy) return;
    setState(() => _sending = true);
    try {
      await widget.onDecide(decision);
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  TextEditingController _otherFor(String question) =>
      _other.putIfAbsent(question, () {
        final controller = TextEditingController();
        controller.addListener(() => setState(() {}));
        return controller;
      });

  Map<String, String>? _answers() {
    final answers = <String, String>{};
    for (final question in widget.interaction.questions) {
      final values = <String>[
        ...?_picked[question.question],
        if (_otherFor(question.question).text.trim().isNotEmpty)
          _otherFor(question.question).text.trim(),
      ];
      if (values.isEmpty) return null;
      answers[question.question] = values.join(', ');
    }
    return answers.isEmpty ? null : answers;
  }

  @override
  Widget build(BuildContext context) {
    final interaction = widget.interaction;
    final (icon, label) = interaction.isQuestion
        ? (Icons.help_outline_rounded, 'Te pregunta')
        : interaction.isPlan
            ? (Icons.map_outlined, 'Propone un plan')
            : (Icons.shield_outlined, 'Necesita tu permiso');
    return Semantics(
      container: true,
      label: '$label: ${interaction.title}',
      child: Container(
        padding: EdgeInsets.all(widget.dense ? 12 : 14),
        decoration: BoxDecoration(
          color: _card,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: _border),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(
              children: <Widget>[
                Icon(icon, size: 18, color: _amber),
                const SizedBox(width: 8),
                Text(label,
                    style: const TextStyle(
                        color: _amber,
                        fontWeight: FontWeight.w700,
                        fontSize: 13)),
              ],
            ),
            const SizedBox(height: 8),
            if (interaction.isQuestion)
              ..._buildQuestions()
            else if (interaction.isPlan)
              ..._buildPlan()
            else
              ..._buildPermission(),
            if (_writingNote) ...<Widget>[
              const SizedBox(height: 10),
              TextField(
                controller: _note,
                autofocus: true,
                minLines: 1,
                maxLines: 4,
                textInputAction: TextInputAction.send,
                onSubmitted: (_) => _sendNote(),
                decoration: InputDecoration(
                  isDense: true,
                  hintText: interaction.isPlan
                      ? '¿Qué cambiarías del plan?'
                      : '¿Qué debería hacer en cambio? (opcional)',
                ),
              ),
              const SizedBox(height: 8),
              Wrap(spacing: 8, runSpacing: 8, children: <Widget>[
                FilledButton(
                  onPressed: _busy ? null : _sendNote,
                  child: Text(interaction.isPlan ? 'Enviar cambios' : 'Rechazar'),
                ),
                TextButton(
                  onPressed: _busy ? null : () => setState(() => _writingNote = false),
                  child: const Text('Volver'),
                ),
              ]),
            ],
            if (_busy)
              const Padding(
                padding: EdgeInsets.only(top: 10),
                child: LinearProgressIndicator(minHeight: 2),
              ),
          ],
        ),
      ),
    );
  }

  void _sendNote() {
    _decide(InteractionDecision.deny(message: _note.text.trim()));
  }

  Widget _codeBox(String text) {
    final lines = text.split('\n');
    final long = lines.length > 8 || text.length > 600;
    final shown = !long || _expanded
        ? text
        : '${lines.take(8).join('\n').characters.take(600)}…';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(
            color: _code,
            borderRadius: BorderRadius.circular(10),
          ),
          child: SelectableText(
            shown,
            style: const TextStyle(
                fontFamily: 'monospace', fontSize: 12.5, color: _text, height: 1.35),
          ),
        ),
        if (long)
          TextButton(
            onPressed: () => setState(() => _expanded = !_expanded),
            child: Text(_expanded ? 'Ver menos' : 'Ver todo'),
          ),
      ],
    );
  }

  List<Widget> _buildPermission() {
    final interaction = widget.interaction;
    final tool = interaction.toolName ?? 'herramienta';
    final what = switch (tool) {
      'Bash' => 'Quiere ejecutar este comando',
      'Edit' || 'MultiEdit' || 'Write' || 'NotebookEdit' =>
        'Quiere modificar este archivo',
      'WebFetch' => 'Quiere abrir esta página',
      'WebSearch' => 'Quiere buscar en la web',
      _ => 'Quiere usar $tool',
    };
    final description = (interaction.input['description'] ?? '').toString();
    return <Widget>[
      Text(what,
          style: const TextStyle(
              color: _text, fontWeight: FontWeight.w600, fontSize: 15)),
      if (description.isNotEmpty) ...<Widget>[
        const SizedBox(height: 2),
        Text(description, style: const TextStyle(color: _muted, fontSize: 13)),
      ],
      if (interaction.detail.trim().isNotEmpty) ...<Widget>[
        const SizedBox(height: 8),
        _codeBox(interaction.detail.trim()),
      ],
      if (!_writingNote) ...<Widget>[
        const SizedBox(height: 10),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: <Widget>[
            FilledButton.icon(
              onPressed: _busy
                  ? null
                  : () => _decide(const InteractionDecision.allow()),
              icon: const Icon(Icons.check_rounded, size: 18),
              label: const Text('Permitir'),
            ),
            if (interaction.canRemember)
              Tooltip(
                message: 'Permitir y no volver a preguntar por esto en este proyecto',
                child: FilledButton.tonal(
                  onPressed: _busy
                      ? null
                      : () => _decide(
                          const InteractionDecision.allow(remember: true)),
                  child: const Text('Permitir siempre'),
                ),
              ),
            OutlinedButton(
              onPressed:
                  _busy ? null : () => setState(() => _writingNote = true),
              child: const Text('Rechazar…'),
            ),
          ],
        ),
      ],
    ];
  }

  List<Widget> _buildQuestions() {
    final questions = widget.interaction.questions;
    final answers = _answers();
    return <Widget>[
      for (final question in questions) ...<Widget>[
        if (question.header.isNotEmpty && question.header != question.question)
          Padding(
            padding: const EdgeInsets.only(bottom: 4),
            child: Text(question.header.toUpperCase(),
                style: const TextStyle(
                    color: _muted, fontSize: 11, letterSpacing: .6)),
          ),
        Text(question.question,
            style: const TextStyle(
                color: _text, fontWeight: FontWeight.w600, fontSize: 15)),
        if (question.multiSelect)
          const Text('Podés elegir varias',
              style: TextStyle(color: _muted, fontSize: 12)),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: <Widget>[
            for (final option in question.options)
              Tooltip(
                message: option.description,
                child: ChoiceChip(
                  label: Text(option.label),
                  selected:
                      _picked[question.question]?.contains(option.label) ?? false,
                  onSelected: _busy
                      ? null
                      : (selected) => setState(() {
                            final set = _picked.putIfAbsent(
                                question.question, () => <String>{});
                            if (!question.multiSelect) set.clear();
                            if (selected) {
                              set.add(option.label);
                            } else {
                              set.remove(option.label);
                            }
                          }),
                ),
              ),
          ],
        ),
        const SizedBox(height: 8),
        TextField(
          controller: _otherFor(question.question),
          minLines: 1,
          maxLines: 3,
          decoration: const InputDecoration(
              isDense: true, hintText: 'Otra respuesta (opcional)'),
        ),
        const SizedBox(height: 12),
      ],
      Wrap(spacing: 8, runSpacing: 8, children: <Widget>[
        FilledButton.icon(
          onPressed: _busy || answers == null
              ? null
              : () => _decide(InteractionDecision.answer(answers)),
          icon: const Icon(Icons.send_rounded, size: 18),
          label: const Text('Responder'),
        ),
        TextButton(
          onPressed:
              _busy ? null : () => _decide(const InteractionDecision.deny()),
          child: const Text('No responder'),
        ),
      ]),
    ];
  }

  List<Widget> _buildPlan() {
    return <Widget>[
      ConstrainedBox(
        constraints: BoxConstraints(maxHeight: widget.dense ? 220 : 360),
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(
              color: _code, borderRadius: BorderRadius.circular(10)),
          child: SingleChildScrollView(
            child: MarkdownBody(
              data: widget.interaction.plan,
              selectable: true,
              styleSheet: MarkdownStyleSheet.fromTheme(Theme.of(context))
                  .copyWith(p: const TextStyle(color: _text, height: 1.4)),
            ),
          ),
        ),
      ),
      if (!_writingNote) ...<Widget>[
        const SizedBox(height: 10),
        Wrap(spacing: 8, runSpacing: 8, children: <Widget>[
          Tooltip(
            message: 'Aprueba el plan y deja que edite archivos sin preguntar',
            child: FilledButton.icon(
              onPressed: _busy
                  ? null
                  : () => _decide(
                      const InteractionDecision.approvePlan('acceptEdits')),
              icon: const Icon(Icons.check_rounded, size: 18),
              label: const Text('Aprobar'),
            ),
          ),
          FilledButton.tonal(
            onPressed: _busy
                ? null
                : () =>
                    _decide(const InteractionDecision.approvePlan('default')),
            child: const Text('Aprobar y preguntarme cada cambio'),
          ),
          OutlinedButton(
            onPressed: _busy ? null : () => setState(() => _writingNote = true),
            child: const Text('Seguir planificando…'),
          ),
        ]),
      ],
    ];
  }
}
