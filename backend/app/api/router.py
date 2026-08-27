from fastapi import APIRouter

from app.api.routes import (
    admin,
    analytics,
    auth,
    collector,
    collector_map,
    dealer,
    inventory,
    jobs,
    marketplace,
    notifications,
    pickup_requests,
    pilot_metrics,
)

api_router = APIRouter()

# Authentication
api_router.include_router(
    auth.router,
    prefix="/auth",
    tags=["Authentication"],
)

# Pickup Requests
api_router.include_router(
    pickup_requests.router,
    prefix="/pickup-requests",
    tags=["Pickup Requests"],
)

# Collector
api_router.include_router(
    collector.router,
    prefix="/collector",
    tags=["Collector"],
)

# Collector Map
api_router.include_router(
    collector_map.router,
    prefix="/collector",
    tags=["Collector Map"],
)

# Dealer
api_router.include_router(
    dealer.router,
    prefix="/dealer",
    tags=["Dealer"],
)

# Marketplace
api_router.include_router(
    marketplace.router,
    prefix="/marketplace",
    tags=["Marketplace"],
)

# Admin
api_router.include_router(
    admin.router,
    prefix="/admin",
    tags=["Admin"],
)

# Admin Analytics
api_router.include_router(
    analytics.router,
    prefix="/admin/analytics",
    tags=["Admin Analytics"],
)

# Notifications
api_router.include_router(
    notifications.router,
    prefix="/notifications",
    tags=["Notifications"],
)

# Background Jobs
api_router.include_router(
    jobs.router,
)

# Inventory - Admin
api_router.include_router(
    inventory.admin_router,
    prefix="/admin",
    tags=["Admin Inventory"],
)

# Inventory - Dealer
api_router.include_router(
    inventory.dealer_router,
    prefix="/dealer",
    tags=["Dealer Inventory"],
)
# Pilot Metrics
api_router.include_router(
    pilot_metrics.router,
    prefix="/admin/pilot-metrics",
    tags=["Pilot Metrics"],
)
