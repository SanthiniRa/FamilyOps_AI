"use client";
import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { mealsApi } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sparkles, UtensilsCrossed, ChevronLeft, ChevronRight, Salad } from "lucide-react";
import { formatDate, cn } from "@/lib/utils";
import { startOfWeek, addWeeks, subWeeks, addDays, format } from "date-fns";

const DAYS = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"];
const MEALS = ["breakfast","lunch","dinner"];

const DAY_LABELS: Record<string, string> = {
  monday: "Mon", tuesday: "Tue", wednesday: "Wed",
  thursday: "Thu", friday: "Fri", saturday: "Sat", sunday: "Sun",
};

const MEAL_COLORS: Record<string, string> = {
  breakfast: "bg-amber-50 border-amber-200",
  lunch: "bg-sky-50 border-sky-200",
  dinner: "bg-indigo-50 border-indigo-200",
};

// normalize week to avoid timezone mismatch
function normalizeWeek(date: Date) {
  return startOfWeek(date, { weekStartsOn: 1 });
}

function getWeekKey(date: Date) {
  return format(normalizeWeek(date), "yyyy-MM-dd");
}

export default function MealsPage() {
  const qc = useQueryClient();

  const [weekStart, setWeekStart] = useState(() =>
    normalizeWeek(new Date())
  );
  const weekKey = useMemo(() => getWeekKey(weekStart), [weekStart]);

  const { data: plans = [] } = useQuery({
    queryKey: ["meal-plans", weekKey],
    queryFn: () => mealsApi.listPlans({ week_start: weekKey }).then((r) => r.data),
  });

  const generatePlan = useMutation({
    mutationFn: () =>
      mealsApi.generatePlan({
        week_start: weekKey,
        preferences: {},
      }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["meal-plans"] });
      await qc.refetchQueries({ queryKey: ["meal-plans"] });
    }
  });

  const currentPlan = useMemo(() => {
    return plans.find((plan) => plan.week_start?.slice(0, 10) === weekKey);
  }, [plans, weekKey]);

  const weekStatus = currentPlan
    ? { label: "Plan saved for this week", variant: "success" as const }
    : { label: "No plan saved yet", variant: "warning" as const };

  return (
    <div className="flex flex-col gap-6 p-6">

      {/* HEADER */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Meal Plans</h1>
          <p className="text-sm text-muted-foreground">
            AI-generated weekly meal planning
          </p>
        </div>

        <Button onClick={() => generatePlan.mutate()} disabled={generatePlan.isPending}>
          <Sparkles className="mr-2 h-4 w-4" />
          {generatePlan.isPending ? "Generating..." : "Generate AI Plan"}
        </Button>
      </div>

      {/* WEEK NAV */}
      <Card>
        <CardContent className="flex items-center justify-between py-3">
          <Button variant="ghost" size="icon" onClick={() => setWeekStart(subWeeks(weekStart, 1))}>
            <ChevronLeft className="h-4 w-4" />
          </Button>

          <div className="text-center">
            <p className="font-semibold">
              {formatDate(weekStart)} — {formatDate(addDays(weekStart, 6))}
            </p>

            <Badge variant={weekStatus.variant} className="mt-1 gap-1">
              <Salad className="h-3 w-3" />
              {weekStatus.label}
            </Badge>

            {currentPlan?.generated_by_ai && (
              <Badge variant="secondary" className="mt-1">
                <Sparkles className="h-3 w-3 mr-1" />
                AI Generated
              </Badge>
            )}
          </div>

          <Button variant="ghost" size="icon" onClick={() => setWeekStart(addWeeks(weekStart, 1))}>
            <ChevronRight className="h-4 w-4" />
          </Button>
        </CardContent>
      </Card>

      {/* MAIN GRID */}
      {currentPlan ? (
        <div className="grid grid-cols-7 gap-2">
          {DAYS.map((day) => (
            <div key={day} className="space-y-2">
              <div className="rounded-md bg-muted px-2 py-1 text-center">
                <p className="text-xs font-semibold text-muted-foreground">
                  {DAY_LABELS[day]}
                </p>
              </div>

              {MEALS.map((meal) => (
                <div
                  key={meal}
                  className={cn("rounded-md border p-2 text-xs", MEAL_COLORS[meal])}
                >
                  <p className="font-medium capitalize mb-1">{meal}</p>
                  <p className="font-medium leading-tight">
                    {currentPlan.meals?.[day]?.[meal] ?? "—"}
                  </p>
                </div>
              ))}
            </div>
          ))}
        </div>
      ) : (
        <Card className="border-dashed bg-gradient-to-br from-muted/60 via-background to-amber-50/50">
          <CardContent className="py-16 text-center">
            <div className="mx-auto flex max-w-sm flex-col items-center">
              <div className="mb-4 rounded-full border border-amber-200 bg-white/80 p-4 shadow-sm">
                <UtensilsCrossed className="h-10 w-10 text-amber-600" />
              </div>

              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-amber-700">
                Week not planned
              </p>
              <p className="mt-2 text-lg font-semibold">
                No meal plan for this week yet.
              </p>
              <p className="mt-2 text-sm text-muted-foreground">
                Generate a plan for this week to fill in breakfast, lunch, and dinner for every day.
              </p>

              <Button onClick={() => generatePlan.mutate()} disabled={generatePlan.isPending} className="mt-6">
                <Sparkles className="mr-2 h-4 w-4" />
                Generate Plan
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* SUMMARY */}
      {currentPlan?.nutritional_summary && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Nutritional Summary (avg/day)
            </CardTitle>
          </CardHeader>

          <CardContent className="grid grid-cols-4 gap-4">
            {[
              { label: "Calories", value: currentPlan.nutritional_summary.avg_calories },
              { label: "Protein", value: currentPlan.nutritional_summary.avg_protein_g },
              { label: "Carbs", value: currentPlan.nutritional_summary.avg_carbs_g },
              { label: "Fat", value: currentPlan.nutritional_summary.avg_fat_g },
            ].map((n) => (
              <div key={n.label} className="text-center">
                <p className="text-2xl font-bold">{n.value}</p>
                <p className="text-xs text-muted-foreground">{n.label}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
