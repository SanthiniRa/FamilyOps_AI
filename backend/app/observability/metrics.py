from prometheus_client import Counter, Histogram

REQUEST_COUNTER = Counter(
    "familyops_requests_total",
    "Total requests"
)

AGENT_COUNTER = Counter(
    "familyops_agent_runs_total",
    "Agent executions",
    ["agent"]
)

TOOL_COUNTER = Counter(
    "familyops_tool_calls_total",
    "Tool calls",
    ["tool"]
)

FAILURE_COUNTER = Counter(
    "familyops_failures_total",
    "Failures"
)

TOKEN_COUNTER = Counter(
    "familyops_tokens_total",
    "Token usage"
)

COST_COUNTER = Counter(
    "familyops_cost_total",
    "LLM cost"
)

CACHE_HIT_COUNTER = Counter(
    "familyops_cache_hits_total",
    "Cache hits",
    ["layer"]
)

RETRY_COUNTER = Counter(
    "familyops_retries_total",
    "Retry attempts",
    ["operation"]
)

RATE_LIMIT_COUNTER = Counter(
    "familyops_rate_limited_total",
    "Rate limited requests",
    ["route"]
)

LATENCY = Histogram(
    "familyops_request_seconds",
    "Request latency"
)

AGENT_DURATION = Histogram(
    "familyops_agent_duration",
    "Agent execution time",
    ["agent"]
)
