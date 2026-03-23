class RecordingTarget {
  const RecordingTarget({
    required this.fileName,
    required this.path,
  });

  final String fileName;
  final String path;
}

Future<RecordingTarget> createRecordingTarget(String fileName) async {
  return RecordingTarget(fileName: fileName, path: fileName);
}

Future<void> cleanupRecordingTarget(String path) async {}
