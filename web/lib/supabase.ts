import { createClient, type SupabaseClient } from '@supabase/supabase-js';

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

/**
 * Auth is opt-in. When the Supabase env vars are unset (local dev), the app
 * runs without a client and the backend's dev-auth fallback handles requests.
 * When they are set, real organizer auth is enforced.
 */
export const isAuthEnabled = Boolean(supabaseUrl && supabaseAnonKey);

export const supabase: SupabaseClient | null = isAuthEnabled
  ? createClient(supabaseUrl as string, supabaseAnonKey as string, {
      auth: { persistSession: true, autoRefreshToken: true },
    })
  : null;

/** Current access token for Authorization headers, or null when signed out / auth disabled. */
export async function getAccessToken(): Promise<string | null> {
  if (!supabase) return null;
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}
