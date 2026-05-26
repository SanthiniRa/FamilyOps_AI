"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, CheckSquare, ShoppingCart, UtensilsCrossed,
  Bell, Calendar, Brain, Users, Bot, Settings, Home
} from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/tasks", label: "Tasks", icon: CheckSquare },
  { href: "/calendar", label: "Calendar", icon: Calendar },
  { href: "/grocery", label: "Grocery", icon: ShoppingCart },
  { href: "/meals", label: "Meal Plans", icon: UtensilsCrossed },
  { href: "/reminders", label: "Reminders", icon: Bell },
  { href: "/memory", label: "Memory", icon: Brain },
  { href: "/family", label: "Family", icon: Users },
  { href: "/agent", label: "AI Agent", icon: Bot },
  { href: "/settings", label: "Settings", icon: Settings },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex h-screen w-64 flex-col border-r bg-card">
      <div className="flex h-16 items-center gap-2 border-b px-6">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary">
          <Home className="h-4 w-4 text-primary-foreground" />
        </div>
        <div>
          <p className="text-sm font-bold leading-none">FamilyOps</p>
          <p className="text-xs text-muted-foreground">AI Platform</p>
        </div>
      </div>
      <nav className="flex-1 space-y-1 overflow-auto p-3">
        {navItems.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "sidebar-item",
              pathname === href && "active"
            )}
          >
            <Icon className="h-4 w-4 shrink-0" />
            <span>{label}</span>
          </Link>
        ))}
      </nav>
      <div className="border-t p-4">
        <div className="flex items-center gap-2">
          <div className="h-7 w-7 rounded-full bg-gradient-to-br from-blue-400 to-purple-600" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs font-medium">Family Admin</p>
            <p className="truncate text-xs text-muted-foreground">Connected</p>
          </div>
          <div className="h-2 w-2 rounded-full bg-green-400" />
        </div>
      </div>
    </aside>
  );
}
