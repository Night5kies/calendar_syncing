'use client';

import { RequireAuth } from '../../components/RequireAuth';

export default function CreateLayout({ children }: { children: React.ReactNode }) {
  return <RequireAuth>{children}</RequireAuth>;
}
