import 'dart:convert';
import 'package:cross_file/cross_file.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/outbox_entry.dart';

OutboxStore createOutboxStore(String server) => BrowserOutboxStore(server);

class BrowserOutboxStore implements OutboxStore {
  BrowserOutboxStore(String server) : prefix = 'message-outbox::$server::';
  final String prefix;
  @override
  Future<List<OutboxEntry>> load() async {
    final prefs = await SharedPreferences.getInstance();
    final result = prefs
        .getKeys()
        .where((key) => key.startsWith(prefix))
        .map((key) => OutboxEntry.fromJson(
            jsonDecode(prefs.getString(key)!) as Map<String, dynamic>))
        .toList();
    result.sort((a, b) => a.createdAt.compareTo(b.createdAt));
    return result;
  }

  @override
  Future<void> save(OutboxEntry entry, {XFile? audio}) async {
    if (audio != null) {
      entry.audioData = base64Encode(await audio.readAsBytes());
    }
    final prefs = await SharedPreferences.getInstance();
    if (!await prefs.setString(
        '$prefix${entry.id}', jsonEncode(entry.toJson()))) {
      throw StateError('No hay espacio para guardar el envío.');
    }
  }

  @override
  Future<void> remove(OutboxEntry entry) async {
    final prefs = await SharedPreferences.getInstance();
    if (!await prefs.remove('$prefix${entry.id}')) {
      throw StateError('No se pudo actualizar la cola.');
    }
  }

  @override
  Future<XFile> audioFile(OutboxEntry entry) async =>
      XFile.fromData(base64Decode(entry.audioData!),
          name: entry.payload['filename'] as String,
          mimeType: entry.payload['content_type'] as String?);
}
