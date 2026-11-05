import 'package:flutter/material.dart';
import '../services/work_client.dart';

class ProjectWorkSettingsScreen extends StatefulWidget {
  const ProjectWorkSettingsScreen({super.key, required this.client});
  final WorkClient client;

  @override
  State<ProjectWorkSettingsScreen> createState() =>
      _ProjectWorkSettingsScreenState();
}

class _ProjectWorkSettingsScreenState extends State<ProjectWorkSettingsScreen> {
  List<Map<String, dynamic>> _projects = [];
  final Set<String> _saving = {};
  bool _loading = true;
  String? _error;
  String _query = '';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final result = await widget.client.projectSettings();
      if (!mounted) return;
      setState(() {
        _projects = (result['projects'] as List).cast<Map<String, dynamic>>();
        _error = null;
      });
    } catch (_) {
      if (mounted) {
        setState(
            () => _error = 'No se pudo cargar la configuración. Reintentá.');
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _toggle(Map<String, dynamic> project, bool enabled) async {
    final workspace = project['workspace_path'] as String;
    if (_saving.contains(workspace)) return;
    setState(() => _saving.add(workspace));
    try {
      await widget.client
          .updateProjectSettings(workspace, {'automatic_execution': enabled});
      await _load();
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            content: Text('No se pudo guardar el cambio. Reintentá.')));
      }
    } finally {
      if (mounted) setState(() => _saving.remove(workspace));
    }
  }

  String _status(Map<String, dynamic> project) =>
      switch (project['execution_status']) {
        'enabled' =>
          'Activada · toma el próximo encargo al terminar el anterior',
        'needs_setup' =>
          'Activada · pendiente de preparar la publicación en DEV',
        _ => 'Desactivada · los encargos quedan guardados',
      };

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Automatización'), actions: [
          IconButton(
              tooltip: 'Actualizar',
              onPressed: _load,
              icon: const Icon(Icons.refresh)),
        ]),
        body: Center(
            child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 840),
          child: Column(children: [
            if (_loading) const LinearProgressIndicator(),
            const Padding(
                padding: EdgeInsets.all(16),
                child: Text(
                  'Elegí qué proyectos pueden ejecutar su backlog automáticamente, de día y de noche. Al desactivar, la tarea en curso puede terminar.',
                )),
            Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: TextField(
                  decoration: const InputDecoration(
                      labelText: 'Buscar proyecto',
                      prefixIcon: Icon(Icons.search),
                      border: OutlineInputBorder()),
                  onChanged: (value) =>
                      setState(() => _query = value.trim().toLowerCase()),
                )),
            if (_error != null)
              Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(children: [
                    Text(_error!),
                    TextButton(
                        onPressed: _load, child: const Text('Reintentar')),
                  ])),
            Expanded(
                child: ListView(padding: const EdgeInsets.all(8), children: [
              for (final project in _projects.where(
                  (p) => (p['name'] as String).toLowerCase().contains(_query)))
                Card(
                    child: SwitchListTile.adaptive(
                  title: Text(project['name'] as String),
                  subtitle: Padding(
                      padding: const EdgeInsets.only(top: 6),
                      child: Text(_status(project))),
                  value: (project['settings'] as Map)['automatic_execution'] ==
                      true,
                  onChanged: _saving.contains(project['workspace_path'])
                      ? null
                      : (value) => _toggle(project, value),
                  secondary: _saving.contains(project['workspace_path'])
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2))
                      : const Icon(Icons.auto_mode),
                )),
              if (!_loading && _error == null && _projects.isEmpty)
                const Padding(
                    padding: EdgeInsets.all(24),
                    child: Text('Todavía no hay proyectos disponibles.')),
            ])),
          ]),
        )),
      );
}
