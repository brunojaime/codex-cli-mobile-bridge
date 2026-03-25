class ServerCapabilities {
  const ServerCapabilities({
    required this.supportsAudioInput,
    required this.supportsSpeechOutput,
    required this.supportsImageInput,
    required this.supportsDocumentInput,
    required this.supportsAttachmentBatch,
    required this.supportsJobCancellation,
    required this.supportsJobRetry,
    required this.supportsPushJobStream,
    required this.speechOutputBackend,
    required this.audioMaxUploadBytes,
    required this.imageMaxUploadBytes,
    required this.documentMaxUploadBytes,
    required this.documentTextCharLimit,
    this.speechOutputVoice,
    this.speechOutputResponseFormat,
  });

  final bool supportsAudioInput;
  final bool supportsSpeechOutput;
  final bool supportsImageInput;
  final bool supportsDocumentInput;
  final bool supportsAttachmentBatch;
  final bool supportsJobCancellation;
  final bool supportsJobRetry;
  final bool supportsPushJobStream;
  final String speechOutputBackend;
  final String? speechOutputVoice;
  final String? speechOutputResponseFormat;
  final int audioMaxUploadBytes;
  final int imageMaxUploadBytes;
  final int documentMaxUploadBytes;
  final int documentTextCharLimit;

  factory ServerCapabilities.fromJson(Map<String, dynamic> json) {
    return ServerCapabilities(
      supportsAudioInput: json['supports_audio_input'] as bool? ?? false,
      supportsSpeechOutput: json['supports_speech_output'] as bool? ?? false,
      supportsImageInput: json['supports_image_input'] as bool? ?? false,
      supportsDocumentInput: json['supports_document_input'] as bool? ?? false,
      supportsAttachmentBatch:
          json['supports_attachment_batch'] as bool? ?? false,
      supportsJobCancellation:
          json['supports_job_cancellation'] as bool? ?? false,
      supportsJobRetry: json['supports_job_retry'] as bool? ?? false,
      supportsPushJobStream: json['supports_push_job_stream'] as bool? ?? false,
      speechOutputBackend:
          json['speech_output_backend'] as String? ?? 'disabled',
      speechOutputVoice: json['speech_output_voice'] as String?,
      speechOutputResponseFormat:
          json['speech_output_response_format'] as String?,
      audioMaxUploadBytes: json['audio_max_upload_bytes'] as int? ?? 0,
      imageMaxUploadBytes: json['image_max_upload_bytes'] as int? ?? 0,
      documentMaxUploadBytes: json['document_max_upload_bytes'] as int? ?? 0,
      documentTextCharLimit: json['document_text_char_limit'] as int? ?? 0,
    );
  }
}
