"""GitHub API client with rate limiting, caching, and pagination."""

from __future__ import annotations

import json
import os
import random
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Literal
from urllib.parse import urlencode, urlparse

import requests

Json = Any
AuthMode = Literal["auto", "required", "none"]

DEFAULT_CACHE_PATH = Path(".cache/defibrillator/github_cache.json")
CACHE_MAX_AGE_DAYS = 7


class GitHubError(RuntimeError):
    """Base exception for GitHub API errors."""


class GitHubAuthError(GitHubError):
    """Raised when authentication is required but not available."""


@dataclass
class GitHubHTTPError(GitHubError):
    """Raised for HTTP errors from the GitHub API."""

    status_code: int
    url: str
    response_text: str | None = None
    headers: dict[str, str] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"GitHub API error {self.status_code} for {self.url}: {self.response_text[:200] if self.response_text else 'No response body'}"


@dataclass
class CacheEntry:
    """Cached response entry."""

    etag: str
    url: str
    status_code: int
    headers: dict[str, str]
    body_text: str
    saved_at_epoch: float


@dataclass
class ResponseData:
    """Response from a GitHub API request."""

    url: str
    status_code: int
    headers: dict[str, str]
    text: str

    def json(self) -> Json:
        return json.loads(self.text)


class GitHubClient:
    """GitHub API client with rate limiting, caching, and pagination."""

    def __init__(
        self,
        *,
        token_env: tuple[str, ...] = ("GITHUB_TOKEN", "GH_TOKEN"),
        auth: AuthMode = "auto",
        base_url: str = "https://api.github.com",
        user_agent: str = "IroncladSalvage/defibrillator",
        timeout_s: float = 30.0,
        max_retries: int = 6,
        backoff_base_s: float = 1.0,
        backoff_max_s: float = 60.0,
        cache_path: Path | None = DEFAULT_CACHE_PATH,
        cache_enabled: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.backoff_base_s = backoff_base_s
        self.backoff_max_s = backoff_max_s
        self.cache_path = cache_path
        self.cache_enabled = cache_enabled and cache_path is not None
        self._default_auth = auth

        self._token: str | None = None
        for env_var in token_env:
            if env_var in os.environ:
                self._token = os.environ[env_var]
                break

        if auth == "required" and not self._token:
            raise GitHubAuthError(
                f"GitHub token required but not found in environment variables: {token_env}"
            )

        self._session = requests.Session()
        self._cache: dict[str, CacheEntry] = {}
        self._load_cache()

    def _load_cache(self) -> None:
        """Load cache from disk."""
        if not self.cache_enabled or self.cache_path is None:
            return

        if not self.cache_path.exists():
            return

        try:
            with open(self.cache_path, encoding="utf-8") as f:
                raw = json.load(f)

            now = time.time()
            max_age = CACHE_MAX_AGE_DAYS * 24 * 60 * 60

            for key, entry_data in raw.items():
                entry = CacheEntry(**entry_data)
                if now - entry.saved_at_epoch < max_age:
                    self._cache[key] = entry
        except (json.JSONDecodeError, TypeError, KeyError):
            self._cache = {}

    def _save_cache(self) -> None:
        """Save cache to disk."""
        if not self.cache_enabled or self.cache_path is None:
            return

        self.cache_path.parent.mkdir(parents=True, exist_ok=True)

        data = {}
        for key, entry in self._cache.items():
            data[key] = {
                "etag": entry.etag,
                "url": entry.url,
                "status_code": entry.status_code,
                "headers": entry.headers,
                "body_text": entry.body_text,
                "saved_at_epoch": entry.saved_at_epoch,
            }

        with open(self.cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def _cache_key(self, url: str, accept: str) -> str:
        """Generate cache key from URL and Accept header."""
        return f"{url}|{accept}"

    def _build_url(self, path: str, params: dict[str, Any] | None = None) -> str:
        """Build full URL from path and parameters."""
        if path.startswith("http://") or path.startswith("https://"):
            url = path
        else:
            url = f"{self.base_url}/{path.lstrip('/')}"

        if params:
            sorted_params = sorted(params.items())
            url = f"{url}?{urlencode(sorted_params)}"

        return url

    def _should_retry(self, response: requests.Response) -> bool:
        """Check if request should be retried based on response."""
        if response.status_code == 429:
            return True

        if response.status_code >= 500:
            return True

        if response.status_code == 403:
            remaining = response.headers.get("X-RateLimit-Remaining")
            if remaining == "0":
                return True

            try:
                body = response.json()
                message = body.get("message", "").lower()
                if "rate limit" in message or "secondary rate limit" in message:
                    return True
            except (json.JSONDecodeError, AttributeError):
                pass

        return False

    def _calculate_retry_delay(
        self, response: requests.Response, attempt: int
    ) -> float:
        """Calculate delay before retry."""
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass

        reset_time = response.headers.get("X-RateLimit-Reset")
        remaining = response.headers.get("X-RateLimit-Remaining")
        if reset_time and remaining == "0":
            try:
                reset_epoch = int(reset_time)
                delay = reset_epoch - time.time() + 1
                return min(delay, 300)
            except ValueError:
                pass

        delay = min(self.backoff_max_s, self.backoff_base_s * (2**attempt))
        delay += random.uniform(0, 0.25)
        return delay

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        json_body: Json | None = None,
        data: Any | None = None,
        accept: str = "application/vnd.github+json",
        use_cache: bool = False,
        cache_key: str | None = None,
        auth: AuthMode | None = None,
        expected: tuple[int, ...] = (200,),
    ) -> ResponseData:
        """Make a request to the GitHub API."""
        url = self._build_url(path, params)
        auth_mode = auth if auth is not None else self._default_auth

        req_headers = {
            "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": self.user_agent,
        }

        if auth_mode != "none" and self._token:
            req_headers["Authorization"] = f"Bearer {self._token}"
        elif auth_mode == "required":
            raise GitHubAuthError("GitHub token required but not available")

        if headers:
            req_headers.update(headers)

        effective_cache_key = cache_key or self._cache_key(url, accept)
        cached_entry: CacheEntry | None = None

        if method.upper() == "GET" and use_cache and self.cache_enabled:
            cached_entry = self._cache.get(effective_cache_key)
            if cached_entry and cached_entry.etag:
                req_headers["If-None-Match"] = cached_entry.etag

        last_response: requests.Response | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self._session.request(
                    method,
                    url,
                    headers=req_headers,
                    json=json_body,
                    data=data,
                    timeout=self.timeout_s,
                )
                last_response = response

                if response.status_code == 304 and cached_entry:
                    return ResponseData(
                        url=url,
                        status_code=cached_entry.status_code,
                        headers=cached_entry.headers,
                        text=cached_entry.body_text,
                    )

                if response.status_code in expected:
                    if (
                        method.upper() == "GET"
                        and use_cache
                        and self.cache_enabled
                    ):
                        etag = response.headers.get("ETag", "")
                        if etag:
                            self._cache[effective_cache_key] = CacheEntry(
                                etag=etag,
                                url=url,
                                status_code=response.status_code,
                                headers=dict(response.headers),
                                body_text=response.text,
                                saved_at_epoch=time.time(),
                            )
                            self._save_cache()

                    return ResponseData(
                        url=url,
                        status_code=response.status_code,
                        headers=dict(response.headers),
                        text=response.text,
                    )

                if self._should_retry(response) and attempt < self.max_retries:
                    delay = self._calculate_retry_delay(response, attempt)
                    time.sleep(delay)
                    continue

                raise GitHubHTTPError(
                    status_code=response.status_code,
                    url=url,
                    response_text=response.text,
                    headers=dict(response.headers),
                )

            except requests.RequestException as e:
                if attempt < self.max_retries:
                    delay = self.backoff_base_s * (2**attempt) + random.uniform(
                        0, 0.25
                    )
                    time.sleep(delay)
                    continue
                raise GitHubError(f"Request failed: {e}") from e

        if last_response is not None:
            raise GitHubHTTPError(
                status_code=last_response.status_code,
                url=url,
                response_text=last_response.text,
                headers=dict(last_response.headers),
            )
        raise GitHubError(f"Request to {url} failed after {self.max_retries} retries")

    def get_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        use_cache: bool = True,
        auth: AuthMode | None = None,
        expected: tuple[int, ...] = (200,),
    ) -> Json:
        """Make a GET request and return JSON response."""
        response = self.request(
            "GET",
            path,
            params=params,
            headers=headers,
            use_cache=use_cache,
            auth=auth,
            expected=expected,
        )
        return response.json()

    def get_text(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        use_cache: bool = True,
        auth: AuthMode | None = None,
        expected: tuple[int, ...] = (200,),
    ) -> str:
        """Make a GET request and return text response."""
        response = self.request(
            "GET",
            path,
            params=params,
            headers=headers,
            use_cache=use_cache,
            auth=auth,
            expected=expected,
        )
        return response.text

    def paginate(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        item_key: str | None = None,
        per_page: int = 100,
        limit_pages: int | None = None,
        auth: AuthMode | None = None,
    ) -> Iterator[Json]:
        """Iterate over paginated results."""
        params = dict(params) if params else {}
        params["per_page"] = per_page

        url: str | None = self._build_url(path, params)
        pages_fetched = 0

        while url:
            if limit_pages is not None and pages_fetched >= limit_pages:
                break

            response = self.request(
                "GET",
                url,
                use_cache=False,
                auth=auth,
            )
            pages_fetched += 1

            data = response.json()

            if isinstance(data, list):
                yield from data
            elif isinstance(data, dict) and item_key:
                items = data.get(item_key, [])
                if isinstance(items, list):
                    yield from items

            url = self._parse_next_link(response.headers.get("Link", ""))

    def _parse_next_link(self, link_header: str) -> str | None:
        """Parse Link header to find next page URL."""
        if not link_header:
            return None

        for part in link_header.split(","):
            match = re.match(r'\s*<([^>]+)>\s*;\s*rel="next"', part.strip())
            if match:
                return match.group(1)

        return None

    def close(self) -> None:
        """Close the session and save cache."""
        self._save_cache()
        self._session.close()

    def __enter__(self) -> GitHubClient:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()
