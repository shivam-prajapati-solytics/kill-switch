import json, hmac
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt
from redis.exceptions import RedisError
from .security import (
    assert_enabled, audit, detect_pii, global_state, kill_run,
    new_run_id, reset_global_kill, set_global_kill, SecurityStateUnavailable,
)
from .rag import retrieve

def _json_body(request):
    try:
        return json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

def _admin_ok(request):
    supplied = request.headers.get("X-Admin-Token", "")
    expected = settings.ADMIN_TOKEN
    return bool(expected) and hmac.compare_digest(supplied, expected)

@require_GET
def health(request):
    return JsonResponse({"status": "ok", "service": "agent-kill-switch-demo"})

@csrf_exempt
@require_POST
def agent_query(request):
    body = _json_body(request)
    if not isinstance(body, dict) or not isinstance(body.get("query"), str):
        return JsonResponse({"error": "Provide JSON with a string 'query'."}, status=400)
    query = body["query"]
    user_id = str(body.get("user_id", "demo-user"))
    # DEMO ONLY: derive role from trusted auth claims in a real deployment.
    role = str(body.get("role", "general"))
    run_id = new_run_id()
    try:
        assert_enabled(run_id)
        doc = retrieve(query, role)
        assert_enabled(run_id)

        if role not in doc["allowed_roles"]:
            kill_run(run_id, "Unauthorized restricted document retrieval")
            audit("POLICY_DENY", {"run_id": run_id, "user_id": user_id, "source": doc["source"]})
            return JsonResponse({"status": "blocked", "run_id": run_id,
                                    "error": "The request was blocked by the security policy."}, status=403)
        
        candidate = f"Answer based on retrieved content: {doc['text']}"
        assert_enabled(run_id)
        if doc["classification"] != "public" or detect_pii(candidate):
            kill_run(run_id, "Potential sensitive-data disclosure")
            audit("OUTPUT_BLOCKED", {"run_id": run_id, "user_id": user_id,
                                        "classification": doc["classification"], "source": doc["source"]})
            return JsonResponse({"status": "blocked", "run_id": run_id,
                                    "error": "The response was blocked by the security policy."}, status=403)
        
        assert_enabled(run_id)  # Final check immediately before release.
        audit("QUERY_ALLOWED", {"run_id": run_id, "user_id": user_id, "source": doc["source"]})
        return JsonResponse({"status": "ok", "run_id": run_id, "answer": candidate})
    
    except PermissionError:
        return JsonResponse({"status": "killed", "run_id": run_id,
                                "error": "Agent execution is disabled."}, status=503)
    except (SecurityStateUnavailable, RedisError):
        audit("SECURITY_STATE_UNAVAILABLE", {"run_id": run_id})
        return JsonResponse({"status": "blocked",
                                "error": "Security control unavailable; request denied."}, status=503)

@csrf_exempt
@require_POST
def remote_kill(request):
    if not _admin_ok(request):
        return JsonResponse({"error": "Unauthorized"}, status=401)
    body = _json_body(request)
    if not isinstance(body, dict):
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    try:
        set_global_kill(str(body.get("reason", "Remote emergency stop")), actor="remote-admin")
        return JsonResponse({"status": "KILLED", "message": "Global agent kill activated."})
    except (SecurityStateUnavailable, RedisError):
        return JsonResponse({"error": "Kill state unconfirmed; isolate service at infrastructure level."}, status=503)

@csrf_exempt
@require_POST
def remote_reset(request):
    if not _admin_ok(request):
        return JsonResponse({"error": "Unauthorized"}, status=401)
    try:
        reset_global_kill(actor="remote-admin")
        return JsonResponse({"status": "ENABLED", "message": "Global kill reset."})
    except (SecurityStateUnavailable, RedisError):
        return JsonResponse({"error": "Security state unavailable; reset refused."}, status=503)

@require_GET
def kill_status(request):
    if not _admin_ok(request):
        return JsonResponse({"error": "Unauthorized"}, status=401)
    try:
        state = global_state()
        return JsonResponse({k: state.get(k, "") for k in ("state", "reason", "actor", "updated_at")})
    except (SecurityStateUnavailable, RedisError):
        return JsonResponse({"error": "Security state unavailable"}, status=503)
