import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'screens/auth/sign_in_screen.dart';
import 'screens/auth/sign_up_screen.dart';
import 'screens/auth/welcome_screen.dart';
import 'screens/chat/chat_detail_screen.dart';
import 'screens/chat/create_request_flow.dart';
import 'screens/chat/request_detail_screen.dart';
import 'screens/home/home_screen.dart';
import 'screens/share/attendee_share_screen.dart';

final appRouterProvider = Provider<GoRouter>((ref) {
  return GoRouter(
    initialLocation: '/',
    routes: [
      GoRoute(
        path: '/',
        builder: (context, state) => const WelcomeScreen(),
      ),
      GoRoute(
        path: '/signin',
        builder: (context, state) => const SignInScreen(),
      ),
      GoRoute(
        path: '/signup',
        builder: (context, state) => const SignUpScreen(),
      ),
      GoRoute(
        path: '/home',
        builder: (context, state) => const HomeScreen(),
      ),
      GoRoute(
        path: '/chat/:id',
        builder: (context, state) =>
            ChatDetailScreen(conversationId: state.pathParameters['id']!),
        routes: [
          GoRoute(
            path: 'request/create',
            builder: (context, state) =>
                CreateRequestFlow(conversationId: state.pathParameters['id']!),
          ),
        ],
      ),
      GoRoute(
        path: '/request/:id',
        builder: (context, state) =>
            RequestDetailScreen(requestId: state.pathParameters['id']!),
      ),
      GoRoute(
        path: '/share/:id',
        builder: (context, state) =>
            AttendeeShareScreen(requestId: state.pathParameters['id']!),
      ),
    ],
  );
});
