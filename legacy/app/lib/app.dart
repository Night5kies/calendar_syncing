import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'routes.dart';
import 'theme/app_theme.dart';

class CalendarSyncApp extends ConsumerWidget {
  const CalendarSyncApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(appRouterProvider);
    return MaterialApp.router(
      title: 'Calendar Syncing',
      theme: AppTheme.lightTheme,
      routerConfig: router,
    );
  }
}
