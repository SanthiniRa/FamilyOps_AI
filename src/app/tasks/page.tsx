"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { tasksApi } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Plus, Trash2, CheckCircle, Circle, Filter } from "lucide-react";
import { formatRelative, PRIORITY_COLORS, cn } from "@/lib/utils";

export default function TasksPage() {
  const qc = useQueryClient();
  const [newTitle, setNewTitle] = useState("");
  const [priority, setPriority] = useState("medium");
  const [filterStatus, setFilterStatus] = useState("");

  const { data: tasks = [], isLoading } = useQuery({
    queryKey: ["tasks", filterStatus],
    queryFn: () => tasksApi.list(filterStatus ? { status: filterStatus } : undefined).then((r) => r.data),
  });

  const { data: stats } = useQuery({
    queryKey: ["task-stats"],
    queryFn: () => tasksApi.stats().then((r) => r.data),
  });

  const createTask = useMutation({
    mutationFn: (data: any) => tasksApi.create(data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["tasks"] }); qc.invalidateQueries({ queryKey: ["task-stats"] }); setNewTitle(""); },
  });

  const updateTask = useMutation({
    mutationFn: ({ id, data }: any) => tasksApi.update(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["tasks"] }); qc.invalidateQueries({ queryKey: ["task-stats"] }); },
  });

  const deleteTask = useMutation({
    mutationFn: (id: string) => tasksApi.delete(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["tasks"] }); qc.invalidateQueries({ queryKey: ["task-stats"] }); },
  });

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    createTask.mutate({ title: newTitle, priority });
  };

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Tasks</h1>
          <p className="text-sm text-muted-foreground">Manage household tasks and assignments</p>
        </div>
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-4 gap-4">
          {[
            { label: "Total", value: stats.total, color: "text-foreground" },
            { label: "Pending", value: stats.by_status?.pending ?? 0, color: "text-blue-600" },
            { label: "Completed", value: stats.by_status?.completed ?? 0, color: "text-green-600" },
            { label: "Overdue", value: stats.overdue, color: "text-red-600" },
          ].map((s) => (
            <Card key={s.label}>
              <CardContent className="pt-4 pb-4">
                <p className="text-xs text-muted-foreground">{s.label}</p>
                <p className={cn("text-2xl font-bold", s.color)}>{s.value}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Add Task */}
      <Card>
        <CardContent className="pt-4">
          <form onSubmit={handleCreate} className="flex gap-2">
            <Input
              placeholder="Add a new task..."
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              className="flex-1"
            />
            <select
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
              className="h-10 rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
            </select>
            <Button type="submit" disabled={createTask.isPending}>
              <Plus className="mr-1 h-4 w-4" /> Add
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Filter */}
      <div className="flex gap-2">
        {["", "pending", "in-progress", "completed"].map((s) => (
          <Button
            key={s}
            variant={filterStatus === s ? "default" : "outline"}
            size="sm"
            onClick={() => setFilterStatus(s)}
          >
            {s === "" ? "All" : s.charAt(0).toUpperCase() + s.slice(1)}
          </Button>
        ))}
      </div>

      {/* Task List */}
      <div className="space-y-2">
        {isLoading ? (
          <p className="text-center text-sm text-muted-foreground py-8">Loading tasks...</p>
        ) : tasks.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center">
              <p className="text-muted-foreground">No tasks found. Create one above!</p>
            </CardContent>
          </Card>
        ) : (
          tasks.map((task: any) => (
            <Card key={task.id} className={cn(task.status === "completed" && "opacity-60")}>
              <CardContent className="flex items-center gap-3 py-3">
                <button
                  onClick={() => updateTask.mutate({ id: task.id, data: { status: task.status === "completed" ? "pending" : "completed" } })}
                  className="shrink-0 text-muted-foreground hover:text-primary"
                >
                  {task.status === "completed" ? <CheckCircle className="h-5 w-5 text-green-500" /> : <Circle className="h-5 w-5" />}
                </button>
                <div className="min-w-0 flex-1">
                  <p className={cn("text-sm font-medium", task.status === "completed" && "line-through text-muted-foreground")}>
                    {task.title}
                  </p>
                  {task.due_date && (
                    <p className="text-xs text-muted-foreground">{formatRelative(task.due_date)}</p>
                  )}
                </div>
                <Badge className={cn("border text-xs", PRIORITY_COLORS[task.priority as keyof typeof PRIORITY_COLORS])}>
                  {task.priority}
                </Badge>
                {task.agent_generated && <Badge variant="info" className="text-xs">AI</Badge>}
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 shrink-0 text-muted-foreground hover:text-destructive"
                  onClick={() => deleteTask.mutate(task.id)}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </CardContent>
            </Card>
          ))
        )}
      </div>
    </div>
  );
}
