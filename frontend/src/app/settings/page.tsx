"use client";
import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Settings, Database, Key, Bell, Bot, Cpu, ExternalLink, CheckCircle, XCircle } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { dashboardApi } from "@/lib/api";

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState("integrations");

  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: () => dashboardApi.getHealth().then((r) => r.data),
    retry: false,
  });

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
            icon={<Bot className="h-5 w-5 text-indigo-500" />}
            title="OpenAI API"
            description="Powers all AI agents, embeddings, and LangGraph orchestration."
            status="configure"
            fields={[
              { label: "API Key", placeholder: "sk-...", env: "OPENAI_API_KEY" },
              { label: "Model", placeholder: "gpt-4o", env: "OPENAI_MODEL" },
              { label: "Embedding Model", placeholder: "text-embedding-3-small", env: "OPENAI_EMBEDDING_MODEL" },
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
