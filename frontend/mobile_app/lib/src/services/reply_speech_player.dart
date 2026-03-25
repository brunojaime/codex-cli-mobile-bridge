String sanitizeTextForSpeech(String text) {
  return text
      .replaceAllMapped(
        RegExp(r'\[([^\]]+)\]\([^)]+\)'),
        (match) => match.group(1) ?? '',
      )
      .replaceAll(RegExp(r'```[\s\S]*?```'), ' ')
      .replaceAll('`', '')
      .replaceAll(RegExp(r'\s+'), ' ')
      .trim();
}

abstract class ReplySpeechPlayer {
  Future<bool> speak(String rawText);

  Future<void> stop();

  Future<void> dispose();
}
