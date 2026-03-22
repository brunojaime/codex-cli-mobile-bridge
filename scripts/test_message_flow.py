from __future__ import annotations

import argparse
import sys
import time

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(description="Send a message and poll for a Codex response.")
    parser.add_argument("message", help="Message to send to the backend.")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Backend base URL.")
    parser.add_argument("--poll-interval", type=float, default=2.0, help="Polling interval in seconds.")
    parser.add_argument("--timeout", type=float, default=180.0, help="Overall timeout in seconds.")
    args = parser.parse_args()

    with httpx.Client(base_url=args.base_url, timeout=30.0) as client:
        create_response = client.post("/message", json={"message": args.message})
        create_response.raise_for_status()
        job_id = create_response.json()["job_id"]
        print(f"job_id={job_id}")

        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            response = client.get(f"/response/{job_id}")
            response.raise_for_status()
            payload = response.json()
            status = payload["status"]
            print(f"status={status}")

            if status == "completed":
                print(payload["response"])
                return 0

            if status == "failed":
                print(payload.get("error") or "Execution failed.", file=sys.stderr)
                return 1

            time.sleep(args.poll_interval)

    print("Timed out while waiting for the response.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
