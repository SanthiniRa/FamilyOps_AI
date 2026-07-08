"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getSmsShortcutEndpoint, smsApi } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  MessageSquare, Calendar, CheckSquare, Smartphone, Send,
  RefreshCw, AlertCircle, ChevronDown, ChevronUp, Apple, Clipboard, Image as ImageIcon
} from "lucide-react";

// ─── helpers ──────────────────────────────────────────────────────────────────
function timeAgo(iso: string | null) {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function sourceLabel(src: string) {
  if (!src) return "Unknown";
  if (src.toLowerCase().includes("whatsapp")) return "WhatsApp";
  if (src.toLowerCase().includes("sms")) return "SMS";
  if (src.toLowerCase().includes("shortcut")) return "Shortcut";
  return src.charAt(0).toUpperCase() + src.slice(1);
}

function sourceBadgeColor(src: string) {
  if (src?.toLowerCase().includes("whatsapp")) return "bg-green-100 text-green-800";
  if (src?.toLowerCase().includes("sms")) return "bg-blue-100 text-blue-800";
  return "bg-purple-100 text-purple-800";
}

// ─── Message card ─────────────────────────────────────────────────────────────
function MessageCard({ msg }: { msg: any }) {
  const [expanded, setExpanded] = useState(false);
  const src = msg.extracted_data?.source || msg.from_number || "";

  return (
    <Card className={`transition-all ${msg.is_appointment ? "border-blue-200 bg-blue-50/30" : ""}`}>
      <CardContent className="p-4">
        <div className="flex items-start gap-3">
          {/* icon */}
          <div className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full
            ${msg.is_appointment ? "bg-blue-100 text-blue-600" : "bg-muted text-muted-foreground"}`}>
            <MessageSquare className="h-4 w-4" />
          </div>

          <div className="min-w-0 flex-1 space-y-1">
            {/* top row */}
            <div className="flex flex-wrap items-center gap-2">
              <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${sourceBadgeColor(src)}`}>
                {sourceLabel(src)}
              </span>
              {msg.is_appointment && (
                <span className="inline-flex items-center gap-1 rounded-full bg-blue-600 px-2 py-0.5 text-xs font-medium text-white">
                  <Calendar className="h-3 w-3" /> Appointment
                </span>
              )}
              {(msg.tasks_created?.length > 0) && (
                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700">
                  <CheckSquare className="h-3 w-3" /> {msg.tasks_created.length} task{msg.tasks_created.length > 1 ? "s" : ""}
                </span>
              )}
              {(msg.events_created?.length > 0) && (
                <span className="inline-flex items-center gap-1 rounded-full bg-violet-100 px-2 py-0.5 text-xs font-medium text-violet-700">
                  <Calendar className="h-3 w-3" /> {msg.events_created.length} event{msg.events_created.length > 1 ? "s" : ""}
                </span>
              )}
              <span className="ml-auto text-xs text-muted-foreground">{timeAgo(msg.created_at)}</span>
            </div>

            {/* message body */}
            <p className="text-sm leading-snug text-foreground">
              {expanded ? msg.body : (msg.body?.slice(0, 160) + (msg.body?.length > 160 ? "…" : ""))}
            </p>

            {/* sender */}
            {msg.from_number && msg.from_number !== "shortcut" && (
              <p className="text-xs text-muted-foreground">From: {msg.from_number}</p>
            )}

            {/* extracted appointment info */}
            {msg.is_appointment && msg.extracted_data && (
              <div className="mt-2 rounded-md border border-blue-200 bg-white p-3 text-xs space-y-1">
                {msg.extracted_data.doctor_or_clinic && (
                  <p><span className="font-medium text-muted-foreground">Who:</span> {msg.extracted_data.doctor_or_clinic}</p>
                )}
                {msg.extracted_data.appointment_date && (
                  <p><span className="font-medium text-muted-foreground">When:</span>{" "}
                    {new Date(msg.extracted_data.appointment_date).toLocaleString("en-GB", {
                      weekday: "short", day: "numeric", month: "short",
                      hour: "2-digit", minute: "2-digit"
                    })}
                  </p>
                )}
                {msg.extracted_data.location && (
                  <p><span className="font-medium text-muted-foreground">Where:</span> {msg.extracted_data.location}</p>
                )}
                {msg.extracted_data.purpose && (
                  <p><span className="font-medium text-muted-foreground">Purpose:</span> {msg.extracted_data.purpose}</p>
                )}
              </div>
            )}

            {/* expand/collapse */}
            {msg.body?.length > 160 && (
              <button
                onClick={() => setExpanded(!expanded)}
                className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
              >
                {expanded ? <><ChevronUp className="h-3 w-3" /> Show less</> : <><ChevronDown className="h-3 w-3" /> Show full message</>}
              </button>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Setup guide card ─────────────────────────────────────────────────────────
function SetupGuide({ endpoint, instructions }: { endpoint: string; instructions?: any }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  const resolvedEndpoint = instructions?.endpoint ?? endpoint;
  const posterEndpoint = instructions?.poster_endpoint ?? endpoint.replace(/\/shortcut$/, "/shortcut-image");
  const tokenNote = instructions?.token_note ?? "";
  const bodyFormat = instructions?.body_format ?? {
    text: "<the copied/shared message>",
    source: "sms  or  whatsapp  or  other",
    sender: "optional sender label",
    token: "<your SMS_WEBHOOK_TOKEN or leave blank>",
  };

  const copy = (text: string, key: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(key);
      setTimeout(() => setCopied(null), 2000);
    });
  };

  const smsSteps = [
    { step: "1", label: "Open Shortcuts app → tap + → tap Add Action" },
    { step: "2", label: 'Search "Get Clipboard" → select it' },
    { step: "3", label: 'Add another action → search "Get Contents of URL" → select it' },
    { step: "4", label: "Set Method to POST. Paste the URL below as the request URL (do not append the SMS to the URL):", url: resolvedEndpoint, urlKey: "sms" },
    { step: "5", label: 'Set Request Body to JSON and add these keys: text, source, sender, token. Use Clipboard for text.' },
    { step: "6", label: 'Add action → search "Show Notification" → Message: tap variable picker → choose "Contents of URL" → key: summary' },
    { step: "7", label: 'Name it "SMS → FamilyOps" → Done' },
  ];

  const waSteps = [
    { step: "1", label: 'Create a new shortcut with the same actions, but use the same POST endpoint below:' , url: resolvedEndpoint, urlKey: "wa" },
    { step: "2", label: 'For "Get Contents of URL" → use Shortcut Input as the text value (not Clipboard).' },
    { step: "3", label: 'Set source to whatsapp in the JSON body and keep the rest the same.' },
    { step: "4", label: 'Tap the shortcut name → ⓘ icon → turn on "Use as Quick Action" → tick Share Sheet → Receive: Text.' },
    { step: "5", label: 'Name it "WhatsApp → FamilyOps" → Done.' },
    { step: "6", label: 'To use: long-press a WhatsApp message → Share → "WhatsApp → FamilyOps".' },
  ];

  const posterSteps = [
    { step: "1", label: "Create a new shortcut → turn on Share Sheet → Receive: Images" },
    { step: "2", label: 'Add action → search "Get Contents of URL" → select it' },
    { step: "3", label: "Set Method to POST. Paste the image endpoint below as the request URL:", url: posterEndpoint, urlKey: "poster" },
    { step: "4", label: 'Set Request Body to Form. Add a file field named "file" and set it to Shortcut Input.' },
    { step: "5", label: 'Add text fields: source = poster, sender = optional, token = your token.' },
    { step: "6", label: 'Add action → "Show Notification" → Message: Contents of URL → summary' },
    { step: "7", label: 'Name it "Poster → FamilyOps" → Done' },
  ];

  return (
    <Card className="border-dashed border-2 border-muted">
      <CardHeader className="pb-2 cursor-pointer" onClick={() => setOpen(!open)}>
        <CardTitle className="flex items-center justify-between text-sm">
          <span className="flex items-center gap-2">
            <Apple className="h-4 w-4" />
            iPhone Setup — tap to see exact steps
          </span>
          {open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </CardTitle>
      </CardHeader>

      {open && (
        <CardContent className="pt-0 space-y-6 text-sm">

          {/* how it works */}
          <div className="rounded-md bg-blue-50 border border-blue-200 p-3 text-xs text-blue-800">
            <strong>How it works:</strong> Copy an SMS, share a WhatsApp message, or share a poster image → run the Shortcut → the AI reads it, detects appointments or date-based reminders, and adds tasks + calendar events automatically. No typing needed.
            <div className="mt-2">
              <strong>Important:</strong> use POST JSON, not a GET query string. That avoids broken URLs when messages contain punctuation or ampersands.
            </div>
          </div>

          {/* SMS shortcut */}
          <div>
            <p className="mb-3 font-semibold flex items-center gap-2">
              <Smartphone className="h-4 w-4 text-blue-500" /> Shortcut 1 — Doctor SMS (copy &amp; run)
            </p>
            <ol className="space-y-3">
              {smsSteps.map(({ step, label, url, urlKey }) => (
                <li key={step} className="flex gap-3">
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-blue-100 text-xs font-bold text-blue-700">{step}</span>
                  <div className="space-y-1">
                    <span className="text-muted-foreground leading-snug">{label}</span>
                    {url && (
                      <div className="flex items-center gap-2">
                        <code className="block rounded bg-muted px-2 py-1 text-xs break-all font-mono flex-1">{url}</code>
                        <button
                          onClick={() => copy(url, urlKey!)}
                          className="shrink-0 rounded border px-2 py-1 text-xs hover:bg-muted"
                        >
                          {copied === urlKey ? "✓" : "Copy"}
                        </button>
                      </div>
                    )}
                  </div>
                </li>
              ))}
            </ol>
            <div className="mt-3 rounded-md bg-green-50 border border-green-200 p-2 text-xs text-green-800">
              <strong>To use:</strong> Copy a doctor SMS → open Shortcuts → tap "SMS → FamilyOps" → notification appears ✅
            </div>
            <div className="mt-3 rounded-md border bg-muted/30 p-3 text-xs">
              <p className="font-semibold mb-2">JSON body</p>
              <pre className="overflow-x-auto whitespace-pre-wrap break-words font-mono text-[11px] leading-5">
{JSON.stringify(bodyFormat, null, 2)}
              </pre>
              {tokenNote && <p className="mt-2 text-muted-foreground">{tokenNote}</p>}
            </div>
          </div>

          <hr />

          {/* WhatsApp shortcut */}
          <div>
            <p className="mb-3 font-semibold flex items-center gap-2 text-green-700">
              <MessageSquare className="h-4 w-4 text-green-500" /> Shortcut 2 — School WhatsApp (share menu)
            </p>
            <ol className="space-y-3">
              {waSteps.map(({ step, label, url, urlKey }) => (
                <li key={step} className="flex gap-3">
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-green-100 text-xs font-bold text-green-700">{step}</span>
                  <div className="space-y-1">
                    <span className="text-muted-foreground leading-snug">{label}</span>
                    {url && (
                      <div className="flex items-center gap-2">
                        <code className="block rounded bg-muted px-2 py-1 text-xs break-all font-mono flex-1">{url}</code>
                        <button
                          onClick={() => copy(url, urlKey!)}
                          className="shrink-0 rounded border px-2 py-1 text-xs hover:bg-muted"
                        >
                          {copied === urlKey ? "✓" : "Copy"}
                        </button>
                      </div>
                    )}
                  </div>
                </li>
              ))}
            </ol>
            <div className="mt-3 rounded-md bg-green-50 border border-green-200 p-2 text-xs text-green-800">
              <strong>To use:</strong> Long-press a WhatsApp message → Share → "WhatsApp → FamilyOps" → notification appears ✅
            </div>
            <div className="mt-3 rounded-md border bg-muted/30 p-3 text-xs">
              <p className="font-semibold mb-2">JSON body</p>
              <pre className="overflow-x-auto whitespace-pre-wrap break-words font-mono text-[11px] leading-5">
{JSON.stringify({ ...bodyFormat, source: "whatsapp" }, null, 2)}
              </pre>
              {tokenNote && <p className="mt-2 text-muted-foreground">{tokenNote}</p>}
            </div>
          </div>

          <hr />

          {/* Poster shortcut */}
          <div>
            <p className="mb-3 font-semibold flex items-center gap-2 text-amber-700">
              <ImageIcon className="h-4 w-4 text-amber-500" /> Shortcut 3 — Poster / Flyer (share image)
            </p>
            <ol className="space-y-3">
              {posterSteps.map(({ step, label, url, urlKey }) => (
                <li key={step} className="flex gap-3">
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-amber-100 text-xs font-bold text-amber-700">{step}</span>
                  <div className="space-y-1">
                    <span className="text-muted-foreground leading-snug">{label}</span>
                    {url && (
                      <div className="flex items-center gap-2">
                        <code className="block rounded bg-muted px-2 py-1 text-xs break-all font-mono flex-1">{url}</code>
                        <button
                          onClick={() => copy(url, urlKey!)}
                          className="shrink-0 rounded border px-2 py-1 text-xs hover:bg-muted"
                        >
                          {copied === urlKey ? "✓" : "Copy"}
                        </button>
                      </div>
                    )}
                  </div>
                </li>
              ))}
            </ol>
            <div className="mt-3 rounded-md bg-amber-50 border border-amber-200 p-2 text-xs text-amber-800">
              <strong>To use:</strong> Share a flyer or poster image → run "Poster → FamilyOps" → it OCRs the image, finds the date, and creates a task or calendar event.
            </div>
          </div>

        </CardContent>
      )}
    </Card>
  );
}

// ─── Test panel ───────────────────────────────────────────────────────────────
function TestPanel({ onTested }: { onTested: () => void }) {
  const [text, setText] = useState("");
  const [result, setResult] = useState<any>(null);

  const test = useMutation({
    mutationFn: (body: string) => smsApi.test(body).then(r => r.data),
    onSuccess: (data) => { setResult(data); onTested(); },
  });

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Send className="h-4 w-4 text-muted-foreground" />
          Test — paste any SMS or WhatsApp message below
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <textarea
          className="w-full rounded-md border bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          rows={3}
          placeholder="e.g. Reminder: Your appointment with Dr. Patel is on Fri 4 Jul at 10:30 AM. City Dental Clinic. Reply YES to confirm."
          value={text}
          onChange={e => setText(e.target.value)}
        />
        <Button
          size="sm"
          disabled={!text.trim() || test.isPending}
          onClick={() => test.mutate(text.trim())}
        >
          {test.isPending ? <><RefreshCw className="mr-2 h-3 w-3 animate-spin" />Processing…</> : "Send to AI"}
        </Button>

        {result && (
          <div className={`rounded-md border p-3 text-xs space-y-1 ${result.is_appointment ? "border-blue-200 bg-blue-50" : "border-muted bg-muted/30"}`}>
            <p className="font-semibold">{result.is_appointment ? "✅ Appointment detected!" : "💬 No appointment detected"}</p>
            {result.is_appointment && result.extracted?.doctor_or_clinic && (
              <p>Who: <strong>{result.extracted.doctor_or_clinic}</strong></p>
            )}
            {result.is_appointment && result.extracted?.appointment_date && (
              <p>When: <strong>{new Date(result.extracted.appointment_date).toLocaleString("en-GB", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</strong></p>
            )}
            {result.is_appointment && result.extracted?.location && (
              <p>Where: <strong>{result.extracted.location}</strong></p>
            )}
            <p className="pt-1 text-muted-foreground">
              {result.tasks_created?.length ?? 0} task(s) · {result.events_created?.length ?? 0} calendar event(s) created
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────
export default function MessagesPage() {
  const qc = useQueryClient();
  const [filter, setFilter] = useState<"all" | "appointments">("all");

  const { data: messages = [], isLoading, error } = useQuery({
    queryKey: ["sms-messages", filter],
    queryFn: () =>
      smsApi.list(filter === "appointments" ? { appointments_only: "true" } : {}).then(r => r.data),
    refetchInterval: 30000,
  });

  const { data: instructions } = useQuery({
    queryKey: ["sms-instructions"],
    queryFn: () => smsApi.instructions().then(r => r.data),
  });

  const msgs = Array.isArray(messages) ? messages : [];
  const apptCount = msgs.filter((m: any) => m.is_appointment).length;

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Messages</h1>
          <p className="text-sm text-muted-foreground">
            SMS &amp; WhatsApp messages forwarded from your iPhone — appointments auto-detected by AI
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => qc.invalidateQueries({ queryKey: ["sms-messages"] })}>
          <RefreshCw className="mr-2 h-3 w-3" /> Refresh
        </Button>
      </div>

      {/* stats */}
      <div className="grid grid-cols-3 gap-4">
        <Card>
          <CardContent className="flex items-center gap-3 p-4">
            <MessageSquare className="h-5 w-5 text-muted-foreground" />
            <div>
              <p className="text-2xl font-bold">{msgs.length}</p>
              <p className="text-xs text-muted-foreground">Total messages</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center gap-3 p-4">
            <Calendar className="h-5 w-5 text-blue-500" />
            <div>
              <p className="text-2xl font-bold text-blue-600">{apptCount}</p>
              <p className="text-xs text-muted-foreground">Appointments found</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center gap-3 p-4">
            <CheckSquare className="h-5 w-5 text-emerald-500" />
            <div>
              <p className="text-2xl font-bold text-emerald-600">
                {msgs.reduce((acc: number, m: any) => acc + (m.tasks_created?.length ?? 0), 0)}
              </p>
              <p className="text-xs text-muted-foreground">Tasks created</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* setup guide */}
      <SetupGuide
        endpoint={getSmsShortcutEndpoint()}
        instructions={instructions}
      />

      {/* test panel */}
      <TestPanel onTested={() => qc.invalidateQueries({ queryKey: ["sms-messages"] })} />

      {/* filter tabs */}
      <div className="flex gap-2">
        {(["all", "appointments"] as const).map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
              filter === f ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-muted/80"
            }`}
          >
            {f === "all" ? "All Messages" : "Appointments Only"}
          </button>
        ))}
      </div>

      {/* error */}
      {error && (
        <Card className="border-destructive/30 bg-destructive/5">
          <CardContent className="flex items-center gap-2 py-3 text-sm text-destructive">
            <AlertCircle className="h-4 w-4" /> Could not load messages — check the backend connection.
          </CardContent>
        </Card>
      )}

      {/* list */}
      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-24 animate-pulse rounded-lg bg-muted" />
          ))}
        </div>
      ) : msgs.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
            <Clipboard className="h-10 w-10 text-muted-foreground/40" />
            <div>
              <p className="font-medium">No messages yet</p>
              <p className="text-sm text-muted-foreground">
                Use the test panel above to try it out, or set up the iPhone Shortcut and forward a real SMS.
              </p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {msgs.map((msg: any) => <MessageCard key={msg.id} msg={msg} />)}
        </div>
      )}
    </div>
  );
}
