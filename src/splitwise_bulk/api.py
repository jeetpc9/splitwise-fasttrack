from __future__ import annotations

import time
from typing import Any

import requests

API_BASE = "https://secure.splitwise.com/api/v3.0"
DEFAULT_RATE_LIMIT_DELAY = 0.15


class SplitwiseError(Exception):
    pass


class SplitwiseClient:
    def __init__(self, api_key: str, rate_limit_delay: float = DEFAULT_RATE_LIMIT_DELAY):
        self.rate_limit_delay = rate_limit_delay
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {api_key.strip()}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            }
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> dict:
        response = self.session.request(method, f"{API_BASE}/{path}", timeout=15, **kwargs)
        data = response.json()
        if response.status_code not in (200, 201):
            raise SplitwiseError(self._format_errors(data, response.status_code))
        errors = data.get("errors", {})
        if errors:
            raise SplitwiseError(self._format_errors(data, response.status_code))
        return data

    @staticmethod
    def _format_errors(data: dict, status_code: int) -> str:
        errors = data.get("errors", {})
        if isinstance(errors, dict):
            for key in ("base", "general", "message"):
                if key in errors and errors[key]:
                    value = errors[key]
                    if isinstance(value, list):
                        return str(value[0])
                    return str(value)
            for value in errors.values():
                if isinstance(value, list) and value:
                    return str(value[0])
                if value:
                    return str(value)
        return f"Splitwise API error (HTTP {status_code})"

    def get_current_user(self) -> dict:
        return self._request("GET", "get_current_user").get("user", {})

    def get_groups(self) -> list[dict]:
        groups = self._request("GET", "get_groups").get("groups", [])
        return [{"id": group["id"], "name": group["name"]} for group in groups]

    def get_group(self, group_id: int) -> dict:
        return self._request("GET", f"get_group/{group_id}").get("group", {})

    def get_group_members(self, group_id: int) -> list[dict]:
        group = self.get_group(group_id)
        members = []
        for member in group.get("members", []):
            name = f"{member.get('first_name', '')} {member.get('last_name', '')}".strip()
            members.append(
                {
                    "id": member["id"],
                    "name": name,
                    "email": member.get("email", ""),
                }
            )
        return members

    def get_friends(self) -> list[dict]:
        friends = self._request("GET", "get_friends").get("friends", [])
        result = []
        for friend in friends:
            name = f"{friend.get('first_name', '')} {friend.get('last_name', '')}".strip()
            result.append(
                {
                    "id": friend["id"],
                    "name": name,
                    "email": friend.get("email", ""),
                }
            )
        return result

    def create_expense(self, payload: dict) -> dict:
        data = self._request("POST", "create_expense", data=payload)
        expenses = data.get("expenses", [])
        if self.rate_limit_delay:
            time.sleep(self.rate_limit_delay)
        return expenses[0] if expenses else {}
