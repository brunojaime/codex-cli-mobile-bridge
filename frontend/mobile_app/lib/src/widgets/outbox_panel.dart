import 'package:flutter/material.dart';
import '../models/outbox_entry.dart';

class OutboxPanel extends StatelessWidget {
  const OutboxPanel(
      {super.key,
      required this.entries,
      required this.sessionTitle,
      required this.onRetry,
      required this.onDiscard,
      this.storageError});
  final List<OutboxEntry> entries;
  final String Function(String) sessionTitle;
  final Future<void> Function(String) onRetry;
  final Future<void> Function(String) onDiscard;
  final String? storageError;

  @override
  Widget build(BuildContext context) {
    if (entries.isEmpty && storageError == null) return const SizedBox.shrink();
    final failures = entries.where((entry) => entry.needsAttention).length;
    return Material(
      color: const Color(0xFF17232B),
      child: ExpansionTile(
        key: const PageStorageKey('message-outbox'),
        leading: Icon(
            failures > 0 || storageError != null
                ? Icons.error_outline
                : Icons.cloud_upload_outlined,
            color: failures > 0 ? Colors.orangeAccent : null),
        title: Text(
            storageError ??
                '${entries.length} envío${entries.length == 1 ? '' : 's'} pendiente${entries.length == 1 ? '' : 's'}${failures == 0 ? '' : ' · $failures para revisar'}',
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontSize: 13)),
        subtitle: const Text('Podés seguir escribiendo o cambiar de proyecto',
            style: TextStyle(fontSize: 11)),
        children: [
          ConstrainedBox(
            constraints: const BoxConstraints(maxHeight: 180),
            child: ListView.builder(
              key: const PageStorageKey('message-outbox-scroll'),
              shrinkWrap: true,
              itemCount: entries.length,
              itemBuilder: (context, index) {
                final entry = entries[index];
                final message = entry.isAudio
                    ? 'Audio'
                    : entry.payload['message'] as String;
                return ListTile(
                  dense: true,
                  title: Text(
                      '${sessionTitle(entry.sessionId)} · ${entry.label}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis),
                  subtitle: Text(entry.error ?? message,
                      maxLines: 2, overflow: TextOverflow.ellipsis),
                  trailing: entry.needsAttention ||
                          entry.state == 'waiting_connection'
                      ? Row(mainAxisSize: MainAxisSize.min, children: [
                          if (entry.state != 'uncertain')
                            IconButton(
                                tooltip: 'Reintentar envío',
                                icon: const Icon(Icons.refresh),
                                onPressed: () => onRetry(entry.id)),
                          IconButton(
                              tooltip: 'Descartar envío',
                              icon: const Icon(Icons.delete_outline),
                              onPressed: () async {
                                final discard = await showDialog<bool>(
                                    context: context,
                                    builder: (context) => AlertDialog(
                                            title: const Text(
                                                '¿Descartar este envío?'),
                                            content: Text(entry.state ==
                                                    'uncertain'
                                                ? 'La entrega es incierta. Revisá primero si el mensaje ya está en el chat. Descartarlo libera los mensajes siguientes y no cancela una ejecución existente.'
                                                : 'Se quitará de la cola y podrán avanzar los mensajes siguientes de esta conversación.'),
                                            actions: [
                                              TextButton(
                                                  onPressed: () =>
                                                      Navigator.pop(
                                                          context, false),
                                                  child: const Text('Volver')),
                                              TextButton(
                                                  onPressed: () =>
                                                      Navigator.pop(
                                                          context, true),
                                                  child:
                                                      const Text('Descartar')),
                                            ]));
                                if (discard == true) await onDiscard(entry.id);
                              }),
                        ])
                      : null,
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}
