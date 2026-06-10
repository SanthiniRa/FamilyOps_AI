"use client";

import { useEffect, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import Sidebar from "@/components/layout/sidebar";
import { useAuth } from "@/components/auth/auth-provider";

const AUTH_ROUTES = ["/login", "/register"];

export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { isLoading, isAuthenticated } = useAuth();

  const isAuthRoute = AUTH_ROUTES.includes(pathname);

  useEffect(() => {
    if (isAuthRoute && isAuthenticated) {
      router.replace("/");
      return;
    }

    if (!isAuthRoute && !isLoading && !isAuthenticated) {
      router.replace("/login");
    }
  }, [isAuthRoute, isAuthenticated, isLoading, router]);

  if (isAuthRoute) {
    return <>{children}</>;
  }

  if (isLoading || !isAuthenticated) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[radial-gradient(circle_at_top,_rgba(59,130,246,0.14),_transparent_35%),linear-gradient(135deg,_#f8fbff,_#eef4ff)] p-6">
        <div className="rounded-2xl border bg-white/85 px-6 py-5 shadow-xl backdrop-blur">
          <div className="flex items-center gap-3">
            <div className="h-3 w-3 animate-pulse rounded-full bg-primary" />
            <p className="text-sm font-medium text-slate-700">
              Verifying your FamilyOps session...
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <Sidebar />
      <main className="flex-1 overflow-auto">{children}</main>
    </div>
  );
}
