import 'dart:async';
import 'package:flutter/material.dart';
import '../services/objective_team_client.dart';

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

  String _stagePurpose(Map<String, dynamic> data) {
    if (data['status'] == 'paused') {
      return 'La ejecución está pausada. El trabajo realizado se conserva.';
    }
    if (data['status'] == 'needs_attention' || data['status'] == 'blocked') {
      return 'Hay un impedimento registrado antes de continuar.';
    }
    if (data['status'] == 'cancelled') {
      return 'La ejecución fue cancelada.';
    }
    if (data['status'] == 'budget_exhausted') {
      return 'Se alcanzó el límite de ejecución; el trabajo realizado se conserva.';
    }
    if (data['status'] == 'completed') {
      return 'La ejecución finalizó. Consultá los resultados disponibles.';
    }
    return 'Organizando las historias, dependencias y primeros incrementos.';
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
  List<Widget> _overview() {
    final runs = _rows(_data!['runs']);
    return [
      _heading('Tus proyectos, en movimiento',
          'Elegí un proyecto para entender qué está pasando.'),
      if (runs.isEmpty)
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
                      Text(_beforePlan(run)
                          ? _stagePurpose(run)
                          : '${_product(run)['purpose'] ?? 'Preparando el plan de trabajo.'}'),
                      const SizedBox(height: 18),
                      Wrap(spacing: 10, runSpacing: 8, children: [
                        _pill(_label(run['status'])),
                        _pill(_agentCount(run)),
                        if (!_beforePlan(run))
                          _pill(
                              '${_product(run)['verified'] ?? run['accepted_units'] ?? 0} entregas verificadas',
                              color: const Color(0xFF72DAC4))
                      ])
                    ]))))
    ];
  }

  List<Widget> _detail(Map<String, dynamic> data) {
    final product = _product(data);
    return [
      Container(
          padding: const EdgeInsets.all(22),
          decoration: BoxDecoration(
              gradient: const LinearGradient(
                  colors: [Color(0xFF213455), Color(0xFF18233D)],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight),
              borderRadius: BorderRadius.circular(24)),
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            _pill(_label(data['status']), color: const Color(0xFF72DAC4)),
            const SizedBox(height: 16),
            Text('${product['name'] ?? data['project']}',
                style: Theme.of(context)
                    .textTheme
                    .headlineMedium
                    ?.copyWith(fontWeight: FontWeight.w800)),
            const SizedBox(height: 10),
            Text(_beforePlan(data)
                ? _stagePurpose(data)
                : '${product['purpose'] ?? 'El equipo está preparando el plan de trabajo.'}'),
            const SizedBox(height: 20),
            if (_beforePlan(data)) ...[
              _pill(_agentCount(data), color: const Color(0xFF72DAC4)),
              const SizedBox(height: 10),
              const Text('Aún no hay entregas para verificar.',
                  style: TextStyle(color: Color(0xFFAAB8D0))),
            ] else
              Wrap(spacing: 18, runSpacing: 12, children: [
                _metric('${product['verified'] ?? data['accepted_units'] ?? 0}',
                    'Verificadas'),
                _metric('${_agents(data).length}', 'Agentes activos'),
                _metric('${product['issues'] ?? 0}', 'Por resolver'),
              ]),
          ])),
      if (!_beforePlan(data) && product['communication'] != 'current')
        Padding(
            padding: const EdgeInsets.only(top: 12),
            child: Text(
                'El comunicador está preparando la explicación. El equipo puede seguir trabajando.',
                style: Theme.of(context).textTheme.bodySmall)),
      const SizedBox(height: 20),
      SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(children: [
            for (final (index, label) in [
              'Ahora',
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
      if (_tab == 0) ..._now(data),
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

  Widget _metric(String number, String label) => SizedBox(
      width: 86,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(number,
            style: const TextStyle(fontSize: 26, fontWeight: FontWeight.w800)),
        Text(label,
            style: const TextStyle(fontSize: 12, color: Color(0xFFAAB8D0)))
      ]));
  List<Widget> _now(Map<String, dynamic> data) {
    final tasks = _rows(_product(data)['tasks']);
    final active = tasks
        .where((t) => ['building', 'reviewing'].contains(t['status']))
        .toList();
    final waiting = tasks.where((t) => t['status'] == 'waiting').toList();
    final agents = _agents(data);
    final independent = agents
        .where((a) =>
            a['unit'] == null || !active.any((t) => t['id'] == a['unit']))
        .toList();
    return [
      _heading('En marcha', 'Responsables, propósito y siguiente entrega.'),
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
      for (final task in active) _task(task),
      if (waiting.isNotEmpty) ...[
        _heading('Lo que sigue', 'Estas tareas esperan una etapa anterior.'),
        for (final task in waiting.take(3)) _task(task, compact: true),
      ],
    ];
  }

  Widget _task(Map<String, dynamic> task, {bool compact = false}) => _surface(
      Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Wrap(spacing: 8, runSpacing: 8, children: [
          _pill('${task['owner']}'),
          _pill(_status(task['status']), color: _tone(task['status']))
        ]),
        const SizedBox(height: 14),
        Text('${task['title']}',
            style: Theme.of(context)
                .textTheme
                .titleLarge
                ?.copyWith(fontWeight: FontWeight.w700)),
        const SizedBox(height: 8),
        Text('${task['purpose']}',
            style: const TextStyle(color: Color(0xFFB9C5D9))),
        if (!compact) ...[
          const SizedBox(height: 16),
          const Text('Entrega esperada',
              style: TextStyle(fontSize: 12, color: Color(0xFF72DAC4))),
          const SizedBox(height: 5),
          Text('${task['outcome']}')
        ],
        if ((task['dependencies'] as List? ?? []).isNotEmpty) ...[
          const SizedBox(height: 12),
          Text('Espera: ${(task['dependencies'] as List).join(' · ')}',
              style: const TextStyle(fontSize: 12, color: Color(0xFFEBC581)))
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
            Text('${area['verified']} de ${area['total']} entregas verificadas')
          ]),
        ]))
    ];
  }

  List<Widget> _results(Map<String, dynamic> data) {
    final tasks = _rows(_product(data)['tasks'])
        .where((t) => t['status'] == 'verified')
        .toList();
    return [
      _heading('Entregas verificadas',
          'Sólo aparecen trabajos aceptados por la revisión.'),
      _empty(Icons.public_outlined, 'Publicación sin acreditar',
          'La integración de código no confirma que ya esté disponible para usar.'),
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
    final blocker = data['blocker'] as Map? ?? {};
    return [
      _heading('Lo que necesita atención',
          'Las correcciones del equipo y las dependencias pendientes.'),
      if ('${blocker['reason'] ?? ''}'.isNotEmpty)
        _empty(Icons.pause_circle_outline, 'Hay una dependencia externa',
            'El equipo registró un impedimento. El detalle técnico conserva el motivo y el siguiente paso.'),
      if (issues.isEmpty)
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
          const Text(
              'La revisión pidió ajustes antes de aceptar esta entrega.'),
        ]))
    ];
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
      const Text('Propuestas y pantallas del producto.'),
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
