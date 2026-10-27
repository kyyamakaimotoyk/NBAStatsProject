import type { Metadata } from "next";
import ContactContent from "./ContactContent";

export const metadata: Metadata = {
  title: "Contact",
  description:
    "How to reach HoopModel: questions about the predictions, data corrections, bug reports, and privacy requests.",
  alternates: { canonical: "/contact/" },
};

// Metadata must stay in a server component; the prose itself is language-
// switched on the client, so it lives in ContactContent.
export default function ContactPage() {
  return <ContactContent />;
}
