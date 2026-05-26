"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { memoryApi } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Plus, Search, Trash2, Brain, Tag } from "lucide-react";
import { formatTimeAgo, cn } from "@/lib/utils";

const CATEGORIES = ["preference", "routine", "medical", "emergency", "password-hint", "contact", "note"];
const CATEGORY_COLORS: Record<string, string> = {
  preference: "bg-blue-100 text-blue-700",
  routine: "bg-green-100 text-green-700",
  medical: "bg-red-100 text-red-700",
  emergency: "bg-orange-100 text-orange-700",
  "password-hint": "bg-purple-100 text-purple-700",
  contact: "bg-teal-100 text-teal-700",
  note: "bg-gray-100 text-gray-700",
};

export default function MemoryPage() {
  const qc = useQueryClient();
  const [filterCategory, setFilterCategory] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [form, setForm] = useState({ content: "", category: "note", tags: "", importance: "0.5" });

  const { data: memories = [], isLoading } = useQuery({
    queryKey: ["memories", filterCategory],
    queryFn: () => memoryApi.list(filterCategory ? { category: filterCategory } : undefined).then((r) => r.data),
  });

  const { data: categories } = useQuery({
    queryKey: ["memory-categories"],
    queryFn: () => memoryApi.categories().then((r) => r.data),
  });

  const store = useMutation({
    mutationFn: (data: any) => memoryApi.store(data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["memories"] }); qc.invalidateQueries({ queryKey: ["memory-categories"] }); setForm({ content: "", category: "note", tags: "", importance: "0.5" }); },
  });

  const del = useMutation({
    mutationFn: (id: string) => memoryApi.delete(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["memories"] }); qc.invalidateQueries({ queryKey: ["memory-categories"] }); },
  });

  const [searchResults, setSearchResults] = useState<any[] | null>(null);
  const search = useMutation({
    mutationFn: (query: string) => memoryApi.search({ query, k: 5 }),
    onSuccess: (r) => setSearchResults(r.data.results),
  });

  const displayed = searchResults !== null ? searchResults : memories;

  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Household Memory</h1>
        <p className="text-sm text-muted-foreground">AI-powered household knowledge base with semantic search</p>
      </div>

      {/* Stats */}
      {categories && (
        <div className="flex flex-wrap gap-2">
          <button onClick={() => { setFilterCategory(""); setSearchResults(null); }} className={cn("rounded-full border px-3 py-1 text-xs font-medium transition-colors", filterCategory === "" ? "bg-primary text-primary-foreground" : "hover:bg-muted")}>
            All ({categories.total})
          </button>
          {Object.entries(categories.categories || {}).map(([cat, count]: any) => (
            <button
              key={cat}
              onClick={() => { setFilterCategory(cat); setSearchResults(null); }}
              className={cn("rounded-full border px-3 py-1 text-xs font-medium transition-colors", filterCategory === cat ? "bg-primary text-primary-foreground" : "hover:bg-muted")}
            >
              {cat} ({count})
            </button>
          ))}
        </div>
      )}

      {/* Search */}
      <div className="flex gap-2">
        <Input
          placeholder="Semantic search memories..."
          value={searchQuery}
          onChange={(e) => { setSearchQuery(e.target.value); if (!e.target.value) setSearchResults(null); }}
          className="flex-1"
        />
        <Button onClick={() => searchQuery && search.mutate(searchQuery)} disabled={search.isPending || !searchQuery}>
          <Search className="mr-1 h-4 w-4" /> Search
        </Button>
        {searchResults && (
          <Button variant="outline" onClick={() => { setSearchResults(null); setSearchQuery(""); }}>Clear</Button>
        )}
      </div>

      {/* Add memory */}
      <Card>
        <CardHeader><CardTitle className="text-base">Store New Memory</CardTitle></CardHeader>
        <CardContent>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              store.mutate({
                content: form.content,
                category: form.category,
                tags: form.tags ? form.tags.split(",").map((t) => t.trim()) : [],
                importance: parseFloat(form.importance),
              });
            }}
            className="grid gap-3 sm:grid-cols-2"
          >
            <textarea
              placeholder="What should I remember? (e.g. Alice is allergic to peanuts)"
              value={form.content}
              onChange={(e) => setForm({ ...form, content: e.target.value })}
              required
              className="sm:col-span-2 h-20 resize-none rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
            <select
              value={form.category}
              onChange={(e) => setForm({ ...form, category: e.target.value })}
              className="h-10 rounded-md border border-input bg-background px-3 text-sm"
            >
              {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
            <Input placeholder="Tags (comma-separated)" value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} />
            <div className="sm:col-span-2 flex items-center gap-3">
              <label className="text-sm text-muted-foreground shrink-0">Importance:</label>
              <input
                type="range" min="0" max="1" step="0.1"
                value={form.importance}
                onChange={(e) => setForm({ ...form, importance: e.target.value })}
                className="flex-1"
              />
              <span className="text-sm w-8 text-right">{form.importance}</span>
            </div>
            <Button type="submit" className="sm:col-span-2" disabled={store.isPending}>
              <Brain className="mr-2 h-4 w-4" /> Store Memory
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Memory list */}
      <div className="space-y-3">
        {searchResults !== null && (
          <p className="text-sm text-muted-foreground">Showing {searchResults.length} semantic search results</p>
        )}
        {displayed.length === 0 ? (
          <Card><CardContent className="py-12 text-center"><Brain className="mx-auto mb-2 h-10 w-10 text-muted-foreground" /><p className="text-muted-foreground">No memories found</p></CardContent></Card>
        ) : (
          displayed.map((m: any) => (
            <Card key={m.id}>
              <CardContent className="flex gap-3 pt-4">
                <div className="flex-1 min-w-0">
                  <p className="text-sm leading-relaxed">{m.content}</p>
                  <div className="flex flex-wrap items-center gap-2 mt-2">
                    {m.category && (
                      <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", CATEGORY_COLORS[m.category] || "bg-gray-100 text-gray-700")}>
                        {m.category}
                      </span>
                    )}
                    {(m.tags ?? []).map((tag: string) => (
                      <span key={tag} className="text-xs text-muted-foreground flex items-center gap-0.5">
                        <Tag className="h-3 w-3" />{tag}
                      </span>
                    ))}
                    <span className="text-xs text-muted-foreground ml-auto">{formatTimeAgo(m.created_at)}</span>
                    {m.score !== undefined && (
                      <Badge variant="info" className="text-xs">Score: {m.score?.toFixed(2)}</Badge>
                    )}
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 shrink-0 text-muted-foreground hover:text-destructive"
                  onClick={() => del.mutate(m.id)}
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
