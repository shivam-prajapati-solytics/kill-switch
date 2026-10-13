import re, uuid, json
from datetime import datetime, timezone
from redis import Redis
from redis.exceptions import RedisError
from django.conf import settings

GLOBAL_KEY = "agentguard:global_state"
AUDIT_KEY = "agentguard:audit_events"
RUN_PREFIX = "agentguard:run:"

class SecurityStateUnavailable(Exception):
    pass

def redis_client():
    return Redis.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=1, socket_timeout=1)

def _client():
    client = redis_client()
    try:
        client.ping()
    except RedisError as exc:
        raise SecurityStateUnavailable("Security state unavailable") from exc
    return client

def global_state():
    return _client().hgetall(GLOBAL_KEY) or {"state": "ENABLED"}

def assert_enabled(run_id=None):
    client = _client()
    if (client.hget(GLOBAL_KEY, "state") or "ENABLED") != "ENABLED":
        raise PermissionError("Agent globally disabled")
    if run_id and client.get(RUN_PREFIX + run_id) == "KILLED":
        raise PermissionError("Execution killed")

def kill_run(run_id, reason):
    _client().set(RUN_PREFIX + run_id, "KILLED", ex=86400)
    audit("RUN_KILLED", {"run_id": run_id, "reason": reason})

def set_global_kill(reason, actor="admin"):
    client = _client()
    client.hset(GLOBAL_KEY, mapping={
        "state": "KILLED", "reason": reason[:240], "actor": actor[:100],
        "updated_at": datetime.now(timezone.utc).isoformat()
    })
    audit("GLOBAL_KILL", {"reason": reason[:240], "actor": actor[:100]})

def reset_global_kill(actor="admin"):
    _client().hset(GLOBAL_KEY, mapping={
        "state": "ENABLED", "reason": "", "actor": actor[:100],
        "updated_at": datetime.now(timezone.utc).isoformat()
    })
    audit("GLOBAL_RESET", {"actor": actor[:100]})

def audit(event, details):
    try:
        item = {"event": event, "at": datetime.now(timezone.utc).isoformat(), **details}
        client = redis_client()
        client.lpush(AUDIT_KEY, json.dumps(item))
        client.ltrim(AUDIT_KEY, 0, 999)
    except RedisError:
        pass

def detect_pii(text):
    patterns = [
        r"\b\d{3}-\d{2}-\d{4}\b",
        r"\b[A-Z]{5}[0-9]{4}[A-Z]\b",
        r"\b(?:\+91[\s-]?)?[6-9]\d{9}\b",
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    ]
    return any(re.search(p, text, flags=re.IGNORECASE) for p in patterns)

def new_run_id():
    return str(uuid.uuid4())
