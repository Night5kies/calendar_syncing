import type { Metadata } from 'next';
import './globals.css';
import { AuthProvider } from '../components/AuthProvider';

export const metadata: Metadata = {
  title: 'SYZY',
  description: 'Link-first social scheduling for meals, hangouts, and group plans.',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
