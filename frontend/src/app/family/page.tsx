"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { familyApi } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Plus, Trash2, User, Shield, Users } from "lucide-react";
import { formatDate, getInitials } from "@/lib/utils";

const ROLES = ["admin", "parent", "child", "member"];
const AVATAR_COLORS = ["from-blue-400 to-indigo-600", "from-pink-400 to-rose-600", "from-green-400 to-teal-600", "from-yellow-400 to-orange-600", "from-purple-400 to-violet-600"];

export default function FamilyPage() {
  const qc = useQueryClient();
  const [form, setForm] = useState({ name: "", email: "", role: "member", dietary_restrictions: "" });

  const { data: members = [], isLoading } = useQuery({
    queryKey: ["family-members"],
    queryFn: () => familyApi.list().then((r) => r.data),
  });

  const create = useMutation({
    mutationFn: (data: any) => familyApi.create(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["family-members"] });
      setForm({ name: "", email: "", role: "member", dietary_restrictions: "" });
    },
  });

  const del = useMutation({
    mutationFn: (id: string) => familyApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["family-members"] }),
  });

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    create.mutate({
      name: form.name,
      email: form.email || undefined,
      role: form.role,
      dietary_restrictions: form.dietary_restrictions
        ? form.dietary_restrictions.split(",").map((s) => s.trim())
        : [],
    });
  };

  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Family Members</h1>
        <p className="text-sm text-muted-foreground">Manage your household members and their preferences</p>
      </div>

      {/* Member Grid */}
      {isLoading ? (
        <p className="text-center text-muted-foreground">Loading...</p>
      ) : members.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <Users className="mx-auto mb-3 h-12 w-12 text-muted-foreground" />
            <p className="text-muted-foreground">No family members yet. Add your first member below!</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {members.map((m: any, i: number) => (
            <Card key={m.id}>
              <CardContent className="pt-6">
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className={`flex h-12 w-12 items-center justify-center rounded-full bg-gradient-to-br ${AVATAR_COLORS[i % AVATAR_COLORS.length]} text-lg font-bold text-white`}>
                      {getInitials(m.name)}
                    </div>
                    <div>
                      <p className="font-semibold">{m.name}</p>
                      {m.email && <p className="text-xs text-muted-foreground">{m.email}</p>}
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 text-muted-foreground hover:text-destructive"
                    onClick={() => del.mutate(m.id)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Badge variant={m.role === "admin" || m.role === "parent" ? "default" : "secondary"} className="gap-1">
                    {(m.role === "admin" || m.role === "parent") && <Shield className="h-3 w-3" />}
                    {m.role}
                  </Badge>
                  {(m.dietary_restrictions ?? []).map((d: string) => (
                    <Badge key={d} variant="outline" className="text-xs">{d}</Badge>
                  ))}
                </div>
                <p className="mt-3 text-xs text-muted-foreground">Added {formatDate(m.created_at)}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Add Member */}
      <Card>
        <CardHeader><CardTitle className="text-base">Add Family Member</CardTitle></CardHeader>
        <CardContent>
          <form onSubmit={handleCreate} className="grid gap-3 sm:grid-cols-2">
            <Input placeholder="Full name *" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
            <Input placeholder="Email (optional)" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
            <select
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value })}
              className="h-10 rounded-md border border-input bg-background px-3 text-sm"
            >
              {ROLES.map((r) => <option key={r} value={r}>{r.charAt(0).toUpperCase() + r.slice(1)}</option>)}
            </select>
            <Input
              placeholder="Dietary restrictions (comma-separated)"
              value={form.dietary_restrictions}
              onChange={(e) => setForm({ ...form, dietary_restrictions: e.target.value })}
            />
            <Button type="submit" className="sm:col-span-2" disabled={create.isPending}>
              <Plus className="mr-2 h-4 w-4" /> Add Member
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
