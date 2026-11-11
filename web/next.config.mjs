/** Static export served under https://tokenfly.ai/snow/ */
const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "/snow";

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",
  basePath,
  trailingSlash: true,
  images: { unoptimized: true },
  env: { NEXT_PUBLIC_BASE_PATH: basePath },
};
export default nextConfig;
