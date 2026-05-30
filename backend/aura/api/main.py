"""FastAPI application factory + dependency wiring.

D1: only `mode=mock` is wired. D2 adds an Azure factory that injects
real Foundry-backed clients.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from aura.agents import Orchestrator, Referee, default_council
from aura.observability import bind_trace_id, configure_logging, get_logger, new_trace_id
from aura.safety import InjectionBlocked, guard, redact
from aura.schemas import DebateRequest, DecisionDossier, StreamEvent

_log = get_logger(__name__)
_FRONTEND_DIR = Path(__file__).resolve().parents[3] / "frontend"


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    _log.info("aura.api.start", version="0.1.0")
    yield
    _log.info("aura.api.stop")


def create_app() -> FastAPI:
    app = FastAPI(
        title="AURA",
        version="0.1.0",
        description="Adversarial Unified Reasoning Arena — Liga dos Agentes 2026",
        lifespan=_lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # hackathon demo — qualquer origem pode chamar a API
        allow_methods=["POST", "GET", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def _security_headers(request: Request, call_next: object) -> Response:
        response = await call_next(request)  # type: ignore[operator]
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        return response

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    # Serve the War Room (zero-build static frontend) at "/".
    if _FRONTEND_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=_FRONTEND_DIR), name="static")

        @app.get("/", include_in_schema=False)
        async def root() -> FileResponse:
            return FileResponse(_FRONTEND_DIR / "index.html")

    @app.post("/debates")
    async def start_debate(req: DebateRequest) -> EventSourceResponse:
        trace_id = new_trace_id()

        try:
            guarded_q = guard(req.question)
            guarded_ctx = guard(req.context) if req.context else None
        except InjectionBlocked as exc:
            _log.warning("aura.api.injection_blocked", reason=exc.verdict.reason)
            raise HTTPException(
                status_code=400,
                detail={"error": "prompt_injection_blocked", "reason": exc.verdict.reason},
            ) from None

        try:
            orchestrator = _build_orchestrator(
                mode=req.mode, max_rounds=req.max_rounds, gh_model=req.gh_model,
            )
        except RuntimeError as exc:
            raise HTTPException(
                status_code=503,
                detail={"error": "backend_unavailable", "reason": str(exc)},
            ) from None

        async def event_source() -> AsyncIterator[dict[str, str]]:
            bind_trace_id(trace_id)
            safe_question = redact(guarded_q)
            safe_context = redact(guarded_ctx) if guarded_ctx else None
            _log.info("aura.debate.start", trace=trace_id, max_rounds=req.max_rounds)
            async for item in orchestrator.run(question=safe_question, context=safe_context):
                if isinstance(item, StreamEvent):
                    yield {"event": item.kind.value, "data": item.model_dump_json()}
                elif isinstance(item, DecisionDossier):
                    _log.info(
                        "aura.debate.dossier",
                        trace=trace_id,
                        confidence=item.confidence,
                        debate_id=str(item.debate_id),
                    )
                    yield {"event": "dossier", "data": item.model_dump_json()}

        return EventSourceResponse(event_source())

    return app


def _build_orchestrator(*, mode: str, max_rounds: int, gh_model: str | None = None) -> Orchestrator:
    from aura.factory import build_knowledge, build_llm

    llm = build_llm(mode, gh_model=gh_model)  # type: ignore[arg-type]
    knowledge = build_knowledge(mode)  # type: ignore[arg-type]
    agents = default_council(llm=llm, knowledge=knowledge)
    referee = Referee()
    return Orchestrator(agents=agents, referee=referee, max_rounds=max_rounds)


app = create_app()
