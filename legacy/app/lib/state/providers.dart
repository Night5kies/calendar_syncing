import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/mock_repository.dart';
import 'app_state.dart';
import 'app_state_notifier.dart';

final mockRepositoryProvider = Provider<MockRepository>((ref) {
  return MockRepository();
});

final appStateProvider =
    StateNotifierProvider<AppStateNotifier, AppState>((ref) {
  final repository = ref.watch(mockRepositoryProvider);
  return AppStateNotifier(repository);
});
