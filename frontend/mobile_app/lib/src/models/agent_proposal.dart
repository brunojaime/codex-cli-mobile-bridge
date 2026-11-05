class AgentProposal {
  AgentProposal(this.data);
  final Map<String, dynamic> data;
  String get id => data['id'] as String;
  int get revision => data['revision'] as int;
  String get title => data['title'] as String;
  String get summary => data['summary'] as String;
  String get rationale => data['rationale'] as String;
  String get workspaceName => data['workspace_name'] as String;
  String get status => data['status'] as String;
  bool get unread => data['unread'] == true;
  bool get canRespond => status == 'pending';
  String? get sessionId => data['session_id'] as String?;
  String get observations => data['observations'] as String? ?? '';
  String? get problem => data['problem'] as String?;
  int get generatorTurns => data['generator_turns'] as int;
  int get reviewerTurns => data['reviewer_turns'] as int;
  List<String> get evidence => (data['evidence'] as List).cast<String>();
  String get kickoff => data['kickoff'] as String;
  String get statusLabel => switch (status) {
        'pending' => 'Pendiente',
        'needs_revision' => 'Esperando revisión',
        'rejected' => 'Rechazada',
        'started' => 'Trabajo iniciado',
        'preparing' || 'starting' => 'Preparando trabajo',
        'uncertain' => 'Arranque sin confirmar',
        'failed' => 'No se pudo iniciar',
        _ => status,
      };
}
