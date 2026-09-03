const Set<String> _cadMimeTypes = <String>{
  'application/acad',
  'application/autocad_dwg',
  'application/dwg',
  'application/dxf',
  'application/x-acad',
  'application/x-autocad',
  'application/x-dwg',
  'application/x-dxf',
  'drawing/dwg',
  'drawing/x-dwg',
  'drawing/x-dxf',
  'image/vnd.dwg',
  'image/vnd.dxf',
  'image/x-dwg',
  'image/x-dxf',
};

bool isCadAttachment({required String fileName, String? mimeType}) {
  final normalizedName = fileName.trim().toLowerCase();
  if (normalizedName.endsWith('.dxf') || normalizedName.endsWith('.dwg')) {
    return true;
  }
  final normalizedMimeType = mimeType?.split(';').first.trim().toLowerCase();
  return _cadMimeTypes.contains(normalizedMimeType);
}
