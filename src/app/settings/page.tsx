"use client";
import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Settings, Database, Key, Bell, Bot, Cpu, ExternalLink, CheckCircle, XCircle, CloudSun, CalendarDays, UtensilsCrossed } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { dashboardApi } from "@/lib/api";

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState("integrations");

  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: () => dashboardApi.getHealth().then((r) => r.data),
    retry: false,
  });

  const { data: versionInfo } = useQuery({
    queryKey: ["dashboard-version"],
    queryFn: () => dashboardApi.getVersion().then((r) => r.data),
    retry: false,
  });

  const sharedRedis = health?.shared_resilience_redis as
    | { enabled?: boolean; available?: boolean; detail?: string; backend?: string }
    | undefined;
  const promptVersions = (versionInfo?.prompt_versions ?? {}) as Record<string, string>;
  const promptEntries = Object.entries(promptVersions) as Array<[string, string]>;

  const tabs = [
    { id: "integrations", label: "Integrations" },
    { id: "agents", label: "AI Agents" },
    { id: "notifications", label: "Notifications" },
    { id: "system", label: "System" },
  ];

  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">Configure your FamilyOps AI platform</p>
      </div>

      <div className="flex gap-1 border-b">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id)}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
              activeTab === t.id
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {activeTab === "integrations" && (
        <div className="space-y-4">
          <IntegrationCard
            icon={<Database className="h-5 w-5 text-green-500" />}
            title="Supabase Database"
            description="PostgreSQL database with pgvector for RAG. Configure your Supabase project credentials."
            status="configure"
            fields={[
              { label: "Supabase URL", placeholder: "https://your-project.supabase.co", env: "SUPABASE_URL" },
              { label: "Anon Key", placeholder: "eyJ...", env: "SUPABASE_KEY" },
              { label: "Service Key", placeholder: "eyJ...", env: "SUPABASE_SERVICE_KEY" },
            ]}
          />
          <IntegrationCard
            icon={<Bot className="h-5 w-5 text-blue-500" />}
            title="OpenAI API (Primary)"
            description="Powers all AI agents, embeddings, and LangGraph orchestration from your OPENAI_API_KEY and OPENAI_MODEL."
            status="configure"
            fields={[
              { label: "API Key", placeholder: "sk-...", env: "OPENAI_API_KEY" },
              { label: "Model", placeholder: "gpt-5.4-mini", env: "OPENAI_MODEL" },
              { label: "Embedding Model", placeholder: "text-embedding-3-small", env: "OPENAI_EMBEDDING_MODEL" },
            ]}
          />
          <IntegrationCard
            icon={<Bot className="h-5 w-5 text-indigo-500" />}
            title="Google Gemini API (Fallback)"
            description="Used only if OPENAI_API_KEY is not available."
            status="configure"
            fields={[
              { label: "API Key", placeholder: "AIza...", env: "GOOGLE_API_KEY" },
              { label: "Model", placeholder: "gemini-2.5-flash", env: "GOOGLE_MODEL" },
              { label: "Embedding Model", placeholder: "models/embedding-001", env: "GOOGLE_EMBEDDING_MODEL" },
            ]}
          />
          <IntegrationCard
            icon={<ExternalLink className="h-5 w-5 text-blue-500" />}
            title="Google Calendar"
            description="Sync and import events from Google Calendar."
            status="configure"
            fields={[
              { label: "Client ID", placeholder: "xxx.apps.googleusercontent.com", env: "GOOGLE_CLIENT_ID" },
              { label: "Client Secret", placeholder: "GOCSPX-...", env: "GOOGLE_CLIENT_SECRET" },
            ]}
          />
          <IntegrationCard
            icon={<Bell className="h-5 w-5 text-yellow-500" />}
            title="Email Ingestion (IMAP)"
            description="Ingest emails and extract action items automatically."
            status="configure"
            fields={[
              { label: "IMAP Host", placeholder: "imap.gmail.com", env: "EMAIL_IMAP_HOST" },
              { label: "Email Address", placeholder: "you@gmail.com", env: "EMAIL_ADDRESS" },
              { label: "App Password", placeholder: "xxxx xxxx xxxx xxxx", env: "EMAIL_PASSWORD" },
            ]}
          />
          <IntegrationCard
            icon={<ExternalLink className="h-5 w-5 text-cyan-500" />}
            title="Web Search"
            description="Fetches current external information with a pluggable provider layer."
            status="active"
            fields={[
              { label: "Provider", placeholder: "duckduckgo | tavily | auto", env: "WEB_SEARCH_PROVIDER" },
              { label: "Tavily API Key", placeholder: "tvly-...", env: "WEB_SEARCH_TAVILY_API_KEY" },
              { label: "Tavily Depth", placeholder: "basic", env: "WEB_SEARCH_TAVILY_SEARCH_DEPTH" },
              { label: "Max Results", placeholder: "5", env: "WEB_SEARCH_MAX_RESULTS" },
              { label: "Fetch Pages", placeholder: "3", env: "WEB_SEARCH_FETCH_LIMIT" },
            ]}
          />
          <IntegrationCard
            icon={<CloudSun className="h-5 w-5 text-sky-500" />}
            title="Weather"
            description="UK-friendly weather forecasts and current conditions powered by Open-Meteo."
            status="active"
            fields={[
              { label: "Country Code", placeholder: "GB", env: "WEATHER_DEFAULT_COUNTRY_CODE" },
              { label: "Forecast Days", placeholder: "5", env: "WEATHER_FORECAST_DAYS" },
            ]}
          />
          <IntegrationCard
            icon={<CalendarDays className="h-5 w-5 text-rose-500" />}
            title="Family Events"
            description="Search local family-friendly events around the area using Ticketmaster."
            status="configure"
            fields={[
              { label: "API Key", placeholder: "TM...", env: "TICKETMASTER_API_KEY" },
              { label: "Country Code", placeholder: "GB", env: "EVENT_SEARCH_COUNTRY_CODE" },
            ]}
          />
          <IntegrationCard
            icon={<UtensilsCrossed className="h-5 w-5 text-orange-500" />}
            title="Recipe Search"
            description="Search external recipe ideas and meal inspiration from TheMealDB."
            status="active"
            fields={[
              { label: "Provider", placeholder: "themealdb", env: "RECIPE_SEARCH_PROVIDER" },
            ]}
          />
        </div>
      )}

      {activeTab === "agents" && (
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Cpu className="h-4 w-4" /> Multi-Agent Architecture
              </CardTitle>
              <CardDescription>LangGraph-orchestrated specialist agents</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {[
                  { name: "Orchestrator", desc: "Routes requests to specialist agents, manages workflow state", status: "active" },
                  { name: "Email Agent", desc: "Ingests and processes emails, extracts action items", status: "active" },
                  { name: "Calendar Agent", desc: "Manages scheduling, syncs with Google Calendar", status: "active" },
                  { name: "Grocery Agent", desc: "Smart shopping list management and AI suggestions", status: "active" },
                  { name: "Meal Agent", desc: "Weekly meal planning with dietary preference awareness", status: "active" },
                  { name: "Reminder Agent", desc: "Schedules and dispatches family reminders", status: "active" },
                  { name: "Memory Agent", desc: "Stores and retrieves household knowledge via RAG", status: "active" },
                  { name: "Task Agent", desc: "Task orchestration and assignment", status: "active" },
                  { name: "Web Search Agent", desc: "Fetches current web results when household data is not enough", status: "active" },
                  { name: "Weather Agent", desc: "Fetches live weather for UK and other locations", status: "active" },
                  { name: "Event Agent", desc: "Finds family-friendly events around the area", status: "active" },
                  { name: "Recipe Agent", desc: "Searches external recipe ideas and cooking inspiration", status: "active" },
                ].map((agent) => (
                  <div key={agent.name} className="flex items-center justify-between rounded-md border p-3">
                    <div>
                      <p className="text-sm font-medium">{agent.name}</p>
                      <p className="text-xs text-muted-foreground">{agent.desc}</p>
                    </div>
                    <Badge variant="success" className="shrink-0">{agent.status}</Badge>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {activeTab === "system" && (
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">System Status</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {[
                { label: "Backend API", healthy: !!health, detail: health ? `v${health.version}` : "Not reachable" },
                { label: "Database", healthy: !!health, detail: health ? "SQLite (dev)" : "Disconnected" },
                { label: "Event Bus", healthy: !!health, detail: health ? "Running" : "Offline" },
                {
                  label: "Shared Redis",
                  healthy: !!sharedRedis?.enabled && !!sharedRedis?.available,
                  detail: sharedRedis
                    ? sharedRedis.enabled
                      ? sharedRedis.detail || "Shared resilience enabled"
                      : "Disabled in this environment"
                    : "Unknown",
                },
                { label: "LangGraph", healthy: true, detail: "Initialized" },
              ].map((s) => (
                <div key={s.label} className="flex items-center justify-between rounded-md border p-3">
                  <div className="flex items-center gap-2">
                    {s.healthy ? <CheckCircle className="h-4 w-4 text-green-500" /> : <XCircle className="h-4 w-4 text-red-500" />}
                    <p className="text-sm font-medium">{s.label}</p>
                  </div>
                  <span className="text-xs text-muted-foreground">{s.detail}</span>
                </div>
              ))}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Key className="h-4 w-4" /> Prompt Snapshot
              </CardTitle>
              <CardDescription>Versioned prompt registry surfaced by the backend</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center justify-between rounded-md border p-3">
                <p className="text-sm font-medium">Backend version</p>
                <span className="text-xs text-muted-foreground">
                  {versionInfo?.app_version ? `v${versionInfo.app_version}` : "Unknown"}
                </span>
              </div>
              <div className="flex items-center justify-between rounded-md border p-3">
                <p className="text-sm font-medium">Prompt registry</p>
                <span className="text-xs text-muted-foreground">
                  {versionInfo?.prompt_registry_version || "Unknown"}
                </span>
              </div>
              <div className="flex items-center justify-between rounded-md border p-3">
                <p className="text-sm font-medium">Prompt count</p>
                <span className="text-xs text-muted-foreground">
                  {typeof versionInfo?.prompt_count === "number" ? versionInfo.prompt_count : promptEntries.length}
                </span>
              </div>
              <div className="rounded-md border bg-muted/30 p-3">
                <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Prompt versions
                </p>
                <div className="space-y-1 font-mono text-xs text-muted-foreground">
                  {promptEntries.length > 0 ? (
                    promptEntries.map(([key, value]) => (
                      <div key={key} className="flex items-center justify-between gap-4">
                        <span>{key}</span>
                        <span>{value}</span>
                      </div>
                    ))
                  ) : (
                    <p>Version snapshot not loaded yet.</p>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Architecture Diagram</CardTitle>
              <CardDescription>Production-grade service boundaries</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="rounded-lg bg-muted p-4 font-mono text-xs space-y-1 text-muted-foreground">
                <p>┌─────────────────────────────────────────┐</p>
                <p>│          Next.js Frontend (port 5000)     │</p>
                <p>└──────────────────┬──────────────────────┘</p>
                <p>                   │ /api/v1/*</p>
                <p>┌──────────────────▼──────────────────────┐</p>
                <p>│       FastAPI Backend (port 8000)         │</p>
                <p>│  ┌──────────┐  ┌──────────────────────┐ │</p>
                <p>│  │ REST API │  │   LangGraph Engine   │ │</p>
                <p>│  └──────────┘  │  ┌────────────────┐  │ │</p>
                <p>│                │  │  Orchestrator  │  │ │</p>
                <p>│                │  │ ┌────┐ ┌────┐  │  │ │</p>
                <p>│                │  │ │Email│ │Cal.│  │  │ │</p>
                <p>│                │  │ └────┘ └────┘  │  │ │</p>
                <p>│                │  └────────────────┘  │ │</p>
                <p>│  ┌──────────┐  └──────────────────────┘ │</p>
                <p>│  │Event Bus │                            │</p>
                <p>│  └──────────┘  ┌──────────────────────┐ │</p>
                <p>│                │  SQLite / PostgreSQL  │ │</p>
                <p>│                │  + pgvector RAG       │ │</p>
                <p>│                └──────────────────────┘ │</p>
                <p>└─────────────────────────────────────────┘</p>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {activeTab === "notifications" && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Notification Channels</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {[
              { channel: "In-App", desc: "Push reminders in the browser", enabled: true },
              { channel: "Email", desc: "Send reminders via email", enabled: false },
              { channel: "SMS", desc: "Text message reminders (Twilio)", enabled: false },
              { channel: "Webhook", desc: "POST to custom webhook URL", enabled: false },
            ].map((n) => (
              <div key={n.channel} className="flex items-center justify-between rounded-md border p-3">
                <div>
                  <p className="text-sm font-medium">{n.channel}</p>
                  <p className="text-xs text-muted-foreground">{n.desc}</p>
                </div>
                <Badge variant={n.enabled ? "success" : "secondary"}>{n.enabled ? "Enabled" : "Disabled"}</Badge>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function IntegrationCard({ icon, title, description, status, fields }: any) {
  const [expanded, setExpanded] = useState(false);
  return (
    <Card>
      <CardContent className="pt-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="rounded-lg bg-muted p-2">{icon}</div>
            <div>
              <p className="font-medium text-sm">{title}</p>
              <p className="text-xs text-muted-foreground">{description}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline">{status}</Badge>
            <Button variant="ghost" size="sm" onClick={() => setExpanded(!expanded)}>
              {expanded ? "Hide" : "Configure"}
            </Button>
          </div>
        </div>
        {expanded && (
          <div className="mt-4 space-y-2 border-t pt-4">
            <p className="text-xs text-muted-foreground mb-2">
              Set these as environment variables in your <code className="bg-muted px-1 rounded">.env</code> file or Replit Secrets.
            </p>
            {fields.map((f: any) => (
              <div key={f.env} className="grid grid-cols-3 gap-2 items-center">
                <label className="text-xs font-mono text-muted-foreground col-span-1">{f.env}</label>
                <Input placeholder={f.placeholder} className="col-span-2 h-8 text-xs font-mono" readOnly />
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
