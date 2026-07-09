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
    this.feedbackSourceWorkspaceAliases = const <String, String>{},
    this.supportsSdd = false,
    this.supportsProjectFactory = false,
    this.backendVersion,
    this.backendCommit,
    this.features = const <String, bool>{},
    this.speechOutputVoice,
    this.speechOutputResponseFormat,
    this.preferredClientUrl,
    this.publicBaseUrls = const <String>[],
  });

  final bool supportsAudioInput;
  final bool supportsSpeechOutput;
  final bool supportsImageInput;
  final bool supportsDocumentInput;
  final bool supportsAttachmentBatch;
  final bool supportsJobCancellation;
  final bool supportsJobRetry;
  final bool supportsPushJobStream;
  final bool supportsSdd;
  final bool supportsProjectFactory;
  final String? backendVersion;
  final String? backendCommit;
  final Map<String, bool> features;
  final String speechOutputBackend;
  final String? speechOutputVoice;
  final String? speechOutputResponseFormat;
  final int audioMaxUploadBytes;
  final int imageMaxUploadBytes;
  final int documentMaxUploadBytes;
  final int documentTextCharLimit;
  final Map<String, String> feedbackSourceWorkspaceAliases;
  final String? preferredClientUrl;
  final List<String> publicBaseUrls;

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
      supportsSdd: json['supports_sdd'] as bool? ?? false,
      supportsProjectFactory:
          json['supports_project_factory'] as bool? ?? false,
      backendVersion: json['backend_version'] as String?,
      backendCommit: json['backend_commit'] as String?,
      features: _boolMapFromJson(json['features']),
      speechOutputBackend:
          json['speech_output_backend'] as String? ?? 'disabled',
      speechOutputVoice: json['speech_output_voice'] as String?,
      speechOutputResponseFormat:
          json['speech_output_response_format'] as String?,
      audioMaxUploadBytes: json['audio_max_upload_bytes'] as int? ?? 0,
      imageMaxUploadBytes: json['image_max_upload_bytes'] as int? ?? 0,
      documentMaxUploadBytes: json['document_max_upload_bytes'] as int? ?? 0,
      documentTextCharLimit: json['document_text_char_limit'] as int? ?? 0,
      feedbackSourceWorkspaceAliases: _stringMapFromJson(
        json['feedback_source_workspace_aliases'],
      ),
      preferredClientUrl: json['preferred_client_url'] as String?,
      publicBaseUrls: _stringListFromJson(json['public_base_urls']),
    );
  }

  static Map<String, String> _stringMapFromJson(Object? value) {
    if (value is! Map) return const <String, String>{};
    return value.map(
      (key, raw) => MapEntry(key.toString(), raw?.toString() ?? ''),
    )..removeWhere((key, raw) => key.trim().isEmpty || raw.trim().isEmpty);
  }

  static List<String> _stringListFromJson(Object? value) {
    if (value is! List) return const <String>[];
    return value
        .map((item) => item?.toString() ?? '')
        .where((item) => item.trim().isNotEmpty)
        .toList(growable: false);
  }

  static Map<String, bool> _boolMapFromJson(Object? value) {
    if (value is! Map) return const <String, bool>{};
    return value.map(
      (key, raw) => MapEntry(key.toString(), raw == true),
    )..removeWhere((key, _) => key.trim().isEmpty);
  }
}
