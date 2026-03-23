import 'dart:typed_data';

class ClipboardImagePastePayload {
  const ClipboardImagePastePayload({
    required this.bytes,
    required this.fileName,
    required this.mimeType,
  });

  final Uint8List bytes;
  final String fileName;
  final String mimeType;
}

class ClipboardImagePasteListener {
  const ClipboardImagePasteListener();

  void dispose() {}
}

ClipboardImagePasteListener attachClipboardImagePasteListener({
  required bool Function() canHandlePaste,
  required Future<void> Function(List<ClipboardImagePastePayload> images)
      onImagesPasted,
}) {
  return const ClipboardImagePasteListener();
}
