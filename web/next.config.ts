import type { NextConfig } from "next";

// The browser only ever talks to this server; /api/* is proxied to the FastAPI
// process on loopback, so the API needs no CORS and its port stays private.
const apiPort = process.env.API_PORT ?? "8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `http://127.0.0.1:${apiPort}/:path*` }];
  },
};

export default nextConfig;
