import type { NextConfig } from 'next';
const config: NextConfig = { distDir: process.env.NODE_ENV === 'production' ? '.next' : '.next-dev', devIndicators:false, experimental:{proxyTimeout:120000}, async rewrites() { return [{ source: '/api/:path*', destination: `${process.env.API_INTERNAL_URL || 'http://127.0.0.1:8000'}/api/:path*` }]; } };
export default config;
