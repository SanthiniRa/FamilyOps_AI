import axios from "axios";

const api = axios.create({
  baseURL: "/api/v1",
  headers: { "Content-Type": "application/json" },
  timeout: 30000,
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    console.error("API error:", err.response?.data || err.message);
    return Promise.reject(err);
  }
);

export default api;

export const dashboardApi = {
  getSummary: () => api.get("/dashboard/summary"),
  getActivityFeed: () => api.get("/dashboard/activity-feed"),
  getHealth: () => api.get("/dashboard/health"),
};

export const tasksApi = {
  list: (params?: { status?: string }) => {
    const cleanParams: Record<string, string> = {};

    if (params?.status) {
      cleanParams.status = params.status;
    }

    return api.get("/tasks/", { params: cleanParams });
  },

  create: (data: unknown) => api.post("/tasks/", data),

  get: (id: string) => api.get(`/tasks/${id}`),

  update: (id: string, data: unknown) =>
    api.patch(`/tasks/${id}`, data),

  delete: (id: string) => api.delete(`/tasks/${id}`),

  stats: () => api.get("/tasks/stats/summary"),
};

export const groceryApi = {
  listLists: () => api.get("/grocery/lists"),
  createList: (data: unknown) => api.post("/grocery/lists", data),
  getList: (id: string) => api.get(`/grocery/lists/${id}`),
  addItem: (listId: string, data: unknown) => api.post(`/grocery/lists/${listId}/items`, data),
  updateItem: (itemId: string, data: unknown) => api.patch(`/grocery/items/${itemId}`, data),
  deleteItem: (itemId: string) => api.delete(`/grocery/items/${itemId}`),
  generateAI: (listId: string) => api.post(`/grocery/lists/${listId}/generate-ai`),
};

export const mealsApi = {
  listRecipes: () => api.get("/meals/recipes"),
  createRecipe: (data: unknown) => api.post("/meals/recipes", data),
  listPlans: () => api.get("/meals/plans"),
  generatePlan: (data: unknown) => api.post("/meals/plans/generate", data),
  getPlan: (id: string) => api.get(`/meals/plans/${id}`),
};

export const remindersApi = {
  list: (params?: Record<string, string>) => api.get("/reminders/", { params }),
  create: (data: unknown) => api.post("/reminders/", data),
  get: (id: string) => api.get(`/reminders/${id}`),
  update: (id: string, data: unknown) => api.patch(`/reminders/${id}`, data),
  delete: (id: string) => api.delete(`/reminders/${id}`),
  today: () => api.get("/reminders/upcoming/today"),
};

export const calendarApi = {
  listEvents: (params?: Record<string, string>) => api.get("/calendar/events", { params }),
  createEvent: (data: unknown) => api.post("/calendar/events", data),
  getEvent: (id: string) => api.get(`/calendar/events/${id}`),
  updateEvent: (id: string, data: unknown) => api.patch(`/calendar/events/${id}`, data),
  deleteEvent: (id: string) => api.delete(`/calendar/events/${id}`),
  upcomingWeek: () => api.get("/calendar/events/upcoming/week"),
};

export const memoryApi = {
  list: (params?: Record<string, string>) => api.get("/memory/", { params }),
  store: (data: unknown) => api.post("/memory/", data),
  search: (data: unknown) => api.post("/memory/search", data),
  delete: (id: string) => api.delete(`/memory/${id}`),
  categories: () => api.get("/memory/categories/summary"),
};

export const familyApi = {
  list: () => api.get("/family/members"),
  create: (data: unknown) => api.post("/family/members", data),
  get: (id: string) => api.get(`/family/members/${id}`),
  update: (id: string, data: unknown) => api.patch(`/family/members/${id}`, data),
  delete: (id: string) => api.delete(`/family/members/${id}`),
};

export const agentApi = {
  chat: (data: { message: string; context?: Record<string, unknown> }) => api.post("/agent/chat", data),
  listRuns: (params?: Record<string, string>) => api.get("/agent/runs", { params }),
  getRun: (id: string) => api.get(`/agent/runs/${id}`),
  stats: () => api.get("/agent/stats"),
};
