import axios from "axios";

export const AUTH_TOKEN_KEY = "familyops_api_token";

const getApiToken = () => {
  const envToken = process.env.NEXT_PUBLIC_API_BEARER_TOKEN;

  if (typeof window === "undefined") {
    return envToken;
  }

  return window.localStorage.getItem(AUTH_TOKEN_KEY) || envToken;
};

export const getStoredAuthToken = () => {
  if (typeof window === "undefined") {
    return null;
  }

  return window.localStorage.getItem(AUTH_TOKEN_KEY);
};

export const setStoredAuthToken = (token: string) => {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.setItem(AUTH_TOKEN_KEY, token);
};

export const clearStoredAuthToken = () => {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.removeItem(AUTH_TOKEN_KEY);
};

const api = axios.create({
  baseURL: "/api/v1",
  headers: { "Content-Type": "application/json" },
  timeout: 30000,
});

api.interceptors.request.use((config) => {
  const token = getApiToken();
  if (token) {
    config.headers = config.headers ?? {};
    config.headers.Authorization = `Bearer ${token}`;
  }

  if (typeof FormData !== "undefined" && config.data instanceof FormData) {
    config.headers = config.headers ?? {};
    delete (config.headers as Record<string, string>)["Content-Type"];
    delete (config.headers as Record<string, string>)["content-type"];
  }

  return config;
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
  getVersion: () => api.get("/dashboard/version"),
};

export const tasksApi = {
  list: (params?: Record<string, string>) => api.get("/tasks/", { params }),
  create: (data: unknown) => api.post("/tasks/", data),
  get: (id: string) => api.get(`/tasks/${id}`),
  update: (id: string, data: unknown) => api.patch(`/tasks/${id}`, data),
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

export const pantryApi = {
  listItems: (params?: Record<string, string>) => api.get("/pantry", { params }),
  createItem: (data: unknown) => api.post("/pantry", data),
  getItem: (id: string) => api.get(`/pantry/${id}`),
  updateItem: (id: string, data: unknown) => api.patch(`/pantry/${id}`, data),
  useItem: (id: string, data: unknown) => api.post(`/pantry/${id}/use`, data),
  deleteItem: (id: string) => api.delete(`/pantry/${id}`),
  summary: () => api.get("/pantry/summary"),
  lowStock: () => api.get("/pantry/alerts/low-stock"),
  expiring: () => api.get("/pantry/alerts/expiring"),
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

export const uploadsApi = {
  uploadDocument: (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return api.post("/uploads/document", formData);
  },
  uploadFoodImage: (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return api.post("/uploads/food-image", formData);
  },
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

export const smsApi = {
  list: (params?: Record<string, string>) => api.get("/sms/messages", { params }),
  test: (body: string, from_number?: string) =>
    api.post(`/sms/test?body=${encodeURIComponent(body)}&from_number=${encodeURIComponent(from_number ?? "+10000000000")}`),
  shortcut: (payload: { text: string; source: string; sender?: string; token?: string }) =>
    api.post("/sms/shortcut", payload),
  instructions: () => api.get("/sms/shortcut-instructions"),
};

export const authApi = {
  login: (data: { email: string; password: string }) => api.post("/auth/login", data),
  register: (data: { email: string; password: string; full_name?: string | null }) =>
    api.post("/auth/register", data),
  me: () => api.get("/auth/me"),
};
