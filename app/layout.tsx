import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = { title: 'RapidSkills AI Job Apply Agent', description: 'A thoughtful job search, with you in control. Discover matches, tailor applications and watch your agent work.', icons: { icon: '/rapidskill-icon.png' } };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="en"><body>{children}</body></html>; }
