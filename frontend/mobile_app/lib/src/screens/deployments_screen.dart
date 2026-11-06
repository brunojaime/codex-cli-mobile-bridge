import 'package:flutter/material.dart';
import '../services/work_client.dart';

class DeploymentsScreen extends StatefulWidget {
  const DeploymentsScreen(
      {super.key, required this.client, this.workspacePath, this.projectName});
  final WorkClient client;
  final String? workspacePath;
  final String? projectName;

  @override
  State<DeploymentsScreen> createState() => _DeploymentsScreenState();
}

class _DeploymentsScreenState extends State<DeploymentsScreen> {
  List<Map<String, dynamic>> _projects = [];
  bool _loading = true;
  String? _error;
  String _query = '';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data =
          await widget.client.deployments(workspacePath: widget.workspacePath);
      if (mounted) {
        setState(() => _projects =
            (data['projects'] as List).cast<Map<String, dynamic>>());
      }
    } catch (_) {
      if (mounted) {
        setState(
            () => _error = 'No se pudieron consultar los deploys. Reintentá.');
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final projects = _projects
        .where((p) => '${p['name']} ${p['workspace_path']}'
            .toLowerCase()
            .contains(_query))
        .toList();
    return Scaffold(
      appBar: AppBar(
          title: Text(
              widget.projectName == null
                  ? 'Deploys · Workspace'
                  : 'Deploys · ${widget.projectName}',
              maxLines: 1,
              overflow: TextOverflow.ellipsis),
          actions: [
            IconButton(
                tooltip: 'Actualizar',
                onPressed: _loading ? null : _load,
                icon: const Icon(Icons.refresh)),
          ]),
      body: Center(
          child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 960),
              child: Column(children: [
                if (_loading) const LinearProgressIndicator(),
                if (widget.workspacePath == null)
                  Padding(
                      padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
                      child: TextField(
                          decoration: const InputDecoration(
                              labelText: 'Buscar proyecto',
                              prefixIcon: Icon(Icons.search),
                              border: OutlineInputBorder()),
                          onChanged: (value) => setState(
                              () => _query = value.trim().toLowerCase()))),
                const Padding(
                    padding: EdgeInsets.all(16),
                    child: Text(
                        'Última publicación registrada por ambiente. La fecha corresponde al comprobante; no es un chequeo de disponibilidad actual.')),
                if (_error != null)
                  Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(children: [
                        Text(_error!,
                            style: TextStyle(
                                color: Theme.of(context).colorScheme.error)),
                        TextButton(
                            onPressed: _load, child: const Text('Reintentar')),
                        if (_projects.isNotEmpty)
                          const Text(
                              'Los datos visibles son de la consulta anterior.'),
                      ])),
                Expanded(
                    child: !_loading && _error == null && projects.isEmpty
                        ? Center(
                            child: Text(_query.isEmpty
                                ? 'No hay proyectos para mostrar.'
                                : 'No hay proyectos que coincidan.'))
                        : ListView.builder(
                            padding: const EdgeInsets.fromLTRB(12, 0, 12, 24),
                            itemCount: projects.length,
                            itemBuilder: (_, index) =>
                                _ProjectDeployments(project: projects[index]))),
              ]))),
    );
  }
}

class _ProjectDeployments extends StatelessWidget {
  const _ProjectDeployments({required this.project});
  final Map<String, dynamic> project;

  @override
  Widget build(BuildContext context) {
    final errors = (project['errors'] as List? ?? []).cast<String>();
    final comparison = switch (project['comparison']) {
      'same' => 'Mismo release en Dev, QA y Pro',
      'partial_same' => 'Mismo release · faltan ambientes',
      'different' => 'Releases diferentes',
      'unknown' => 'Sin trazabilidad suficiente para comparar',
      _ => 'Sin publicaciones suficientes para comparar',
    };
    return Card(
        margin: const EdgeInsets.only(bottom: 12),
        child: Padding(
            padding: const EdgeInsets.all(16),
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(project['name'] as String,
                  style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 6),
              Text(comparison,
                  style: TextStyle(
                      color: project['comparison'] == 'different'
                          ? Theme.of(context).colorScheme.error
                          : Theme.of(context).colorScheme.onSurfaceVariant)),
              for (final error in errors)
                Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Text(error,
                        style: TextStyle(
                            color: Theme.of(context).colorScheme.error))),
              const SizedBox(height: 8),
              for (final env in (project['environments'] as List)
                  .cast<Map<String, dynamic>>())
                _EnvironmentRow(environment: env, uncertain: errors.isNotEmpty),
            ])));
  }
}

String _date(dynamic value) {
  final date = DateTime.tryParse('$value')?.toLocal();
  if (date == null) return 'Fecha no disponible';
  String two(int n) => n.toString().padLeft(2, '0');
  return '${two(date.day)}/${two(date.month)}/${date.year} ${two(date.hour)}:${two(date.minute)}';
}

String _identity(Map<String, dynamic> record) {
  final commit = record['commit'] as String?;
  return [
    if (record['release'] != null) '${record['release']}',
    if (commit != null) commit.substring(0, 8)
  ].join(' · ');
}

String _status(dynamic value) => switch (value) {
      'published' => 'Publicado',
      'deploying' => 'En curso',
      'failed' => 'Falló',
      'disabled' => 'Desactivado',
      'expired' => 'Vencido',
      _ => 'Sin registro',
    };

class _EnvironmentRow extends StatelessWidget {
  const _EnvironmentRow({required this.environment, required this.uncertain});
  final Map<String, dynamic> environment;
  final bool uncertain;

  @override
  Widget build(BuildContext context) {
    final current = environment['current'] as Map<String, dynamic>?;
    final latest = environment['latest'] as Map<String, dynamic>?;
    final history =
        (environment['history'] as List).cast<Map<String, dynamic>>();
    final label = switch (environment['name']) {
      'dev' => 'Dev',
      'qa' => 'QA',
      _ => 'Pro'
    };
    final identity = current == null ? '' : _identity(current);
    final subtitle = current == null
        ? uncertain
            ? '— Sin datos confirmados'
            : latest == null
                ? '— Sin deploy registrado'
                : '— Sin publicación activa'
        : '${identity.isEmpty ? 'Sin versión trazada' : identity}\n${_date(current['deployed_at'])} · Publicado';
    final content =
        Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(subtitle),
      if (latest != null && latest['id'] != current?['id'])
        Text(
            'Último intento: ${_status(latest['status'])} · ${_date(latest['deployed_at'])}',
            style: TextStyle(
                color: latest['status'] == 'failed'
                    ? Theme.of(context).colorScheme.error
                    : null)),
    ]);
    return Column(children: [
      const Divider(height: 16),
      if (history.isEmpty)
        Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              SizedBox(
                  width: 48,
                  child: Text(label,
                      style: const TextStyle(fontWeight: FontWeight.w700))),
              Expanded(child: content),
            ]))
      else
        ExpansionTile(
            tilePadding: EdgeInsets.zero,
            childrenPadding: const EdgeInsets.only(left: 48),
            title: Text(label,
                style: const TextStyle(fontWeight: FontWeight.w700)),
            subtitle: content,
            children: [
              for (final record in history)
                ListTile(
                    dense: true,
                    contentPadding: EdgeInsets.zero,
                    title: Text(
                        '${_status(record['status'])} · ${_identity(record).isEmpty ? 'Sin versión trazada' : _identity(record)}'),
                    subtitle: Text(
                        '${_date(record['deployed_at'])} · ${switch (record['source']) {
                      'delivery' => 'Entrega verificada',
                      'preview' => 'Preview',
                      _ => 'Registro del proyecto'
                    }}\n${record['id']}'))
            ]),
    ]);
  }
}
