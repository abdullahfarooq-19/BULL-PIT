import type { NextConfig } from "next";

// The browser only ever talks to this server; /api/* is proxied to the FastAPI
// process on loopback, so the API needs no CORS and its port stays private.
const apiPort = process.env.API_PORT ?? "8000";

const nextConfig: NextConfig = {
  // History and Trades became one page (M11.2) and the Backtests page was removed (M11.4):
  // the old URLs keep working.
  async redirects() {
    return [
      { source: "/requests", destination: "/trades", permanent: false },
      { source: "/backtests", destination: "/trades", permanent: false },
    ];
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `http://127.0.0.1:${apiPort}/:path*` }];
  },
};

export default nextConfig;
