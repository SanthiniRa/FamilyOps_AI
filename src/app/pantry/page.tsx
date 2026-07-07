"use client";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { pantryApi } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Package, Plus, Trash2, RotateCcw, AlertTriangle } from "lucide-react";

const CATEGORY_OPTIONS = [
  "misc",
  "fruit",
  "vegetables",
  "dairy",
  "meat",
  "bakery",
  "frozen",
  "snacks",
  "drinks",
  "tins",
  "grains",
  "condiments",
  "other",
];

export default function PantryPage() {
  const qc = useQueryClient();
  const [categoryFilter, setCategoryFilter] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);
  const [form, setForm] = useState({
    name: "",
    quantity: "1",
    unit: "unit",
    category: "misc",
    location: "",
    min_quantity: "0",
    price_per_unit: "",
    notes: "",
  });

  const { data: items = [], isLoading } = useQuery({
    queryKey: ["pantry-items", categoryFilter],
    queryFn: () => pantryApi.listItems(categoryFilter ? { category: categoryFilter } : undefined).then((r) => r.data),
  });

  const { data: summary } = useQuery({
    queryKey: ["pantry-summary"],
    queryFn: () => pantryApi.summary().then((r) => r.data),
  });

  const { data: lowStock = [] } = useQuery({
    queryKey: ["pantry-low-stock"],
    queryFn: () => pantryApi.lowStock().then((r) => r.data),
  });

  const createItem = useMutation({
    mutationFn: () =>
      pantryApi.createItem({
        name: form.name.trim(),
        quantity: Number(form.quantity),
        unit: form.unit.trim() || "unit",
        category: form.category || null,
        location: form.location.trim() || null,
        min_quantity: Number(form.min_quantity || 0),
        price_per_unit: form.price_per_unit ? Number(form.price_per_unit) : null,
        notes: form.notes.trim() || null,
      }),
    onSuccess: () => {
      setCreateError(null);
      qc.invalidateQueries({ queryKey: ["pantry-items"] });
      qc.invalidateQueries({ queryKey: ["pantry-summary"] });
      qc.invalidateQueries({ queryKey: ["pantry-low-stock"] });
      setForm({
        name: "",
        quantity: "1",
        unit: "unit",
        category: "misc",
        location: "",
        min_quantity: "0",
        price_per_unit: "",
        notes: "",
      });
    },
    onError: (error: any) => {
      const detail =
        error?.response?.data?.detail ||
        error?.response?.data?.message ||
        error?.message ||
        "Unable to add pantry item.";
      setCreateError(typeof detail === "string" ? detail : "Unable to add pantry item.");
    },
  });

  const deleteItem = useMutation({
    mutationFn: (id: string) => pantryApi.deleteItem(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pantry-items"] });
      qc.invalidateQueries({ queryKey: ["pantry-summary"] });
      qc.invalidateQueries({ queryKey: ["pantry-low-stock"] });
    },
  });

  const useItem = useMutation({
    mutationFn: (id: string) => pantryApi.useItem(id, { quantity: 1 }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pantry-items"] });
      qc.invalidateQueries({ queryKey: ["pantry-summary"] });
      qc.invalidateQueries({ queryKey: ["pantry-low-stock"] });
    },
  });

  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Pantry</h1>
        <p className="text-sm text-muted-foreground">Track household stock and keep meal planning grounded in what is actually available.</p>
      </div>

      {summary && (
        <div className="grid gap-4 md:grid-cols-4">
          {[
            { label: "Items", value: summary.total_items ?? 0 },
            { label: "Value", value: `GBP ${Number(summary.total_value ?? 0).toFixed(2)}` },
            { label: "Low stock", value: summary.low_stock_count ?? 0 },
            { label: "Expiring", value: summary.expired_soon_count ?? 0 },
          ].map((stat) => (
            <Card key={stat.label}>
              <CardContent className="pt-4">
                <p className="text-xs uppercase tracking-wide text-muted-foreground">{stat.label}</p>
                <p className="mt-1 text-2xl font-bold">{stat.value}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {lowStock.length > 0 && (
        <Card className="border-amber-200 bg-amber-50/50">
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-amber-600" />
              Low stock items
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {lowStock.map((item: any) => (
              <Badge key={item.id} variant="outline" className="border-amber-300 text-amber-800">
                {item.name} ({item.quantity} {item.unit})
              </Badge>
            ))}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Add Pantry Item</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            className="grid gap-3 md:grid-cols-2"
            onSubmit={(e) => {
              e.preventDefault();
              createItem.mutate();
            }}
          >
            {createError && (
              <div className="md:col-span-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                {createError}
              </div>
            )}
            <Input
              placeholder="Item name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              required
            />
            <Input
              placeholder="Quantity"
              type="number"
              min="0"
              step="0.1"
              value={form.quantity}
              onChange={(e) => setForm({ ...form, quantity: e.target.value })}
              required
            />
            <Input
              placeholder="Unit"
              value={form.unit}
              onChange={(e) => setForm({ ...form, unit: e.target.value })}
            />
            <Select value={form.category} onValueChange={(value) => setForm({ ...form, category: value })}>
              <SelectTrigger>
                <SelectValue placeholder="Category" />
              </SelectTrigger>
              <SelectContent>
                {CATEGORY_OPTIONS.map((option) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Input
              placeholder="Storage location"
              value={form.location}
              onChange={(e) => setForm({ ...form, location: e.target.value })}
            />
            <Input
              placeholder="Minimum quantity"
              type="number"
              min="0"
              step="0.1"
              value={form.min_quantity}
              onChange={(e) => setForm({ ...form, min_quantity: e.target.value })}
            />
            <Input
              placeholder="Price per unit"
              type="number"
              min="0"
              step="0.01"
              value={form.price_per_unit}
              onChange={(e) => setForm({ ...form, price_per_unit: e.target.value })}
            />
            <Input
              placeholder="Notes"
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
            />
            <div className="md:col-span-2">
              <Button type="submit" disabled={createItem.isPending || !form.name.trim()}>
                <Plus className="mr-2 h-4 w-4" />
                {createItem.isPending ? "Saving..." : "Add Item"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <CardTitle className="text-base">Pantry Items</CardTitle>
          <div className="w-44">
            <Select value={categoryFilter || "all"} onValueChange={(value) => setCategoryFilter(value === "all" ? "" : value)}>
              <SelectTrigger>
                <SelectValue placeholder="All categories" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All categories</SelectItem>
                {CATEGORY_OPTIONS.map((option) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="text-sm text-muted-foreground">Loading...</p>
          ) : items.length === 0 ? (
            <div className="py-10 text-center">
              <Package className="mx-auto mb-3 h-10 w-10 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">No pantry items yet.</p>
            </div>
          ) : (
            <div className="grid gap-3">
              {items.map((item: any) => {
                const lowStock = item.min_quantity != null && item.quantity < item.min_quantity;
                return (
                  <div key={item.id} className="flex items-center gap-3 rounded-md border px-3 py-2">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <p className="font-medium">{item.name}</p>
                        {item.category && <Badge variant="outline">{item.category}</Badge>}
                        {lowStock && <Badge variant="secondary">Low stock</Badge>}
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {item.quantity} {item.unit}
                        {item.location ? ` • ${item.location}` : ""}
                        {item.notes ? ` • ${item.notes}` : ""}
                      </p>
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => useItem.mutate(item.id)}
                      disabled={useItem.isPending}
                    >
                      <RotateCcw className="mr-1 h-3.5 w-3.5" />
                      Use 1
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => deleteItem.mutate(item.id)}
                      disabled={deleteItem.isPending}
                    >
                      <Trash2 className="h-4 w-4 text-muted-foreground" />
                    </Button>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
