from __future__ import annotations

# Auth
LOGIN = "/auth/login"
CLI_LOGIN = "/auth/cli-login"
CLI_REGISTER = "/auth/cli-register"
CLI_VERIFY_EMAIL = "/auth/cli-verify-email"
CLI_OAUTH_START = "/auth/cli-oauth-start"
AUTHORIZE_APP = "/auth/authorize-app"
LOGOUT = "/auth/logout"
ME = "/auth/me"

# System / Health
ROOT = "/"
HEALTH = "/health"
HEALTH_READY = "/health/ready"
HEALTH_LIVE = "/health/live"
HEALTH_APIS = "/health/apis"

# Business
BUSINESSES = "/businesses"
BUSINESS = "/businesses/{business_id}"
BUSINESS_LOGO = "/businesses/{business_id}/logo"
HEALTH_SCORES = "/businesses/{business_id}/health-scores"
HEALTH_SCORES_BREAKDOWN = "/businesses/{business_id}/health-scores/breakdown"

# Business Crawl
CRAWL_DATA = "/businesses/{business_id}/crawl-data"
CRAWL_START = "/businesses/{business_id}/crawl"
CRAWL_CANCEL = "/businesses/{business_id}/crawl/cancel"

# Named Audits (templates)
NAMED_AUDITS = "/named-audits"
NAMED_AUDIT = "/named-audits/{named_audit_id}"

# Audit
AUDIT_START = "/audit/start"
AUDIT_STATUS = "/audit/{job_id}/status"
AUDIT_RESULT = "/audit/{job_id}/result"
AUDIT_DETAILS = "/audit/{job_id}/details"
AUDIT_EXPORT_PDF = "/audit/{job_id}/export/pdf"
AUDIT_EXPORT_URL = "/audit/{job_id}/export/url"
AUDIT_HISTORY = "/audit/history"
AUDIT_CANCEL = "/audit/{job_id}/cancel"

# Free audit (no login; same audit the youcited.com homepage prompt runs)
FREE_AUDIT = "/free-audit"
FREE_AUDIT_REPORT = "/free-audit/report/{token}"
AUDIT_DELETE = "/audit/{job_id}"
AUDIT_PROVIDERS = "/audit/{job_id}/providers"
AUDIT_QUESTION_DETAIL = "/audit/{job_id}/question/{question_id}"
AUDIT_MODELS = "/audit/models"
AUDIT_MODEL_RESULTS = "/audit/{job_id}/models"

# Recommendations
RECOMMEND_START = "/recommendations/start"
RECOMMEND_STATUS = "/recommendations/{job_id}/status"
RECOMMEND_RESULT = "/recommendations/{job_id}/result"
RECOMMEND_HISTORY = "/recommendations/audit/{audit_job_id}/history"
RECOMMEND_EXPORT_PDF = "/recommendations/{job_id}/export/pdf"
RECOMMEND_CANCEL = "/recommendations/{job_id}/cancel"
RECOMMEND_DELETE = "/recommendations/{job_id}"
RECOMMEND_CHECK_STATUS = "/recommendations/{job_id}/check-status"
RECOMMEND_VALIDATE = "/recommendations/{recommendation_id}/validate"
RECOMMEND_VALIDATE_LATEST = "/recommendations/{recommendation_id}/validate/latest"

# Solutions
SOLUTION_REQUEST = "/solutions/request"
SOLUTION_REQUEST_BATCH = "/solutions/request-batch"
SOLUTION_CREATE = "/solutions/create"
SOLUTION_PRIORITY_ACTION = "/solutions/priority-action"
SOLUTION_STATUS = "/solutions/{job_id}/status"
SOLUTION_RESULT = "/solutions/{job_id}/result"
SOLUTION_HISTORY = "/solutions/history"
SOLUTION_CANCEL = "/solutions/{job_id}/cancel"
SOLUTION_DELETE = "/solutions/{job_id}"

# Business HQ
HQ = "/businesses/{business_id}/hq"
HQ_HEAVY = "/businesses/{business_id}/hq/heavy"
HQ_PRIORITY = "/businesses/{business_id}/hq/priority"
HQ_PRIORITY_STATUS = "/businesses/{business_id}/hq/priority/{action_id}/status"
HQ_PRIORITY_SUMMARY = "/businesses/{business_id}/hq/priority/summary"
HQ_RECOMPUTE = "/businesses/{business_id}/hq/recompute"
HQ_OVERVIEW_REFRESH_AUDIT = "/businesses/{business_id}/overview/refresh-audit"
HQ_OVERVIEW_REFRESH_RECS = "/businesses/{business_id}/overview/refresh-recommendations"
HQ_OVERVIEW_REFRESH_ALL = "/businesses/{business_id}/overview/refresh-all"
HQ_AGENT_BRIEF = "/businesses/{business_id}/agent-brief"
PERSONAS = "/businesses/{business_id}/personas"
PERSONA = "/businesses/{business_id}/personas/{persona_id}"
PRODUCTS = "/businesses/{business_id}/products"
PRODUCT = "/businesses/{business_id}/products/{product_id}"
AGENTIC_READINESS = "/businesses/{business_id}/agentic-readiness"
TRUST_SIGNALS = "/businesses/{business_id}/trust-signals"

# Analytics
ANALYTICS_COMPARE = "/analytics/audits/{audit_id}/compare/{baseline_id}"

# Billing (pay-as-you-go credits; 1 credit = $1)
BILLING_PRICES = "/billing/prices"
BILLING_CREDITS = "/billing/credits"
BILLING_CREDIT_TRANSACTIONS = "/billing/credits/transactions"
BILLING_CREDITS_CHECKOUT = "/billing/credits/checkout"
BILLING_AUDIT_CHECKOUT = "/billing/audit-checkout"
BILLING_AUTO_REFILL = "/billing/credits/auto-refill"
BILLING_CREDITS_REFUND = "/billing/credits/refund"
BILLING_CREDITS_REDEEM = "/billing/credits/redeem"
BILLING_AUDIT_QUOTE = "/billing/audit-quote"

# Agent identity (per-user agent keys, sent as X-Agent-API-Key)
AGENT_SIGNUP = "/agent/signup"
AGENT_KEY_STATUS = "/agent/key-status"
AGENT_KEYS = "/agent-keys"
AGENT_KEY = "/agent-keys/{key_id}"
