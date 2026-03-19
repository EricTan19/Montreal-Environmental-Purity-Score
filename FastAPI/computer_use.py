from __future__ import annotations

import base64
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import HTTPException
from openai import OpenAI
from pydantic import BaseModel, Field

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - dependency availability varies by environment
    PlaywrightError = RuntimeError
    PlaywrightTimeoutError = RuntimeError
    sync_playwright = None


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
SCREENSHOT_ROOT = STATIC_DIR / "computer-use"
SCREENSHOT_ROOT.mkdir(parents=True, exist_ok=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _model_dump(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=True)
    if isinstance(value, list):
        return [_model_dump(item) for item in value]
    if isinstance(value, tuple):
        return [_model_dump(item) for item in value]
    if isinstance(value, dict):
        return {key: _model_dump(item) for key, item in value.items()}
    return value


def _normalize_key(key: str) -> str:
    key_map = {
        "CTRL": "Control",
        "CONTROL": "Control",
        "CMD": "Meta",
        "COMMAND": "Meta",
        "OPTION": "Alt",
        "ESC": "Escape",
        "DEL": "Delete",
        "PGUP": "PageUp",
        "PGDN": "PageDown",
    }
    upper_key = key.upper()
    return key_map.get(upper_key, key.title() if len(key) > 1 else key)


def _hostname(url: str | None) -> str | None:
    if not url:
        return None
    try:
        return urlparse(url).hostname
    except ValueError:
        return None


class ComputerUseStartRequest(BaseModel):
    task: str = Field(min_length=10, max_length=4000)
    url: str = Field(default="http://127.0.0.1:3000", min_length=1, max_length=1024)
    model: str = "computer-use-preview"
    display_width: int = Field(default=1280, ge=640, le=2560)
    display_height: int = Field(default=900, ge=480, le=1600)
    environment: str = "browser"
    max_steps_per_run: int = Field(default=8, ge=1, le=25)
    headless: bool = True
    allowed_hosts: list[str] = Field(default_factory=list)


class ComputerUseApprovalRequest(BaseModel):
    approved: bool


class ComputerUseSessionResponse(BaseModel):
    id: str
    task: str
    target_url: str
    model: str
    status: str
    current_url: str | None = None
    screenshot_url: str | None = None
    latest_output_text: str | None = None
    last_action: dict[str, Any] | None = None
    pending_safety_checks: list[dict[str, Any]] = Field(default_factory=list)
    steps_executed: int = 0
    allowed_hosts: list[str] = Field(default_factory=list)
    last_error: str | None = None
    created_at: str
    updated_at: str
    event_log: list[dict[str, str]] = Field(default_factory=list)


@dataclass
class BrowserSnapshot:
    data_url: str
    screenshot_url: str
    current_url: str
    title: str


class BrowserHarness:
    def __init__(
        self,
        *,
        session_id: str,
        width: int,
        height: int,
        headless: bool,
        allowed_hosts: list[str],
    ) -> None:
        self.session_id = session_id
        self.width = width
        self.height = height
        self.headless = headless
        self.allowed_hosts = {host for host in allowed_hosts if host}
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._screenshot_index = 0
        self._session_dir = SCREENSHOT_ROOT / session_id
        self._session_dir.mkdir(parents=True, exist_ok=True)

    @property
    def page(self):
        if self._page is None:
            raise RuntimeError("The browser page has not been started.")
        return self._page

    def start(self, url: str) -> None:
        if sync_playwright is None:
            raise RuntimeError(
                "Playwright is not installed. Install it with `pip install playwright` "
                "and then run `python -m playwright install chromium`."
            )

        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=self.headless)
            self._context = self._browser.new_context(
                viewport={"width": self.width, "height": self.height},
            )
            self._page = self._context.new_page()
            self._page.goto(url, wait_until="domcontentloaded", timeout=15000)
            self._page.wait_for_timeout(1000)
            self._assert_allowed_url()
        except PlaywrightTimeoutError as exc:
            self.close()
            raise RuntimeError(
                f"Timed out opening {url}. Make sure the frontend is running and reachable."
            ) from exc
        except PlaywrightError as exc:
            self.close()
            raise RuntimeError(str(exc)) from exc

    def close(self) -> None:
        for resource in (self._context, self._browser, self._playwright):
            try:
                if resource is not None:
                    resource.close() if hasattr(resource, "close") else resource.stop()
            except Exception:
                pass
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None

    def execute(self, action: dict[str, Any]) -> BrowserSnapshot:
        action_type = action.get("type")

        if action_type == "click":
            self.page.mouse.click(
                action["x"],
                action["y"],
                button=action.get("button", "left"),
            )
            self._settle()
        elif action_type == "double_click":
            self.page.mouse.dblclick(action["x"], action["y"])
            self._settle()
        elif action_type == "drag":
            path = action.get("path", [])
            if not path:
                raise RuntimeError("The computer call returned a drag action without a path.")
            start = path[0]
            self.page.mouse.move(start["x"], start["y"])
            self.page.mouse.down()
            for point in path[1:]:
                self.page.mouse.move(point["x"], point["y"])
                self.page.wait_for_timeout(60)
            self.page.mouse.up()
            self._settle()
        elif action_type == "keypress":
            keys = action.get("keys", [])
            if not keys:
                raise RuntimeError("The computer call returned an empty keypress action.")
            combo = "+".join(_normalize_key(key) for key in keys)
            self.page.keyboard.press(combo)
            self._settle()
        elif action_type == "move":
            self.page.mouse.move(action["x"], action["y"])
            self.page.wait_for_timeout(150)
        elif action_type == "scroll":
            self.page.mouse.move(action["x"], action["y"])
            self.page.mouse.wheel(action.get("scroll_x", 0), action.get("scroll_y", 0))
            self._settle(wait_ms=450)
        elif action_type == "type":
            self.page.keyboard.type(action.get("text", ""), delay=18)
            self._settle()
        elif action_type == "wait":
            self.page.wait_for_timeout(1000)
        elif action_type == "screenshot":
            pass
        else:
            raise RuntimeError(f"Unsupported computer action: {action_type}")

        self._assert_allowed_url()
        return self.take_snapshot(prefix=action_type or "step")

    def take_snapshot(self, *, prefix: str) -> BrowserSnapshot:
        self._assert_allowed_url()
        screenshot_name = f"{self._screenshot_index:03d}-{prefix}.png"
        screenshot_path = self._session_dir / screenshot_name
        self.page.screenshot(path=str(screenshot_path))
        self._screenshot_index += 1

        data_url = "data:image/png;base64," + base64.b64encode(
            screenshot_path.read_bytes()
        ).decode("ascii")
        relative_url = (
            "/static/" + screenshot_path.relative_to(STATIC_DIR).as_posix()
        )
        title = ""
        try:
            title = self.page.title()
        except Exception:
            title = ""

        return BrowserSnapshot(
            data_url=data_url,
            screenshot_url=relative_url,
            current_url=self.page.url,
            title=title,
        )

    def _settle(self, *, wait_ms: int = 800) -> None:
        try:
            self.page.wait_for_load_state("networkidle", timeout=3000)
        except Exception:
            self.page.wait_for_timeout(wait_ms)

    def _assert_allowed_url(self) -> None:
        current_host = _hostname(getattr(self.page, "url", ""))
        if not current_host or not self.allowed_hosts:
            return
        if current_host not in self.allowed_hosts:
            raise RuntimeError(
                "The browser moved to a host outside the allow-list: "
                f"{current_host}. Allowed hosts: {', '.join(sorted(self.allowed_hosts))}."
            )


@dataclass
class ComputerUseSession:
    id: str
    task: str
    target_url: str
    model: str
    display_width: int
    display_height: int
    environment: str
    max_steps_per_run: int
    headless: bool
    allowed_hosts: list[str]
    browser: BrowserHarness
    status: str = "created"
    current_url: str | None = None
    screenshot_url: str | None = None
    latest_output_text: str | None = None
    last_action: dict[str, Any] | None = None
    pending_safety_checks: list[dict[str, Any]] = field(default_factory=list)
    pending_call: dict[str, Any] | None = None
    previous_response_id: str | None = None
    steps_executed: int = 0
    last_error: str | None = None
    event_log: list[dict[str, str]] = field(default_factory=list)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def log(self, kind: str, message: str) -> None:
        self.updated_at = _now_iso()
        self.event_log.append(
            {
                "timestamp": self.updated_at,
                "kind": kind,
                "message": message,
            }
        )
        self.event_log = self.event_log[-20:]


class ComputerUseManager:
    def __init__(self) -> None:
        self._sessions: dict[str, ComputerUseSession] = {}
        self._lock = RLock()

    def create_session(self, request: ComputerUseStartRequest) -> ComputerUseSessionResponse:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="OPENAI_API_KEY is not set in the backend environment.",
            )

        requested_host = _hostname(request.url)
        allowed_hosts = {host.strip() for host in request.allowed_hosts if host.strip()}
        if requested_host:
            allowed_hosts.add(requested_host)
        allowed_hosts.update({"localhost", "127.0.0.1"})

        session_id = str(uuid4())
        browser = BrowserHarness(
            session_id=session_id,
            width=request.display_width,
            height=request.display_height,
            headless=request.headless,
            allowed_hosts=sorted(allowed_hosts),
        )

        try:
            browser.start(request.url)
            initial_snapshot = browser.take_snapshot(prefix="bootstrap")
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        session = ComputerUseSession(
            id=session_id,
            task=request.task,
            target_url=request.url,
            model=request.model,
            display_width=request.display_width,
            display_height=request.display_height,
            environment=request.environment,
            max_steps_per_run=request.max_steps_per_run,
            headless=request.headless,
            allowed_hosts=sorted(allowed_hosts),
            browser=browser,
            current_url=initial_snapshot.current_url,
            screenshot_url=initial_snapshot.screenshot_url,
        )
        session.log("browser", f"Opened {request.url}")

        with self._lock:
            self._sessions[session_id] = session

        return self._run_session(session)

    def get_session(self, session_id: str) -> ComputerUseSessionResponse:
        return self._to_response(self._get(session_id))

    def continue_session(self, session_id: str) -> ComputerUseSessionResponse:
        session = self._get(session_id)
        if session.status == "awaiting_approval":
            raise HTTPException(
                status_code=409,
                detail="This session is waiting for approval. Approve or deny the safety check first.",
            )
        if session.status in {"completed", "denied", "error"}:
            return self._to_response(session)
        return self._run_session(session)

    def resolve_approval(
        self, session_id: str, request: ComputerUseApprovalRequest
    ) -> ComputerUseSessionResponse:
        session = self._get(session_id)
        if session.status != "awaiting_approval" or session.pending_call is None:
            raise HTTPException(status_code=409, detail="This session is not awaiting approval.")

        if not request.approved:
            session.status = "denied"
            session.log("approval", "User denied the pending safety checks.")
            session.browser.close()
            return self._to_response(session)

        input_items = [
            self._execute_pending_call(
                session,
                acknowledged_safety_checks=session.pending_safety_checks,
            )
        ]
        return self._run_session(session, input_items=input_items)

    def _run_session(
        self,
        session: ComputerUseSession,
        *,
        input_items: list[dict[str, Any]] | None = None,
    ) -> ComputerUseSessionResponse:
        client = OpenAI()
        session.status = "running"
        session.last_error = None

        try:
            for _ in range(session.max_steps_per_run):
                request_kwargs: dict[str, Any] = {
                    "model": session.model,
                    "tools": [
                        {
                            "type": "computer_use_preview",
                            "display_width": session.display_width,
                            "display_height": session.display_height,
                            "environment": session.environment,
                        }
                    ],
                    "input": input_items if input_items is not None else session.task,
                    "truncation": "auto",
                }
                if session.previous_response_id:
                    request_kwargs["previous_response_id"] = session.previous_response_id

                response = client.responses.create(
                    **request_kwargs,
                )

                session.previous_response_id = response.id
                session.latest_output_text = (response.output_text or "").strip() or None
                if session.latest_output_text:
                    session.log("assistant", session.latest_output_text)

                computer_call = self._first_computer_call(response)
                if computer_call is None:
                    session.status = "completed"
                    session.log("status", "The model finished without requesting another browser action.")
                    session.browser.close()
                    return self._to_response(session)

                session.pending_call = _model_dump(computer_call)
                session.last_action = _model_dump(getattr(computer_call, "action", None))
                session.pending_safety_checks = _model_dump(
                    getattr(computer_call, "pending_safety_checks", [])
                ) or []

                if session.pending_safety_checks:
                    session.status = "awaiting_approval"
                    session.log("approval", "The model requested approval before the next browser action.")
                    return self._to_response(session)

                input_items = [self._execute_pending_call(session, acknowledged_safety_checks=[])]

            session.status = "paused"
            session.log(
                "status",
                "The per-run step budget was reached. Continue the session to let the model keep working.",
            )
            return self._to_response(session)

        except HTTPException:
            raise
        except Exception as exc:
            session.status = "error"
            session.last_error = str(exc)
            session.log("error", session.last_error)
            session.browser.close()
            return self._to_response(session)

    def _execute_pending_call(
        self,
        session: ComputerUseSession,
        *,
        acknowledged_safety_checks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if session.pending_call is None:
            raise HTTPException(status_code=409, detail="There is no pending computer call to execute.")

        call_id = session.pending_call.get("call_id")
        action = session.pending_call.get("action")
        if not isinstance(action, dict):
            raise RuntimeError("The computer call did not include an executable action.")
        if not call_id:
            raise RuntimeError("The computer call did not include a call ID.")

        snapshot = session.browser.execute(action)
        session.pending_call = None
        session.pending_safety_checks = []
        session.last_action = action
        session.steps_executed += 1
        session.current_url = snapshot.current_url
        session.screenshot_url = snapshot.screenshot_url
        session.log("action", f"Executed {action.get('type', 'unknown')} on {snapshot.current_url}")

        output_item: dict[str, Any] = {
            "type": "computer_call_output",
            "call_id": call_id,
            "output": {
                "type": "computer_screenshot",
                "image_url": snapshot.data_url,
            },
        }

        if acknowledged_safety_checks:
            output_item["acknowledged_safety_checks"] = [
                {
                    "id": item["id"],
                    "code": item.get("code"),
                    "message": item.get("message"),
                }
                for item in acknowledged_safety_checks
                if item.get("id")
            ]

        return output_item

    def _first_computer_call(self, response: Any) -> Any | None:
        for item in getattr(response, "output", []):
            if getattr(item, "type", None) == "computer_call":
                return item
        return None

    def _get(self, session_id: str) -> ComputerUseSession:
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Computer Use session not found.")
        return session

    def _to_response(self, session: ComputerUseSession) -> ComputerUseSessionResponse:
        return ComputerUseSessionResponse(
            id=session.id,
            task=session.task,
            target_url=session.target_url,
            model=session.model,
            status=session.status,
            current_url=session.current_url,
            screenshot_url=session.screenshot_url,
            latest_output_text=session.latest_output_text,
            last_action=session.last_action,
            pending_safety_checks=session.pending_safety_checks,
            steps_executed=session.steps_executed,
            allowed_hosts=session.allowed_hosts,
            last_error=session.last_error,
            created_at=session.created_at,
            updated_at=session.updated_at,
            event_log=session.event_log,
        )


computer_use_manager = ComputerUseManager()
