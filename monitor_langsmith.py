
import asyncio
import os
from datetime import datetime, timedelta, timezone

from langsmith import Client
from redis import Redis
from redis.exceptions import RedisError

PROJECT_NAME = os.getenv("LANGSMITH_PROJECT", "KILLSWITCH")
POLL_INTERVAL = 10

SENSITIVE_VALUES = [
    "9876543210",
    "123456789",
]

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
GLOBAL_KEY = "agentguard:global_state"
AUDIT_KEY = "agentguard:audit_events"


def find_sensitive_values(output):
    text = str(output or "")
    return [value for value in SENSITIVE_VALUES if value in text]


def activate_kill_switch(matches, run):
    client = Redis.from_url(
        REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )

    try:
        client.ping()

        # Keep the existing application's Redis state format.
        client.hset(
            GLOBAL_KEY,
            mapping={
                "state": "KILLED",
                "reason": "Sensitive value detected in LangSmith trace",
                "actor": "langsmith-monitor",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        print("\n🚨 SUSPICIOUS TRACE DETECTED")
        print("Run ID:", run.id)
        print("Matched test values:", len(matches))
        print("🛑 Redis kill switch activated.")
    finally:
        client.close()


async def main():
    client = Client()
    project = await client.aread_project(project_name=PROJECT_NAME)
    project_id = str(project.id)
    seen_run_ids = set()

    print(f"Monitoring LangSmith project: {PROJECT_NAME}")
    print(f"Checking every {POLL_INTERVAL} seconds.")
    print("Press Ctrl+C to stop.\n")

    while True:
        try:
            now = datetime.now(timezone.utc)

            async for run in client.runs.query(
                project_ids=[project_id],
                min_start_time=now - timedelta(minutes=5),
                max_start_time=now,
                filter='eq(name, "KILLSWITCH Ollama Generation")',
                selects=["ID", "NAME", "START_TIME", "OUTPUTS", "ERROR"],
                page_size=100,
            ):
                run_id = str(run.id)

                if run_id in seen_run_ids or not run.outputs:
                    continue

                matches = find_sensitive_values(run.outputs)
                seen_run_ids.add(run_id)

                if matches:
                    activate_kill_switch(matches, run)
                else:
                    print(f"[OK] New trace: {run_id}")

        except asyncio.CancelledError:
            raise
        except (RedisError, Exception) as exc:
            print(f"Monitor error: {type(exc).__name__}: {exc}")

        await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nLangSmith monitor stopped.")

