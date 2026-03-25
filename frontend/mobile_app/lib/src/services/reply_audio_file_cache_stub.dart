Future<String> cacheReplyAudioFile(
  List<int> bytes, {
  required String fileExtension,
}) async {
  throw UnsupportedError('Local reply audio caching is unavailable.');
}

Future<void> deleteReplyAudioFile(String path) async {}
