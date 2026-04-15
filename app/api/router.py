from fastapi import APIRouter

from app.api.routes.admin import router as admin_router
from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.api.routes.leaderboard import router as leaderboard_router
from app.api.routes.leetcode import router as leetcode_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(leetcode_router)
api_router.include_router(admin_router)
api_router.include_router(leaderboard_router)
