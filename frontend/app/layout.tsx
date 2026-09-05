import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AlphaPilot",
  description: "Find opportunities. Control risk. Optimize capital.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col bg-ink text-text">{children}</body>
    </html>
  );
}
