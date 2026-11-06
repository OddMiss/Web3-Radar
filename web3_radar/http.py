from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class HttpError(RuntimeError):
    pass


class HttpClient:
    def __init__(self, timeout: int = 20, retries: int = 2) -> None:
        self.timeout = timeout
        self.retries = retries

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if params:
            query = urllib.parse.urlencode(params)
            url = f"{url}{'&' if '?' in url else '?'}{query}"
        return self._request_json("GET", url, headers=headers)

    def post_form_json(
        self,
        url: str,
        *,
        data: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        body = urllib.parse.urlencode(data).encode("utf-8")
        merged = {"Content-Type": "application/x-www-form-urlencoded"}
        if headers:
            merged.update(headers)
        return self._request_json("POST", url, body=body, headers=merged)

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        request_headers = {
            "Accept": "application/json",
            "User-Agent": "Web3-Radar/0.1 (+https://github.com/OddMiss/Web3-Radar)",
        }
        if headers:
            request_headers.update(headers)
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = response.read().decode("utf-8")
                parsed = json.loads(payload)
                if not isinstance(parsed, dict):
                    raise HttpError(f"expected JSON object from {self._safe_url(url)}")
                return parsed
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                last_error = HttpError(
                    f"HTTP {exc.code} from {self._safe_url(url)}: {detail}"
                )
                if exc.code < 500 and exc.code != 429:
                    break
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, HttpError) as exc:
                last_error = exc
            if attempt < self.retries:
                time.sleep(1.5 * (2**attempt))
        raise HttpError(str(last_error or f"request failed: {self._safe_url(url)}"))

    @staticmethod
    def _safe_url(url: str) -> str:
        parsed = urllib.parse.urlsplit(url)
        path = parsed.path
        if parsed.netloc == "api.telegram.org" and path.startswith("/bot"):
            suffix = path.split("/", 2)
            path = "/bot***/" + (suffix[2] if len(suffix) > 2 else "")
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))
