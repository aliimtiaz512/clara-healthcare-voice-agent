/** @type {import('next').NextConfig} */
const nextConfig = {
  // Silence the "require('events')" warning from the livekit-client bundle
  webpack: (config) => {
    config.resolve.fallback = { ...config.resolve.fallback, events: false };
    return config;
  },
};

export default nextConfig;
