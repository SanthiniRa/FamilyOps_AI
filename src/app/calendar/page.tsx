"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { calendarApi } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Plus, Trash2, Calendar, Clock, MapPin, ChevronLeft, ChevronRight } from "lucide-react";
import { format, startOfMonth, endOfMonth, eachDayOfInterval, isSameMonth, isToday, isSameDay, addMonths, subMonths } from "date-fns";
import { cn, formatRelative } from "@/lib/utils";

export default function CalendarPage() {
  const qc = useQueryClient();
  const [currentMonth, setCurrentMonth] = useState(new Date());
  const [selectedDate, setSelectedDate] = useState<Date | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ title: "", description: "", start_time: "", end_time: "", location: "" });

  const { data: events = [] } = useQuery({
    queryKey: ["calendar-events"],
    queryFn: () => calendarApi.listEvents().then((r) => r.data),
  });

  const createEvent = useMutation({
    mutationFn: (data: any) => calendarApi.createEvent(data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["calendar-events"] }); setShowForm(false); setForm({ title: "", description: "", start_time: "", end_time: "", location: "" }); },
  });

  const deleteEvent = useMutation({
    mutationFn: (id: string) => calendarApi.deleteEvent(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["calendar-events"] }),
  });

  const monthDays = eachDayOfInterval({
    start: startOfMonth(currentMonth),
    end: endOfMonth(currentMonth),
  });

  const getEventsForDay = (day: Date) =>
    events.filter((e: any) => isSameDay(new Date(e.start_time), day));

  const selectedDayEvents = selectedDate ? getEventsForDay(selectedDate) : [];

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Calendar</h1>
          <p className="text-sm text-muted-foreground">Family schedule and events</p>
        </div>
        <Button onClick={() => setShowForm(!showForm)}>
          <Plus className="mr-2 h-4 w-4" /> Add Event
        </Button>
      </div>

      {showForm && (
        <Card>
          <CardHeader><CardTitle className="text-base">New Event</CardTitle></CardHeader>
          <CardContent>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                createEvent.mutate({
                  ...form,
                  start_time: new Date(form.start_time).toISOString(),
                  end_time: new Date(form.end_time).toISOString(),
                });
              }}
              className="grid gap-3 sm:grid-cols-2"
            >
              <Input placeholder="Event title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required className="sm:col-span-2" />
              <Input placeholder="Description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
              <Input placeholder="Location" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} />
              <Input type="datetime-local" value={form.start_time} onChange={(e) => setForm({ ...form, start_time: e.target.value })} required />
              <Input type="datetime-local" value={form.end_time} onChange={(e) => setForm({ ...form, end_time: e.target.value })} required />
              <div className="flex gap-2 sm:col-span-2">
                <Button type="submit" disabled={createEvent.isPending}>Create Event</Button>
                <Button type="button" variant="outline" onClick={() => setShowForm(false)}>Cancel</Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Month view */}
        <Card className="lg:col-span-2">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle>{format(currentMonth, "MMMM yyyy")}</CardTitle>
              <div className="flex gap-1">
                <Button variant="ghost" size="icon" onClick={() => setCurrentMonth(subMonths(currentMonth, 1))}>
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <Button variant="ghost" size="icon" onClick={() => setCurrentMonth(addMonths(currentMonth, 1))}>
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-7 gap-1 mb-2">
              {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((d) => (
                <div key={d} className="text-center text-xs font-medium text-muted-foreground py-1">{d}</div>
              ))}
            </div>
            <div className="grid grid-cols-7 gap-1">
              {Array.from({ length: startOfMonth(currentMonth).getDay() }).map((_, i) => (
                <div key={`empty-${i}`} />
              ))}
              {monthDays.map((day) => {
                const dayEvents = getEventsForDay(day);
                const isSelected = selectedDate && isSameDay(day, selectedDate);
                return (
                  <button
                    key={day.toISOString()}
                    onClick={() => setSelectedDate(day)}
                    className={cn(
                      "relative aspect-square rounded-md p-1 text-sm transition-colors hover:bg-muted",
                      isToday(day) && "font-bold text-primary",
                      isSelected && "bg-primary text-primary-foreground hover:bg-primary/90",
                      !isSameMonth(day, currentMonth) && "text-muted-foreground opacity-50"
                    )}
                  >
                    {format(day, "d")}
                    {dayEvents.length > 0 && (
                      <span className={cn(
                        "absolute bottom-0.5 left-1/2 h-1 w-1 -translate-x-1/2 rounded-full",
                        isSelected ? "bg-white" : "bg-primary"
                      )} />
                    )}
                  </button>
                );
              })}
            </div>
          </CardContent>
        </Card>

        {/* Selected day events */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              {selectedDate ? format(selectedDate, "MMMM d") : "Select a day"}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {selectedDate && selectedDayEvents.length === 0 ? (
              <p className="text-sm text-muted-foreground py-4 text-center">No events on this day</p>
            ) : (
              selectedDayEvents.map((e: any) => (
                <div key={e.id} className="rounded-md border p-3 space-y-1">
                  <div className="flex items-start justify-between">
                    <p className="text-sm font-medium">{e.title}</p>
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-6 w-6 -mt-0.5 text-muted-foreground hover:text-destructive"
                      onClick={() => deleteEvent.mutate(e.id)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                  <p className="text-xs text-muted-foreground flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    {format(new Date(e.start_time), "h:mm a")} – {format(new Date(e.end_time), "h:mm a")}
                  </p>
                  {e.location && (
                    <p className="text-xs text-muted-foreground flex items-center gap-1">
                      <MapPin className="h-3 w-3" />{e.location}
                    </p>
                  )}
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
