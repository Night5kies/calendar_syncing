import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../widgets/input_field.dart';
import '../../widgets/primary_button.dart';

class SignInScreen extends StatelessWidget {
  const SignInScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Welcome back',
                style: Theme.of(context).textTheme.headlineSmall,
              ),
              const SizedBox(height: 8),
              Text(
                'Sign in to access your scheduling inbox.',
                style: Theme.of(context).textTheme.bodyMedium,
              ),
              const SizedBox(height: 24),
              const InputField(
                label: 'Email',
                hint: 'you@work.com',
                keyboardType: TextInputType.emailAddress,
              ),
              const SizedBox(height: 16),
              const InputField(
                label: 'Password',
                hint: '••••••••',
                keyboardType: TextInputType.visiblePassword,
              ),
              const Spacer(),
              PrimaryButton(
                label: 'Continue',
                onPressed: () => context.go('/home'),
              ),
              const SizedBox(height: 12),
              TextButton(
                onPressed: () => context.go('/signup'),
                child: const Text('Need an account? Sign up'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
