"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { remindersApi } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Plus, Trash2, Bell, BellOff, Clock } from "lucide-react";
import { formatRelative, cn } from "@/lib/utils";

export default function RemindersPage() {
  const qc = useQueryClient();
  const [form, setForm] = useState({ title: "", body: "", remind_at: "", recurrence: "", channel: "app" });

  const { data: reminders = [], isLoading } = useQuery({
    queryKey: ["reminders"],
    queryFn: () => remindersApi.list().then((r) => r.data),
  });

  const { data: todayReminders = [] } = useQuery({
    queryKey: ["reminders-today"],
    queryFn: () => remindersApi.today().then((r) => r.data),
  });

  const create = useMutation({
    mutationFn: (data: any) => remindersApi.create(data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["reminders"] }); setForm({ title: "", body: "", remind_at: "", recurrence: "", channel: "app" }); },
  });

  const dismiss = useMutation({
    mutationFn: (id: string) => remindersApi.update(id, { status: "dismissed" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["reminders"] }),
  });

  const del = useMutation({
    mutationFn: (id: string) => remindersApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["reminders"] }),
  });

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.title || !form.remind_at) return;
    create.mutate({ ...form, remind_at: new Date(form.remind_at).toISOString() });
  };

  const pending = reminders.filter((r: any) => r.status === "pending");
  const dismissed = reminders.filter((r: any) => r.status === "dismissed");

  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Reminders</h1>
        <p className="text-sm text-muted-foreground">Family alerts and scheduled notifications</p>
      </div>

      {/* Today's reminders */}
      {todayReminders.length > 0 && (
        <Card className="border-yellow-200 bg-yellow-50">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base text-yellow-800">
              <Bell className="h-4 w-4" /> Today's Reminders ({todayReminders.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {todayReminders.map((r: any) => (
                <div key={r.id} className="flex items-center justify-between rounded-md bg-white border border-yellow-200 p-2">
                  <div>
                    <p className="text-sm font-medium">{r.title}</p>
                    <p className="text-xs text-muted-foreground flex items-center gap-1">
                      <Clock className="h-3 w-3" />{formatRelative(r.remind_at)}
                    </p>
                  </div>
                  <Button size="sm" variant="outline" onClick={() => dismiss.mutate(r.id)}>Dismiss</Button>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Create reminder */}
      <Card>
        <CardHeader><CardTitle className="text-base">New Reminder</CardTitle></CardHeader>
        <CardContent>
          <form onSubmit={handleCreate} className="grid gap-3 sm:grid-cols-2">
            <Input placeholder="Reminder title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required />
            <Input placeholder="Notes (optional)" value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} />
            <Input type="datetime-local" value={form.remind_at} onChange={(e) => setForm({ ...form, remind_at: e.target.value })} required />
            <select
              value={form.recurrence}
              onChange={(e) => setForm({ ...form, recurrence: e.target.value })}
              className="h-10 rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="">No recurrence</option>
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
            </select>
            <Button type="submit" className="sm:col-span-2" disabled={create.isPending}>
              <Plus className="mr-1 h-4 w-4" /> Create Reminder
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Pending */}
      <div>
        <h2 className="text-base font-semibold mb-3">Pending ({pending.length})</h2>
        <div className="space-y-2">
          {pending.length === 0 ? (
            <Card><CardContent className="py-8 text-center text-muted-foreground">No pending reminders</CardContent></Card>
          ) : (
            pending.map((r: any) => (
              <Card key={r.id}>
                <CardContent className="flex items-center gap-3 py-3">
                  <Bell className="h-5 w-5 shrink-0 text-yellow-500" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium">{r.title}</p>
                    {r.body && <p className="text-xs text-muted-foreground">{r.body}</p>}
                    <p className="text-xs text-muted-foreground flex items-center gap-1 mt-0.5">
                      <Clock className="h-3 w-3" />{formatRelative(r.remind_at)}
                    </p>
                  </div>
                  {r.recurrence && <Badge variant="outline" className="text-xs">{r.recurrence}</Badge>}
                  <Badge variant="outline" className="text-xs">{r.channel}</Badge>
                  <div className="flex gap-1">
                    <Button size="sm" variant="outline" onClick={() => dismiss.mutate(r.id)}>Dismiss</Button>
                    <Button size="icon" variant="ghost" className="h-8 w-8 text-muted-foreground hover:text-destructive" onClick={() => del.mutate(r.id)}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
