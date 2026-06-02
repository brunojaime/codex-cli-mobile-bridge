import 'package:flutter/material.dart';

String formatChatMessageTime(BuildContext context, DateTime timestamp) {
  final localTimestamp = timestamp.toLocal();
  final localizations = MaterialLocalizations.of(context);
  return localizations.formatTimeOfDay(
    TimeOfDay.fromDateTime(localTimestamp),
    alwaysUse24HourFormat: MediaQuery.of(context).alwaysUse24HourFormat,
  );
}

String formatChatDaySeparatorLabel(
  BuildContext context,
  DateTime timestamp, {
  DateTime? now,
  Locale? locale,
}) {
  final resolvedLocale =
      locale ?? Localizations.maybeLocaleOf(context) ?? View.of(context).platformDispatcher.locale;
  final localTimestamp = timestamp.toLocal();
  final referenceNow = (now ?? DateTime.now()).toLocal();
  final yesterday = referenceNow.subtract(const Duration(days: 1));

  if (_isSameCalendarDay(localTimestamp, referenceNow)) {
    return resolvedLocale.languageCode.toLowerCase() == 'es' ? 'Hoy' : 'Today';
  }
  if (_isSameCalendarDay(localTimestamp, yesterday)) {
    return resolvedLocale.languageCode.toLowerCase() == 'es'
        ? 'Ayer'
        : 'Yesterday';
  }
  return MaterialLocalizations.of(context).formatMediumDate(localTimestamp);
}

bool isSameChatCalendarDay(DateTime left, DateTime right) {
  return _isSameCalendarDay(left.toLocal(), right.toLocal());
}

bool _isSameCalendarDay(DateTime left, DateTime right) {
  return left.year == right.year &&
      left.month == right.month &&
      left.day == right.day;
}
