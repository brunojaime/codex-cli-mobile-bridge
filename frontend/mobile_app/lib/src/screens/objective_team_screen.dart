import 'dart:async';
import 'package:url_launcher/url_launcher.dart';
import 'package:flutter/material.dart';
import '../services/objective_team_client.dart';
import '../models/objective_progress.dart';
import '../models/objective_brief.dart';
import '../models/objective_attention.dart';
import '../widgets/objective_flow_graph.dart';

const _labels = {
  'planning': 'Preparando el plan',
  'executing': 'En construcción',
  'final_review': 'Revisión final',
  'completed': 'Completado',
  'needs_attention': 'Necesita atención',
  'paused': 'En pausa',
  'cancelled': 'Cancelado',
  'budget_exhausted': 'Límite de ejecución alcanzado',
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
  const ObjectiveTeamScreen(
      {super.key,
      required this.client,
      this.onOpenChat,
      this.onRequestAttention});
  final ObjectiveTeamClient client;
  final Future<void> Function(String)? onOpenChat;
  final Future<void> Function(String project, String message)?
      onRequestAttention;
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
  bool _openingAttention = false;
  Timer? _timer;
  DateTime? _received;
  List<Map<String, dynamic>> _preparations = [];
  String? _preparationError;
  Map<String, dynamic>? _publications;
  bool _publicationError = false;
  DateTime? _publicationChecked;

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
    final preparation =
        selected == null ? _refreshPreparations() : Future<void>.value();
    try {
      final data =
          await widget.client.get(selected == null ? '' : '/$selected');
      if (mounted && selected == _selected) {
        setState(() {
          _data = data;
          _error = null;
          _received = DateTime.now();
        });
        if (selected != null &&
            (_publicationChecked == null ||
                DateTime.now().difference(_publicationChecked!).inSeconds >=
                    60)) {
          unawaited(_loadPublications(selected, '${data['project']}'));
        }
      }
    } catch (_) {
      if (mounted && selected == _selected) {
        setState(() => _error =
            'Sin conexión al equipo. Los datos anteriores pueden estar desactualizados.');
      }
    } finally {
      await preparation;
      if (mounted) {
        setState(() => _loading = false);
        if (selected != _selected) unawaited(_refresh());
      }
    }
  }

  Future<void> _refreshPreparations() async {
    try {
      final items = await widget.client.preparations();
      if (mounted) {
        setState(() {
          _preparations = items;
          _preparationError = null;
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() => _preparationError =
            'No se pudo actualizar la preparación desde el chat.');
      }
    }
  }

  Future<void> _loadPublications(String selected, String project) async {
    _publicationChecked = DateTime.now();
    try {
      final result = await widget.client.publications(project);
      if (mounted && selected == _selected) {
        setState(() {
          _publications = result;
          _publicationError = false;
        });
      }
    } catch (_) {
      if (mounted && selected == _selected) {
        setState(() {
          _publicationError = true;
          _publications = null;
        });
      }
    }
  }

  void _select(String? id) {
    setState(() {
      _selected = id;
      _publications = null;
      _publicationError = false;
      _publicationChecked = null;
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
                              if (_selected == null) ..._preparationCards(),
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

  Map<String, dynamic> _product(Map<String, dynamic> data) =>
      Map<String, dynamic>.from(data['presentation'] as Map? ?? {});
  bool _beforePlan(Map<String, dynamic> data) =>
      data['status'] == 'planning' ||
      (data['total_units'] == 0 && _rows(_product(data)['tasks']).isEmpty);
  List<Map<String, dynamic>> _agents(Map<String, dynamic> data) {
    const active = ['running', 'starting', 'launching', 'pending'];
    final jobs =
        _rows(data['jobs']).where((j) => active.contains(j['status'])).toList();
    return jobs.isNotEmpty ? jobs : _rows(data['active_agents']);
  }

  String _agentCount(Map<String, dynamic> data) {
    final count = _agents(data).length;
    return '$count ${count == 1 ? 'agente activo' : 'agentes activos'}';
  }

  Widget _agentCard(Map<String, dynamic> agent) {
    final role = agent['role'];
    final title = const {
          'requirements': 'Preparar el plan de trabajo',
          'recovery': 'Resolver el impedimento',
          'reviewer': 'Comprobar las entregas',
          'security': 'Verificar la protección de datos y accesos',
          'ux': 'Diseñar la experiencia',
          'ux_review': 'Revisar las pantallas',
          'generator': 'Construir el siguiente incremento',
        }[role] ??
        'Trabajar en la etapa actual';
    final detail = agent['phase'] == 'Drafting reply' ||
            agent['phase'] == 'Finalizing'
        ? 'Preparando la entrega de esta etapa.'
        : role == 'requirements'
            ? 'Organiza el relevamiento en tareas y criterios que el equipo pueda comprobar.'
            : 'La entrega aparecerá como verificada cuando supere la revisión.';
    final start = DateTime.tryParse('${agent['started_at'] ?? ''}');
    final elapsed =
        start == null ? null : DateTime.now().difference(start).inMinutes;
    return _surface(
        Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Wrap(spacing: 8, runSpacing: 8, children: [
        _pill(_role(role)),
        _pill('Actividad registrada', color: const Color(0xFF72DAC4)),
      ]),
      const SizedBox(height: 14),
      Text(title,
          style: Theme.of(context)
              .textTheme
              .titleLarge
              ?.copyWith(fontWeight: FontWeight.w700)),
      const SizedBox(height: 8),
      Text(detail, style: const TextStyle(color: Color(0xFFB9C5D9))),
      if (elapsed != null && elapsed >= 0) ...[
        const SizedBox(height: 12),
        Text(
            elapsed == 0
                ? 'Inició hace menos de un minuto'
                : 'Inició hace $elapsed min',
            style: const TextStyle(fontSize: 12, color: Color(0xFFAAB8D0))),
      ],
    ]));
  }

  String _status(dynamic value) =>
      const {
        'verified': 'Verificado',
        'building': 'En construcción',
        'reviewing': 'En revisión',
        'waiting': 'Esperando otra etapa',
        'planned': 'Por comenzar',
      }[value] ??
      'Por confirmar';
  Color _tone(dynamic status) => status == 'verified'
      ? const Color(0xFF72DAC4)
      : status == 'waiting'
          ? const Color(0xFFEBC581)
          : const Color(0xFF9EAEFF);
  Widget _pill(String value, {Color color = const Color(0xFF9EAEFF)}) =>
      Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
          decoration: BoxDecoration(
              color: color.withValues(alpha: .12),
              borderRadius: BorderRadius.circular(10)),
          child: Text(value,
              style: TextStyle(
                  color: color, fontSize: 12, fontWeight: FontWeight.w600)));
  Widget _surface(Widget child, {Color? accent}) => Container(
      margin: const EdgeInsets.only(bottom: 14),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
          color: const Color(0xFF141E32),
          borderRadius: BorderRadius.circular(22),
          border: Border.all(
              color:
                  (accent ?? const Color(0xFF60718F)).withValues(alpha: .22))),
      child: child);
  Widget _empty(IconData icon, String title, String description) =>
      _surface(Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Icon(icon, color: const Color(0xFF9EAEFF), size: 30),
        const SizedBox(height: 16),
        Text(title, style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 8),
        Text(description, style: const TextStyle(color: Color(0xFFAAB8D0)))
      ]));
  Widget _heading(String title, String subtitle) => Padding(
      padding: const EdgeInsets.only(top: 6, bottom: 18),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(title,
            style: Theme.of(context)
                .textTheme
                .titleLarge
                ?.copyWith(fontWeight: FontWeight.w700)),
        const SizedBox(height: 5),
        Text(subtitle, style: const TextStyle(color: Color(0xFFAAB8D0)))
      ]));
  List<Widget> _preparationCards() => [
        if (_preparationError != null)
          Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: Text(
                  '$_preparationError Los datos previos pueden estar desactualizados.',
                  style:
                      TextStyle(color: Theme.of(context).colorScheme.error))),
        if (_preparations.isNotEmpty)
          _heading('Preparación desde el chat',
              'El equipo aparece abajo cuando queda registrado.'),
        for (final job in _preparations)
          _surface(
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Wrap(spacing: 8, runSpacing: 8, children: [
              _pill(job['status'] == 'failed'
                  ? 'Preparación interrumpida'
                  : job['status'] == 'cancelled'
                      ? 'Preparación cancelada'
                      : job['status'] == 'pending'
                          ? 'Pedido en cola'
                          : 'Preparando el proyecto'),
              _pill('Coordinación inicial'),
            ]),
            const SizedBox(height: 14),
            Text('${job['title']}',
                style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 10),
            Text(
                job['status'] == 'failed' || job['status'] == 'cancelled'
                    ? 'El chat se detuvo. Revisá el resultado antes de continuar.'
                    : 'El chat está atendiendo el encargo y preparando el inicio del equipo.',
                style: const TextStyle(color: Color(0xFFAAB8D0))),
            if (DateTime.tryParse('${job['created_at']}')
                case final DateTime started)
              Padding(
                  padding: const EdgeInsets.only(top: 12),
                  child: Text(
                      'Pedido hace ${DateTime.now().difference(started).inMinutes.clamp(0, 999999)} min',
                      style: Theme.of(context).textTheme.bodySmall)),
            if (widget.onOpenChat != null) ...[
              const SizedBox(height: 12),
              TextButton.icon(
                  icon: const Icon(Icons.chat_bubble_outline_rounded),
                  label: const Text('Ver chat de preparación'),
                  onPressed: () async {
                    await widget.onOpenChat!(job['session_id'] as String);
                    if (mounted) Navigator.of(context).pop();
                  }),
            ],
          ])),
      ];

  List<Widget> _overview() {
    final runs = _rows(_data!['runs']);
    return [
      _heading('Tus proyectos, en movimiento',
          'Elegí un proyecto para entender qué está pasando.'),
      if (runs.isEmpty && _preparations.isEmpty)
        _empty(Icons.hub_outlined, 'Todavía no hay ejecuciones',
            'Creá el encargo desde el chat de Code.'),
      for (final run in runs)
        Semantics(
            key: ValueKey('objective-run-${run['id']}'),
            button: true,
            container: true,
            excludeSemantics: true,
            label:
                'Abrir ejecución: ${_product(run)['name'] ?? run['project']}',
            onTap: () => _select(run['id'] as String),
            child: InkWell(
                borderRadius: BorderRadius.circular(22),
                onTap: () => _select(run['id'] as String),
                child: _surface(Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(children: [
                        Expanded(
                            child: Text(
                                '${_product(run)['name'] ?? run['project']}',
                                style:
                                    Theme.of(context).textTheme.headlineSmall)),
                        const Icon(Icons.arrow_forward_rounded,
                            color: Color(0xFF72DAC4))
                      ]),
                      const SizedBox(height: 12),
                      Text(ObjectiveProgress.fromData(run).summary),
                      const SizedBox(height: 18),
                      Wrap(spacing: 10, runSpacing: 8, children: [
                        _pill(ObjectiveProgress.fromData(run).title),
                        _pill(_agentCount(run)),
                        if (!_beforePlan(run))
                          _pill(
                              '${_product(run)['verified'] ?? run['accepted_units'] ?? 0} etapas aprobadas',
                              color: const Color(0xFF72DAC4))
                      ])
                    ]))))
    ];
  }

  Widget _briefLine(IconData icon, String label, String value) => Padding(
      padding: const EdgeInsets.only(top: 14),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Icon(icon, size: 20, color: const Color(0xFF72DAC4)),
        const SizedBox(width: 10),
        Expanded(
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(label,
              style: const TextStyle(
                  fontWeight: FontWeight.w600, color: Color(0xFF72DAC4))),
          const SizedBox(height: 3),
          Text(value),
        ])),
      ]));

  String _trySummary() {
    if (_publicationError) {
      return 'No pudimos consultar la publicación. No podemos confirmar qué está disponible.';
    }
    if (_publications == null) {
      return 'Estamos consultando si hay una versión publicada.';
    }
    final records = _rows(_publications?['records']);
    if (records.isEmpty) {
      return 'Todavía no hay una publicación acreditada. Las capturas de diseño no equivalen a una app publicada.';
    }
    return 'Hay ${records.length == 1 ? 'una versión registrada' : 'versiones registradas'} del proyecto. No implica que incluya estos cambios; consultá el detalle en Resultados.';
  }

  List<Widget> _detail(Map<String, dynamic> data) {
    final product = _product(data);
    final progress = ObjectiveProgress.fromData(data);
    final brief = ObjectiveBrief.fromData(data);
    return [
      Text('${product['name'] ?? data['project']}',
          style: Theme.of(context)
              .textTheme
              .headlineSmall
              ?.copyWith(fontWeight: FontWeight.w800)),
      const SizedBox(height: 10),
      Wrap(spacing: 8, runSpacing: 8, children: [
        _pill(progress.title),
        if (ObjectiveAttention.fromData(data).needsDecision)
          FilledButton.icon(
              onPressed: () => setState(() => _tab = 4),
              icon: const Icon(Icons.front_hand_outlined),
              label: const Text('Atender ahora')),
      ]),
      const SizedBox(height: 16),
      SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(children: [
            for (final (index, label) in [
              'Mapa',
              'Producto',
              'Resultados',
              'Diseño',
              'Atención'
            ].indexed)
              Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: ChoiceChip(
                      label: Text(label),
                      selected: _tab == index,
                      onSelected: (_) => setState(() => _tab = index))),
          ])),
      const SizedBox(height: 20),
      if (_tab == 0) ...[
        ObjectiveFlowGraph(
            data: data, onAttention: () => setState(() => _tab = 4)),
        const SizedBox(height: 16),
        ExpansionTile(title: const Text('Resumen en palabras'), children: [
          Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(brief.now),
                    _briefLine(Icons.pending_actions_outlined, 'Qué falta',
                        brief.remaining),
                    _briefLine(
                        Icons.arrow_forward_rounded, 'Qué sigue', brief.next),
                    _briefLine(
                        Icons.open_in_new, 'Qué podés probar', _trySummary()),
                    _briefLine(Icons.person_outline_rounded,
                        '¿Necesitás hacer algo?', brief.action),
                  ])),
        ]),
        OutlinedButton.icon(
            onPressed: () => setState(() => _tab = 3),
            icon: const Icon(Icons.photo_library_outlined),
            label: const Text('Ver diseño')),
        ExpansionTile(
            title: const Text('Detalle de actividad'), children: _now(data)),
      ],
      if (_tab == 1) ..._capabilities(data),
      if (_tab == 2) ..._results(data),
      if (_tab == 3) ..._visual(data),
      if (_tab == 4) ..._attention(data),
      const SizedBox(height: 16),
      OutlinedButton.icon(
          icon: const Icon(Icons.manage_search_outlined),
          label: const Text('Detalle técnico'),
          onPressed: () => _technical(data)),
    ];
  }

  List<Widget> _now(Map<String, dynamic> data) {
    final tasks = _rows(_product(data)['tasks']);
    final active = tasks
        .where((t) => _agents(data).any((a) => a['unit'] == t['id']))
        .toList();
    final waiting = tasks.where((t) => t['status'] == 'waiting').toList();
    final agents = _agents(data);
    final independent = agents
        .where((a) =>
            a['unit'] == null || !active.any((t) => t['id'] == a['unit']))
        .toList();
    return [
      _heading(
          agents.length > 1
              ? 'Trabajo en paralelo'
              : agents.length == 1
                  ? 'Una tarea en marcha'
                  : 'Actividad del equipo',
          agents.length > 1
              ? '${agents.length} agentes activos · ${agents.map((a) => a['unit'] ?? a['role']).toSet().length == 1 ? 'sobre la misma entrega' : '${agents.map((a) => a['unit'] ?? a['role']).toSet().length} tareas distintas'}.'
              : 'Sólo se muestra como activo lo que está ejecutándose.'),
      for (final agent in independent) _agentCard(agent),
      if (active.isEmpty && agents.isEmpty)
        _empty(
            Icons.timelapse_outlined,
            data['status'] == 'cancelled' ||
                    data['status'] == 'budget_exhausted'
                ? _label(data['status'])
                : data['status'] == 'paused'
                    ? 'Ejecución pausada'
                    : data['status'] == 'completed'
                        ? 'Trabajo finalizado'
                        : _beforePlan(data)
                            ? 'Esperando actividad de planificación'
                            : 'Sin tarea activa registrada',
            data['status'] == 'completed'
                ? 'Revisá las entregas y sus comprobaciones.'
                : data['status'] == 'paused'
                    ? 'No se registran agentes activos.'
                    : 'La última consulta no registra un agente trabajando. El panel se actualizará con la próxima actividad.'),
      for (final task in active)
        _task({
          ...task,
          'owner': agents
              .where((a) => a['unit'] == task['id'])
              .map((a) => _role(a['role']))
              .toSet()
              .join(' · ')
        }, activity: ObjectiveProgress.activity(data, task['id'])),
      if (waiting.isNotEmpty) ...[
        _heading('En espera',
            'Todavía no están ejecutándose. No indica un orden confirmado.'),
        for (final task in waiting.take(3)) _task(task, compact: true),
      ],
    ];
  }

  Widget _task(Map<String, dynamic> task,
          {bool compact = false, String? activity}) =>
      _surface(
          Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Wrap(spacing: 8, runSpacing: 8, children: [
              _pill('${task['owner']}'),
              _pill(activity ?? _status(task['status']),
                  color: _tone(task['status']))
            ]),
            const SizedBox(height: 14),
            Text('${task['title']}',
                style: Theme.of(context)
                    .textTheme
                    .titleLarge
                    ?.copyWith(fontWeight: FontWeight.w700)),
            const SizedBox(height: 8),
            Text(
                activity == 'Corrigiendo observaciones'
                    ? 'La revisión pidió cambios en esta etapa. El equipo los está resolviendo.'
                    : activity == 'Ajustando una entrega revisada'
                        ? 'Se están ajustando cambios sobre una etapa revisada; deberán comprobarse nuevamente.'
                        : '${task['purpose']}',
                style: const TextStyle(color: Color(0xFFB9C5D9))),
            if (!compact && activity == null) ...[
              const SizedBox(height: 16),
              const Text('Entrega esperada',
                  style: TextStyle(fontSize: 12, color: Color(0xFF72DAC4))),
              const SizedBox(height: 5),
              Text('${task['outcome']}')
            ],
            if ((task['dependencies'] as List? ?? []).isNotEmpty) ...[
              const SizedBox(height: 12),
              Text('Espera: ${(task['dependencies'] as List).join(' · ')}',
                  style:
                      const TextStyle(fontSize: 12, color: Color(0xFFEBC581)))
            ],
          ]),
          accent: _tone(task['status']));
  List<Widget> _capabilities(Map<String, dynamic> data) {
    final areas = _rows(_product(data)['capabilities']);
    return [
      _heading('El mapa del producto',
          'Qué tendrá la aplicación y cómo avanza cada área.'),
      if (areas.isEmpty)
        _empty(
            Icons.grid_view_outlined,
            'Organizando las capacidades',
            _beforePlan(data)
                ? 'Primero se organiza y valida el plan de trabajo.'
                : 'El mapa aparecerá cuando el comunicador termine de describir el plan.'),
      for (final area in areas)
        _surface(
            Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            const Icon(Icons.widgets_outlined, color: Color(0xFF9EAEFF)),
            const SizedBox(width: 12),
            Expanded(
                child: Text('${area['title']}',
                    style: Theme.of(context).textTheme.titleLarge))
          ]),
          const SizedBox(height: 10),
          Text('${area['purpose']}'),
          const SizedBox(height: 14),
          Wrap(spacing: 10, runSpacing: 8, children: [
            _pill(_status(area['status']), color: _tone(area['status'])),
            Text('${area['verified']} de ${area['total']} etapas aprobadas')
          ]),
        ]))
    ];
  }

  List<Widget> _availability(Map<String, dynamic> data) {
    final records = _rows(_publications?['records']);
    final images = _rows(data['images']);
    return [
      _heading('Para ver y probar',
          'La app publicada y el trabajo del equipo se muestran por separado.'),
      _surface(Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.rocket_launch_outlined, color: Color(0xFF72DAC4)),
          const SizedBox(width: 12),
          Expanded(
              child: Text(
                  _publicationError
                      ? 'No pudimos consultar la publicación'
                      : _publications == null
                          ? 'Consultando publicaciones…'
                          : records.isEmpty
                              ? 'Sin publicación acreditada'
                              : 'Publicaciones del proyecto',
                  style: Theme.of(context).textTheme.titleLarge))
        ]),
        const SizedBox(height: 12),
        if (records.isEmpty)
          Text(_publicationError
              ? 'Reintentamos automáticamente. No podemos confirmar qué versión está disponible.'
              : 'Las etapas aprobadas son avance interno; no confirman una app disponible.'),
        for (final record in records) ...[
          Text(
              '${record['environment'] == 'prod' ? 'Producción' : record['environment'] == 'qa' ? 'Pruebas' : 'Desarrollo'} · ${_date(record['deployed_at'])}',
              style: const TextStyle(fontWeight: FontWeight.w600)),
          Text(record['release'] != null
              ? 'Versión: ${record['release']}'
              : record['commit'] != null
                  ? 'Versión: ${'${record['commit']}'.substring(0, 8)}'
                  : 'Versión de código sin identificar'),
          Text(record['commit'] != null && record['commit'] == data['commit']
              ? 'Coincide con el código actual del equipo.'
              : 'No confirma que incluya los últimos cambios del equipo.'),
          if (!_publicationError && record['url'] != null)
            FilledButton.icon(
                onPressed: () => _openPublished('${record['url']}'),
                icon: const Icon(Icons.open_in_new),
                label: const Text('Abrir app'))
          else
            const Text('Sin enlace de acceso acreditado.'),
          const SizedBox(height: 12),
        ],
        if ((_publications?['errors'] as List? ?? []).isNotEmpty)
          const Text(
              'Hay registros que no se pudieron leer. La información puede estar incompleta.'),
        const Divider(),
        OutlinedButton.icon(
            onPressed: () => setState(() => _tab = 3),
            icon: const Icon(Icons.photo_library_outlined),
            label: const Text('Ver diseño')),
        Text(images.isEmpty
            ? 'Aún no hay capturas disponibles.'
            : '${images.length} capturas del trabajo visual. No acreditan publicación.'),
      ])),
    ];
  }

  Future<void> _openPublished(String url) async {
    try {
      if (await launchUrl(Uri.parse(url),
          mode: LaunchMode.externalApplication)) {
        return;
      }
    } catch (_) {/* Show a recoverable error below. */}
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('No se pudo abrir la app. Intentá nuevamente.')));
    }
  }

  List<Widget> _latest(Map<String, dynamic> data) {
    final jobs = _rows(data['jobs'])
        .where((j) =>
            j['status'] == 'completed' &&
            DateTime.tryParse('${j['finished_at']}') != null)
        .toList()
      ..sort((a, b) => DateTime.parse('${b['finished_at']}')
          .compareTo(DateTime.parse('${a['finished_at']}')));
    final job = jobs.firstOrNull;
    final task = _rows(_product(data)['tasks'])
        .where((t) => job != null && t['id'] == job['unit'])
        .firstOrNull;
    return [
      _heading('Última actividad completada',
          'Lo más reciente registrado por el equipo.'),
      _surface(Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(
            job == null
                ? 'Todavía no hay una actividad completada registrada'
                : '${task?['title'] ?? _role(job['role'])}',
            style: Theme.of(context).textTheme.titleLarge),
        if (job != null) ...[
          const SizedBox(height: 8),
          Text('${_role(job['role'])} · ${_date(job['finished_at'])}'),
          Text(job['verdict'] == 'changes'
              ? 'La revisión pidió ajustes.'
              : job['verdict'] == 'pass' &&
                      ['reviewer', 'ux_review', 'security']
                          .contains(job['role'])
                  ? 'Esta revisión fue aprobada. No confirma publicación.'
                  : 'Terminó esta intervención. La aceptación de la etapa se muestra en Resultados.'),
          TextButton(
              onPressed: () => setState(() => _tab = 2),
              child: const Text('Ver resultados')),
        ],
      ])),
    ];
  }

  List<Widget> _results(Map<String, dynamic> data) {
    final tasks = _rows(_product(data)['tasks'])
        .where((t) => t['status'] == 'verified')
        .toList();
    return [
      _heading('Entregas verificadas',
          'Sólo aparecen trabajos aceptados por la revisión.'),
      ..._availability(data),
      ..._latest(data),
      if (tasks.isEmpty)
        _empty(Icons.fact_check_outlined, 'Todavía no hay entregas verificadas',
            'El trabajo en curso aparece en Ahora. Una tarea iniciada no es un resultado.'),
      for (final task in tasks) _task(task),
    ];
  }

  List<Widget> _attention(Map<String, dynamic> data) {
    final issues =
        _rows(data['issues']).where((i) => i['status'] == 'open').toList();
    final tasks = _rows(_product(data)['tasks']);
    final attention = ObjectiveAttention.fromData(data);
    return [
      _heading('Lo que necesita atención',
          'Las correcciones del equipo y las dependencias pendientes.'),
      _surface(Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(attention.title, style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 10),
        Text(attention.explanation),
        const SizedBox(height: 10),
        const Text('Enviar una indicación abre un chat: consultá allí el envío y la respuesta. La alerta permanece mientras el impedimento siga pendiente.'),
        const SizedBox(height: 12),
        const Text('Cómo seguir',
            style: TextStyle(fontWeight: FontWeight.bold)),
        Text(attention.suggestion),
        const SizedBox(height: 14),
        FilledButton.icon(
            onPressed: widget.onRequestAttention == null || _openingAttention
                ? null
                : () => _requestAttention(data),
            icon: const Icon(Icons.chat_bubble_outline),
            label: const Text('Resolver con el agente')),
        const Text(
            'Podés pedir un diagnóstico o dar una indicación. El envío no aprueba permisos ni aumenta límites automáticamente.',
            style: TextStyle(fontSize: 12)),
      ])),
      if (issues.isEmpty && !attention.needsDecision)
        _empty(Icons.check_circle_outline, 'Sin problemas abiertos registrados',
            'Esto no reemplaza la verificación de las entregas.'),
      for (final issue in issues)
        _surface(
            Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          _pill('Corrección pendiente', color: const Color(0xFFEBC581)),
          const SizedBox(height: 12),
          Text(
              '${tasks.where((t) => t['id'] == issue['unit']).firstOrNull?['title'] ?? 'Revisión del proyecto'}',
              style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 8),
          Text('Responsable: ${_role(issue['owner'])}'),
          const SizedBox(height: 8),
          Text('${issue['summary']}'),
          if ('${issue['expected'] ?? ''}'.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text('Qué falta: ${issue['expected']}')
          ],
        ]))
    ];
  }

  Future<void> _requestAttention(Map<String, dynamic> data) async {
    if (_openingAttention) return;
    setState(() => _openingAttention = true);
    try {
      // Revalidate before preparing an operator action; never act on a stale banner.
      final latest = await widget.client.get('/${data['id']}');
      if (!mounted || _selected != data['id']) return;
      setState(() => _data = latest);
      final attention = ObjectiveAttention.fromData(latest);
      var input = '';
      final decision = await showDialog<String>(
          context: context,
          builder: (context) => AlertDialog(
                title: const Text('¿Cómo querés seguir?'),
                content: SingleChildScrollView(
                    child: Column(
                        mainAxisSize: MainAxisSize.min,
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                      Text(attention.title),
                      const SizedBox(height: 8),
                      Text(attention.suggestion),
                      const SizedBox(height: 16),
                      TextField(
                          onChanged: (value) => input = value,
                          maxLines: 4,
                          maxLength: 1500,
                          decoration: const InputDecoration(
                              labelText: 'Tu indicación (opcional)',
                              hintText:
                                  'Por ejemplo: explicame las opciones antes de hacer cambios.')),
                      const Text(
                          'Se abrirá un chat para atender esta ejecución. No se reinicia el proyecto ni se considera resuelto el problema por enviar el pedido.'),
                    ])),
                actions: [
                  TextButton(
                      onPressed: () => Navigator.pop(context),
                      child: const Text('Cancelar')),
                  FilledButton(
                      onPressed: () => Navigator.pop(
                          context,
                          input.trim().isEmpty
                              ? 'Diagnosticá el impedimento actual y resolvé lo reversible dentro del alcance autorizado. Si hace falta una decisión mía, explicame las opciones.'
                              : input.trim()),
                      child: const Text('Enviar al agente'))
                ],
              ));
      if (decision == null || !mounted) return;
      await widget.onRequestAttention!(
          '${latest['project']}', ObjectiveAttention.request(latest, decision));
      if (mounted) Navigator.of(context).pop();
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            content: Text(
                'No se pudo completar el pedido. Revisá el chat y la conexión antes de volver a enviarlo.')));
      }
    } finally {
      if (mounted) setState(() => _openingAttention = false);
    }
  }

  String _role(dynamic role) =>
      const {
        'generator': 'Construcción',
        'ux': 'Diseño',
        'reviewer': 'Verificación',
        'ux_review': 'Revisión visual',
        'requirements': 'Planificación',
        'security': 'Seguridad',
        'recovery': 'Resolución'
      }[role] ??
      'Equipo';
  void _technical(Map<String, dynamic> data) => showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (context) => SafeArea(
          child: SizedBox(
              height: MediaQuery.sizeOf(context).height * .8,
              child: ListView(padding: const EdgeInsets.all(20), children: [
                Text('Registro técnico',
                    style: Theme.of(context).textTheme.headlineSmall),
                Text(
                    '${data['calls']} / ${data['max_calls']} llamadas · ${_date(data['updated_at'])}'),
                const Text('Integrado no significa publicado'),
                for (final job in _rows(data['jobs']).reversed)
                  ListTile(
                      title: Text(
                          '${_role(job['role'])} · ${_label(job['status'])}'),
                      subtitle: Text(
                          '${job['unit'] ?? 'Proyecto'} · ${_date(job['started_at'])}'),
                      trailing: job['session_id'] != null &&
                              widget.onOpenChat != null &&
                              data['can_open_chats'] == true
                          ? IconButton(
                              icon: const Icon(Icons.open_in_new),
                              tooltip: 'Abrir chat del agente',
                              onPressed: () async {
                                Navigator.of(context).pop();
                                Navigator.of(this.context).pop();
                                await widget
                                    .onOpenChat!(job['session_id'] as String);
                              })
                          : null),
                for (final issue in _rows(data['issues']))
                  ListTile(
                      title: Text('${issue['summary']}'),
                      subtitle: Text('${issue['observed']}')),
              ]))));
  String _date(dynamic value) {
    final date = DateTime.tryParse('$value')?.toLocal();
    return date == null
        ? 'Sin registro'
        : '${date.day}/${date.month} ${TimeOfDay.fromDateTime(date).format(context)}';
  }

  List<Widget> _visual(Map<String, dynamic> data) {
    final images = _rows(data['images']);
    return [
      const Text(
          'Capturas del trabajo de diseño. Pueden ser propuestas o pantallas piloto; no acreditan la versión publicada.'),
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
                          title: Text(image['reviewed'] == true
                              ? 'Pantalla revisada'
                              : 'Propuesta visual'),
                          subtitle: Text(
                              '${image['reviewed'] == true ? 'Con revisión registrada' : 'Sin revisión todavía'} · ${image['commit'] == data['commit'] ? 'Versión actual' : 'Versión anterior'}',
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
}
