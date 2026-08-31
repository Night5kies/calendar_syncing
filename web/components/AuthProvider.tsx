'use client';

import type { Session } from '@supabase/supabase-js';
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';

import { isAuthEnabled, supabase } from '../lib/supabase';

type AuthContextValue = {
  authEnabled: boolean;
  loading: boolean;
  session: Session | null;
  email: string | null;
  signInWithEmail: (email: string) => Promise<void>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  // When auth is disabled there is nothing to load.
  const [loading, setLoading] = useState<boolean>(isAuthEnabled);

  useEffect(() => {
    if (!supabase) return;
    let active = true;
    supabase.auth.getSession().then(({ data }) => {
      if (!active) return;
      setSession(data.session);
      setLoading(false);
    });
    const { data: sub } = supabase.auth.onAuthStateChange((_event, next) => {
      setSession(next);
      setLoading(false);
    });
    return () => {
      active = false;
      sub.subscription.unsubscribe();
    };
  }, []);

  const value: AuthContextValue = {
    authEnabled: isAuthEnabled,
    loading,
    session,
    email: session?.user?.email ?? null,
    async signInWithEmail(email: string) {
      if (!supabase) throw new Error('Auth is not configured.');
      const redirectTo =
        typeof window !== 'undefined' ? `${window.location.origin}/create` : undefined;
      const { error } = await supabase.auth.signInWithOtp({
        email,
        options: { emailRedirectTo: redirectTo },
      });
      if (error) throw error;
    },
    async signOut() {
      if (!supabase) return;
      await supabase.auth.signOut();
      setSession(null);
    },
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
