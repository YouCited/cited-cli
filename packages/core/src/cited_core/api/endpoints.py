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
AUDIT_DELETE = "/audit/{job_id}"
AUDIT_PROVIDERS = "/audit/{job_id}/providers"
AUDIT_QUESTION_DETAIL = "/audit/{job_id}/question/{question_id}"

# Recommendations
RECOMMEND_START = "/recommendations/start"
RECOMMEND_STATUS = "/recommendations/{job_id}/status"
RECOMMEND_RESULT = "/recommendations/{job_id}/result"
RECOMMEND_HISTORY = "/recommendations/audit/{audit_job_id}/history"
RECOMMEND_EXPORT_PDF = "/recommendations/{job_id}/export/pdf"
RECOMMEND_CANCEL = "/recommendations/{job_id}/cancel"
RECOMMEND_DELETE = "/recommendations/{job_id}"

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
HQ_EXPORT_PDF = "/businesses/{business_id}/hq/export/pdf"
HQ_RECOMPUTE = "/businesses/{business_id}/hq/recompute"
PERSONAS = "/businesses/{business_id}/personas"
PRODUCTS = "/businesses/{business_id}/products"
BUYER_INTENTS = "/businesses/{business_id}/buyer-intents"
AGENTIC_READINESS = "/businesses/{business_id}/agentic-readiness"
TRUST_SIGNALS = "/businesses/{business_id}/trust-signals"

# Analytics
ANALYTICS_COMPARE = "/analytics/audits/{audit_id}/compare/{baseline_id}"
ANALYTICS_DASHBOARD = "/analytics/businesses/{business_id}/dashboard"
ANALYTICS_TRENDS = "/analytics/businesses/{business_id}/trends"
ANALYTICS_ADVANCED = "/analytics/businesses/{business_id}/advanced-scoring"

# Agent Query API (v1)
AGENT_ROOT = "/agent/v1"
AGENT_BUSINESS = "/agent/v1/business/{business_id}"
AGENT_FACTS = "/agent/v1/business/{business_id}/facts"
AGENT_CLAIMS = "/agent/v1/business/{business_id}/claims"
AGENT_COMPARISON = "/agent/v1/business/{business_id}/comparison"
AGENT_SEMANTIC_HEALTH = "/agent/v1/business/{business_id}/semantic-health"
AGENT_BUYER_FIT = "/agent/v1/query/buyer-fit"

# Billing (agentic payments)
BILLING_PRICING = "/billing/pricing"
BILLING_AGENT_UPGRADE = "/billing/agent-upgrade"
