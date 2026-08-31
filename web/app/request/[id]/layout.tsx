'use client';

import { RequireAuth } from '../../../components/RequireAuth';

export default function RequestDetailLayout({ children }: { children: React.ReactNode }) {
  return <RequireAuth>{children}</RequireAuth>;
}
