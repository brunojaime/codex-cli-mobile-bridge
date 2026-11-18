import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:file_picker/file_picker.dart';
import 'package:http/http.dart' as http;
import '../services/chat_notification_service.dart';
import '../services/bridge_push_endpoint.dart';

class NotificationSettingsScreen extends StatefulWidget {
  const NotificationSettingsScreen(
      {super.key,
      required this.server,
      required this.service,
      this.sessionId,
      this.projectName});
  final String server;
  final ChatNotificationService service;
  final String? sessionId;
  final String? projectName;
  @override
  State<NotificationSettingsScreen> createState() =>
      _NotificationSettingsScreenState();
}

class _NotificationSettingsScreenState
    extends State<NotificationSettingsScreen> {
  Map<String, dynamic>? _status;
  String? _error;
  bool _busy = false;
  int _logoRevision = 0;
  Timer? _timer;
  ChatPushNotificationSettings? get _push =>
      widget.service is ChatPushNotificationSettings
          ? widget.service as ChatPushNotificationSettings
          : null;
  @override
  void initState() {
    super.initState();
    unawaited(_refresh());
    _timer = Timer.periodic(const Duration(seconds: 5), (_) {
      if (!_busy && _status?['enabled'] == true && _status?['verified'] != true) {
        unawaited(_refresh());
      }
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _refresh() async {
    try {
      final status = await _push?.pushStatus(widget.server);
      if (mounted) {
        setState(() {
          _status = status;
          _error = null;
        });
      }
    } catch (error) {
      if (mounted) setState(() => _error = '$error');
    }
  }

  Future<void> _run(Future<void> Function() action) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await action();
      await _refresh();
    } catch (error) {
      if (mounted) setState(() => _error = '$error');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _uploadLogo() async {
    final result = await FilePicker.platform.pickFiles(
        type: FileType.custom,
        allowedExtensions: ['png', 'jpg', 'jpeg', 'webp'],
        withData: true);
    if (result == null) return;
    final file = result.files.single;
    if (file.bytes == null || file.size > 512 * 1024) {
      throw Exception('Elegí una imagen de hasta 512 KB.');
    }
    final request = http.MultipartRequest(
        'POST',
        Uri.parse(
            '${bridgePushServiceUrl(widget.server)}/notifications/projects/${Uri.encodeComponent(widget.sessionId!)}/logo'));
    request.files.add(http.MultipartFile.fromBytes('image', file.bytes!,
        filename: file.name));
    final response = await request.send().timeout(const Duration(seconds: 30));
    final body = await response.stream.bytesToString();
    if (response.statusCode != 200) {
      throw Exception((jsonDecode(body) as Map<String, dynamic>)['detail'] ??
          'No se pudo guardar el logo.');
    }
    if (mounted) setState(() => _logoRevision++);
  }

  @override
  Widget build(BuildContext context) {
    final enabled = _status?['enabled'] == true;
    final verified = _status?['verified'] == true;
    return Scaffold(
        appBar: AppBar(title: Text(widget.projectName == null ? 'Notificaciones' : 'Notificaciones · ${widget.projectName}',
          maxLines: 1, overflow: TextOverflow.ellipsis)),
        body: ListView(padding: const EdgeInsets.all(20), children: [
          if (widget.projectName != null) ...[
            Text(widget.projectName!, style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 8),
            if (widget.sessionId == null) const Text('Este proyecto todavía no tiene una conversación disponible. El logo se podrá configurar cuando tenga una.'),
            const SizedBox(height: 16),
          ],
          const Text('Enterate cuando tu proyecto termine',
              style: TextStyle(fontSize: 23, fontWeight: FontWeight.w700)),
          const SizedBox(height: 12),
          const Text(
              'Recibí un aviso con una vista previa cuando ya no quede nadie trabajando. Al tocarlo vas directo al mensaje. Los avisos se limpian al entrar al proyecto.'),
          const SizedBox(height: 20),
          const Text('Configuración de este teléfono · se aplica a todos los proyectos'),
          Card(
              child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                            verified && enabled
                                ? 'Este teléfono está listo'
                                : enabled
                                    ? 'Esperando el aviso de prueba'
                                    : 'Avisos con la app cerrada',
                            style: const TextStyle(
                                fontSize: 18, fontWeight: FontWeight.w600)),
                        const SizedBox(height: 8),
                        Text(verified && enabled
                            ? 'La recepción de la prueba está confirmada.'
                            : enabled
                                ? 'La recepción de la prueba habilita los avisos de tus proyectos. Mantené Tailscale conectado.'
                                : 'Activá los avisos de este teléfono y comprobá que llegan. Necesitás Tailscale conectado para abrir el contenido.'),
                        const SizedBox(height: 16),
                        if (_push == null)
                          const Text(
                              'Esta opción está disponible en la app Android.'),
                        if (_push != null && !enabled)
                          FilledButton.icon(
                              onPressed: _busy
                                  ? null
                                  : () => _run(
                                      () => _push!.enablePush(widget.server)),
                              icon: const Icon(
                                  Icons.notifications_active_outlined),
                              label: const Text('Activar y probar')),
                        if (_push != null && enabled)
                          Wrap(spacing: 12, children: [
                            FilledButton.tonal(
                                onPressed: _busy
                                    ? null
                                    : () => _run(
                                        () => _push!.testPush(widget.server)),
                                child: const Text('Enviar prueba')),
                            TextButton(
                                onPressed: _busy
                                    ? null
                                    : () => _run(() =>
                                        _push!.disablePush(widget.server)),
                                child:
                                    const Text('Desactivar en este teléfono')),
                          ]),
                      ]))),
          if (widget.sessionId != null) ...[
            const SizedBox(height: 20),
            Text(widget.projectName ?? 'Este proyecto',
                style:
                    const TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
            const SizedBox(height: 12),
            Row(children: [
              ClipRRect(
                  borderRadius: BorderRadius.circular(16),
                  child: Image.network(
                      '${bridgePushServiceUrl(widget.server)}/notifications/projects/${Uri.encodeComponent(widget.sessionId!)}/logo?v=$_logoRevision',
                      width: 64,
                      height: 64,
                      fit: BoxFit.contain,
                      errorBuilder: (_, error, stack) => const SizedBox(
                          width: 64,
                          height: 64,
                          child: Icon(Icons.folder_outlined, size: 36)))),
              const SizedBox(width: 16),
              Expanded(
                  child: TextButton.icon(
                      onPressed: _busy ? null : () => _run(_uploadLogo),
                      icon: const Icon(Icons.image_outlined),
                      label: const Text('Elegir logo del proyecto'))),
            ]),
            const Text(
                'Se usa el logo disponible en el proyecto. También podés elegir una imagen desde tu teléfono.'),
          ],
          if (_busy)
            const Padding(
                padding: EdgeInsets.all(16),
                child: Center(child: CircularProgressIndicator())),
          if (_error != null)
            Padding(
                padding: const EdgeInsets.only(top: 16),
                child: Text(_error!,
                    style:
                        TextStyle(color: Theme.of(context).colorScheme.error))),
          if (_error != null)
            TextButton(
                onPressed: _busy ? null : _refresh,
                child: const Text('Reintentar')),
        ]));
  }
}
