class SupervisorAgent:

    def route(self, state: dict) -> str:

        query = state["user_query"].lower()

        if any(k in query for k in ["meal", "food", "eat", "recipe", "diet"]):
            return "meal_planning"

        if any(k in query for k in ["buy", "shopping", "groceries"]):
            return "shopping"

        if any(k in query for k in ["email"]):
            return "email"

        if any(k in query for k in ["calendar", "schedule"]):
            return "calendar"

        return "knowledge"