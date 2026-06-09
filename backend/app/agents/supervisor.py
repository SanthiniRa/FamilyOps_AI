from app.observability.tracing import agent_tracer
from app.observability.metrics import AGENT_COUNTER

class SupervisorAgent:

    def route(
        self,
        state: dict
    ):

        trace = agent_tracer.start(
            "supervisor",
            state["user_query"]
        )

        AGENT_COUNTER.labels(
            agent="supervisor"
        ).inc()

        query = state["user_query"].lower()

        if any(
            k in query
            for k in [
                "meal",
                "food",
                "eat",
                "recipe",
                "diet"
            ]
        ):
            agent_tracer.finish(
                trace,
                "meal_planning"
            )
            return "meal_planning"

        if any(
            k in query
            for k in [
                "buy",
                "shopping",
                "groceries"
            ]
        ):
            return "shopping"

        if "email" in query:
            return "email"

        if any(
            k in query
            for k in [
                "calendar",
                "schedule"
            ]
        ):
            return "calendar"

        return "knowledge"