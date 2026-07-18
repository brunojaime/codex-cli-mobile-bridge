import 'session_detail.dart';

class DomainFactoryStart {
  const DomainFactoryStart({
    required this.status,
    required this.session,
    this.firstMessageId,
    this.statePath,
    this.specRoot,
  });

  final String status;
  final SessionDetail session;
  final String? firstMessageId;
  final String? statePath;
  final String? specRoot;

  bool get isReady => status == 'ready';

  factory DomainFactoryStart.fromJson(Map<String, dynamic> json) {
    return DomainFactoryStart(
      status: json['status'] as String? ?? 'blocked',
      firstMessageId: json['firstMessageId'] as String?,
      statePath: json['statePath'] as String?,
      specRoot: json['specRoot'] as String?,
      session: SessionDetail.fromJson(
        json['session'] as Map<String, dynamic>,
      ),
    );
  }
}

class DomainFactoryMediaReference {
  const DomainFactoryMediaReference({
    this.id,
    this.role,
    this.kind,
    this.filename,
    this.assetId,
    this.path,
    this.url,
    this.mimeType,
    this.sha256,
    this.source,
  });

  final String? id;
  final String? role;
  final String? kind;
  final String? filename;
  final String? assetId;
  final String? path;
  final String? url;
  final String? mimeType;
  final String? sha256;
  final String? source;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      if (id != null) 'id': id,
      if (role != null) 'role': role,
      if (kind != null) 'kind': kind,
      if (filename != null) 'filename': filename,
      if (assetId != null) 'assetId': assetId,
      if (path != null) 'path': path,
      if (url != null) 'url': url,
      if (mimeType != null) 'mimeType': mimeType,
      if (sha256 != null) 'sha256': sha256,
      if (source != null) 'source': source,
    };
  }
}

class DomainFactoryIntake {
  const DomainFactoryIntake({
    required this.status,
    required this.session,
    required this.contractPreview,
    this.specRoot,
    this.briefPath,
    this.mediaReferencesPath,
    this.contractPreviewPath,
    this.messageId,
  });

  final String status;
  final SessionDetail session;
  final Map<String, dynamic> contractPreview;
  final String? specRoot;
  final String? briefPath;
  final String? mediaReferencesPath;
  final String? contractPreviewPath;
  final String? messageId;

  bool get isImplementationReady => status == 'implementation_ready';

  factory DomainFactoryIntake.fromJson(Map<String, dynamic> json) {
    return DomainFactoryIntake(
      status: json['status'] as String? ?? 'blocked',
      specRoot: json['specRoot'] as String?,
      briefPath: json['briefPath'] as String?,
      mediaReferencesPath: json['mediaReferencesPath'] as String?,
      contractPreviewPath: json['contractPreviewPath'] as String?,
      messageId: json['messageId'] as String?,
      contractPreview: (json['contractPreview'] as Map?)?.map(
            (key, value) => MapEntry(key.toString(), value),
          ) ??
          const <String, dynamic>{},
      session: SessionDetail.fromJson(
        json['session'] as Map<String, dynamic>,
      ),
    );
  }
}

class DomainFactoryImplementation {
  const DomainFactoryImplementation({
    required this.status,
    required this.session,
    this.specRoot,
    this.workflowEvidencePath,
    this.messageId,
  });

  final String status;
  final SessionDetail session;
  final String? specRoot;
  final String? workflowEvidencePath;
  final String? messageId;

  bool get isImplementing => status == 'implementing';

  factory DomainFactoryImplementation.fromJson(Map<String, dynamic> json) {
    return DomainFactoryImplementation(
      status: json['status'] as String? ?? 'blocked',
      specRoot: json['specRoot'] as String?,
      workflowEvidencePath: json['workflowEvidencePath'] as String?,
      messageId: json['messageId'] as String?,
      session: SessionDetail.fromJson(
        json['session'] as Map<String, dynamic>,
      ),
    );
  }
}

class DomainFactoryReleaseEvidence {
  const DomainFactoryReleaseEvidence({
    required this.status,
    required this.ok,
    required this.specRoot,
    required this.releaseEvidencePath,
    required this.statePath,
    required this.validation,
    required this.errors,
    this.sourceApp,
  });

  final String status;
  final bool ok;
  final String? sourceApp;
  final String specRoot;
  final String releaseEvidencePath;
  final String statePath;
  final Map<String, dynamic> validation;
  final List<Map<String, dynamic>> errors;

  bool get isReady => ok && status == 'ready';

  factory DomainFactoryReleaseEvidence.fromJson(Map<String, dynamic> json) {
    return DomainFactoryReleaseEvidence(
      status: json['status'] as String? ?? 'blocked',
      ok: json['ok'] as bool? ?? false,
      sourceApp: json['sourceApp'] as String?,
      specRoot: json['specRoot'] as String? ?? '',
      releaseEvidencePath: json['releaseEvidencePath'] as String? ?? '',
      statePath: json['statePath'] as String? ?? '',
      validation: (json['validation'] as Map?)?.map(
            (key, value) => MapEntry(key.toString(), value),
          ) ??
          const <String, dynamic>{},
      errors: ((json['errors'] as List<dynamic>?) ?? const <dynamic>[])
          .whereType<Map>()
          .map(
            (item) => item.map(
              (key, value) => MapEntry(key.toString(), value),
            ),
          )
          .toList(growable: false),
    );
  }
}
