import 'dart:async';
import 'package:flutter/material.dart';
import '../services/work_client.dart';

class WorkScreen extends StatefulWidget {
  const WorkScreen(
      {super.key,
      required this.baseUrl,
      this.workspacePath,
      this.onOpenChat,
      this.clientOverride});
  final String baseUrl;
  final String? workspacePath;
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

  Future<void> _add() async {
    final text = await showDialog<String>(
        context: context, builder: (_) => const _AddWorkDialog());
    if (text == null || !mounted) return;
    await _act(() async {
      await _client.enqueue(widget.workspacePath!, text);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            content: Text(
                'Agregado al backlog. Se tomará al completar el trabajo anterior.')));
      }
    });
  }

  List<Map<String, dynamic>> get _projects =>
      ((_data?['projects'] as List?) ?? []).cast<Map<String, dynamic>>();
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
      length: 3,
      child: Scaffold(
        appBar: AppBar(
            title: const Text('Trabajo de proyectos'),
            actions: [
              IconButton(
                  tooltip: 'Actualizar',
                  onPressed: _refresh,
                  icon: const Icon(Icons.refresh))
            ],
            bottom: const TabBar(tabs: [
              Tab(text: 'Backlog'),
              Tab(text: 'Tu noche'),
              Tab(text: 'Decisiones')
            ])),
        floatingActionButton: widget.workspacePath == null
            ? null
            : FloatingActionButton.extended(
                onPressed: _acting ? null : _add,
                icon: const Icon(Icons.add),
                label: const Text('Agregar tarea')),
        body: Column(children: [
          if (_loading) const LinearProgressIndicator(),
          if (_error != null)
            Padding(padding: const EdgeInsets.all(12), child: Text(_error!)),
          Expanded(
              child:
                  TabBarView(children: [_backlog(), _night(), _questions()])),
        ]),
      ));
  Widget _list(List<Widget> children) => Center(
      child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 840),
          child: ListView(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 100),
              children: children)));
  Widget _backlog() => _list([
        if (_projects.isEmpty && !_loading)
          const Padding(
              padding: EdgeInsets.all(24),
              child: Text(
                  'Todavía no hay encargos. Podés usar «Agregar tarea» o escribir /backlog seguido del pedido en el chat del proyecto.')),
        for (final project in _projects) ...[
          Text(project['name'] as String,
              style: Theme.of(context).textTheme.titleLarge),
          if (project['policy'] == null)
            const Padding(
                padding: EdgeInsets.symmetric(vertical: 8),
                child: Text(
                    'Los encargos se conservan. Falta configurar el procedimiento DEV de este proyecto.')),
          if (project['policy'] != null)
            Row(children: [
              Expanded(
                  child: Text((project['policy'] as Map)['enabled'] == true
                      ? 'Cola habilitada'
                      : 'Nuevos encargos pausados')),
              TextButton(
                  onPressed: _acting
                      ? null
                      : () => _act(() => _client.policy(
                          Map<String, dynamic>.from(project['policy'] as Map)
                            ..['enabled'] =
                                !(project['policy'] as Map)['enabled'])),
                  child: Text((project['policy'] as Map)['enabled'] == true
                      ? 'Pausar nuevos'
                      : 'Reanudar'))
            ]),
          if (project['active'] != null)
            _task(Map<String, dynamic>.from(project['active'] as Map)),
          for (final task in (project['queue'] as List))
            _task(Map<String, dynamic>.from(task as Map)),
          const SizedBox(height: 24),
        ],
      ]);
  Widget _task(Map<String, dynamic> task) => Card(
      child: Padding(
          padding: const EdgeInsets.all(16),
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(
                (task['title'] as String?)?.isNotEmpty == true
                    ? task['title'] as String
                    : (task['instruction'] as String).split('\n').first,
                style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            Text('${_label(task['status'] as String)} · ${task['source']}'),
            if (task['problem'] != null)
              Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text(task['problem'] as String)),
            if (task['receipt'] != null)
              Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: SelectableText(
                      'Git remoto confirmado · DEV comprobado\n${(task['receipt'] as Map)['dev_url']}')),
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
          ])));
  Widget _night() {
    final summary = (_data?['night'] ?? _data?['summary']) as Map? ?? {};
    final projects = _allProjects ? _projects : _projects.take(3);
    return _list([
      Text('Tu noche', style: Theme.of(context).textTheme.headlineSmall),
      const SizedBox(height: 8),
      Text(
          '${summary['completed'] ?? 0} avances en DEV · ${summary['blocked'] ?? 0} bloqueos · ${(_data?['questions'] as List?)?.length ?? 0} por decidir'),
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
        if (((_data?['questions'] as List?) ?? []).isEmpty)
          const Padding(
              padding: EdgeInsets.all(24),
              child: Text('No hay decisiones pendientes.')),
        for (final question in ((_data?['questions'] as List?) ?? []))
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
