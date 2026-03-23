import 'dart:async';
import 'dart:js_interop';
import 'dart:typed_data';

import 'package:web/web.dart' as web;

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
  ClipboardImagePasteListener(this._dispose);

  final void Function() _dispose;

  void dispose() {
    _dispose();
  }
}

ClipboardImagePasteListener attachClipboardImagePasteListener({
  required bool Function() canHandlePaste,
  required Future<void> Function(List<ClipboardImagePastePayload> images)
      onImagesPasted,
}) {
  late final web.EventListener listener;
  listener = ((web.Event event) {
    if (!canHandlePaste()) {
      return;
    }

    final clipboardEvent = event as web.ClipboardEvent;
    final items = clipboardEvent.clipboardData?.items;
    if (items == null || items.length == 0) {
      return;
    }

    final imageFiles = <web.File>[];
    for (var index = 0; index < items.length; index += 1) {
      final item = items[index];
      if (item.kind != 'file' ||
          !item.type.toLowerCase().startsWith('image/')) {
        continue;
      }

      final file = item.getAsFile();
      if (file != null) {
        imageFiles.add(file);
      }
    }

    if (imageFiles.isEmpty) {
      return;
    }

    event.preventDefault();
    unawaited(() async {
      final pastedImages = <ClipboardImagePastePayload>[];
      for (var index = 0; index < imageFiles.length; index += 1) {
        final payload =
            await _readClipboardImagePayload(imageFiles[index], index: index);
        if (payload != null) {
          pastedImages.add(payload);
        }
      }
      if (pastedImages.isEmpty) {
        return;
      }
      await onImagesPasted(pastedImages);
    }());
  }).toJS;

  web.document.addEventListener('paste', listener);
  return ClipboardImagePasteListener(() {
    web.document.removeEventListener('paste', listener);
  });
}

Future<ClipboardImagePastePayload?> _readClipboardImagePayload(
  web.File file, {
  required int index,
}) async {
  final arrayBuffer = await file.arrayBuffer().toDart;
  final bytes = arrayBuffer.toDart.asUint8List();
  if (bytes.isEmpty) {
    return null;
  }

  final mimeType = file.type.isEmpty ? 'image/png' : file.type;
  final extension = _fileExtensionForMimeType(mimeType);
  final baseName = file.name.trim().isEmpty ? 'pasted-image' : file.name.trim();
  final normalizedName = baseName.contains('.')
      ? baseName
      : '$baseName-${DateTime.now().millisecondsSinceEpoch + index}.$extension';

  return ClipboardImagePastePayload(
    bytes: bytes,
    fileName: normalizedName,
    mimeType: mimeType,
  );
}

String _fileExtensionForMimeType(String mimeType) {
  switch (mimeType.toLowerCase()) {
    case 'image/jpeg':
      return 'jpg';
    case 'image/gif':
      return 'gif';
    case 'image/webp':
      return 'webp';
    case 'image/bmp':
      return 'bmp';
    case 'image/tiff':
      return 'tiff';
    default:
      return 'png';
  }
}
