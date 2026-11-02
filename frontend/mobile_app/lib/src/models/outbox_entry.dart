import 'package:cross_file/cross_file.dart';

class OutboxEntry {
  OutboxEntry(
      {required this.id,
      required this.payload,
      required this.createdAt,
      this.state = 'queued',
      this.error,
      this.audioPath,
      this.audioData,
      this.receiptKnown = false,
      this.job});

  final String id;
  final Map<String, dynamic> payload;
  final DateTime createdAt;
  String state;
  String? error;
  String? audioPath;
  String? audioData;
  bool receiptKnown;
  Map<String, dynamic>? job;

  String get sessionId => payload['session_id'] as String;
  bool get isAudio => payload['kind'] == 'audio';
  bool get needsAttention => state == 'failed' || state == 'uncertain';
  bool get isAccepted => state == 'accepted';
  String get label => switch (state) {
        'queued' => 'En cola',
        'uploading' => 'Subiendo',
        'transcribing' => 'Transcribiendo',
        'submitting' => 'Entregando',
        'waiting_connection' => 'Esperando conexión',
        'failed' => 'No se pudo enviar',
        'uncertain' => 'Revisar entrega',
        'accepted' => 'Entregado',
        _ => 'En cola',
      };
  Map<String, dynamic> toJson() => {
        'id': id,
        'payload': payload,
        'created_at': createdAt.toIso8601String(),
        'state': state,
        'error': error,
        'audio_path': audioPath,
        'audio_data': audioData,
        'receipt_known': receiptKnown,
        'job': job,
      };
  factory OutboxEntry.fromJson(Map<String, dynamic> json) => OutboxEntry(
        id: json['id'] as String,
        payload: Map<String, dynamic>.from(json['payload'] as Map),
        createdAt: DateTime.parse(json['created_at'] as String),
        state: json['state'] as String,
        error: json['error'] as String?,
        audioPath: json['audio_path'] as String?,
        audioData: json['audio_data'] as String?,
        receiptKnown: json['receipt_known'] == true,
        job: json['job'] == null
            ? null
            : Map<String, dynamic>.from(json['job'] as Map),
      );
}

abstract class OutboxStore {
  Future<List<OutboxEntry>> load();
  Future<void> save(OutboxEntry entry, {XFile? audio});
  Future<void> remove(OutboxEntry entry);
  Future<XFile> audioFile(OutboxEntry entry);
}
