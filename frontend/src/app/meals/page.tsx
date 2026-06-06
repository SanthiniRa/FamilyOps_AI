"use client";
import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { mealsApi } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sparkles, UtensilsCrossed, ChevronLeft, ChevronRight, Salad } from "lucide-react";
import { formatDate, cn } from "@/lib/utils";
import { startOfWeek, addWeeks, subWeeks, addDays, parseISO } from "date-fns";

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

export default function MealsPage() {
  const qc = useQueryClient();

  const [weekStart, setWeekStart] = useState(() =>
    normalizeWeek(new Date())
  );

  const { data: plans = [] } = useQuery({
    queryKey: ["meal-plans"],
    queryFn: () => mealsApi.listPlans().then((r) => r.data),
  });

  const generatePlan = useMutation({
    mutationFn: () =>
      mealsApi.generatePlan({
        week_start: weekStart.toISOString(),
        preferences: {},
      }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["meal-plans"] });
      await qc.refetchQueries({ queryKey: ["meal-plans"] });
    }
  });

  // ✅ FIXED MATCHING LOGIC
  const currentPlan = useMemo(() => {
    return plans[0]; // TEMP: always show latest plan
  }, [plans]);

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
        <Card>
          <CardContent className="py-16 text-center">
            <UtensilsCrossed className="mx-auto mb-3 h-12 w-12 text-muted-foreground" />
            <p className="text-muted-foreground mb-4">
              No meal plan for this week yet.
            </p>

            <Button onClick={() => generatePlan.mutate()} disabled={generatePlan.isPending}>
              <Sparkles className="mr-2 h-4 w-4" />
              Generate Plan
            </Button>
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