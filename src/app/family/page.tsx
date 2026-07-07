"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { familyApi } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Plus, Trash2, User, Shield, Users, Pencil, Check, X } from "lucide-react";
import { formatDate, getInitials } from "@/lib/utils";

const ROLES = ["admin", "parent", "child", "member"];
const AVATAR_COLORS = ["from-blue-400 to-indigo-600", "from-pink-400 to-rose-600", "from-green-400 to-teal-600", "from-yellow-400 to-orange-600", "from-purple-400 to-violet-600"];

function parseJsonArray(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((item) => String(item));
  }

  if (typeof value === "string" && value.trim()) {
    try {
      const parsed = JSON.parse(value);
      if (Array.isArray(parsed)) {
        return parsed.map((item) => String(item));
      }
    } catch {
      return [value];
    }
  }

  return [];
}

function parseJsonObject(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }

  if (typeof value === "string" && value.trim()) {
    try {
      const parsed = JSON.parse(value);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        return parsed as Record<string, unknown>;
      }
    } catch {
      return {};
    }
  }

  return {};
}

function normalizeMember(member: any) {
  return {
    ...member,
    preferences: parseJsonObject(member?.preferences),
    dietary_restrictions: parseJsonArray(member?.dietary_restrictions),
  };
}

export default function FamilyPage() {
  const qc = useQueryClient();
  const [form, setForm] = useState({ name: "", email: "", role: "member", dietary_restrictions: "" });
  const [editingMemberId, setEditingMemberId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState({
    name: "",
    email: "",
    role: "member",
    dietary_restrictions: "",
    likes: "",
    dislikes: "",
  });
  const {
    data: members = [],
    isLoading,
    error,
  } = useQuery({
    queryKey: ["family-members"],
    queryFn: () => familyApi.list().then((r) => r.data),
  });

  const normalizedMembers = Array.isArray(members) ? members.map(normalizeMember) : [];

  const create = useMutation({
    mutationFn: (data: any) => familyApi.create(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["family-members"] });
      setForm({ name: "", email: "", role: "member", dietary_restrictions: "" });
    },
  });

  const update = useMutation({
    mutationFn: ({ id, data }: { id: string; data: any }) => familyApi.update(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["family-members"] });
      setEditingMemberId(null);
    },
  });

  const del = useMutation({
    mutationFn: (id: string) => familyApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["family-members"] }),
  });

  const startEdit = (member: any) => {
    setEditingMemberId(member.id);
    setEditForm({
      name: member.name || "",
      email: member.email || "",
      role: member.role || "member",
      dietary_restrictions: (member.dietary_restrictions ?? []).join(", "),
      likes: Array.isArray(member.preferences?.likes) ? member.preferences.likes.join(", ") : "",
      dislikes: Array.isArray(member.preferences?.dislikes) ? member.preferences.dislikes.join(", ") : "",
    });
  };

  const cancelEdit = () => {
    setEditingMemberId(null);
    setEditForm({
      name: "",
      email: "",
      role: "member",
      dietary_restrictions: "",
      likes: "",
      dislikes: "",
    });
  };

  const saveEdit = (memberId: string) => {
    update.mutate({
      id: memberId,
      data: {
        name: editForm.name.trim(),
        email: editForm.email.trim() || null,
        role: editForm.role,
        dietary_restrictions: editForm.dietary_restrictions
          ? editForm.dietary_restrictions.split(",").map((s) => s.trim()).filter(Boolean)
          : [],
        preferences: {
          likes: editForm.likes ? editForm.likes.split(",").map((s) => s.trim()).filter(Boolean) : [],
          dislikes: editForm.dislikes ? editForm.dislikes.split(",").map((s) => s.trim()).filter(Boolean) : [],
        },
      },
    });
  };

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
      ) : error ? (
        <Card>
          <CardContent className="py-12 text-center">
            <Users className="mx-auto mb-3 h-12 w-12 text-muted-foreground" />
            <p className="text-muted-foreground">Could not load family members.</p>
            <p className="mt-2 text-xs text-muted-foreground">Check the backend connection and API response.</p>
          </CardContent>
        </Card>
      ) : normalizedMembers.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <Users className="mx-auto mb-3 h-12 w-12 text-muted-foreground" />
            <p className="text-muted-foreground">No family members yet. Add your first member below!</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {normalizedMembers.map((m: any, i: number) => (
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
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 text-muted-foreground hover:text-primary"
                    onClick={() => editingMemberId === m.id ? cancelEdit() : startEdit(m)}
                  >
                    {editingMemberId === m.id ? <X className="h-4 w-4" /> : <Pencil className="h-4 w-4" />}
                  </Button>
                </div>
                {editingMemberId === m.id ? (
                  <div className="space-y-3">
                    <div className="grid gap-2 sm:grid-cols-2">
                      <Input
                        placeholder="Full name"
                        value={editForm.name}
                        onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                      />
                      <Input
                        placeholder="Email"
                        type="email"
                        value={editForm.email}
                        onChange={(e) => setEditForm({ ...editForm, email: e.target.value })}
                      />
                    </div>
                    <select
                      value={editForm.role}
                      onChange={(e) => setEditForm({ ...editForm, role: e.target.value })}
                      className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                    >
                      {ROLES.map((r) => <option key={r} value={r}>{r.charAt(0).toUpperCase() + r.slice(1)}</option>)}
                    </select>
                    <Input
                      placeholder="Dietary restrictions (comma-separated)"
                      value={editForm.dietary_restrictions}
                      onChange={(e) => setEditForm({ ...editForm, dietary_restrictions: e.target.value })}
                    />
                    <Input
                      placeholder="Likes (comma-separated, e.g. high protein, chicken, eggs)"
                      value={editForm.likes}
                      onChange={(e) => setEditForm({ ...editForm, likes: e.target.value })}
                    />
                    <Input
                      placeholder="Dislikes (comma-separated)"
                      value={editForm.dislikes}
                      onChange={(e) => setEditForm({ ...editForm, dislikes: e.target.value })}
                    />
                    <div className="flex gap-2">
                      <Button
                        onClick={() => saveEdit(m.id)}
                        disabled={update.isPending || !editForm.name.trim()}
                      >
                        <Check className="mr-2 h-4 w-4" />
                        Save Changes
                      </Button>
                      <Button variant="outline" onClick={cancelEdit}>
                        Cancel
                      </Button>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="flex flex-wrap gap-2">
                      <Badge variant={m.role === "admin" || m.role === "parent" ? "default" : "secondary"} className="gap-1">
                        {(m.role === "admin" || m.role === "parent") && <Shield className="h-3 w-3" />}
                        {m.role}
                      </Badge>
                      {(m.dietary_restrictions ?? []).map((d: string) => (
                        <Badge key={d} variant="outline" className="text-xs">{d}</Badge>
                      ))}
                      {Array.isArray(m.preferences?.likes) && m.preferences.likes.map((like: string) => (
                        <Badge key={like} variant="secondary" className="text-xs">{like}</Badge>
                      ))}
                    </div>
                    <p className="mt-3 text-xs text-muted-foreground">
                      {m.created_at ? `Added ${formatDate(m.created_at)}` : "Recently added"}
                    </p>
                  </>
                )}
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
