from threading import Lock

class TokenTracker:
    def __init__(self):
        self.lock = Lock()

        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_tokens = 0
        self.total_cost = 0.0
        self.total_requests = 0

    def track_usage(self, usage: dict, cost: float = 0.0):
        with self.lock:
            self.total_prompt_tokens += usage.get(
                "prompt_tokens", 0
            )

            self.total_completion_tokens += usage.get(
                "completion_tokens", 0
            )

            self.total_tokens += usage.get(
                "total_tokens", 0
            )

            self.total_cost += cost
            self.total_requests += 1

    def metrics(self):
        return {
            "requests": self.total_requests,
            "prompt_tokens": self.total_prompt_tokens,
            "completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_tokens,
            "cost": self.total_cost,
        }


token_tracker = TokenTracker()