import 'dart:async';
import 'package:flutter/material.dart';
import '../services/objective_team_client.dart';

const _labels = {
  'planning': 'Definiendo alcance',
  'executing': 'En construcción',
  'final_review': 'Revisión final',
  'completed': 'Completado',
  'needs_attention': 'Necesita atención',
  'paused': 'En pausa',
  'blocked': 'Bloqueado',
  'accepted': 'Aceptado',
  'pending': 'Pendiente',
  'implementing': 'Implementando',
  'implemented': 'Implementado',
  'reviewing': 'En revisión',
  'running': 'Trabajando',
  'generator': 'Generator',
  'ux': 'UX',
  'ux_review': 'Revisión UX',
  'reviewer': 'Reviewer',
  'requirements': 'Requisitos',
  'security': 'Seguridad',
  'recovery': 'Recuperación',
  'resolved': 'Resuelto',
  'open': 'Abierto',
  'pass': 'Aprobado',
  'changes': 'Cambios pedidos',
  'failed': 'Falló',
};
String _label(dynamic value) => _labels[value] ?? '${value ?? 'Pendiente'}';
List<Map<String, dynamic>> _rows(dynamic value) =>
    (value as List? ?? []).whereType<Map<String, dynamic>>().toList();

class ObjectiveTeamScreen extends StatefulWidget {
  const ObjectiveTeamScreen({super.key, required this.client, this.onOpenChat});
  final ObjectiveTeamClient client;
  final Future<void> Function(String)? onOpenChat;
  @override
  State<ObjectiveTeamScreen> createState() => _ObjectiveTeamScreenState();
}

class _ObjectiveTeamScreenState extends State<ObjectiveTeamScreen>
    with WidgetsBindingObserver {
  Map<String, dynamic>? _data;
  String? _selected;
  String? _error;
  bool _loading = false;
  int _tab = 0;
  Timer? _timer;
  DateTime? _received;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _start();
  }

  void _start() {
    _timer ??= Timer.periodic(const Duration(seconds: 10), (_) => _refresh());
    unawaited(_refresh());
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _start();
    } else {
      _timer?.cancel();
      _timer = null;
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _refresh() async {
    if (_loading) return;
    final selected = _selected;
    setState(() => _loading = true);
    try {
      final data =
          await widget.client.get(selected == null ? '' : '/$selected');
      if (mounted && selected == _selected) {
        setState(() {
          _data = data;
          _error = null;
          _received = DateTime.now();
        });
      }
    } catch (_) {
      if (mounted && selected == _selected) {
        setState(() => _error =
            'Sin conexión al equipo. Los datos anteriores pueden estar desactualizados.');
      }
    } finally {
      if (mounted) {
        setState(() => _loading = false);
        if (selected != _selected) unawaited(_refresh());
      }
    }
  }

  void _select(String? id) {
    setState(() {
      _selected = id;
      _data = null;
      _error = null;
      _received = null;
      _tab = 0;
    });
    unawaited(_refresh());
  }

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Equipo por objetivos'),
        actions: [
          IconButton(
              tooltip: 'Actualizar',
              onPressed: _loading ? null : _refresh,
              icon: const Icon(Icons.refresh_rounded))
        ],
      ),
      body: Center(
          child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 1120),
              child: Column(children: [
                if (_loading) const LinearProgressIndicator(minHeight: 2),
                if (_error != null)
                  Material(
                      color: colors.errorContainer,
                      child: ListTile(
                          leading: const Icon(Icons.cloud_off_outlined),
                          title: Text(_error!),
                          trailing: IconButton(
                              tooltip: 'Reintentar',
                              onPressed: _refresh,
                              icon: const Icon(Icons.refresh)))),
                Expanded(
                    child: RefreshIndicator(
                        onRefresh: _refresh,
                        child: ListView(
                            physics: const AlwaysScrollableScrollPhysics(),
                            padding: const EdgeInsets.all(20),
                            children: [
                              if (_selected != null)
                                Align(
                                    alignment: Alignment.centerLeft,
                                    child: TextButton.icon(
                                        onPressed: () => _select(null),
                                        icon: const Icon(Icons.arrow_back),
                                        label: const Text(
                                            'Todas las ejecuciones'))),
                              if (_data != null && _selected == null)
                                ..._overview(),
                              if (_data != null && _selected != null)
                                ..._detail(_data!),
                              if (_data == null && _loading)
                                const Padding(
                                    padding: EdgeInsets.all(40),
                                    child: Center(
                                        child: Text('Consultando el equipo…'))),
                              if (_received != null)
                                Padding(
                                    padding: const EdgeInsets.only(top: 24),
                                    child: Text(
                                        'Consulta ${TimeOfDay.fromDateTime(_received!).format(context)} · Se actualiza cada 10 s',
                                        style: Theme.of(context)
                                            .textTheme
                                            .bodySmall)),
                            ]))),
              ]))),
    );
  }

  List<Widget> _overview() {
    final runs = _rows(_data!['runs']);
    final active = runs.where((r) => r['status'] != 'completed').length;
    return [
      Text('Del objetivo al resultado.',
          style: Theme.of(context)
              .textTheme
              .headlineLarge
              ?.copyWith(fontWeight: FontWeight.w800)),
      const SizedBox(height: 8),
      Text('$active en curso · ${runs.length} ejecuciones',
          style: Theme.of(context).textTheme.titleMedium),
      const SizedBox(height: 24),
      if ((_data!['unavailable'] as num? ?? 0) > 0 ||
          _data!['truncated'] == true)
        const Text(
            'Hay registros que no se pudieron incluir. La lista puede estar incompleta.'),
      if (runs.isEmpty)
        const Padding(
            padding: EdgeInsets.symmetric(vertical: 56),
            child: Column(children: [
              Icon(Icons.hub_outlined, size: 56),
              SizedBox(height: 16),
              Text('Todavía no hay ejecuciones por objetivos.'),
              SizedBox(height: 8),
              Text(
                  'Creá el encargo desde el chat de Code. Los ciclos anteriores no aparecen aquí.',
                  textAlign: TextAlign.center)
            ])),
      for (final run in runs)
        Padding(
            padding: const EdgeInsets.only(bottom: 14),
            child: Semantics(
                key: ValueKey('objective-run-${run['id']}'),
                container: true,
                button: true,
                excludeSemantics: true,
                label:
                    'Abrir ejecución: ${run['project']}. ${run['objective']}. ${_label(run['status'])}. ${run['accepted_units']} de ${run['total_units']} incrementos aceptados.',
                onTap: () => _select(run['id'] as String),
                child: Card(
                    clipBehavior: Clip.antiAlias,
                    child: InkWell(
                        onTap: () => _select(run['id'] as String),
                        child: Padding(
                            padding: const EdgeInsets.all(20),
                            child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Wrap(
                                      spacing: 12,
                                      runSpacing: 8,
                                      crossAxisAlignment:
                                          WrapCrossAlignment.center,
                                      children: [
                                        Text('${run['project']}',
                                            style: Theme.of(context)
                                                .textTheme
                                                .titleLarge),
                                        _badge(_label(run['status']))
                                      ]),
                                  const SizedBox(height: 12),
                                  Text('${run['objective']}',
                                      maxLines: 3,
                                      overflow: TextOverflow.ellipsis),
                                  const SizedBox(height: 18),
                                  _progress(run),
                                  const SizedBox(height: 12),
                                  Wrap(
                                    spacing: 10,
                                    runSpacing: 8,
                                    children: [
                                      for (final agent
                                          in _rows(run['active_agents']))
                                        _badge(
                                            _label(agent['role']), Icons.bolt),
                                      const Icon(Icons.arrow_forward_rounded)
                                    ],
                                  ),
                                ])))))),
    ];
  }

  Widget _badge(String label, [IconData? icon]) {
    final status = icon == Icons.check_circle
        ? '$label: sí'
        : icon == Icons.radio_button_unchecked
            ? '$label: pendiente'
            : label;
    return Semantics(
        label: status,
        excludeSemantics: true,
        child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.surfaceContainerHighest,
                borderRadius: BorderRadius.circular(12)),
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              if (icon != null) ...[
                Icon(icon, size: 16),
                const SizedBox(width: 6)
              ],
              Text(label),
            ])));
  }

  Widget _progress(Map<String, dynamic> data) {
    final total = (data['total_units'] as num? ?? 0).toInt();
    final accepted = (data['accepted_units'] as num? ?? 0).toInt();
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      LinearProgressIndicator(
          value: total == 0 ? 0 : (accepted / total).clamp(0, 1),
          minHeight: 6,
          borderRadius: BorderRadius.circular(5)),
      const SizedBox(height: 8),
      Text('$accepted de $total incrementos aceptados'),
    ]);
  }

  List<Widget> _detail(Map<String, dynamic> data) {
    final delivery = data['delivery'] as Map? ?? {};
    final blocker = data['blocker'] as Map? ?? {};
    return [
      Text('${data['project']}',
          style: Theme.of(context)
              .textTheme
              .headlineMedium
              ?.copyWith(fontWeight: FontWeight.w800)),
      const SizedBox(height: 8),
      ExpansionTile(
          title: const Text('Objetivo y alcance'),
          children: [SelectableText('${data['objective']}')]),
      const SizedBox(height: 16),
      Wrap(spacing: 10, runSpacing: 8, children: [
        _badge(_label(data['status'])),
        for (final entry in {
          'implemented': 'Implementado',
          'verified': 'Verificado',
          'applied': 'Integrado'
        }.entries)
          _badge(
              entry.value,
              delivery[entry.key] == true
                  ? Icons.check_circle
                  : Icons.radio_button_unchecked),
      ]),
      const SizedBox(height: 14),
      _progress(data),
      const SizedBox(height: 8),
      Text(
          '${data['calls']} / ${data['max_calls']} llamadas · Integrado no significa publicado',
          style: Theme.of(context).textTheme.bodySmall),
      Text('Último cambio: ${_date(data['updated_at'])}',
          style: Theme.of(context).textTheme.bodySmall),
      if ('${blocker['reason'] ?? ''}'.isNotEmpty)
        Card(
            child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('Qué falta resolver',
                          style: TextStyle(fontWeight: FontWeight.bold)),
                      Text('${blocker['reason']}'),
                      if ('${blocker['next_action'] ?? ''}'.isNotEmpty)
                        Text('${blocker['next_action']}'),
                    ]))),
      const SizedBox(height: 22),
      Wrap(spacing: 8, runSpacing: 8, children: [
        for (final (index, label) in [
          'Ahora',
          'Resultados',
          'Diseño',
          'Problemas',
          'Actividad'
        ].indexed)
          ChoiceChip(
              label: Text(label),
              selected: _tab == index,
              onSelected: (_) => setState(() => _tab = index)),
      ]),
      const SizedBox(height: 16),
      if (_tab == 0) ..._now(data),
      if (_tab == 1) ..._advance(data),
      if (_tab == 2) ..._visual(data),
      if (_tab == 3) ..._issues(data),
      if (_tab == 4) ..._team(data),
    ];
  }

  List<Widget> _now(Map<String, dynamic> data) {
    final active = _rows(data['jobs'])
        .where((j) => ['running', 'starting', 'launching', 'pending'].contains(j['status']))
        .toList();
    final units = _rows(data['units']);
    return [
      Text('En qué está trabajando el equipo',
          style: Theme.of(context).textTheme.titleLarge),
      const SizedBox(height: 12),
      if (active.isEmpty)
        Text(data['status'] == 'completed'
            ? 'La ejecución terminó. Consultá los resultados y sus evidencias.'
            : 'No hay una tarea activa registrada en esta consulta.'),
      for (final job in active)
        Builder(builder: (context) {
          final unit = units.where((u) => u['id'] == job['unit']).firstOrNull;
          return Card(
              child: Padding(
                  padding: const EdgeInsets.all(18),
                  child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(children: [
                          const Icon(Icons.bolt_outlined),
                          const SizedBox(width: 8),
                          Expanded(
                              child: Text(_label(job['role']),
                                  style:
                                      Theme.of(context).textTheme.titleLarge)),
                          _badge(_label(job['status']))
                        ]),
                        const SizedBox(height: 12),
                        Text(
                            unit?['objective'] as String? ??
                                'Preparar y revisar el objetivo del proyecto',
                            maxLines: 3,
                            overflow: TextOverflow.ellipsis),
                        const SizedBox(height: 8),
                        Text('Desde ${_date(job['started_at'])}',
                            style: Theme.of(context).textTheme.bodySmall),
                        ExpansionTile(
                            title: const Text('Contexto y dependencias'),
                            children: [
                              ListTile(
                                  title: const Text('Historias asignadas'),
                                  subtitle: Text(
                                      (unit?['stories'] as List? ?? [])
                                          .join(' · '))),
                              ListTile(
                                  title: const Text('Depende de'),
                                  subtitle: Text(
                                      (unit?['depends_on'] as List? ?? [])
                                          .join(' · '))),
                              for (final source in _rows((job['context'] as Map?)?['sources']))
                ListTile(leading: const Icon(Icons.description_outlined),
                  title: Text('${source['name']}'),
                  subtitle: const Text('Referenciado en el encargo · lectura sin acreditar')),
              const ListTile(
                                  title: Text('Lecturas del agente'),
                                  subtitle: Text(
                                      'Todavía no hay registro verificable de los documentos consultados.')),
                            ]),
                      ])));
        }),
      const SizedBox(height: 16),
      Text('Próximas tareas', style: Theme.of(context).textTheme.titleMedium),
      for (final unit in units
          .where((u) => ['ready', 'pending'].contains(u['state']))
          .take(3))
        ListTile(
            leading: const Icon(Icons.arrow_forward),
            title: Text('${unit['objective']}',
                maxLines: 2, overflow: TextOverflow.ellipsis),
            subtitle: Text(_label(unit['owner']))),
    ];
  }

  String _date(dynamic value) {
    final date = DateTime.tryParse('$value')?.toLocal();
    if (date == null) return 'Sin registro';
    return '${date.day}/${date.month} ${TimeOfDay.fromDateTime(date).format(context)}';
  }

  List<Widget> _advance(Map<String, dynamic> data) => [
        for (final unit in _rows(data['units']))
          Card(
              child: ListTile(
                  leading: Icon(unit['state'] == 'accepted'
                      ? Icons.task_alt
                      : Icons.pending_actions),
                  title: Text('${unit['objective']}'),
                  subtitle: Text(
                      '${_label(unit['owner'])} · ${_label(unit['state'])}\n${(unit['stories'] as List? ?? []).join(' · ')}'),
                  isThreeLine: true)),
        const SizedBox(height: 16),
        Text('Historias y aceptación',
            style: Theme.of(context).textTheme.titleMedium),
        for (final story in _rows(data['stories']))
          ExpansionTile(
              title: Text('${story['id']} · ${story['priority']}'),
              subtitle: Text('${story['role']} · ${_label(story['state'])}'),
              children: [
                for (final criterion in story['acceptance'] as List? ?? [])
                  ListTile(
                      leading: const Icon(Icons.rule_outlined),
                      title: Text('$criterion'))
              ]),
      ];
  List<Widget> _team(Map<String, dynamic> data) => [
        const Text('Actividad y revisiones · más recientes primero'),
        for (final job in _rows(data['jobs']).reversed)
          Card(
              child: ListTile(
            leading: Icon(job['role'] == 'ux' || job['role'] == 'ux_review'
                ? Icons.palette_outlined
                : Icons.account_tree_outlined),
            title: Text('${_label(job['role'])} · ${_label(job['status'])}'),
            subtitle: Text(
                '${job['unit'] ?? 'Objetivo completo'} · ${_date(job['finished_at'] ?? job['started_at'])}\n${job['verdict'] != null ? _label(job['verdict']) : job['phase'] ?? ''}'),
            trailing: job['session_id'] != null &&
                    widget.onOpenChat != null &&
                    data['can_open_chats'] == true
                ? IconButton(
                    tooltip: 'Abrir chat del agente',
                    icon: const Icon(Icons.open_in_new),
                    onPressed: () async {
                      Navigator.of(context).pop();
                      await widget.onOpenChat!(job['session_id'] as String);
                    })
                : null,
          )),
        if (data['can_open_chats'] != true)
          const Text('Las conversaciones del equipo están en Bridge PROD.'),
      ];
  List<Widget> _visual(Map<String, dynamic> data) {
    final images = _rows(data['images']);
    return [
      const Text(
          'Capturas registradas por revisión. Cada imagen conserva su commit.'),
      if (images.isEmpty)
        const Padding(
            padding: EdgeInsets.all(32),
            child: Text(
                'Todavía no hay capturas verificadas. No implica que UX haya terminado.')),
      for (final image in images)
        Padding(
            padding: const EdgeInsets.symmetric(vertical: 12),
            child: Card(
                clipBehavior: Clip.antiAlias,
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      ListTile(
                          title: Text('${image['label']}'),
                          subtitle: Text(
                              '${image['reviewed'] == true ? 'Con revisión registrada' : 'Propuesta · sin revisar'} · ${image['commit'] == data['commit'] ? 'Commit actual' : 'Otro commit'} · ${image['commit']}',
                              maxLines: 2)),
                      InkWell(
                          onTap: () => showDialog<void>(
                              context: context,
                              builder: (context) => Dialog.fullscreen(
                                  child: Scaffold(
                                      appBar: AppBar(
                                          title: const Text('Evidencia UX')),
                                      body: InteractiveViewer(
                                          minScale: .5,
                                          maxScale: 5,
                                          child: Center(
                                              child: _image(data, image)))))),
                          child: SizedBox(
                              height: 280,
                              width: double.infinity,
                              child: _image(data, image))),
                    ]))),
    ];
  }

  Widget _image(Map<String, dynamic> data, Map<String, dynamic> image) =>
      Image.network(widget.client.url('/${data['id']}/images/${image['id']}'),
          fit: BoxFit.contain,
          semanticLabel: 'Captura UX ${image['label']}',
          errorBuilder: (context, error, stackTrace) => const Center(
              child:
                  Text('Evidencia no disponible. Actualizá para reintentar.')));
  List<Widget> _issues(Map<String, dynamic> data) {
    final issues = _rows(data['issues']);
    final open = issues.where((i) => i['status'] == 'open').length;
    return [
      Text('$open abiertos · ${issues.length - open} resueltos',
          style: Theme.of(context).textTheme.titleMedium),
      if (issues.isEmpty)
        const Padding(
            padding: EdgeInsets.all(32),
            child: Text(
                'Sin hallazgos registrados. La verificación se indica arriba.')),
      for (final issue in issues)
        Card(
            child: ExpansionTile(
          leading: Icon(issue['status'] == 'resolved'
              ? Icons.check_circle_outline
              : Icons.build_circle_outlined),
          title: Text('${issue['summary']}'),
          subtitle: Text(
              '${_label(issue['owner'])} · ${_label(issue['status'])} · ${issue['severity']}'),
          childrenPadding: const EdgeInsets.all(16),
          expandedCrossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Esperado: ${issue['expected']}'),
            const SizedBox(height: 8),
            Text('Observado: ${issue['observed']}')
          ],
        )),
    ];
  }
}
