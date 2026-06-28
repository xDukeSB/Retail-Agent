from fastapi import APIRouter

from app.api.v1.endpoints import auth, health, users, cameras, websocket, analytics, timeline, reports, cloud
from app.services.detection_pipeline import detection_router
from app.services.tracking_pipeline import tracking_router
from app.services.event_service import event_router

router = APIRouter(prefix="/v1")

router.include_router(health.router)
router.include_router(auth.router)
router.include_router(users.router)
router.include_router(cameras.router)
router.include_router(tracking_router)
router.include_router(event_router)
router.include_router(analytics.router)
router.include_router(timeline.router)
router.include_router(reports.router)
router.include_router(cloud.router)
router.include_router(websocket.router)
