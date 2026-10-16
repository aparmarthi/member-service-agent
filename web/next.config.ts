import type { NextConfig } from "next";

// On Vercel the browser calls /api/* on this origin (NEXT_PUBLIC_API_URL=/api),
// proxied to the API on Cloud Run: same-origin, so no CORS preflight per turn.
const API_ORIGIN = process.env.API_ORIGIN;

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return API_ORIGIN ? [{ source: "/api/:path*", destination: `${API_ORIGIN}/:path*` }] : [];
  },
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
