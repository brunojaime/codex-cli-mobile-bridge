import 'dart:convert';
import 'dart:io';
import 'package:cross_file/cross_file.dart';
import 'package:path_provider/path_provider.dart';
import '../models/outbox_entry.dart';

OutboxStore createOutboxStore(String server) => FileOutboxStore(server);

class FileOutboxStore implements OutboxStore {
  FileOutboxStore(this.server, {this.rootDirectory});
  final String server;
  final String? rootDirectory;
  Future<Directory> _directory() async {
    final root = rootDirectory ?? (await getApplicationSupportDirectory()).path;
    final key = base64Url.encode(utf8.encode(server)).replaceAll('=', '');
    return Directory('$root/message-outbox/$key').create(recursive: true);
  }

  @override
  Future<List<OutboxEntry>> load() async {
    final directory = await _directory();
    final entries = <OutboxEntry>[];
    await for (final file in directory.list()) {
      if (file is File && file.path.endsWith('.json')) {
        // A damaged record is reported rather than silently dropping a message.
        entries.add(OutboxEntry.fromJson(
            jsonDecode(await file.readAsString()) as Map<String, dynamic>));
      }
    }
    entries.sort((a, b) => a.createdAt.compareTo(b.createdAt));
    return entries;
  }

  @override
  Future<void> save(OutboxEntry entry, {XFile? audio}) async {
    final directory = await _directory();
    if (audio != null) {
      final target = File('${directory.path}/${entry.id}.audio');
      final sink = target.openWrite();
      try {
        await sink.addStream(audio.openRead());
        await sink.flush();
      } finally {
        await sink.close();
      }
      // Explicit flush before the durable record becomes visible.
      final handle = await target.open(mode: FileMode.append);
      try {
        await handle.flush();
      } finally {
        await handle.close();
      }
      entry.audioPath = target.path;
    }
    final temp = File('${directory.path}/${entry.id}.json.tmp');
    await temp.writeAsString(jsonEncode(entry.toJson()), flush: true);
    await temp.rename('${directory.path}/${entry.id}.json');
  }

  @override
  Future<void> remove(OutboxEntry entry) async {
    final directory = await _directory();
    final record = File('${directory.path}/${entry.id}.json');
    if (await record.exists()) await record.delete();
    // Record first: an interrupted cleanup leaves only an unused audio file.
    final audio = File('${directory.path}/${entry.id}.audio');
    if (await audio.exists()) await audio.delete();
  }

  @override
  Future<XFile> audioFile(OutboxEntry entry) async => XFile(entry.audioPath!,
      name: entry.payload['filename'] as String,
      mimeType: entry.payload['content_type'] as String?);
}
