import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emit a fully static site (HTML/CSS/JS) into out/ on `next build`.
  // No Node server at runtime — perfect for S3 + CloudFront.
  output: "export",
  // Emit /accuracy/index.html (not /accuracy.html) so S3+CloudFront serve
  // clean URLs like /accuracy/ without custom rewrite rules.
  trailingSlash: true,
};

export default nextConfig;
