"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { tasksApi } from "@/lib/api";

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import { Plus, Trash2, CheckCircle, Circle } from "lucide-react";
import { formatRelative, PRIORITY_COLORS, cn } from "@/lib/utils";

type TaskStatus = "pending" | "in-progress" | "completed";
type TaskPriority = "low" | "medium" | "high";

type Task = {
  id: string;
  title: string;
  status: TaskStatus;
  priority: TaskPriority;
  due_date?: string;
  agent_generated: boolean;
};

type TaskStats = {
  total: number;
  by_status: Record<string, number>;
  by_priority: Record<string, number>;
  overdue: number;
};

const FILTERS: TaskStatus[] = ["pending", "in-progress", "completed"];

export default function TasksPage() {
  const qc = useQueryClient();

  const [filterStatus, setFilterStatus] = useState<TaskStatus>("pending");
  const [newTitle, setNewTitle] = useState("");
  const [priority, setPriority] = useState<TaskPriority>("medium");

  // -----------------------------
  // TASK LIST (FIXED QUERY)
  // -----------------------------
  const { data: tasks = [], isLoading } = useQuery<Task[]>({
    queryKey: ["tasks", filterStatus],
    queryFn: async () => {
      const res = await tasksApi.list({ status: filterStatus });

      console.log("API RESPONSE:", res.data); // DEBUG LINE (keep for now)

      return res.data;
    },
  });

  // -----------------------------
  // STATS
  // -----------------------------
  const { data: stats } = useQuery<TaskStats>({
    queryKey: ["task-stats"],
    queryFn: async () => {
      const res = await tasksApi.stats();
      return res.data;
    },
  });

  // -----------------------------
  // CREATE
  // -----------------------------
  const createTask = useMutation({
    mutationFn: (data: { title: string; priority: TaskPriority }) =>
      tasksApi.create(data),

    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["tasks"] });
      await qc.invalidateQueries({ queryKey: ["task-stats"] });
      setNewTitle("");
    },
  });

  // -----------------------------
  // UPDATE
  // -----------------------------
  const updateTask = useMutation({
    mutationFn: ({ id, data }: { id: string; data: any }) =>
      tasksApi.update(id, data),

    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["tasks"] });
      await qc.invalidateQueries({ queryKey: ["task-stats"] });
    },
  });

  // -----------------------------
  // DELETE
  // -----------------------------
  const deleteTask = useMutation({
    mutationFn: (id: string) => tasksApi.delete(id),

    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["tasks"] });
      await qc.invalidateQueries({ queryKey: ["task-stats"] });
    },
  });

  // -----------------------------
  // CREATE HANDLER
  // -----------------------------
  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;

    createTask.mutate({
      title: newTitle,
      priority,
    });
  };

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* HEADER */}
      <div>
        <h1 className="text-2xl font-bold">Tasks</h1>
        <p className="text-sm text-muted-foreground">
          Manage household tasks
        </p>
      </div>

      {/* STATS */}
      {stats && (
        <div className="grid grid-cols-4 gap-4">
          <Card>
            <CardContent className="pt-4">
              <p>Total</p>
              <p className="text-xl font-bold">{stats.total}</p>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-4">
              <p>Pending</p>
              <p className="text-xl font-bold">
                {stats.by_status?.pending ?? 0}
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-4">
              <p>Completed</p>
              <p className="text-xl font-bold">
                {stats.by_status?.completed ?? 0}
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-4">
              <p>Overdue</p>
              <p className="text-xl font-bold">{stats.overdue}</p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* CREATE */}
      <Card>
        <CardContent className="pt-4">
          <form onSubmit={handleCreate} className="flex gap-2">
            <Input
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="New task..."
              className="flex-1"
            />

            <select
              value={priority}
              onChange={(e) =>
                setPriority(e.target.value as TaskPriority)
              }
              className="border rounded px-2"
            >
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
            </select>

            <Button type="submit">
              <Plus className="w-4 h-4 mr-1" />
              Add
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* FILTER */}
      <div className="flex gap-2">
        {FILTERS.map((status) => (
          <Button
            key={status}
            variant={filterStatus === status ? "default" : "outline"}
            size="sm"
            onClick={() => setFilterStatus(status)}
          >
            {status}
          </Button>
        ))}
      </div>

      {/* TASK LIST */}
      <div className="space-y-2">
        {isLoading ? (
          <p>Loading...</p>
        ) : tasks.length === 0 ? (
          <Card>
            <CardContent className="py-10 text-center text-muted-foreground">
              No tasks found in "{filterStatus}"
            </CardContent>
          </Card>
        ) : (
          tasks.map((task) => (
            <Card key={task.id}>
              <CardContent className="flex items-center gap-3 py-3">
                {/* TOGGLE */}
                <button
                  onClick={() =>
                    updateTask.mutate({
                      id: task.id,
                      data: {
                        status:
                          task.status === "completed"
                            ? "pending"
                            : "completed",
                      },
                    })
                  }
                >
                  {task.status === "completed" ? (
                    <CheckCircle className="text-green-500" />
                  ) : (
                    <Circle />
                  )}
                </button>

                {/* TITLE */}
                <div className="flex-1">
                  <p>{task.title}</p>
                </div>

                {/* PRIORITY */}
                <Badge>{task.priority}</Badge>

                {/* DELETE */}
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => deleteTask.mutate(task.id)}
                >
                  <Trash2 className="w-4 h-4" />
                </Button>
              </CardContent>
            </Card>
          ))
        )}
      </div>
    </div>
  );
}