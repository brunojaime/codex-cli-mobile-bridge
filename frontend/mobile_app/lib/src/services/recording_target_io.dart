import 'dart:io';

class RecordingTarget {
  const RecordingTarget({
    required this.fileName,
    required this.path,
  });

  final String fileName;
  final String path;
}

Future<RecordingTarget> createRecordingTarget(String fileName) async {
  final directory = await Directory.systemTemp.createTemp('codex-voice-note-');
  final path = '${directory.path}${Platform.pathSeparator}$fileName';
  return RecordingTarget(fileName: fileName, path: path);
}

Future<void> cleanupRecordingTarget(String path) async {
  final file = File(path);
  if (await file.exists()) {
    await file.delete();
  }

  final parent = file.parent;
  if (await parent.exists()) {
    await parent.delete(recursive: true);
  }
}
