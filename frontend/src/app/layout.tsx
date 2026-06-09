import type { Metadata } from "next";
import "./globals.css";
import Providers from "@/components/providers";
import Sidebar from "@/components/layout/sidebar";

export const metadata: Metadata = {
  title: "FamilyOps AI",
  description: "AI-powered Household Operations Platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <Providers>
          <div className="flex h-screen overflow-hidden bg-background">
            <Sidebar />
            <main className="flex-1 overflow-auto">
              {children}
            </main>
          </div>
        </Providers>
      </body>
    </html>
  );
}
