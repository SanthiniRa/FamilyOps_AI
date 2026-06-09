"use client";
import { useState, useRef, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { agentApi } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Bot, Send, User, Zap, Activity, Clock, CheckCircle, XCircle } from "lucide-react";
import { formatTimeAgo, cn } from "@/lib/utils";

interface Message {
  id: string;
  role: "user" | "agent";
  content: string;
  status?: string;
  timestamp: Date;
}

const QUICK_PROMPTS = [
  "What tasks are overdue?",
  "Generate a grocery list for this week",
  "Create a meal plan for next week",
  "Remind me to call the doctor tomorrow at 9am",
  "What's on the family calendar this week?",
  "Store a memory: Alice is allergic to peanuts",
];

export default function AgentPage() {
  const qc = useQueryClient();
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "agent",
      content: "Hi! I'm your FamilyOps AI assistant. I can help you manage tasks, calendar events, grocery lists, meal plans, reminders, and household memory. What can I do for you today?",
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const { data: runs = [] } = useQuery({
    queryKey: ["agent-runs"],
    queryFn: () => agentApi.listRuns().then((r) => r.data),
    refetchInterval: 10000,
  });

  const { data: stats } = useQuery({
    queryKey: ["agent-stats"],
    queryFn: () => agentApi.stats().then((r) => r.data),
  });

  const chat = useMutation({
    mutationFn: (message: string) => agentApi.chat({ message }),
    onMutate: (message) => {
      const userMsg: Message = {
        id: Date.now().toString(),
        role: "user",
        content: message,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, userMsg]);
    },
    onSuccess: (response) => {
      const result = response.data;
      const agentMsg: Message = {
        id: result.run_id,
        role: "agent",
        content: formatAgentResponse(result),
        status: result.status,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, agentMsg]);
      qc.invalidateQueries({ queryKey: ["agent-runs"] });
      qc.invalidateQueries({ queryKey: ["agent-stats"] });
      qc.invalidateQueries({ queryKey: ["grocery-lists"] });
      qc.invalidateQueries({ queryKey: ["meal-plans"] });
    },
    onError: () => {
      setMessages((prev) => [...prev, {
        id: Date.now().toString(),
        role: "agent",
        content: "Sorry, I encountered an error. Please check that the backend is running and try again.",
        timestamp: new Date(),
      }]);
    },
  });

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = () => {
    if (!input.trim() || chat.isPending) return;
    const msg = input;
    setInput("");
    chat.mutate(msg);
  };

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">AI Agent</h1>
        <p className="text-sm text-muted-foreground">LangGraph-powered multi-agent orchestration</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-4">
        {/* Stats */}
        {stats && [
          { label: "Total Runs", value: stats.total_runs, icon: <Activity className="h-4 w-4 text-blue-500" /> },
          { label: "Completed", value: stats.by_status?.completed ?? 0, icon: <CheckCircle className="h-4 w-4 text-green-500" /> },
          { label: "Failed", value: stats.by_status?.failed ?? 0, icon: <XCircle className="h-4 w-4 text-red-500" /> },
          { label: "Tokens Used", value: stats.total_tokens.toLocaleString(), icon: <Zap className="h-4 w-4 text-yellow-500" /> },
        ].map((s) => (
          <Card key={s.label}>
            <CardContent className="flex items-center gap-3 py-3">
              {s.icon}
              <div>
                <p className="text-xs text-muted-foreground">{s.label}</p>
                <p className="text-lg font-bold">{s.value}</p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid flex-1 gap-4 lg:grid-cols-3" style={{ minHeight: 0 }}>
        {/* Chat */}
        <Card className="flex flex-col lg:col-span-2" style={{ minHeight: "400px" }}>
          <CardHeader className="border-b pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Bot className="h-5 w-5 text-indigo-500" /> FamilyOps Assistant
              {chat.isPending && (
                <Badge variant="info" className="text-xs animate-pulse">Thinking...</Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-1 flex-col overflow-hidden p-0">
            <div className="flex-1 overflow-auto p-4 space-y-3">
              {messages.map((msg) => (
                <div key={msg.id} className={cn("flex", msg.role === "user" ? "justify-end" : "justify-start")}>
                  <div className={cn(
                    "flex max-w-[80%] gap-2",
                    msg.role === "user" && "flex-row-reverse"
                  )}>
                    <div className={cn(
                      "flex h-7 w-7 shrink-0 items-center justify-center rounded-full",
                      msg.role === "user" ? "bg-primary" : "bg-indigo-100"
                    )}>
                      {msg.role === "user"
                        ? <User className="h-3.5 w-3.5 text-white" />
                        : <Bot className="h-3.5 w-3.5 text-indigo-600" />}
                    </div>
                    <div className={cn(
                      "rounded-2xl px-4 py-2 text-sm",
                      msg.role === "user"
                        ? "bg-primary text-primary-foreground rounded-tr-sm"
                        : "bg-muted rounded-tl-sm"
                    )}>
                      {msg.content}
                    </div>
                  </div>
                </div>
              ))}
              {chat.isPending && (
                <div className="flex justify-start">
                  <div className="flex gap-2">
                    <div className="flex h-7 w-7 items-center justify-center rounded-full bg-indigo-100">
                      <Bot className="h-3.5 w-3.5 text-indigo-600" />
                    </div>
                    <div className="rounded-2xl rounded-tl-sm bg-muted px-4 py-3">
                      <div className="flex gap-1">
                        {[0, 1, 2].map((i) => (
                          <div key={i} className="h-2 w-2 rounded-full bg-muted-foreground animate-bounce" style={{ animationDelay: `${i * 0.15}s` }} />
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
            <div className="border-t p-3">
              <div className="flex gap-2 mb-2 flex-wrap">
                {QUICK_PROMPTS.slice(0, 3).map((p) => (
                  <button
                    key={p}
                    onClick={() => { setInput(p); }}
                    className="rounded-full border bg-background px-3 py-1 text-xs text-muted-foreground hover:bg-muted transition-colors"
                  >
                    {p}
                  </button>
                ))}
              </div>
              <form onSubmit={(e) => { e.preventDefault(); sendMessage(); }} className="flex gap-2">
                <Input
                  placeholder="Ask your household AI..."
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  disabled={chat.isPending}
                  className="flex-1"
                />
                <Button type="submit" disabled={!input.trim() || chat.isPending} size="icon">
                  <Send className="h-4 w-4" />
                </Button>
              </form>
            </div>
          </CardContent>
        </Card>

        {/* Run History */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Clock className="h-4 w-4" /> Recent Runs
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 overflow-auto" style={{ maxHeight: "450px" }}>
            {runs.length === 0 ? (
              <p className="text-center text-sm text-muted-foreground py-6">No runs yet</p>
            ) : (
              runs.map((r: any) => (
                <div key={r.id} className="rounded-md border p-2 space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium capitalize">{r.agent_name}</span>
                    <Badge
                      variant={r.status === "completed" ? "success" : r.status === "failed" ? "destructive" : "info"}
                      className="text-xs"
                    >
                      {r.status}
                    </Badge>
                  </div>
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span>{formatTimeAgo(r.started_at)}</span>
                    {r.duration_ms && <span>{r.duration_ms}ms</span>}
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function formatAgentResponse(result: any): string {
  const { status, result: r } = result;
  if (status === "failed") return `I encountered an error: ${r?.error || "Unknown error"}. Please try again.`;
  if (result?.reply?.trim()) return result.reply.trim();
  const intent = r?.context?.intent;
  const tools = r?.tools_called ?? [];
  const resource = r?.context?.resource;
  if (resource?.type === "grocery_list") {
    return `Created grocery list "${resource.name}" with ${resource.item_count} items. Open the Grocery tab to review it.`;
  }
  if (resource?.type === "meal_plan") {
    return `Created a meal plan for the requested week. Open the Meals tab to review it.`;
  }
  if (tools.length > 0) {
    return `I've processed your request using the ${tools.join(", ")} agent(s). The task has been handled successfully! You can see the results in the relevant section of the app.`;
  }
  return `I understood your request (intent: ${intent || "general"}). I'm ready to help with tasks, calendar, grocery, meals, reminders, and household memory. Try asking me something specific!`;
}
