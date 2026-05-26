"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { groceryApi } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Plus, Trash2, CheckSquare, Square, Sparkles, ShoppingCart, ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

export default function GroceryPage() {
  const qc = useQueryClient();
  const [newListName, setNewListName] = useState("");
  const [activeList, setActiveList] = useState<string | null>(null);
  const [newItemName, setNewItemName] = useState("");
  const [expandedLists, setExpandedLists] = useState<Set<string>>(new Set());

  const { data: lists = [], isLoading } = useQuery({
    queryKey: ["grocery-lists"],
    queryFn: () => groceryApi.listLists().then((r) => r.data),
  });

  const createList = useMutation({
    mutationFn: (name: string) => groceryApi.createList({ name }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["grocery-lists"] }); setNewListName(""); },
  });

  const addItem = useMutation({
    mutationFn: ({ listId, name }: { listId: string; name: string }) => groceryApi.addItem(listId, { name }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["grocery-lists"] }); setNewItemName(""); },
  });

  const toggleItem = useMutation({
    mutationFn: ({ itemId, checked }: { itemId: string; checked: boolean }) =>
      groceryApi.updateItem(itemId, { checked }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["grocery-lists"] }),
  });

  const deleteItem = useMutation({
    mutationFn: (itemId: string) => groceryApi.deleteItem(itemId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["grocery-lists"] }),
  });

  const generateAI = useMutation({
    mutationFn: (listId: string) => groceryApi.generateAI(listId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["grocery-lists"] }),
  });

  const toggleExpand = (listId: string) => {
    setExpandedLists((prev) => {
      const next = new Set(prev);
      if (next.has(listId)) next.delete(listId);
      else next.add(listId);
      return next;
    });
  };

  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Grocery</h1>
        <p className="text-sm text-muted-foreground">Smart shopping lists with AI suggestions</p>
      </div>

      {/* Create list */}
      <Card>
        <CardContent className="pt-4">
          <form onSubmit={(e) => { e.preventDefault(); createList.mutate(newListName); }} className="flex gap-2">
            <Input
              placeholder="New grocery list name..."
              value={newListName}
              onChange={(e) => setNewListName(e.target.value)}
            />
            <Button type="submit" disabled={!newListName.trim() || createList.isPending}>
              <Plus className="mr-1 h-4 w-4" /> Create List
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Lists */}
      {isLoading ? (
        <p className="text-center text-muted-foreground">Loading...</p>
      ) : lists.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <ShoppingCart className="mx-auto mb-3 h-10 w-10 text-muted-foreground" />
            <p className="text-muted-foreground">No grocery lists yet. Create one above!</p>
          </CardContent>
        </Card>
      ) : (
        lists.map((list: any) => {
          const expanded = expandedLists.has(list.id);
          const checkedCount = (list.items ?? []).filter((i: any) => i.checked).length;
          return (
            <Card key={list.id}>
              <CardHeader className="pb-0">
                <div className="flex items-center justify-between">
                  <button
                    onClick={() => toggleExpand(list.id)}
                    className="flex items-center gap-2 text-left"
                  >
                    {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                    <CardTitle className="text-base">{list.name}</CardTitle>
                  </button>
                  <div className="flex items-center gap-2">
                    {list.store && <Badge variant="outline">{list.store}</Badge>}
                    <Badge variant="secondary">
                      {checkedCount}/{(list.items ?? []).length} done
                    </Badge>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => generateAI.mutate(list.id)}
                      disabled={generateAI.isPending}
                    >
                      <Sparkles className="mr-1 h-3 w-3" /> AI Fill
                    </Button>
                  </div>
                </div>
              </CardHeader>
              {expanded && (
                <CardContent className="pt-3">
                  {/* Add item */}
                  <form
                    onSubmit={(e) => { e.preventDefault(); if (newItemName.trim()) addItem.mutate({ listId: list.id, name: newItemName }); }}
                    className="mb-3 flex gap-2"
                  >
                    <Input
                      placeholder="Add item..."
                      value={activeList === list.id ? newItemName : ""}
                      onChange={(e) => { setActiveList(list.id); setNewItemName(e.target.value); }}
                      onFocus={() => setActiveList(list.id)}
                      className="flex-1"
                    />
                    <Button type="submit" size="sm" variant="outline" disabled={addItem.isPending}>
                      <Plus className="h-4 w-4" />
                    </Button>
                  </form>
                  <div className="space-y-1">
                    {(list.items ?? []).length === 0 ? (
                      <p className="text-center text-sm text-muted-foreground py-4">No items — add some or use AI Fill</p>
                    ) : (
                      (list.items ?? []).map((item: any) => (
                        <div key={item.id} className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-muted/50">
                          <button onClick={() => toggleItem.mutate({ itemId: item.id, checked: !item.checked })}>
                            {item.checked ? <CheckSquare className="h-4 w-4 text-green-500" /> : <Square className="h-4 w-4 text-muted-foreground" />}
                          </button>
                          <span className={cn("flex-1 text-sm", item.checked && "line-through text-muted-foreground")}>
                            {item.name}
                          </span>
                          {item.quantity > 1 && <span className="text-xs text-muted-foreground">×{item.quantity}</span>}
                          {item.category && <Badge variant="outline" className="text-xs">{item.category}</Badge>}
                          <button onClick={() => deleteItem.mutate(item.id)} className="text-muted-foreground hover:text-destructive">
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      ))
                    )}
                  </div>
                </CardContent>
              )}
            </Card>
          );
        })
      )}
    </div>
  );
}
