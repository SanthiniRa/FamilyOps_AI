"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { ArrowRight, ShieldCheck, Sparkles, Users, Brain, CalendarDays, ShoppingCart } from "lucide-react";

type AuthLayoutProps = {
  title: string;
  description: string;
  eyebrow: string;
  children: ReactNode;
  footerLink: {
    label: string;
    href: string;
    text: string;
  };
};

const highlights = [
  { icon: ShieldCheck, label: "JWT sessions", detail: "Per-user sign-in with role-aware access" },
  { icon: Brain, label: "Agent memory", detail: "Household context, RAG, and search-backed recall" },
  { icon: CalendarDays, label: "Calendar sync", detail: "Task, event, and reminder workflows in one place" },
  { icon: ShoppingCart, label: "Live utilities", detail: "Web, weather, events, and recipe integrations" },
  { icon: Users, label: "Family ready", detail: "Built for shared household workflows" },
];

export default function AuthLayout({ title, description, eyebrow, children, footerLink }: AuthLayoutProps) {
  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(59,130,246,0.18),_transparent_32%),radial-gradient(circle_at_top_right,_rgba(168,85,247,0.16),_transparent_28%),linear-gradient(135deg,_#fbfdff,_#eef4ff_42%,_#f8faff)] px-4 py-8 sm:px-6 lg:px-8">
      <div className="mx-auto grid min-h-[calc(100vh-4rem)] max-w-6xl gap-8 lg:grid-cols-[1.1fr_0.9fr] lg:items-center">
        <div className="relative overflow-hidden rounded-3xl border border-white/60 bg-slate-950 px-6 py-8 text-white shadow-2xl shadow-slate-300/50 sm:px-10 sm:py-12">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,_rgba(96,165,250,0.28),_transparent_30%),radial-gradient(circle_at_bottom_left,_rgba(168,85,247,0.24),_transparent_28%)]" />
          <div className="relative space-y-8">
            <div className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/8 px-3 py-1 text-xs font-medium text-sky-100">
              <Sparkles className="h-3.5 w-3.5" />
              {eyebrow}
            </div>

            <div className="max-w-xl space-y-4">
              <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">{title}</h1>
              <p className="max-w-lg text-sm leading-6 text-slate-300 sm:text-base">{description}</p>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              {highlights.map((item) => {
                const Icon = item.icon;
                return (
                  <div key={item.label} className="rounded-2xl border border-white/10 bg-white/6 p-4 backdrop-blur">
                    <div className="flex items-center gap-3">
                      <div className="rounded-xl bg-white/10 p-2 text-sky-200">
                        <Icon className="h-4 w-4" />
                      </div>
                      <div>
                        <p className="text-sm font-semibold">{item.label}</p>
                        <p className="text-xs leading-5 text-slate-300">{item.detail}</p>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="flex items-center gap-2 text-sm text-sky-100">
              <span className="h-2 w-2 rounded-full bg-emerald-400" />
              Ready for secure household access
            </div>
          </div>
        </div>

        <div className="mx-auto w-full max-w-lg">
          <div className="rounded-3xl border bg-background/90 p-6 shadow-xl backdrop-blur sm:p-8">
            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase tracking-[0.3em] text-primary">{eyebrow}</p>
              <h2 className="text-2xl font-semibold tracking-tight">{title}</h2>
              <p className="text-sm text-muted-foreground">{description}</p>
            </div>

            <div className="mt-6">{children}</div>

            <div className="mt-6 border-t pt-5 text-sm text-muted-foreground">
              <div className="flex items-center justify-between gap-3">
                <span>{footerLink.label}</span>
                <Link href={footerLink.href} className="inline-flex items-center gap-1 font-medium text-primary hover:underline">
                  {footerLink.text}
                  <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
