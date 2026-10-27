import type { Metadata } from "next";
import PrivacyContent from "./PrivacyContent";

export const metadata: Metadata = {
  title: "Privacy policy",
  description:
    "What HoopModel collects (analytics, ads, server logs), why, and the choices you have.",
  alternates: { canonical: "/privacy/" },
};

// Metadata must stay in a server component; the prose itself is language-
// switched on the client, so it lives in PrivacyContent.
export default function PrivacyPage() {
  return <PrivacyContent />;
}
