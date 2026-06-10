"use client";
import { useQuery } from "@tanstack/react-query";
import { dashboardApi } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { CheckSquare, Calendar, ShoppingCart, Bell, Bot, Users, AlertTriangle, Zap } from "lucide-react";
import { formatRelative, formatTimeAgo, cn } from "@/lib/utils";

export default function DashboardPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => dashboardApi.getSummary().then((r) => r.data),
    refetchInterval: 30000,
  });

  if (isLoading) return <LoadingState />;
  if (error) return <ErrorState />;

  const d = data;

  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground text-sm">
          Welcome back — here&apos;s what&apos;s happening today
        </p>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          icon={<CheckSquare className="h-5 w-5 text-blue-500" />}
          label="Pending Tasks"
          value={d?.tasks?.pending ?? 0}
          sub={d?.tasks?.overdue ? `${d.tasks.overdue} overdue` : "All on track"}
          subColor={d?.tasks?.overdue ? "text-red-500" : "text-green-500"}
        />
        <StatCard
          icon={<Calendar className="h-5 w-5 text-purple-500" />}
          label="Upcoming Events"
          value={d?.calendar?.upcoming_count ?? 0}
          sub="Next 7 days"
        />
        <StatCard
          icon={<Bell className="h-5 w-5 text-yellow-500" />}
          label="Today's Reminders"
          value={d?.reminders?.today_count ?? 0}
          sub="Pending alerts"
        />
        <StatCard
          icon={<ShoppingCart className="h-5 w-5 text-green-500" />}
          label="Active Lists"
          value={d?.grocery?.active_lists ?? 0}
          sub="Grocery lists"
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Tasks */}
        <Card className="lg:col-span-1">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <CheckSquare className="h-4 w-4 text-blue-500" />
              Recent Tasks
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {(d?.tasks?.recent ?? []).length === 0 ? (
              <EmptySlot text="No tasks yet" />
            ) : (
              (d?.tasks?.recent ?? []).map((t: any) => (
                <div key={t.id} className="flex items-center justify-between rounded-md border p-2">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{t.title}</p>
                    {t.due_date && (
                      <p className="text-xs text-muted-foreground">{formatRelative(t.due_date)}</p>
                    )}
                  </div>
                  <Badge variant={t.priority === "high" ? "destructive" : t.priority === "medium" ? "warning" : "success"} className="ml-2 shrink-0">
                    {t.priority}
                  </Badge>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        {/* Calendar */}
        <Card className="lg:col-span-1">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Calendar className="h-4 w-4 text-purple-500" />
              Upcoming Events
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {(d?.calendar?.next_events ?? []).length === 0 ? (
              <EmptySlot text="No upcoming events" />
            ) : (
              (d?.calendar?.next_events ?? []).map((e: any) => (
                <div key={e.id} className="rounded-md border p-2">
                  <p className="text-sm font-medium">{e.title}</p>
                  <p className="text-xs text-muted-foreground">{formatRelative(e.start_time)}</p>
                  {e.location && <p className="text-xs text-muted-foreground">📍 {e.location}</p>}
                </div>
              ))
            )}
          </CardContent>
        </Card>

        {/* Agent Activity */}
        <Card className="lg:col-span-1">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Bot className="h-4 w-4 text-indigo-500" />
              Agent Activity
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {(d?.agents?.recent_runs ?? []).length === 0 ? (
              <EmptySlot text="No agent runs yet" />
            ) : (
              (d?.agents?.recent_runs ?? []).map((r: any) => (
                <div key={r.id} className="flex items-center justify-between rounded-md border p-2">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium capitalize">{r.agent_name}</p>
                    <p className="text-xs text-muted-foreground">{formatTimeAgo(r.started_at)}</p>
                  </div>
                  <Badge
                    variant={r.status === "completed" ? "success" : r.status === "failed" ? "destructive" : "info"}
                    className="ml-2 shrink-0"
                  >
                    {r.status}
                  </Badge>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>

      {/* Important Emails */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <AlertTriangle className="h-4 w-4 text-amber-500" />
            Important Emails Today
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {(d?.emails?.important_today ?? []).length === 0 ? (
            <EmptySlot text="No important emails matched today" />
          ) : (
            (d?.emails?.important_today ?? []).map((email: any) => (
              <div key={email.id} className="rounded-md border p-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{email.subject || "Untitled email"}</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {email.sender || "Unknown sender"}
                      {email.received_at && ` • ${formatRelative(email.received_at)}`}
                    </p>
                  </div>
                  <Badge variant="warning" className="shrink-0">
                    {email.reason}
                  </Badge>
                </div>

                {email.snippet && (
                  <p className="mt-2 text-sm text-muted-foreground">
                    {email.snippet}
                  </p>
                )}

                {(email.matched_keywords ?? []).length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {(email.matched_keywords ?? []).map((keyword: string) => (
                      <Badge key={keyword} variant="outline" className="text-xs">
                        {keyword}
                      </Badge>
                    ))}
                  </div>
                )}
              </div>
            ))
          )}
        </CardContent>
      </Card>

      {/* Family Members */}
      {(d?.family?.members ?? []).length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Users className="h-4 w-4 text-teal-500" />
              Family Members
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-3">
              {(d?.family?.members ?? []).map((m: any) => (
                <div key={m.id} className="flex items-center gap-2 rounded-full border px-3 py-1.5">
                  <div className="flex h-6 w-6 items-center justify-center rounded-full bg-gradient-to-br from-blue-400 to-purple-600 text-xs font-bold text-white">
                    {m.name.charAt(0).toUpperCase()}
                  </div>
                  <span className="text-sm font-medium">{m.name}</span>
                  <Badge variant="outline" className="text-xs">{m.role}</Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function StatCard({ icon, label, value, sub, subColor = "text-muted-foreground" }: any) {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center justify-between">
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">{label}</p>
            <p className="text-2xl font-bold">{value}</p>
            <p className={cn("text-xs", subColor)}>{sub}</p>
          </div>
          <div className="rounded-lg bg-muted p-2">{icon}</div>
        </div>
      </CardContent>
    </Card>
  );
}

function EmptySlot({ text }: { text: string }) {
  return <p className="py-4 text-center text-sm text-muted-foreground">{text}</p>;
}

function LoadingState() {
  return (
    <div className="flex h-full items-center justify-center p-6">
      <div className="flex flex-col items-center gap-3">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
        <p className="text-sm text-muted-foreground">Loading dashboard...</p>
      </div>
    </div>
  );
}

function ErrorState() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-6">
      <AlertTriangle className="h-10 w-10 text-yellow-500" />
      <p className="text-sm text-muted-foreground">Could not load dashboard. Is the backend running?</p>
    </div>
  );
}
