"""
cloud.py — API endpoints for the Mock Cloud Dashboard.
"""
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.deps import get_current_active_user
from app.models.user import User
from app.services.cloud_service import cloud_service

router = APIRouter(prefix="/cloud", tags=["cloud"])

@router.get("/dashboard")
async def get_cloud_dashboard(
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """Retrieve multi-store aggregated cloud metrics."""
    data = await cloud_service.get_dashboard_data()
    return JSONResponse(content=data)
