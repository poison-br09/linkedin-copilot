from fastapi import APIRouter

from api.v1 import auth, admin, linkedin, config_routes, status

router = APIRouter(prefix="/api/v1")

router.include_router(auth.router,          prefix="/auth",     tags=["Authentication"])
router.include_router(admin.router,         prefix="/admin",    tags=["Admin"])
router.include_router(linkedin.router,      prefix="/linkedin", tags=["LinkedIn"])
router.include_router(config_routes.router, prefix="/config",   tags=["Configuration"])
router.include_router(status.router,        prefix="/status",   tags=["Status"])
