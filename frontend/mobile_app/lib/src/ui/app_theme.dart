import 'package:flutter/material.dart';

/// Neutral, low-chroma dark palette shared by the whole app.
abstract final class AppPalette {
  static const background = Color(0xFF111214);
  static const sidebar = Color(0xFF15161A);
  static const surface = Color(0xFF1B1D22);
  static const surfaceHigh = Color(0xFF23252B);
  static const surfaceHigher = Color(0xFF2B2E35);
  static const border = Color(0xFF2C2F36);
  static const borderStrong = Color(0xFF3A3E47);
  static const text = Color(0xFFE8EAF0);
  static const textMuted = Color(0xFF9AA1B0);
  static const textFaint = Color(0xFF6E7585);
  static const accent = Color(0xFF55D6BE);
  static const accentDev = Color(0xFF38BDF8);
  static const amber = Color(0xFFFFC857);
  static const red = Color(0xFFFF6B81);
}

ThemeData buildAppTheme({required Color accent}) {
  final scheme = ColorScheme.fromSeed(
    seedColor: accent,
    brightness: Brightness.dark,
  ).copyWith(
    primary: accent,
    onPrimary: const Color(0xFF07130F),
    secondary: accent,
    surface: AppPalette.surface,
    onSurface: AppPalette.text,
    onSurfaceVariant: AppPalette.textMuted,
    surfaceContainerLowest: AppPalette.background,
    surfaceContainerLow: AppPalette.sidebar,
    surfaceContainer: AppPalette.surface,
    surfaceContainerHigh: AppPalette.surfaceHigh,
    surfaceContainerHighest: AppPalette.surfaceHigher,
    outline: AppPalette.borderStrong,
    outlineVariant: AppPalette.border,
    error: AppPalette.red,
  );

  final base = ThemeData(
    useMaterial3: true,
    brightness: Brightness.dark,
    colorScheme: scheme,
    visualDensity: VisualDensity.standard,
  );
  final text = base.textTheme
      .apply(bodyColor: AppPalette.text, displayColor: AppPalette.text)
      .copyWith(
        titleLarge: base.textTheme.titleLarge?.copyWith(
            fontWeight: FontWeight.w700, letterSpacing: -0.2, fontSize: 20),
        titleMedium: base.textTheme.titleMedium
            ?.copyWith(fontWeight: FontWeight.w600, letterSpacing: -0.1),
        bodyMedium: base.textTheme.bodyMedium?.copyWith(height: 1.45),
        bodyLarge: base.textTheme.bodyLarge?.copyWith(height: 1.5),
        labelLarge: base.textTheme.labelLarge
            ?.copyWith(fontWeight: FontWeight.w600, letterSpacing: 0.1),
      );

  const radius = 12.0;
  final rounded =
      RoundedRectangleBorder(borderRadius: BorderRadius.circular(radius));
  const buttonPadding = EdgeInsets.symmetric(horizontal: 16, vertical: 12);

  return base.copyWith(
    scaffoldBackgroundColor: AppPalette.background,
    canvasColor: AppPalette.background,
    textTheme: text,
    dividerColor: AppPalette.border,
    dividerTheme: const DividerThemeData(
        color: AppPalette.border, thickness: 1, space: 1),
    splashFactory: InkSparkle.splashFactory,
    appBarTheme: AppBarTheme(
      backgroundColor: AppPalette.background,
      surfaceTintColor: Colors.transparent,
      foregroundColor: AppPalette.text,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: false,
      titleTextStyle: text.titleMedium?.copyWith(fontSize: 17),
      shape: const Border(bottom: BorderSide(color: AppPalette.border)),
    ),
    drawerTheme: const DrawerThemeData(
      backgroundColor: AppPalette.sidebar,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(),
    ),
    cardTheme: CardThemeData(
      color: AppPalette.surface,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: const BorderSide(color: AppPalette.border),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: AppPalette.surface,
      hintStyle: const TextStyle(color: AppPalette.textFaint),
      labelStyle: const TextStyle(color: AppPalette.textMuted),
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(radius),
        borderSide: const BorderSide(color: AppPalette.border),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(radius),
        borderSide: const BorderSide(color: AppPalette.border),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(radius),
        borderSide: BorderSide(color: accent.withValues(alpha: .8), width: 1.4),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        shape: rounded,
        padding: buttonPadding,
        textStyle: text.labelLarge,
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        shape: rounded,
        padding: buttonPadding,
        foregroundColor: AppPalette.text,
        side: const BorderSide(color: AppPalette.borderStrong),
        textStyle: text.labelLarge,
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        shape: rounded,
        foregroundColor: accent,
        textStyle: text.labelLarge,
      ),
    ),
    iconButtonTheme: IconButtonThemeData(
      style: IconButton.styleFrom(
        foregroundColor: AppPalette.textMuted,
        highlightColor: AppPalette.surfaceHigh,
        shape: rounded,
      ),
    ),
    chipTheme: ChipThemeData(
      backgroundColor: AppPalette.surface,
      selectedColor: accent.withValues(alpha: .18),
      side: const BorderSide(color: AppPalette.border),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      labelStyle: const TextStyle(color: AppPalette.text, fontSize: 13),
      checkmarkColor: accent,
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
    ),
    listTileTheme: ListTileThemeData(
      shape: rounded,
      iconColor: AppPalette.textMuted,
      textColor: AppPalette.text,
      selectedColor: AppPalette.text,
      selectedTileColor: AppPalette.surfaceHigh,
    ),
    popupMenuTheme: PopupMenuThemeData(
      color: AppPalette.surfaceHigh,
      surfaceTintColor: Colors.transparent,
      elevation: 8,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: const BorderSide(color: AppPalette.border),
      ),
      textStyle: const TextStyle(color: AppPalette.text, fontSize: 14),
    ),
    menuTheme: const MenuThemeData(
      style: MenuStyle(
        backgroundColor: WidgetStatePropertyAll(AppPalette.surfaceHigh),
        surfaceTintColor: WidgetStatePropertyAll(Colors.transparent),
      ),
    ),
    bottomSheetTheme: const BottomSheetThemeData(
      backgroundColor: AppPalette.surface,
      surfaceTintColor: Colors.transparent,
      modalBackgroundColor: AppPalette.surface,
      showDragHandle: true,
      dragHandleColor: AppPalette.borderStrong,
      constraints: BoxConstraints(maxWidth: 720),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: AppPalette.surface,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(18),
        side: const BorderSide(color: AppPalette.border),
      ),
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: AppPalette.surfaceHigher,
      contentTextStyle: const TextStyle(color: AppPalette.text),
      actionTextColor: accent,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      width: 520,
    ),
    tooltipTheme: TooltipThemeData(
      waitDuration: const Duration(milliseconds: 400),
      decoration: BoxDecoration(
        color: AppPalette.surfaceHigher,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppPalette.borderStrong),
      ),
      textStyle: const TextStyle(color: AppPalette.text, fontSize: 12.5),
    ),
    scrollbarTheme: ScrollbarThemeData(
      thickness: const WidgetStatePropertyAll(6),
      radius: const Radius.circular(8),
      thumbColor: WidgetStatePropertyAll(
          AppPalette.borderStrong.withValues(alpha: .8)),
    ),
    progressIndicatorTheme: ProgressIndicatorThemeData(
      color: accent,
      linearTrackColor: AppPalette.surfaceHigh,
    ),
    badgeTheme: const BadgeThemeData(
      backgroundColor: AppPalette.amber,
      textColor: Color(0xFF2A1600),
    ),
    floatingActionButtonTheme: FloatingActionButtonThemeData(
      backgroundColor: AppPalette.surfaceHigh,
      foregroundColor: accent,
      elevation: 2,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
    ),
  );
}
