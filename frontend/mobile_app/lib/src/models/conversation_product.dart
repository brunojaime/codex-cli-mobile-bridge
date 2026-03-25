class ConversationProduct {
  const ConversationProduct({
    required this.statusLine,
    required this.description,
    this.latestUpdate,
    this.currentFocus,
    this.nextStep,
  });

  final String statusLine;
  final String description;
  final String? latestUpdate;
  final String? currentFocus;
  final String? nextStep;

  factory ConversationProduct.fromJson(Map<String, dynamic> json) {
    return ConversationProduct(
      statusLine: json['status_line'] as String? ?? 'Ready for the next turn',
      description: json['description'] as String? ?? 'No messages yet.',
      latestUpdate: json['latest_update'] as String?,
      currentFocus: json['current_focus'] as String?,
      nextStep: json['next_step'] as String?,
    );
  }
}
