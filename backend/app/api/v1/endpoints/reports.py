"""
reports.py — Reporting Engine API endpoints.
"""
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import JSONResponse

from app.core.deps import get_current_active_user
from app.models.user import User
from app.services.reporting_service import reporting_service

router = APIRouter(prefix="/reports", tags=["reports"])

@router.get("/data")
async def get_report_data(
    timeframe: str = Query("daily", regex="^(daily|weekly|monthly)$"),
    days_back: int = Query(30, ge=1, le=365),
    camera_id: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """Get the JSON report data for UI."""
    data = await reporting_service.generate_report_data(timeframe, days_back, camera_id)
    return JSONResponse(content=data)

@router.get("/export/csv")
async def export_csv(
    timeframe: str = Query("daily", regex="^(daily|weekly|monthly)$"),
    days_back: int = Query(30, ge=1, le=365),
    camera_id: Optional[str] = None,
) -> Response:
    """Export report as CSV."""
    # Note: no auth dependancy required for file downloads usually or passed via token query param
    data = await reporting_service.generate_report_data(timeframe, days_back, camera_id)
    csv_str = reporting_service.export_csv(data)
    
    headers = {
        "Content-Disposition": f"attachment; filename=report_{timeframe}.csv"
    }
    return Response(content=csv_str, media_type="text/csv", headers=headers)

@router.get("/export/excel")
async def export_excel(
    timeframe: str = Query("daily", regex="^(daily|weekly|monthly)$"),
    days_back: int = Query(30, ge=1, le=365),
    camera_id: Optional[str] = None,
) -> Response:
    """Export report as Excel (.xlsx)."""
    data = await reporting_service.generate_report_data(timeframe, days_back, camera_id)
    excel_bytes = reporting_service.export_excel(data)
    
    headers = {
        "Content-Disposition": f"attachment; filename=report_{timeframe}.xlsx"
    }
    return Response(content=excel_bytes, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers=headers)

@router.get("/export/pdf")
async def export_pdf(
    timeframe: str = Query("daily", regex="^(daily|weekly|monthly)$"),
    days_back: int = Query(30, ge=1, le=365),
    camera_id: Optional[str] = None,
) -> Response:
    """Export report as PDF."""
    data = await reporting_service.generate_report_data(timeframe, days_back, camera_id)
    pdf_bytes = reporting_service.export_pdf(data)
    
    headers = {
        "Content-Disposition": f"attachment; filename=report_{timeframe}.pdf"
    }
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)
