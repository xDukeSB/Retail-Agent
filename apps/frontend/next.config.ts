import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
    NEXT_PUBLIC_WS_URL:  process.env.NEXT_PUBLIC_WS_URL  || "ws://localhost:8000",
    NEXT_PUBLIC_HLS_BASE_URL: process.env.NEXT_PUBLIC_HLS_BASE_URL || "http://localhost:8888",
  },
  // Allow cross-origin images from camera streams
  images: {
    remotePatterns: [
      { protocol: "http",  hostname: "**" },
      { protocol: "https", hostname: "**" },
    ],
  },
};

export default nextConfig;
