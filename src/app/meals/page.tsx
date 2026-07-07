"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { mealsApi } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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

const NUTRITION_FIELDS = ["calories", "protein", "carbs", "fat", "fiber"] as const;

const DEFAULT_NUTRITION_BLOCK = {
  calories: 0,
  protein: 0,
  carbs: 0,
  fat: 0,
  fiber: 0,
};

function emptyNutritionBlock() {
  return { ...DEFAULT_NUTRITION_BLOCK };
}

function normalizeNutritionBlock(value: any) {
  if (!value || typeof value !== "object") {
    return emptyNutritionBlock();
  }

  return {
    calories: Number(value.calories ?? value.avg_calories ?? 0) || 0,
    protein: Number(value.protein ?? value.avg_protein_g ?? 0) || 0,
    carbs: Number(value.carbs ?? value.avg_carbs_g ?? 0) || 0,
    fat: Number(value.fat ?? value.avg_fat_g ?? 0) || 0,
    fiber: Number(value.fiber ?? value.avg_fiber_g ?? 0) || 0,
  };
}

function normalizeMealCell(value: any) {
  return {
    name: typeof value?.name === "string" ? value.name : null,
    ...normalizeNutritionBlock(value),
  };
}

function estimateMealNutrition(mealName: string) {
  const name = mealName.toLowerCase();
  let calories = 320;
  let protein = 10;
  let carbs = 35;
  let fat = 12;
  let fiber = 4;

  if (/(salad|soup|stew|broth)/.test(name)) {
    calories = 220;
    protein = 8;
    carbs = 18;
    fat = 8;
    fiber = 5;
  } else if (/(breakfast|oat|porridge|toast|cereal|yogurt)/.test(name)) {
    calories = 280;
    protein = 9;
    carbs = 32;
    fat = 10;
    fiber = 5;
  } else if (/(pasta|rice|bowl|wrap|sandwich|taco|pizza)/.test(name)) {
    calories = 380;
    protein = 14;
    carbs = 42;
    fat = 14;
    fiber = 5;
  } else if (/(cake|cookie|brownie|dessert|ice cream|treat|sweet)/.test(name)) {
    calories = 260;
    protein = 3;
    carbs = 34;
    fat = 11;
    fiber = 2;
  } else if (/(fish|salmon|chicken|beef|turkey|egg|omelette|omelet)/.test(name)) {
    calories = 420;
    protein = 28;
    carbs = 12;
    fat = 18;
    fiber = 3;
  }

  return { calories, protein, carbs, fat, fiber };
}

function addNutrition(target: Record<string, number>, source: Record<string, number>) {
  NUTRITION_FIELDS.forEach((field) => {
    target[field] = Math.round(((target[field] || 0) + (source[field] || 0)) * 100) / 100;
  });
}

function normalizeDailyNutrition(value: any) {
  return {
    meals: MEALS.reduce((acc, meal) => {
      acc[meal] = normalizeMealCell(value?.meals?.[meal]);
      return acc;
    }, {} as Record<string, { name: string | null; calories: number; protein: number; carbs: number; fat: number; fiber: number }>),
    total: normalizeNutritionBlock(value?.total),
  };
}

function buildFallbackNutritionBreakdown(meals: Record<string, Record<string, string>> | undefined | null) {
  const days = DAYS.reduce((acc, day) => {
    const dayMeals = meals?.[day] || {};
    const total = emptyNutritionBlock();
    const mealEntries = MEALS.reduce((mealAcc, meal) => {
      const mealName = dayMeals?.[meal]?.trim?.() || dayMeals?.[meal] || "";
      if (!mealName) {
        mealAcc[meal] = { name: null, ...emptyNutritionBlock() };
        return mealAcc;
      }

      const nutrition = estimateMealNutrition(String(mealName));
      mealAcc[meal] = { name: String(mealName), ...nutrition };
      addNutrition(total, nutrition);
      return mealAcc;
    }, {} as Record<string, { name: string | null; calories: number; protein: number; carbs: number; fat: number; fiber: number }>);

    acc[day] = { meals: mealEntries, total };
    return acc;
  }, {} as Record<string, { meals: Record<string, { name: string | null; calories: number; protein: number; carbs: number; fat: number; fiber: number }>; total: { calories: number; protein: number; carbs: number; fat: number; fiber: number } }>);

  const weeklyTotals = Object.values(days).reduce(
    (acc, day) => {
      addNutrition(acc, day.total);
      return acc;
    },
    emptyNutritionBlock()
  );

  const mealCount = DAYS.length * MEALS.length;
  const weeklyAveragePerMeal = {
    calories: Math.round((weeklyTotals.calories / mealCount) * 100) / 100,
    protein: Math.round((weeklyTotals.protein / mealCount) * 100) / 100,
    carbs: Math.round((weeklyTotals.carbs / mealCount) * 100) / 100,
    fat: Math.round((weeklyTotals.fat / mealCount) * 100) / 100,
    fiber: Math.round((weeklyTotals.fiber / mealCount) * 100) / 100,
  };

  return { days, weekly_totals: weeklyTotals, weekly_average_per_meal: weeklyAveragePerMeal };
}

function normalizeNutritionBreakdown(value: any, meals: Record<string, Record<string, string>> | undefined | null) {
  if (value && typeof value === "object" && value.days) {
    const normalizedDays = DAYS.reduce((acc, day) => {
      acc[day] = normalizeDailyNutrition(value.days?.[day]);
      return acc;
    }, {} as Record<string, ReturnType<typeof normalizeDailyNutrition>>);

    return {
      days: normalizedDays,
      weekly_totals: normalizeNutritionBlock(value.weekly_totals),
      weekly_average_per_meal: normalizeNutritionBlock(value.weekly_average_per_meal),
    };
  }

  return buildFallbackNutritionBreakdown(meals);
}

export default function MealsPage() {
  const qc = useQueryClient();
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date(), { weekStartsOn: 1 }));
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [recipeForm, setRecipeForm] = useState({
    name: "",
    description: "",
    ingredients: "",
    instructions: "",
    prep_time: "",
    cook_time: "",
    servings: "",
    cuisine: "",
    tags: "",
  });
  const selectedWeekKey = weekStart.toISOString().slice(0, 10);

  const { data: plans = [] } = useQuery({
    queryKey: ["meal-plans"],
    queryFn: () => mealsApi.listPlans().then((r) => r.data),
  });

  const { data: recipes = [] } = useQuery({
    queryKey: ["recipes"],
    queryFn: () => mealsApi.listRecipes().then((r) => r.data),
  });

  const generatePlan = useMutation({
    mutationFn: () => mealsApi.generatePlan({ week_start: selectedWeekKey, preferences: {} }),
    onSuccess: () => {
      setGenerateError(null);
      qc.invalidateQueries({ queryKey: ["meal-plans"] });
    },
    onError: (error: any) => {
      const detail =
        error?.response?.data?.detail ||
        error?.response?.data?.message ||
        error?.message ||
        "Unable to generate meal plan.";
      setGenerateError(typeof detail === "string" ? detail : "Unable to generate meal plan.");
    },
  });

  const createRecipe = useMutation({
    mutationFn: () =>
      mealsApi.createRecipe({
        name: recipeForm.name.trim(),
        description: recipeForm.description.trim() || null,
        ingredients: recipeForm.ingredients
          .split("\n")
          .map((line) => line.trim())
          .filter(Boolean)
          .map((name) => ({ name })),
        instructions: recipeForm.instructions
          .split("\n")
          .map((line) => line.trim())
          .filter(Boolean),
        prep_time: recipeForm.prep_time ? Number(recipeForm.prep_time) : null,
        cook_time: recipeForm.cook_time ? Number(recipeForm.cook_time) : null,
        servings: recipeForm.servings ? Number(recipeForm.servings) : null,
        cuisine: recipeForm.cuisine.trim() || null,
        tags: recipeForm.tags
          .split(",")
          .map((tag) => tag.trim())
          .filter(Boolean),
        dietary_info: {},
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["recipes"] });
      setRecipeForm({
        name: "",
        description: "",
        ingredients: "",
        instructions: "",
        prep_time: "",
        cook_time: "",
        servings: "",
        cuisine: "",
        tags: "",
      });
    },
  });

  const currentPlan = plans.find((p: any) => {
    if (!p.week_start) return false;
    return new Date(p.week_start).toISOString().slice(0, 10) === selectedWeekKey;
  });
  const nutritionSummary = normalizeNutritionBreakdown(currentPlan?.nutritional_summary, currentPlan?.meals);
  const nutritionIsEstimated = !(currentPlan?.nutritional_summary?.days);

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

      {generateError && (
        <Card className="border-red-200 bg-red-50/70">
          <CardContent className="py-3">
            <p className="text-sm font-medium text-red-900">Meal plan generation failed</p>
            <p className="text-sm text-red-800">{generateError}</p>
          </CardContent>
        </Card>
      )}

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

      {currentPlan?.warnings?.length > 0 && (
        <Card className="border-amber-200 bg-amber-50/60">
          <CardContent className="py-3">
            <p className="text-sm font-medium text-amber-900">Plan fallback used</p>
            <ul className="mt-1 list-disc pl-5 text-sm text-amber-900/80">
              {currentPlan.warnings.map((warning: string) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

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
      {currentPlan && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <CardTitle className="text-base">Nutrition by Meal and Day</CardTitle>
              {nutritionIsEstimated && <Badge variant="outline" className="text-xs">Estimated</Badge>}
            </div>
          </CardHeader>
          <CardContent>
            <div className="mb-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {[
                { label: "Weekly calories", value: nutritionSummary.weekly_totals.calories, unit: "kcal", color: "text-orange-600" },
                { label: "Weekly protein", value: nutritionSummary.weekly_totals.protein, unit: "g", color: "text-blue-600" },
                { label: "Weekly carbs", value: nutritionSummary.weekly_totals.carbs, unit: "g", color: "text-yellow-600" },
                { label: "Weekly fat", value: nutritionSummary.weekly_totals.fat, unit: "g", color: "text-red-600" },
              ].map((n) => (
                <div key={n.label} className="rounded-lg border bg-background p-3 text-center">
                  <p className={cn("text-2xl font-bold", n.color)}>{n.value}</p>
                  <p className="text-xs text-muted-foreground">{n.label} ({n.unit})</p>
                </div>
              ))}
            </div>

            <div className="grid gap-3">
              {DAYS.map((day) => {
                const dayNutrition = nutritionSummary.days?.[day] ?? normalizeDailyNutrition(undefined);
                return (
                  <div key={day} className="rounded-lg border p-4">
                    <div className="mb-3 flex items-center justify-between gap-3">
                      <p className="font-semibold capitalize">{day}</p>
                      <p className="text-xs text-muted-foreground">
                        Total: {dayNutrition.total.calories} kcal | {dayNutrition.total.protein}g protein | {dayNutrition.total.carbs}g carbs
                      </p>
                    </div>
                    <div className="grid gap-2 md:grid-cols-3">
                      {MEALS.map((meal) => {
                        const mealNutrition = dayNutrition.meals?.[meal] ?? normalizeMealCell(undefined);
                        return (
                          <div key={meal} className="rounded-md border bg-muted/30 p-3 text-sm">
                            <p className="mb-1 capitalize font-medium">{meal}</p>
                            <p className="leading-tight">{mealNutrition.name ?? "—"}</p>
                            <p className="mt-2 text-xs text-muted-foreground">
                              {mealNutrition.calories} kcal | {mealNutrition.protein}g protein
                            </p>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Add Recipe</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            className="grid gap-3 md:grid-cols-2"
            onSubmit={(e) => {
              e.preventDefault();
              createRecipe.mutate();
            }}
          >
            <Input
              placeholder="Recipe name"
              value={recipeForm.name}
              onChange={(e) => setRecipeForm({ ...recipeForm, name: e.target.value })}
              required
              className="md:col-span-2"
            />
            <Input
              placeholder="Description"
              value={recipeForm.description}
              onChange={(e) => setRecipeForm({ ...recipeForm, description: e.target.value })}
              className="md:col-span-2"
            />
            <textarea
              placeholder="Ingredients, one per line"
              value={recipeForm.ingredients}
              onChange={(e) => setRecipeForm({ ...recipeForm, ingredients: e.target.value })}
              className="min-h-28 rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:col-span-2"
            />
            <textarea
              placeholder="Instructions, one step per line"
              value={recipeForm.instructions}
              onChange={(e) => setRecipeForm({ ...recipeForm, instructions: e.target.value })}
              required
              className="min-h-32 rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:col-span-2"
            />
            <Input
              placeholder="Prep time (minutes)"
              type="number"
              min="0"
              value={recipeForm.prep_time}
              onChange={(e) => setRecipeForm({ ...recipeForm, prep_time: e.target.value })}
            />
            <Input
              placeholder="Cook time (minutes)"
              type="number"
              min="0"
              value={recipeForm.cook_time}
              onChange={(e) => setRecipeForm({ ...recipeForm, cook_time: e.target.value })}
            />
            <Input
              placeholder="Servings"
              type="number"
              min="1"
              value={recipeForm.servings}
              onChange={(e) => setRecipeForm({ ...recipeForm, servings: e.target.value })}
            />
            <Input
              placeholder="Cuisine"
              value={recipeForm.cuisine}
              onChange={(e) => setRecipeForm({ ...recipeForm, cuisine: e.target.value })}
            />
            <Input
              placeholder="Tags, comma-separated"
              value={recipeForm.tags}
              onChange={(e) => setRecipeForm({ ...recipeForm, tags: e.target.value })}
              className="md:col-span-2"
            />
            <div className="md:col-span-2 flex items-center gap-3">
              <Button type="submit" disabled={createRecipe.isPending || !recipeForm.name.trim()}>
                <Salad className="mr-2 h-4 w-4" />
                {createRecipe.isPending ? "Saving..." : "Save Recipe"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

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
