import 'dart:async';
import 'package:flutter/material.dart';
import '../services/work_client.dart';
import 'project_work_settings_screen.dart';
import 'backlog_history.dart';

class WorkScreen extends StatefulWidget {
  const WorkScreen(
      {super.key,
      required this.baseUrl,
      this.workspacePath,
      this.projectName,
      this.onOpenChat,
      this.clientOverride});
  final String baseUrl;
  final String? workspacePath;
  final String? projectName;
  final Future<void> Function(String id)? onOpenChat;
  final WorkClient? clientOverride;
  @override
  State<WorkScreen> createState() => _WorkScreenState();
}

class _WorkScreenState extends State<WorkScreen> with WidgetsBindingObserver {
  late final WorkClient _client =
      widget.clientOverride ?? WorkClient(widget.baseUrl);
  Map<String, dynamic>? _data;
  String? _error;
  bool _loading = false;
  bool _acting = false;
  bool _allProjects = false;
  String? _selectedWorkspace;
  int _historyRefresh = 0;
  String _query = '';
  String? get _scope => widget.workspacePath ?? _selectedWorkspace;
  Timer? _timer;
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _start();
  }

  void _start() {
    _timer ??= Timer.periodic(const Duration(seconds: 15), (_) => _refresh());
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
    _client.close();
    super.dispose();
  }

  Future<void> _refresh() async {
    if (_loading) return;
    setState(() => _loading = true);
    try {
      final result = await _client.overview();
      if (mounted) {
        setState(() {
          _data = result;
          _error = null;
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() => _error =
            'No se pudo actualizar. Reintentá; los encargos siguen guardados.');
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _act(Future<dynamic> Function() action) async {
    if (_acting) return;
    setState(() => _acting = true);
    try {
      await action();
      await _refresh();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$e')));
      }
    } finally {
      if (mounted) setState(() => _acting = false);
    }
  }

  Future<void> _settings() async {
    await Navigator.of(context).push(MaterialPageRoute<void>(
        builder: (_) =>
            ProjectWorkSettingsScreen(client: _client, workspacePath: _scope)));
    if (mounted) await _refresh();
  }

  Future<void> _add() async {
    var workspace = _scope;
    workspace ??= await showDialog<String>(
        context: context,
        builder: (context) => SimpleDialog(
              title: const Text('¿En qué proyecto?'),
              children: [
                for (final p in _allProjectData)
                  SimpleDialogOption(
                    onPressed: () => Navigator.pop(
                        context, p['workspace_path'] ?? p['workspace']),
                    child: Padding(
                        padding: const EdgeInsets.symmetric(vertical: 8),
                        child: Text(p['name'] as String)),
                  )
              ],
            ));
    if (workspace == null || !mounted) return;
    final destination = workspace;
    final text = await showDialog<String>(
        context: context, builder: (_) => const _AddWorkDialog());
    if (text == null || !mounted) return;
    await _act(() async {
      await _client.enqueue(destination, text);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            content: Text(
                'Agregado al backlog. Se tomará al completar el trabajo anterior.')));
      }
    });
  }

  List<Map<String, dynamic>> get _allProjectData =>
      ((_data?['projects'] as List?) ?? []).cast<Map<String, dynamic>>();
  List<Map<String, dynamic>> get _projects => _allProjectData
      .where((p) =>
          _scope == null || (p['workspace_path'] ?? p['workspace']) == _scope)
      .toList();
  List<Map<String, dynamic>> get _decisions =>
      ((_data?['questions'] as List?) ?? [])
          .cast<Map<String, dynamic>>()
          .where((q) =>
              _scope == null ||
              (q['workspace'] ?? q['workspace_path']) == _scope)
          .toList();
  List<Map<String, dynamic>> _pending(Map<String, dynamic> p) => [
        if (p['active'] != null) Map<String, dynamic>.from(p['active'] as Map),
        ...((p['queue'] as List?) ?? [])
            .map((t) => Map<String, dynamic>.from(t as Map)),
      ]
          .where((t) => !['completed', 'cancelled'].contains(t['status']))
          .toList();
  String get _scopeName =>
      widget.projectName ??
      _projects.firstOrNull?['name'] as String? ??
      'Proyecto';
  String _taskTitle(Map<String, dynamic> task) {
    final title = (task['title'] as String? ?? '').trim();
    final instruction = (task['instruction'] as String? ?? '').trim();
    if (title.isEmpty || title.startsWith('Feedback ·')) {
      return instruction.isNotEmpty ? instruction : title;
    }
    return title;
  }

  String get _historyVersion {
    final changes = _projects
        .expand((project) => [
              ..._pending(project)
                  .map((task) => '${task['id']}:${task['status']}'),
              ...((project['completed'] as List?) ?? [])
                  .map((task) => task['id']),
            ])
        .join(',');
    return '$_scope:$_historyRefresh:$changes';
  }

  String _label(String status) => switch (status) {
        'queued' => 'En espera',
        'starting' => 'Preparando',
        'running' => 'En curso',
        'delivering' => 'Publicando DEV',
        'completed' => 'DEV comprobado',
        'blocked' => 'Bloqueado',
        'uncertain' => 'Requiere comprobar el arranque',
        'cancelled' => 'Retirado',
        _ => status
      };
  @override
  Widget build(BuildContext context) => DefaultTabController(
      length: 4,
      child: Scaffold(
        appBar: AppBar(
          title:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Text('Backlog'),
            Text(_scope == null ? 'Todos los proyectos' : _scopeName,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.bodySmall),
          ]),
          actions: [
            IconButton(
                tooltip: 'Automatización',
                onPressed: _settings,
                icon: const Icon(Icons.tune)),
            IconButton(
                tooltip: 'Actualizar',
                onPressed: () {
                  setState(() => _historyRefresh++);
                  unawaited(_refresh());
                },
                icon: const Icon(Icons.refresh)),
          ],
          bottom: const TabBar(
              isScrollable: true,
              tabAlignment: TabAlignment.start,
              tabs: [
                Tab(text: 'Backlog'),
                Tab(text: 'Historial'),
                Tab(text: 'Tu noche'),
                Tab(text: 'Decisiones'),
              ]),
        ),
        floatingActionButton: _scope == null && _allProjectData.isEmpty
            ? null
            : FloatingActionButton.extended(
                onPressed: _acting ? null : _add,
                icon: const Icon(Icons.add),
                label: const Text('Agregar tarea')),
        body: Column(children: [
          SizedBox(
              height: 3,
              child: _loading ? const LinearProgressIndicator() : null),
          if (_error != null)
            MaterialBanner(content: Text(_error!), actions: [
              TextButton(onPressed: _refresh, child: const Text('Reintentar')),
            ]),
          if (_selectedWorkspace != null && widget.workspacePath == null)
            Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                    onPressed: () => setState(() => _selectedWorkspace = null),
                    icon: const Icon(Icons.arrow_back, size: 18),
                    label: const Text('Todos los proyectos'))),
          Expanded(
              child: Center(
                  child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 960),
                      child: TabBarView(children: [
                        _backlog(),
                        BacklogHistory(
                            key: ValueKey(_historyVersion),
                            client: _client,
                            workspacePath: _scope,
                            taskBuilder: _task),
                        _night(),
                        _questions(),
                      ])))),
        ]),
      ));
  Widget _list(List<Widget> children) => RefreshIndicator(
      onRefresh: _refresh,
      child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(16, 20, 16, 104),
          children: children));

  Widget _empty(String title, String text, IconData icon) => Padding(
      padding: const EdgeInsets.symmetric(vertical: 36, horizontal: 12),
      child: Column(children: [
        Icon(icon, size: 40, color: Theme.of(context).colorScheme.primary),
        const SizedBox(height: 12),
        Text(title, style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        Text(text, textAlign: TextAlign.center)
      ]));

  Widget _badge(String text, IconData icon, {bool attention = false}) {
    final colors = Theme.of(context).colorScheme;
    return Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
            color: attention
                ? colors.errorContainer
                : colors.surfaceContainerHighest,
            borderRadius: BorderRadius.circular(8)),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Icon(icon,
              size: 15,
              color: attention
                  ? colors.onErrorContainer
                  : colors.onSurfaceVariant),
          const SizedBox(width: 6),
          Flexible(
              child: Text(text,
                  style: Theme.of(context).textTheme.labelMedium?.copyWith(
                      color: attention
                          ? colors.onErrorContainer
                          : colors.onSurfaceVariant))),
        ]));
  }

  Widget _projectCard(Map<String, dynamic> project) {
    final tasks = _pending(project);
    final waiting = tasks.where((t) => t['status'] == 'queued').length;
    final blocked = tasks
        .where((t) => ['blocked', 'uncertain'].contains(t['status']))
        .length;
    final active = tasks
        .where(
            (t) => ['starting', 'running', 'delivering'].contains(t['status']))
        .toList();
    final automatic = (project['policy'] as Map?)?['enabled'] == true;
    return Card(
        margin: const EdgeInsets.only(bottom: 12),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: () => setState(() => _selectedWorkspace =
              (project['workspace_path'] ?? project['workspace']) as String),
          child: Padding(
              padding: const EdgeInsets.all(18),
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(children: [
                      Icon(Icons.folder_outlined,
                          color: Theme.of(context).colorScheme.primary),
                      const SizedBox(width: 10),
                      Expanded(
                          child: Text(project['name'] as String,
                              style: Theme.of(context).textTheme.titleMedium,
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis)),
                      const Icon(Icons.chevron_right),
                    ]),
                    const SizedBox(height: 14),
                    Wrap(spacing: 8, runSpacing: 8, children: [
                      if (waiting > 0)
                        _badge('$waiting en espera', Icons.schedule),
                      if (active.isNotEmpty)
                        _badge('${active.length} en curso',
                            Icons.play_circle_outline),
                      if (blocked > 0)
                        _badge('$blocked por revisar', Icons.error_outline,
                            attention: true),
                    ]),
                    const SizedBox(height: 14),
                    Text(active.isNotEmpty ? 'Ahora' : 'Próximo pedido',
                        style: Theme.of(context).textTheme.labelMedium),
                    const SizedBox(height: 4),
                    Text(
                        _taskTitle(
                            active.isNotEmpty ? active.first : tasks.first),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis),
                    const SizedBox(height: 12),
                    Text(
                        project['policy'] == null
                            ? 'Falta configurar la ejecución'
                            : automatic
                                ? 'Ejecución automática activada'
                                : 'Ejecución automática pausada',
                        style: Theme.of(context).textTheme.bodySmall),
                  ])),
        ));
  }

  Widget _backlog() {
    final projects = _projects.where((p) => _pending(p).isNotEmpty).toList();
    final visible = projects
        .where((p) => '${p['name']}'.toLowerCase().contains(_query))
        .toList();
    final tasks = projects.expand(_pending).toList();
    return _list([
      if (_scope == null) ...[
        Text('${tasks.length} pedidos pendientes',
            style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 6),
        Text(
            'En ${projects.length} proyectos · Lo terminado está en Historial.',
            style: Theme.of(context).textTheme.bodyMedium),
        const SizedBox(height: 18),
        TextField(
            decoration: const InputDecoration(
                hintText: 'Buscar proyecto',
                prefixIcon: Icon(Icons.search),
                border: OutlineInputBorder()),
            onChanged: (value) =>
                setState(() => _query = value.trim().toLowerCase())),
        const SizedBox(height: 16),
        for (final project in visible) _projectCard(project),
        if (visible.isEmpty && projects.isNotEmpty)
          _empty('Sin coincidencias', 'Probá con otro nombre de proyecto.',
              Icons.search_off),
      ] else ...[
        for (final project in _projects) ...[
          Wrap(
              spacing: 8,
              runSpacing: 8,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                _badge(
                    '${_pending(project).where((t) => t['status'] == 'queued').length} en espera',
                    Icons.schedule),
                if (project['policy'] != null)
                  TextButton.icon(
                      onPressed: _acting
                          ? null
                          : () => _act(() => _client.updateProjectSettings(
                                  _scope!, {
                                'automatic_execution':
                                    !((project['policy'] as Map)['enabled'] ==
                                        true)
                              })),
                      icon: Icon(
                          (project['policy'] as Map)['enabled'] == true
                              ? Icons.pause_circle_outline
                              : Icons.play_circle_outline,
                          size: 18),
                      label: Text((project['policy'] as Map)['enabled'] == true
                          ? 'Pausar nuevos'
                          : 'Reanudar')),
              ]),
          if (project['policy'] == null)
            const Padding(
                padding: EdgeInsets.symmetric(vertical: 12),
                child: Text(
                    'Los pedidos están guardados. Falta configurar la ejecución en Automatización.')),
          if (_pending(project).any((t) => [
                'starting',
                'running',
                'delivering',
                'uncertain'
              ].contains(t['status']))) ...[
            const SizedBox(height: 18),
            Text('En curso', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            for (final t in _pending(project).where((t) => [
                  'starting',
                  'running',
                  'delivering',
                  'uncertain'
                ].contains(t['status'])))
              _task(t),
          ],
          if (_pending(project)
              .any((t) => ['queued', 'blocked'].contains(t['status']))) ...[
            const SizedBox(height: 20),
            Text('Por hacer', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            for (final t in _pending(project)
                .where((t) => ['queued', 'blocked'].contains(t['status'])))
              _task(t),
          ],
        ],
      ],
      if (tasks.isEmpty && !_loading)
        _empty(
            'Todo al día',
            'No hay pedidos pendientes. Podés agregar uno nuevo o consultar el historial.',
            Icons.check_circle_outline),
    ]);
  }

  Widget _task(Map<String, dynamic> task) => Card(
      margin: const EdgeInsets.symmetric(vertical: 5),
      child: ExpansionTile(
        key: ValueKey('work-${task['id']}'),
        tilePadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
        childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
        expandedCrossAxisAlignment: CrossAxisAlignment.start,
        title: Text(_taskTitle(task),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: Theme.of(context).textTheme.titleSmall),
        subtitle: Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(
                '${_label(task['status'] as String)} · ${task['source'] == 'whatsapp' ? 'WhatsApp' : task['source'] == 'feedback' ? 'Feedback' : 'Chat'}',
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: ['blocked', 'uncertain'].contains(task['status'])
                        ? Theme.of(context).colorScheme.error
                        : null))),
        children: [
          SelectableText(
              task['instruction'] as String? ?? task['title'] as String? ?? ''),
          if (task['updated_at'] != null)
            Padding(
                padding: const EdgeInsets.only(top: 10),
                child: Text(
                    'Actualizado: ${_date(task['updated_at'] as String)}',
                    style: Theme.of(context).textTheme.bodySmall)),
          if (task['problem'] != null)
            Padding(
                padding: const EdgeInsets.symmetric(vertical: 10),
                child: Text(task['problem'] as String,
                    style:
                        TextStyle(color: Theme.of(context).colorScheme.error))),
          if (task['receipt'] != null)
            Padding(
                padding: const EdgeInsets.symmetric(vertical: 10),
                child: SelectableText(
                    'Git confirmado · DEV comprobado\n${(task['receipt'] as Map)['dev_url']}')),
          Wrap(spacing: 8, runSpacing: 8, children: [
            if (task['session_id'] != null && widget.onOpenChat != null)
              TextButton(
                  onPressed: () async {
                    await widget.onOpenChat!(task['session_id'] as String);
                    if (mounted) Navigator.of(context).pop();
                  },
                  child: const Text('Abrir trabajo')),
            if (['starting', 'running'].contains(task['status']) &&
                task['stop_requested'] != 1)
              TextButton(
                  onPressed: _acting
                      ? null
                      : () => _act(() => _client.control(task, 'stop')),
                  child: const Text('Frenar')),
            if (task['status'] == 'queued')
              TextButton(
                  onPressed: _acting
                      ? null
                      : () => _act(() => _client.control(task, 'cancel')),
                  child: const Text('Retirar')),
            if (task['status'] == 'blocked')
              TextButton(
                  onPressed: _acting
                      ? null
                      : () => _act(() => _client.control(task, 'retry')),
                  child: const Text('Revisado: reintentar')),
          ]),
        ],
      ));

  String _date(String value) {
    final date = DateTime.tryParse(value)?.toLocal();
    if (date == null) return value;
    String two(int n) => n.toString().padLeft(2, '0');
    return '${two(date.day)}/${two(date.month)}/${date.year} · ${two(date.hour)}:${two(date.minute)}';
  }

  Widget _night() {
    final summary = _scope == null
        ? ((_data?['night'] ?? _data?['summary']) as Map? ?? {})
        : {
            'completed': _projects.fold<int>(
                0,
                (count, p) =>
                    count + ((p['night_completed'] as List?)?.length ?? 0)),
            'blocked': _projects
                .expand(_pending)
                .where((t) => ['blocked', 'uncertain'].contains(t['status']))
                .length,
          };
    final projects = _allProjects ? _projects : _projects.take(3);
    return _list([
      Text('Tu noche', style: Theme.of(context).textTheme.headlineSmall),
      const SizedBox(height: 8),
      Text(
          '${summary['completed'] ?? 0} avances en DEV · ${summary['blocked'] ?? 0} bloqueos · ${_decisions.length} por decidir'),
      const SizedBox(height: 8),
      Text((_data?['worker'] as Map?)?['recent'] == true
          ? 'Supervisor: revisión reciente'
          : 'Supervisor: sin actividad reciente confirmada'),
      Text('En calibración · 22:30–08:00 Argentina',
          style: Theme.of(context).textTheme.bodySmall),
      Text('Actualizado: ${_data?['updated_at'] ?? 'esperando al servidor'}',
          style: Theme.of(context).textTheme.bodySmall),
      if (summary['completed'] == 0)
        const Padding(
            padding: EdgeInsets.symmetric(vertical: 16),
            child: Text(
                'No hay avances comprobados en esta ventana. Revisá lo que sigue en curso o necesita atención.')),
      for (final project in projects) ...[
        Padding(
            padding: const EdgeInsets.only(top: 20, bottom: 8),
            child: Text(project['name'] as String,
                style: Theme.of(context).textTheme.titleMedium)),
        if (project['active'] != null)
          Text(
              'Ahora: ${_label((project['active'] as Map)['status'] as String)}'),
        for (final task
            in ((project['night_completed'] ?? project['completed']) as List)
                .take(1))
          _task(Map<String, dynamic>.from(task as Map)),
        ExpansionTile(title: const Text('Ver recorrido'), children: [
          for (final event in ((_data?['timeline'] as List?) ?? [])
              .where((e) => [
                    (project['completed'] as List).map((t) => t['id']).toList(),
                    (project['queue'] as List).map((t) => t['id']).toList(),
                    [
                      if (project['active'] != null)
                        (project['active'] as Map)['id']
                    ]
                  ].expand((ids) => ids).contains(e['task_id']))
              .take(5))
            ListTile(
                title: Text(_label(event['kind'] as String)),
                subtitle: Text(event['text'] as String))
        ]),
      ],
      if (_projects.length > 3)
        TextButton(
            onPressed: () => setState(() => _allProjects = !_allProjects),
            child:
                Text(_allProjects ? 'Ver menos' : 'Ver todos los proyectos')),
    ]);
  }

  Widget _questions() => _list([
        if (_decisions.isEmpty)
          const Padding(
              padding: EdgeInsets.all(24),
              child: Text('No hay decisiones pendientes.')),
        for (final question in _decisions)
          Card(
              child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Text(question['title'] as String,
                            style: Theme.of(context).textTheme.titleMedium),
                        if ((question['notes'] as String? ?? '').isNotEmpty)
                          Text('Tus observaciones: ${question['notes']}'),
                        const SizedBox(height: 12),
                        for (var index = 0;
                            index < (question['options'] as List).length;
                            index++)
                          Padding(
                              padding: const EdgeInsets.only(bottom: 8),
                              child: OutlinedButton(
                                  onPressed: _acting
                                      ? null
                                      : () => _act(() => _client.choose(
                                          question['id'] as String, index)),
                                  child: Text((question['options']
                                      as List)[index]['label'] as String))),
                        Wrap(spacing: 8, children: [
                          TextButton(
                              onPressed: _acting
                                  ? null
                                  : () async {
                                      final text = await showDialog<String>(
                                          context: context,
                                          builder: (_) => const _AddWorkDialog(
                                              title: 'Observaciones',
                                              description:
                                                  'Se guardan con esta propuesta. Todavía no se ejecuta; al elegir una opción se tendrán en cuenta.',
                                              submitLabel:
                                                  'Guardar observaciones',
                                              maxLength: 3000));
                                      if (text != null && mounted) {
                                        await _act(() => _client.respond(
                                            question['id'] as String,
                                            'observations',
                                            text));
                                      }
                                    },
                              child: const Text('Observaciones')),
                          TextButton(
                              onPressed: _acting
                                  ? null
                                  : () => _act(() => _client.respond(
                                      question['id'] as String, 'reject')),
                              child: const Text('Rechazar')),
                        ]),
                      ]))),
      ]);
}

class _AddWorkDialog extends StatefulWidget {
  const _AddWorkDialog(
      {this.title = 'Agregar al backlog',
      this.description =
          'Queda autorizado para ejecutarse al completar el trabajo anterior, con validación y entrega en DEV.',
      this.submitLabel = 'Añadir al backlog',
      this.maxLength = 30000});
  final String title, description, submitLabel;
  final int maxLength;
  @override
  State<_AddWorkDialog> createState() => _AddWorkDialogState();
}

class _AddWorkDialogState extends State<_AddWorkDialog> {
  final _text = TextEditingController();
  String? _error;
  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
          scrollable: true,
          title: Text(widget.title),
          content: SizedBox(
              width: 500,
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                Text(widget.description),
                const SizedBox(height: 16),
                TextField(
                    controller: _text,
                    minLines: 3,
                    maxLines: 8,
                    maxLength: widget.maxLength,
                    onChanged: (_) {
                      if (_error != null) setState(() => _error = null);
                    },
                    decoration: InputDecoration(
                        labelText: 'Qué querés que hagamos',
                        errorText: _error)),
              ])),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('Cancelar')),
            FilledButton(
                onPressed: () {
                  if (_text.text.trim().isEmpty) {
                    setState(() => _error = 'Escribí el encargo.');
                    return;
                  }
                  Navigator.pop(context, _text.text.trim());
                },
                child: Text(widget.submitLabel))
          ]);
}
