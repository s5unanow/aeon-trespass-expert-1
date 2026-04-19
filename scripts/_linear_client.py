"""Minimal Linear GraphQL client for CI scripts (S5U-620).

Fails CLOSED on every unresolvable state. Shared by `check_coverage_table.py`
and any future CI gate that needs to read Linear issue metadata.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql"
LINEAR_TIMEOUT_SECONDS = 10.0
LINEAR_RETRY_COUNT = 3
LINEAR_RETRY_BACKOFF_SECONDS = 2.0


@dataclass(frozen=True)
class LinearIssue:
    """Subset of Linear issue fields CI gates care about."""

    identifier: str
    description: str
    state_name: str


class LinearAPIError(RuntimeError):
    """Linear API call failed after retries (fail-CLOSED signal)."""


def fetch_linear_issue(issue_number: str, api_key: str) -> LinearIssue:
    """Fetch a Linear issue by number. Retries on rate-limit / transient errors.

    Raises LinearAPIError on any unresolvable state. Fail-CLOSED.
    """
    query = """
    query ($n: Float!) {
      issues(filter: { number: { eq: $n }, team: { key: { eq: "S5U" } } }) {
        nodes {
          id
          identifier
          description
          state { name }
        }
      }
    }
    """
    payload = json.dumps({"query": query, "variables": {"n": int(issue_number)}}).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": api_key,
    }

    last_error: Exception | None = None
    for attempt in range(1, LINEAR_RETRY_COUNT + 1):
        try:
            request = urllib.request.Request(
                LINEAR_GRAPHQL_URL,
                data=payload,
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=LINEAR_TIMEOUT_SECONDS) as resp:
                status = resp.getcode()
                if status == 429:
                    raise LinearAPIError(f"Linear rate-limit (429) on attempt {attempt}")
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code == 429 and attempt < LINEAR_RETRY_COUNT:
                time.sleep(LINEAR_RETRY_BACKOFF_SECONDS * attempt)
                continue
            raise LinearAPIError(f"Linear HTTP {exc.code}: {exc.reason}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt < LINEAR_RETRY_COUNT:
                time.sleep(LINEAR_RETRY_BACKOFF_SECONDS * attempt)
                continue
            raise LinearAPIError(f"Linear network error after retries: {exc}") from exc

        try:
            body = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LinearAPIError(f"Linear returned non-JSON: {exc}") from exc
        if "errors" in body:
            raise LinearAPIError(f"Linear GraphQL errors: {body['errors']}")
        try:
            nodes = body["data"]["issues"]["nodes"]
        except (KeyError, TypeError) as exc:
            raise LinearAPIError(f"Linear response malformed: {body}") from exc
        if not nodes:
            raise LinearAPIError(f"Linear issue S5U-{issue_number} not found")
        node = nodes[0]
        identifier = node.get("identifier") or f"S5U-{issue_number}"
        description = node.get("description") or ""
        state = node.get("state") or {}
        state_name = state.get("name") or "Unknown"
        return LinearIssue(
            identifier=identifier,
            description=description,
            state_name=state_name,
        )

    raise LinearAPIError(f"Linear fetch failed: {last_error}")
