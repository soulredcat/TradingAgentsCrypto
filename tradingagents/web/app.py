from __future__ import annotations

import asyncio
import os
import threading
from contextlib import asynccontextmanager
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.datastructures import QueryParams
from starlette.websockets import WebSocketDisconnect

from cli.message_buffer import MessageBuffer
from cli.models import AnalystType, get_analyst_label, normalize_analyst_type
from cli.profile import (
    DEFAULT_PROFILE_PATH,
    build_selections_from_profile,
    load_profile,
    normalize_profile,
    save_profile,
)
from tradingagents.services import execute_analysis_context, prepare_analysis_context
from tradingagents.storage import SQLiteRepository
from tradingagents.time_utils import current_analysis_time

WEB_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))
LOOP_SLOT_MINUTES = (0, 12, 24, 36, 48)
MAX_MONITORING_LOOPS = len(LOOP_SLOT_MINUTES)

REPORT_SECTION_TITLES = {
    "market_report": "Market Structure Analysis",
    "sentiment_report": "Volume Flow Analysis",
    "funding_oi_report": "Funding & OI Analysis",
    "news_report": "News Catalyst Analysis",
    "tokenomics_report": "Tokenomics & On-Chain Analysis",
    "investment_plan": "Research Team Verdict",
    "setup_classification": "Decision Team Setup Classification",
    "decision_plan": "Decision Team Formal Decision",
    "trade_risk_assessment": "Trade Risk Assessment",
    "portfolio_risk_assessment": "Portfolio Risk Assessment",
    "trader_investment_plan": "Execution Team Plan",
}

ANALYST_TEAM = [
    (AnalystType.MARKET.value, get_analyst_label(AnalystType.MARKET)),
    (AnalystType.VOLUME_FLOW.value, get_analyst_label(AnalystType.VOLUME_FLOW)),
    (AnalystType.FUNDING_OI.value, get_analyst_label(AnalystType.FUNDING_OI)),
    (AnalystType.NEWS.value, get_analyst_label(AnalystType.NEWS)),
    (AnalystType.TOKENOMICS.value, get_analyst_label(AnalystType.TOKENOMICS)),
]


class AnalysisJobRunner:
    def __init__(self, max_workers: int = 1):
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="tradingagents-web",
        )
        self._futures: dict[int, Future] = {}
        self._lock = threading.Lock()

    def submit(self, selections: dict[str, Any]) -> int:
        context = prepare_analysis_context(selections)
        future = self._executor.submit(self._run_context, context)
        with self._lock:
            self._futures[context.run_id] = future
        future.add_done_callback(lambda _: self._forget(context.run_id))
        return context.run_id

    def _run_context(self, context):
        return execute_analysis_context(context)

    def _forget(self, run_id: int) -> None:
        with self._lock:
            self._futures.pop(run_id, None)


class MonitoringLoopScheduler:
    def __init__(
        self,
        analysis_runner: AnalysisJobRunner,
        poll_interval_seconds: int = 5,
    ):
        self._analysis_runner = analysis_runner
        self._poll_interval_seconds = poll_interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                name="tradingagents-loop-scheduler",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            thread = self._thread
            self._thread = None
        self._stop_event.set()
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.tick()
            except Exception:
                pass
            self._stop_event.wait(self._poll_interval_seconds)

    def tick(self) -> None:
        repository = SQLiteRepository()
        now = _utc_now()
        now_iso = _isoformat(now)
        loops = repository.list_monitoring_loops(limit=100)
        slot_map = _sync_monitoring_loop_schedule(
            repository,
            loops=loops,
            now=now,
        )

        for loop in loops:
            active_run_id = loop.get("active_run_id")
            if not active_run_id:
                continue

            run = repository.get_analysis_run(int(active_run_id))
            if run is not None and run.get("status") == "running":
                continue

            run_status = str((run or {}).get("status") or "failed")
            next_run_at = _next_loop_slot_iso(
                slot_map.get(int(loop["id"])),
                now=_parse_iso_datetime(
                    (run or {}).get("completed_at") or (run or {}).get("updated_at")
                )
                or now,
            )
            error = None if run_status == "completed" else f"Run ended with status: {run_status}"
            repository.mark_monitoring_loop_run_finished(
                int(loop["id"]),
                run_status=run_status,
                next_run_at=next_run_at,
                error=error,
            )

        _sync_monitoring_loop_schedule(repository, now=now)
        due_loops = repository.get_due_monitoring_loops(
            now_iso=now_iso,
            limit=max(1, int(os.getenv("TRADINGAGENTS_WEB_MAX_WORKERS", "1"))),
        )
        for loop in due_loops:
            selections = dict(loop.get("selections") or {})
            selections["asset_symbol"] = loop["asset_symbol"]
            selections["timeframe"] = loop["timeframe"]
            selections["analysis_date"] = current_analysis_time(
                timeframe=loop["timeframe"]
            )
            run_id = self._analysis_runner.submit(
                build_selections_from_profile(selections)
            )
            repository.mark_monitoring_loop_run_started(int(loop["id"]), run_id)


def create_app() -> FastAPI:
    runner = AnalysisJobRunner(
        max_workers=max(1, int(os.getenv("TRADINGAGENTS_WEB_MAX_WORKERS", "1")))
    )
    scheduler = MonitoringLoopScheduler(analysis_runner=runner)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if str(os.getenv("TRADINGAGENTS_WEB_DISABLE_SCHEDULER", "")).lower() not in {
            "1",
            "true",
            "yes",
            "on",
        }:
            scheduler.start()
        try:
            yield
        finally:
            scheduler.stop()

    app = FastAPI(title="TradingAgents Web", version="0.1.0", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

    def render_runs_page(
        request: Request,
        *,
        error_message: str | None = None,
        status_code: int = 200,
    ):
        repository = SQLiteRepository()
        runs = repository.list_analysis_runs(limit=30)
        loops = _decorate_monitoring_loops(repository.list_monitoring_loops(limit=10))
        defaults = _load_web_defaults()
        spotlight_run = _pick_spotlight_run(runs)
        spotlight_detail = (
            _load_run_detail(int(spotlight_run["id"])) if spotlight_run is not None else None
        )
        response = templates.TemplateResponse(
            request,
            "runs.html",
            {
                "request": request,
                "runs": runs,
                "spotlight_run": spotlight_run,
                "spotlight_detail": spotlight_detail,
                "monitoring_loops": loops,
                "loop_rankings": _decorate_monitoring_rankings(
                    repository.get_monitoring_loop_rankings(limit=5),
                    loops,
                ),
                "defaults": defaults,
                "analyst_options": [
                    {"value": value, "label": label}
                    for value, label in ANALYST_TEAM
                ],
                "loop_constraints": {
                    "max_loops": MAX_MONITORING_LOOPS,
                    "slot_minutes": list(LOOP_SLOT_MINUTES),
                },
                "error_message": error_message,
            },
            status_code=status_code,
        )
        return response

    def render_loops_page(
        request: Request,
        *,
        error_message: str | None = None,
        status_code: int = 200,
    ):
        repository = SQLiteRepository()
        loops = _decorate_monitoring_loops(repository.list_monitoring_loops(limit=20))
        rankings = _decorate_monitoring_rankings(
            repository.get_monitoring_loop_rankings(limit=10),
            loops,
        )
        response = templates.TemplateResponse(
            request,
            "loops.html",
            {
                "request": request,
                "monitoring_loops": loops,
                "loop_rankings": rankings,
                "defaults": _load_web_defaults(),
                "loop_constraints": {
                    "max_loops": MAX_MONITORING_LOOPS,
                    "slot_minutes": list(LOOP_SLOT_MINUTES),
                },
                "loop_stats": {
                    "active_pairs": repository.count_monitoring_loops(status="active"),
                    "total_pairs": repository.count_monitoring_loops(),
                    "running_pairs": sum(
                        1 for loop in loops if loop.get("active_run_id") is not None
                    ),
                },
                "error_message": error_message,
            },
            status_code=status_code,
        )
        return response

    @app.get("/", include_in_schema=False)
    def root():
        repository = SQLiteRepository()
        active_run = _pick_spotlight_run(repository.list_analysis_runs(limit=20))
        if active_run is not None and active_run.get("status") == "running":
            return RedirectResponse(url=f"/runs/{active_run['id']}", status_code=302)
        return RedirectResponse(url="/runs", status_code=302)

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.get("/runs", response_class=HTMLResponse)
    def runs_page(request: Request):
        return render_runs_page(request)

    @app.get("/loops", response_class=HTMLResponse)
    def loops_page(request: Request):
        return render_loops_page(request)

    @app.post("/runs", response_class=HTMLResponse)
    async def create_run(request: Request):
        form = await _parse_request_form(request)
        selections, analysis_date_value = _build_selections_from_form(form)

        if str(form.get("save_profile") or "").lower() in {"1", "true", "on", "yes"}:
            save_profile(
                selections,
                DEFAULT_PROFILE_PATH,
                analysis_date_value=analysis_date_value,
                existing_profile=_load_web_defaults(),
            )

        run_id = runner.submit(selections)
        return RedirectResponse(url=f"/runs/{run_id}", status_code=303)

    @app.post("/loops", response_class=HTMLResponse)
    async def create_loop(request: Request):
        form = await _parse_request_form(request)
        asset_symbol = str(form.get("asset_symbol") or "BTC-PERP").strip().upper()
        timeframe = str(form.get("timeframe") or "1h").strip()

        repository = SQLiteRepository()
        if repository.count_monitoring_loops(status="active") >= MAX_MONITORING_LOOPS:
            return render_loops_page(
                request,
                error_message=f"Active monitoring loops are capped at {MAX_MONITORING_LOOPS} pairs.",
                status_code=400,
            )

        for existing_loop in repository.list_monitoring_loops(limit=100):
            if (
                existing_loop["asset_symbol"] == asset_symbol
                and existing_loop["timeframe"] == timeframe
            ):
                return render_loops_page(
                    request,
                    error_message=f"{asset_symbol} {timeframe} already has a monitoring loop.",
                    status_code=400,
                )

        defaults = _load_web_defaults()
        loop_payload = dict(defaults)
        loop_payload["asset_symbol"] = asset_symbol
        loop_payload["timeframe"] = timeframe
        loop_payload["analysis_date"] = "now"
        selections = build_selections_from_profile(loop_payload)
        repository.create_monitoring_loop(
            asset_symbol=asset_symbol,
            timeframe=timeframe,
            interval_minutes=60,
            selections=selections,
            next_run_at=None,
        )
        _sync_monitoring_loop_schedule(repository, now=_utc_now())
        return RedirectResponse(url="/loops", status_code=303)

    @app.post("/loops/{loop_id}/pause")
    def pause_loop(loop_id: int):
        repository = SQLiteRepository()
        if repository.get_monitoring_loop(loop_id) is None:
            raise HTTPException(status_code=404, detail="Loop not found")
        repository.update_monitoring_loop_status(loop_id, "paused")
        _sync_monitoring_loop_schedule(repository, now=_utc_now())
        return RedirectResponse(url="/loops", status_code=303)

    @app.post("/loops/{loop_id}/resume")
    def resume_loop(loop_id: int):
        repository = SQLiteRepository()
        loop = repository.get_monitoring_loop(loop_id)
        if loop is None:
            raise HTTPException(status_code=404, detail="Loop not found")
        if repository.count_monitoring_loops(status="active") >= MAX_MONITORING_LOOPS:
            raise HTTPException(
                status_code=400,
                detail=f"Active monitoring loops are capped at {MAX_MONITORING_LOOPS}.",
            )
        repository.update_monitoring_loop_status(loop_id, "active")
        _sync_monitoring_loop_schedule(repository, now=_utc_now())
        return RedirectResponse(url="/loops", status_code=303)

    @app.get("/runs/{run_id}", response_class=HTMLResponse)
    def run_detail_page(request: Request, run_id: int):
        detail = _load_run_detail(run_id)
        return templates.TemplateResponse(
            request,
            "run_detail.html",
            {
                "request": request,
                **detail,
            },
        )

    @app.get("/api/runs/{run_id}")
    def run_detail_api(run_id: int):
        detail = _load_run_detail(run_id)
        run = detail["run"]
        return JSONResponse(
            {
                "run": run,
                "teams": detail["teams"],
                "messages": detail["messages"],
                "tool_calls": detail["tool_calls"],
                "report_sections": detail["report_sections"],
                "complete_report": detail["complete_report"],
                "full_state_log": detail["full_state_log"],
            }
        )

    @app.websocket("/ws/runs/{run_id}")
    async def run_live_socket(websocket: WebSocket, run_id: int):
        await websocket.accept()
        previous_payload = None
        try:
            while True:
                detail = _load_run_detail(run_id)
                payload = _build_live_run_payload(detail)
                if payload != previous_payload:
                    await websocket.send_json(payload)
                    previous_payload = payload
                if not payload["is_running"]:
                    break
                await asyncio.sleep(2)
        except HTTPException:
            await websocket.send_json({"error": "Run not found", "run_id": run_id})
        except WebSocketDisconnect:
            return
        finally:
            await websocket.close()

    return app


app = create_app()


def main():
    import uvicorn

    uvicorn.run(
        "tradingagents.web.app:app",
        host=os.getenv("TRADINGAGENTS_WEB_HOST", "127.0.0.1"),
        port=int(os.getenv("TRADINGAGENTS_WEB_PORT", "8000")),
        reload=False,
    )


def _load_web_defaults() -> dict[str, Any]:
    return normalize_profile(load_profile(DEFAULT_PROFILE_PATH))


async def _parse_request_form(request: Request) -> QueryParams:
    body = (await request.body()).decode("utf-8")
    parsed = parse_qs(body, keep_blank_values=True)
    flattened: list[tuple[str, str]] = []
    for key, values in parsed.items():
        if not values:
            flattened.append((key, ""))
            continue
        for value in values:
            flattened.append((key, value))
    return QueryParams(flattened)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _build_monitoring_loop_slot_map(
    loops: list[dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    active_loops = sorted(
        (loop for loop in loops if loop.get("status") == "active"),
        key=lambda loop: int(loop["id"]),
    )
    slot_map: dict[int, dict[str, Any]] = {}
    for index, loop in enumerate(active_loops):
        if index >= len(LOOP_SLOT_MINUTES):
            break
        slot_map[int(loop["id"])] = {
            "slot_number": index + 1,
            "slot_minute": LOOP_SLOT_MINUTES[index],
        }
    return slot_map


def _next_slot_time(*, now: datetime, slot_minute: int) -> datetime:
    normalized_now = now.astimezone(timezone.utc)
    candidate = normalized_now.replace(
        minute=slot_minute,
        second=0,
        microsecond=0,
    )
    if candidate <= normalized_now:
        candidate += timedelta(hours=1)
    return candidate


def _next_loop_slot_iso(slot_info: dict[str, Any] | None, *, now: datetime) -> str | None:
    if slot_info is None:
        return None
    return _isoformat(
        _next_slot_time(now=now, slot_minute=int(slot_info["slot_minute"]))
    )


def _sync_monitoring_loop_schedule(
    repository: SQLiteRepository,
    *,
    loops: list[dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> dict[int, dict[str, Any]]:
    monitoring_loops = loops or repository.list_monitoring_loops(limit=100)
    slot_map = _build_monitoring_loop_slot_map(monitoring_loops)
    normalized_now = now or _utc_now()
    for loop in monitoring_loops:
        loop_id = int(loop["id"])
        desired_next_run_at = _next_loop_slot_iso(
            slot_map.get(loop_id),
            now=normalized_now,
        )
        if loop.get("status") != "active":
            desired_next_run_at = None
        if loop.get("next_run_at") != desired_next_run_at:
            repository.set_monitoring_loop_next_run(loop_id, desired_next_run_at)
    return slot_map


def _decorate_monitoring_loops(
    loops: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    slot_map = _build_monitoring_loop_slot_map(loops)
    decorated = []
    for loop in loops:
        item = dict(loop)
        slot = slot_map.get(int(loop["id"]))
        item["slot_number"] = slot["slot_number"] if slot else None
        item["slot_minute"] = slot["slot_minute"] if slot else None
        item["slot_label"] = f"{slot['slot_minute']:02d}" if slot else "—"
        decorated.append(item)
    return sorted(
        decorated,
        key=lambda item: (
            item["slot_number"] is None,
            item["slot_number"] or 999,
            int(item["id"]),
        ),
    )


def _decorate_monitoring_rankings(
    rankings: list[dict[str, Any]],
    loops: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    slots_by_loop_id = {
        int(loop["id"]): {
            "slot_number": loop.get("slot_number"),
            "slot_minute": loop.get("slot_minute"),
            "slot_label": loop.get("slot_label"),
        }
        for loop in loops
    }
    decorated = []
    for ranking in rankings:
        item = dict(ranking)
        slot = slots_by_loop_id.get(int(ranking["loop_id"]), {})
        item["slot_number"] = slot.get("slot_number")
        item["slot_minute"] = slot.get("slot_minute")
        item["slot_label"] = slot.get("slot_label") or "—"
        decorated.append(item)
    sorted_rankings = sorted(
        decorated,
        key=lambda item: (
            item["slot_number"] is None,
            item["slot_number"] or 999,
            int(item["loop_id"]),
        ),
    )
    for index, ranking in enumerate(sorted_rankings, start=1):
        ranking["rank"] = index
    return sorted_rankings


def _build_selections_from_form(form) -> tuple[dict[str, Any], str]:
    analysts = form.getlist("analysts")
    research_depth_raw = str(form.get("research_depth") or "1").strip()
    try:
        research_depth = int(research_depth_raw)
    except ValueError:
        research_depth = 1

    analysis_date_value = str(form.get("analysis_date") or "now").strip() or "now"
    payload = {
        "asset_symbol": str(form.get("asset_symbol") or "BTC-PERP").strip().upper(),
        "timeframe": str(form.get("timeframe") or "1h").strip(),
        "analysis_date": analysis_date_value,
        "output_language": str(form.get("output_language") or "English").strip()
        or "English",
        "analysts": analysts,
        "research_depth": research_depth,
        "llm_provider": str(form.get("llm_provider") or "codex_exec").strip().lower()
        or "codex_exec",
        "backend_url": str(form.get("backend_url") or "").strip() or None,
        "shallow_thinker": str(form.get("shallow_thinker") or "gpt-5.4-mini").strip()
        or "gpt-5.4-mini",
        "deep_thinker": str(form.get("deep_thinker") or "gpt-5.4").strip()
        or "gpt-5.4",
        "google_thinking_level": str(form.get("google_thinking_level") or "").strip()
        or None,
        "openai_reasoning_effort": str(
            form.get("openai_reasoning_effort") or ""
        ).strip()
        or None,
        "anthropic_effort": str(form.get("anthropic_effort") or "").strip() or None,
    }
    return build_selections_from_profile(payload), analysis_date_value


def _load_run_detail(run_id: int) -> dict[str, Any]:
    repository = SQLiteRepository()
    run = repository.get_analysis_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    messages = [dict(row) for row in repository.get_run_messages(run_id)][-120:]
    messages.reverse()

    tool_calls = []
    for row in repository.get_run_tool_calls(run_id)[-80:]:
        tool_calls.append(
            {
                "display_time": row["display_time"],
                "tool_name": row["tool_name"],
                "tool_args_json": row["tool_args_json"],
            }
        )
    tool_calls.reverse()

    report_sections = _ordered_report_sections(
        run.get("report_sections") or repository.get_report_sections(run_id)
    )

    complete_report = repository.get_complete_report(run_id)
    full_state_log = repository.get_full_state_log(run_id)

    return {
        "run": run,
        "teams": _build_team_views(
            selected_analysts=run.get("selected_analysts") or _load_web_defaults()["analysts"],
            agent_status=run.get("agent_status") or {},
        ),
        "messages": messages,
        "tool_calls": tool_calls,
        "report_sections": report_sections,
        "complete_report": complete_report,
        "full_state_log": full_state_log,
        "is_running": run["status"] == "running",
    }


def _build_team_views(
    *,
    selected_analysts: list[str],
    agent_status: dict[str, str],
) -> list[dict[str, Any]]:
    selected_values = []
    for analyst in selected_analysts:
        try:
            selected_values.append(normalize_analyst_type(analyst).value)
        except ValueError:
            selected_values.append(str(analyst).strip().lower())

    analyst_agents = [
        label for value, label in ANALYST_TEAM if value in set(selected_values)
    ]
    teams = []

    if analyst_agents:
        teams.append(
            {
                "name": "Analyst Team",
                "agents": [
                    {"name": agent, "status": agent_status.get(agent, "pending")}
                    for agent in analyst_agents
                ],
            }
        )

    for team_name, agents in MessageBuffer.FIXED_AGENTS.items():
        teams.append(
            {
                "name": team_name,
                "agents": [
                    {"name": agent, "status": agent_status.get(agent, "pending")}
                    for agent in agents
                ],
            }
        )

    return teams


def _ordered_report_sections(sections: dict[str, str]) -> list[dict[str, str]]:
    ordered = []
    for key in MessageBuffer.REPORT_SECTIONS:
        content = sections.get(key)
        if not content:
            continue
        ordered.append(
            {
                "key": key,
                "title": REPORT_SECTION_TITLES.get(key, key.replace("_", " ").title()),
                "content": content,
            }
        )
    return ordered


def _pick_spotlight_run(runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not runs:
        return None
    for run in runs:
        if run.get("status") == "running":
            return run
    return runs[0]


def _build_live_run_payload(detail: dict[str, Any]) -> dict[str, Any]:
    run = detail["run"]
    return {
        "run": {
            "id": run["id"],
            "asset_symbol": run["asset_symbol"],
            "timeframe": run["timeframe"],
            "analysis_time": run["analysis_time"],
            "status": run["status"],
            "current_agent": run.get("current_agent"),
        },
        "is_running": detail["is_running"],
        "report_text": detail["complete_report"] or run.get("current_report") or "No report yet.",
        "messages": [
            {
                "display_time": item.get("display_time") or "—",
                "message_type": item.get("message_type") or "",
                "content": item.get("content") or "",
            }
            for item in detail["messages"][:12]
        ],
    }
