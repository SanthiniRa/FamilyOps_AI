"use client";
import { useState, useRef, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { agentApi } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Bot, Send, User, Activity, Clock, CheckCircle, XCircle, Sparkles } from "lucide-react";
import { formatTimeAgo, cn } from "@/lib/utils";

interface Message {
  id: string;
  role: "user" | "agent";
  content: string;
  status?: string;
  agentUsed?: string;
  durationMs?: number;
  tokensUsed?: number;
  resource?: any;
  timestamp: Date;
}

const QUICK_PROMPTS = [
  "What tasks are overdue?",
  "What's on the calendar this week?",
  "What's left on my grocery list?",
  "Show me this week's meal plan",
  "What reminders are coming up?",
  "What do you remember about our family?",
];

function renderMarkdown(text: string) {
  const lines = text.split("\n");
  return lines.map((line, i) => {
    if (line.startsWith("- ") || line.startsWith("• ")) {
      return (
        <li key={i} className="ml-4 list-disc text-sm leading-relaxed">
          {renderInline(line.slice(2))}
        </li>
      );
    }
    if (line.trim() === "") return <div key={i} className="h-1.5" />;
    return (
      <p key={i} className="text-sm leading-relaxed">
        {renderInline(line)}
      </p>
    );
  });
}

function renderInline(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return (
    <>
      {parts.map((part, i) =>
        part.startsWith("**") && part.endsWith("**") ? (
          <strong key={i}>{part.slice(2, -2)}</strong>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
    </>
  );
}

export default function AgentPage() {
  const qc = useQueryClient();
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "agent",
      content:
        "Hi! I'm your FamilyOps AI assistant powered by Gemini. I can see your tasks, calendar, grocery lists, meal plans, reminders, and household memory in real time.\n\nWhat can I help you with today?",
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
    refetchInterval: 15000,
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
      const data = response.data;
      const agentMsg: Message = {
        id: data.run_id || Date.now().toString(),
        role: "agent",
        content:
          data.reply ||
          formatCreatedResource(data.resource) ||
          "Done! Check the relevant section for updates.",
        status: data.status,
        agentUsed: data.tools_called?.[0],
        durationMs: data.duration_ms,
        tokensUsed: data.tokens_used,
        resource: data.resource,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, agentMsg]);
      qc.invalidateQueries({ queryKey: ["agent-runs"] });
      qc.invalidateQueries({ queryKey: ["agent-stats"] });
      qc.invalidateQueries({ queryKey: ["grocery-lists"] });
      qc.invalidateQueries({ queryKey: ["meal-plans"] });
    },
    onError: () => {
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now().toString(),
          role: "agent",
          content:
            "Sorry, the backend returned an error. Please check the Railway backend logs.",
          timestamp: new Date(),
        },
      ]);
    },
  });

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = () => {
    if (!input.trim() || chat.isPending) return;
    const msg = input.trim();
    setInput("");
    chat.mutate(msg);
  };

  return (
    <div className="flex h-[calc(100vh-64px)] flex-col gap-4 p-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">AI Agent</h1>
        <p className="text-sm text-muted-foreground">
          Gemini-powered household assistant with real-time data access
        </p>
      </div>

      {/* Stats row */}
      {stats && (
        <div className="grid grid-cols-2 gap-3 shrink-0 md:grid-cols-5">
          {[
            {
              label: "Total Runs",
              value: stats.total_runs,
              icon: <Activity className="h-4 w-4 text-blue-500" />,
            },
            {
              label: "Completed",
              value: stats.by_status?.completed ?? 0,
              icon: <CheckCircle className="h-4 w-4 text-green-500" />,
            },
            {
              label: "Failed",
              value: stats.by_status?.failed ?? 0,
              icon: <XCircle className="h-4 w-4 text-red-500" />,
            },
            {
              label: "Avg Time",
              value: stats.avg_duration_ms
                ? `${Math.round(stats.avg_duration_ms)}ms`
                : "—",
              icon: <Clock className="h-4 w-4 text-yellow-500" />,
            },
            {
              label: "Tokens Used",
              value: stats.total_tokens ?? 0,
              icon: <Sparkles className="h-4 w-4 text-indigo-500" />,
            },
          ].map((s) => (
            <Card key={s.label}>
              <CardContent className="flex items-center gap-3 py-3">
                {s.icon}
                <div>
                  <p className="text-xs text-muted-foreground">{s.label}</p>
                  <p className="text-base font-bold">{s.value}</p>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <div className="grid flex-1 gap-4 lg:grid-cols-3 min-h-0 overflow-hidden">
        {/* Chat panel */}
        <Card className="flex flex-col lg:col-span-2 min-h-0 overflow-hidden">
          <CardHeader className="border-b py-3 shrink-0">
            <CardTitle className="flex items-center gap-2 text-base">
              <div className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-indigo-600">
                <Bot className="h-4 w-4 text-white" />
              </div>
              FamilyOps Assistant
              <Badge
                variant="outline"
                className="text-xs ml-1 border-blue-300 text-blue-600"
              >
                Gemini
              </Badge>
              {chat.isPending && (
                <span className="ml-auto flex items-center gap-1 text-xs text-muted-foreground animate-pulse">
                  <Sparkles className="h-3 w-3" /> Thinking...
                </span>
              )}
            </CardTitle>
          </CardHeader>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={cn(
                  "flex gap-2",
                  msg.role === "user" ? "justify-end" : "justify-start"
                )}
              >
                {msg.role === "agent" && (
                  <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 mt-0.5">
                    <Bot className="h-3.5 w-3.5 text-white" />
                  </div>
                )}
                <div
                  className={cn(
                    "max-w-[78%] rounded-2xl px-4 py-2.5",
                    msg.role === "user"
                      ? "bg-primary text-primary-foreground rounded-tr-sm"
                      : "bg-muted rounded-tl-sm"
                  )}
                >
                  {msg.role === "agent" ? (
                    <div className="space-y-0.5">
                      {renderMarkdown(msg.content)}
                      {msg.resource && renderResource(msg.resource)}
                    </div>
                  ) : (
                    <p className="text-sm">{msg.content}</p>
                  )}
                  {msg.role === "agent" &&
                    (msg.agentUsed || msg.durationMs) && (
                      <div className="mt-2 flex items-center gap-2">
                        {msg.agentUsed && (
                          <Badge
                            variant="outline"
                            className="text-xs capitalize"
                          >
                            {msg.agentUsed.replace("_agent", "")} agent
                          </Badge>
                        )}
                        {msg.durationMs && (
                          <span className="text-xs text-muted-foreground">
                            {msg.durationMs}ms
                          </span>
                        )}
                        {msg.tokensUsed !== undefined && (
                          <span className="text-xs text-muted-foreground">
                            {msg.tokensUsed} tokens
                          </span>
                        )}
                      </div>
                    )}
                </div>
                {msg.role === "user" && (
                  <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary mt-0.5">
                    <User className="h-3.5 w-3.5 text-white" />
                  </div>
                )}
              </div>
            ))}

            {/* Typing indicator */}
            {chat.isPending && (
              <div className="flex gap-2 justify-start">
                <div className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-indigo-600">
                  <Bot className="h-3.5 w-3.5 text-white" />
                </div>
                <div className="rounded-2xl rounded-tl-sm bg-muted px-4 py-3">
                  <div className="flex gap-1 items-center">
                    {[0, 1, 2].map((i) => (
                      <div
                        key={i}
                        className="h-1.5 w-1.5 rounded-full bg-muted-foreground animate-bounce"
                        style={{ animationDelay: `${i * 0.15}s` }}
                      />
                    ))}
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input area */}
          <div className="border-t p-3 shrink-0">
            <div className="mb-2 flex flex-wrap gap-1.5">
              {QUICK_PROMPTS.map((p) => (
                <button
                  key={p}
                  onClick={() => setInput(p)}
                  className="rounded-full border bg-background px-3 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                >
                  {p}
                </button>
              ))}
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                sendMessage();
              }}
              className="flex gap-2"
            >
              <Input
                placeholder="Ask about your household..."
                value={input}
                onChange={(e) => setInput(e.target.value)}
                disabled={chat.isPending}
                className="flex-1"
              />
              <Button
                type="submit"
                disabled={!input.trim() || chat.isPending}
                size="icon"
              >
                <Send className="h-4 w-4" />
              </Button>
            </form>
          </div>
        </Card>

        {/* Run history panel */}
        <Card className="flex flex-col min-h-0 overflow-hidden">
          <CardHeader className="py-3 border-b shrink-0">
            <CardTitle className="text-sm flex items-center gap-2">
              <Clock className="h-4 w-4" /> Agent Run History
            </CardTitle>
          </CardHeader>
          <div className="flex-1 overflow-y-auto p-3 space-y-2">
            {runs.length === 0 ? (
              <p className="text-center text-xs text-muted-foreground py-8">
                No runs yet — send a message!
              </p>
            ) : (
              runs.map((r: any) => (
                <div key={r.id} className="rounded-md border p-2 space-y-1">
                  <div className="flex items-center justify-between gap-1">
                    <span className="text-xs font-medium capitalize truncate">
                      {r.agent_name}
                    </span>
                    <Badge
                      variant={
                        r.status === "completed"
                          ? "success"
                          : r.status === "failed"
                          ? "destructive"
                          : "secondary"
                      }
                      className="text-xs shrink-0"
                    >
                      {r.status}
                    </Badge>
                  </div>
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span>{formatTimeAgo(r.started_at)}</span>
                    <div className="flex items-center gap-2">
                      {r.duration_ms && <span>{r.duration_ms}ms</span>}
                      <span>{r.tokens_used ?? 0} tokens</span>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}

function formatCreatedResource(resource: any): string {
  if (!resource?.type) return "";
  if (resource.type === "grocery_list") {
    return `Created grocery list "${resource.name}" with ${resource.item_count ?? 0} items.`;
  }
  if (resource.type === "meal_plan") {
    return "Created a meal plan for the requested week.";
  }
  if (resource.type === "activity_search" || resource.type === "event_search") {
    return `Found ${resource.results?.length ?? 0} activity options.`;
  }
  return "";
}

function renderResource(resource: any) {
  if (resource?.type === "activity_search" || resource?.type === "event_search") {
    return renderActivityResource(resource);
  }

  if (resource?.type === "web_search") {
    return renderWebSearchResource(resource);
  }

  if (resource?.type === "weather_search") {
    return renderWeatherResource(resource);
  }

  return null;
}

function renderActivityResource(resource: any) {
  const results = Array.isArray(resource.results) ? resource.results.slice(0, 5) : [];

  return (
    <div className="mt-3 rounded-2xl border bg-background/80 p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Activity results
        </p>
        <div className="flex gap-1">
          {resource.sources?.events && <Badge variant="outline" className="text-[10px]">events</Badge>}
          {resource.sources?.web && <Badge variant="outline" className="text-[10px]">web</Badge>}
        </div>
      </div>

      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[760px] border-collapse text-left text-xs">
          <thead>
            <tr className="border-b bg-muted/40">
              <th className="px-2 py-2 font-semibold">Activity</th>
              <th className="px-2 py-2 font-semibold">Date</th>
              <th className="px-2 py-2 font-semibold">Time</th>
              <th className="px-2 py-2 font-semibold">Cost</th>
              <th className="px-2 py-2 font-semibold">Transport</th>
              <th className="px-2 py-2 font-semibold">Time taken</th>
              <th className="px-2 py-2 font-semibold">Source</th>
            </tr>
          </thead>
          <tbody>
            {results.map((item: any, index: number) => (
              <tr key={`${item.title || item.name || "activity"}-${index}`} className="border-b last:border-b-0">
                <td className="px-2 py-3 align-top">
                  <div className="space-y-1">
                    <p className="font-medium text-foreground">{item.title || item.name || "Untitled activity"}</p>
                    {item.location && <p className="text-muted-foreground">{item.location}</p>}
                    {item.summary && <p className="text-muted-foreground">{item.summary}</p>}
                  </div>
                </td>
                <td className="px-2 py-3 align-top text-muted-foreground">{item.date || "Not listed"}</td>
                <td className="px-2 py-3 align-top text-muted-foreground">{item.time || "Not listed"}</td>
                <td className="px-2 py-3 align-top">
                  {item.cost ? <Badge variant="secondary" className="whitespace-nowrap">{item.cost}</Badge> : "Not listed"}
                </td>
                <td className="px-2 py-3 align-top text-muted-foreground">{item.transport || "Not listed"}</td>
                <td className="px-2 py-3 align-top text-muted-foreground">{item.time_taken || "Not listed"}</td>
                <td className="px-2 py-3 align-top text-muted-foreground">
                  {item.source === "event_search" ? "Ticketmaster" : item.source === "web_search" ? "Web" : "Unknown"}
                </td>
              </tr>
            ))}
            {results.length === 0 && (
              <tr>
                <td className="px-2 py-3 text-sm text-muted-foreground" colSpan={7}>
                  No structured activity details were found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function renderWeatherResource(resource: any) {
  const current = resource.current || {};
  const daily = Array.isArray(resource.daily) ? resource.daily.slice(0, 5) : [];
  const location = resource.location?.name || resource.query || "your area";

  return (
    <div className="mt-3 rounded-2xl border bg-background/80 p-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Weather forecast
      </p>

      <div className="mt-3 space-y-3">
        <div className="grid gap-2 sm:grid-cols-2">
          <div className="rounded-xl border p-3">
            <p className="text-xs font-semibold text-muted-foreground">Location</p>
            <p className="mt-1 text-sm font-medium">{location}</p>
            {resource.location?.region && (
              <p className="text-xs text-muted-foreground">{resource.location.region}</p>
            )}
          </div>

          <div className="rounded-xl border p-3">
            <p className="text-xs font-semibold text-muted-foreground">Current conditions</p>
            <p className="mt-1 text-sm font-medium">
              {current.temperature !== undefined && current.temperature !== null ? `${current.temperature}°C` : "Not listed"}
              {current.summary ? `, ${current.summary}` : ""}
            </p>
            <p className="text-xs text-muted-foreground">
              {current.apparent_temperature !== undefined && current.apparent_temperature !== null
                ? `Feels like ${current.apparent_temperature}°C`
                : "Feels-like temperature not listed"}
              {current.wind_speed !== undefined && current.wind_speed !== null
                ? ` • Wind ${current.wind_speed} km/h`
                : ""}
            </p>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[620px] border-collapse text-left text-xs">
            <thead>
              <tr className="border-b bg-muted/40">
                <th className="px-2 py-2 font-semibold">Date</th>
                <th className="px-2 py-2 font-semibold">Summary</th>
                <th className="px-2 py-2 font-semibold">Low</th>
                <th className="px-2 py-2 font-semibold">High</th>
                <th className="px-2 py-2 font-semibold">Precipitation</th>
                <th className="px-2 py-2 font-semibold">Wind</th>
              </tr>
            </thead>
            <tbody>
              {daily.map((day: any, index: number) => (
                <tr key={`${day.date || "day"}-${index}`} className="border-b last:border-b-0">
                  <td className="px-2 py-3 text-muted-foreground">{day.date || "Not listed"}</td>
                  <td className="px-2 py-3 text-muted-foreground">{day.summary || "Not listed"}</td>
                  <td className="px-2 py-3 text-muted-foreground">
                    {day.temperature_min !== undefined && day.temperature_min !== null ? `${day.temperature_min}°C` : "Not listed"}
                  </td>
                  <td className="px-2 py-3 text-muted-foreground">
                    {day.temperature_max !== undefined && day.temperature_max !== null ? `${day.temperature_max}°C` : "Not listed"}
                  </td>
                  <td className="px-2 py-3 text-muted-foreground">
                    {day.precipitation_sum !== undefined && day.precipitation_sum !== null ? `${day.precipitation_sum}` : "Not listed"}
                  </td>
                  <td className="px-2 py-3 text-muted-foreground">
                    {day.wind_speed_max !== undefined && day.wind_speed_max !== null ? `${day.wind_speed_max}` : "Not listed"}
                  </td>
                </tr>
              ))}
              {daily.length === 0 && (
                <tr>
                  <td className="px-2 py-3 text-sm text-muted-foreground" colSpan={6}>
                    No forecast details were returned.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function renderWebSearchResource(resource: any) {
  const results = Array.isArray(resource.results) ? resource.results.slice(0, 5) : [];

  return (
    <div className="mt-3 rounded-2xl border bg-background/80 p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Web results
        </p>
        <Badge variant="outline" className="text-[10px]">{resource.provider || "web"}</Badge>
      </div>

      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[760px] border-collapse text-left text-xs">
          <thead>
            <tr className="border-b bg-muted/40">
              <th className="px-2 py-2 font-semibold">Title</th>
              <th className="px-2 py-2 font-semibold">URL</th>
              <th className="px-2 py-2 font-semibold">Snippet</th>
            </tr>
          </thead>
          <tbody>
            {results.map((item: any, index: number) => {
              const title = item.page_title || item.title || "Untitled";
              const url = item.url || "";
              const snippet = item.page_description || item.snippet || item.page_excerpt || "";
              return (
                <tr key={`${title}-${index}`} className="border-b last:border-b-0">
                  <td className="px-2 py-3 align-top">
                    <div className="space-y-1">
                      <p className="font-medium text-foreground">{title}</p>
                      {item.domain && <p className="text-muted-foreground">{item.domain}</p>}
                    </div>
                  </td>
                  <td className="px-2 py-3 align-top text-muted-foreground">
                    {url ? (
                      <a href={url} target="_blank" rel="noreferrer" className="break-all text-primary hover:underline">
                        {url}
                      </a>
                    ) : (
                      "Not listed"
                    )}
                  </td>
                  <td className="px-2 py-3 align-top text-muted-foreground">{snippet || "Not listed"}</td>
                </tr>
              );
            })}
            {results.length === 0 && (
              <tr>
                <td className="px-2 py-3 text-sm text-muted-foreground" colSpan={3}>
                  No web results were found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
