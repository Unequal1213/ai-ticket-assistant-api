from typing import Annotated

from fastapi import Depends, Request

from app.services.ticket_analysis_service import TicketAnalysisService


def get_ticket_analysis_service(request: Request) -> TicketAnalysisService:
    service = getattr(request.app.state, "ticket_analysis_service", None)
    if service is None:
        raise RuntimeError("Ticket analysis service is not initialized")
    return service


TicketAnalysisServiceDependency = Annotated[
    TicketAnalysisService,
    Depends(get_ticket_analysis_service),
]
