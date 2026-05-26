"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { mealsApi } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sparkles, UtensilsCrossed, ChevronLeft, ChevronRight, Salad } from "lucide-react";
import { formatDate, cn } from "@/lib/utils";
import { startOfWeek, addWeeks, subWeeks, addDays } from "date-fns";

const DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];
const MEALS = ["breakfast", "lunch", "dinner"];
const DAY_LABELS: Record<string, string> = {
  monday: "Mon", tuesday: "Tue", wednesday: "Wed",
  thursday: "Thu", friday: "Fri", saturday: "Sat", sunday: "Sun",
};
const MEAL_COLORS: Record<string, string> = {
  breakfast: "bg-amber-50 border-amber-200",
  lunch: "bg-sky-50 border-sky-200",
  dinner: "bg-indigo-50 border-indigo-200",
};

export default function MealsPage() {
  const qc = useQueryClient();
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date(), { weekStartsOn: 1 }));

  const { data: plans = [] } = useQuery({
    queryKey: ["meal-plans"],
    queryFn: () => mealsApi.listPlans().then((r) => r.data),
  });

  const { data: recipes = [] } = useQuery({
    queryKey: ["recipes"],
    queryFn: () => mealsApi.listRecipes().then((r) => r.data),
  });

  const generatePlan = useMutation({
    mutationFn: () => mealsApi.generatePlan({ week_start: weekStart.toISOString(), preferences: {} }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["meal-plans"] }),
  });

  const currentPlan = plans.find((p: any) => {
    const pStart = new Date(p.week_start);
    return pStart.toDateString() === weekStart.toDateString();
  });

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Meal Plans</h1>
          <p className="text-sm text-muted-foreground">AI-generated weekly meal planning</p>
        </div>
        <Button onClick={() => generatePlan.mutate()} disabled={generatePlan.isPending}>
          <Sparkles className="mr-2 h-4 w-4" />
          {generatePlan.isPending ? "Generating..." : "Generate AI Plan"}
        </Button>
      </div>

      {/* Week Navigator */}
      <Card>
        <CardContent className="flex items-center justify-between py-3">
          <Button variant="ghost" size="icon" onClick={() => setWeekStart(subWeeks(weekStart, 1))}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <div className="text-center">
            <p className="font-semibold">
              {formatDate(weekStart)} — {formatDate(addDays(weekStart, 6))}
            </p>
            {currentPlan?.generated_by_ai && (
              <Badge variant="info" className="text-xs mt-1"><Sparkles className="h-3 w-3 mr-1 inline" />AI Generated</Badge>
            )}
          </div>
          <Button variant="ghost" size="icon" onClick={() => setWeekStart(addWeeks(weekStart, 1))}>
            <ChevronRight className="h-4 w-4" />
          </Button>
        </CardContent>
      </Card>

      {/* Meal Grid */}
      {currentPlan ? (
        <div className="grid grid-cols-7 gap-2">
          {DAYS.map((day) => (
            <div key={day} className="space-y-2">
              <div className="rounded-md bg-muted px-2 py-1 text-center">
                <p className="text-xs font-semibold text-muted-foreground">{DAY_LABELS[day]}</p>
              </div>
              {MEALS.map((meal) => (
                <div key={meal} className={cn("rounded-md border p-2 text-xs", MEAL_COLORS[meal])}>
                  <p className="font-medium capitalize text-muted-foreground mb-1">{meal}</p>
                  <p className="font-medium leading-tight">{currentPlan.meals?.[day]?.[meal] ?? "—"}</p>
                </div>
              ))}
            </div>
          ))}
        </div>
      ) : (
        <Card>
          <CardContent className="py-16 text-center">
            <UtensilsCrossed className="mx-auto mb-3 h-12 w-12 text-muted-foreground" />
            <p className="text-muted-foreground mb-4">No meal plan for this week yet.</p>
            <Button onClick={() => generatePlan.mutate()} disabled={generatePlan.isPending}>
              <Sparkles className="mr-2 h-4 w-4" /> Generate Plan with AI
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Nutritional Summary */}
      {currentPlan?.nutritional_summary && (
        <Card>
          <CardHeader><CardTitle className="text-base">Nutritional Summary (avg/day)</CardTitle></CardHeader>
          <CardContent>
            <div className="grid grid-cols-4 gap-4">
              {[
                { label: "Calories", value: currentPlan.nutritional_summary.avg_calories, unit: "kcal", color: "text-orange-600" },
                { label: "Protein", value: currentPlan.nutritional_summary.avg_protein_g, unit: "g", color: "text-blue-600" },
                { label: "Carbs", value: currentPlan.nutritional_summary.avg_carbs_g, unit: "g", color: "text-yellow-600" },
                { label: "Fat", value: currentPlan.nutritional_summary.avg_fat_g, unit: "g", color: "text-red-600" },
              ].map((n) => (
                <div key={n.label} className="text-center">
                  <p className={cn("text-2xl font-bold", n.color)}>{n.value}</p>
                  <p className="text-xs text-muted-foreground">{n.label} ({n.unit})</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Recipes */}
      {recipes.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold mb-3">Recipe Library</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {recipes.map((r: any) => (
              <Card key={r.id}>
                <CardContent className="pt-4">
                  <div className="flex items-start justify-between mb-2">
                    <p className="font-medium">{r.name}</p>
                    <Salad className="h-4 w-4 text-green-500 shrink-0" />
                  </div>
                  {r.description && <p className="text-xs text-muted-foreground mb-2">{r.description}</p>}
                  <div className="flex gap-2 flex-wrap">
                    {r.cuisine && <Badge variant="outline" className="text-xs">{r.cuisine}</Badge>}
                    {r.prep_time && <Badge variant="secondary" className="text-xs">Prep: {r.prep_time}m</Badge>}
                    {r.cook_time && <Badge variant="secondary" className="text-xs">Cook: {r.cook_time}m</Badge>}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
