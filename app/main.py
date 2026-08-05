from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.ai.exceptions import TicketAnalysisError
from app.ai.factory import create_ticket_analysis_service
from app.api.routes import router as api_router
from app.config import AISettings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = AISettings.from_env()
    service = create_ticket_analysis_service(settings)
    app.state.ai_settings = settings
    app.state.ticket_analysis_service = service
    try:
        yield
    finally:
        await service.close()


def create_app() -> FastAPI:
    app = FastAPI(title="AI Ticket Assistant API", lifespan=lifespan)
    app.include_router(api_router)

    @app.exception_handler(TicketAnalysisError)
    async def ticket_analysis_error_handler(
        request: Request,
        exc: TicketAnalysisError,
    ) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=exc.http_status,
            content={
                "error": {
                    "code": exc.category,
                    "message": exc.public_message,
                    "request_id": exc.request_id,
                }
            },
        )

    return app


app = create_app()
