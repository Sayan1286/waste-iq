from collections import defaultdict
from collections.abc import Generator
from threading import Lock
import time

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import decode_access_token
from app.db.session import SessionLocal
from app.models.user import User
from app.services.ai_classifier import AIClassifierProvider, get_classifier
from app.services.pickup_request_creation import PickupRequestCreationService
from app.services.pickup_request_images import PickupRequestImageService
from app.services.upload import CloudinaryUploadConfig, CloudinaryUploader

security = HTTPBearer(auto_error=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
        token_ver = payload.get("ver", 1)
    except (ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    if user.token_version != token_ver:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def require_roles(*roles: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
            )
        return user

    return dependency


def get_ai_classifier() -> AIClassifierProvider:
    return get_classifier()


def get_image_uploader(settings: Settings = Depends(get_settings)) -> CloudinaryUploader:
    return CloudinaryUploader(
        config=CloudinaryUploadConfig(
            cloud_name=settings.cloudinary_cloud_name,
            api_key=settings.cloudinary_api_key,
            api_secret=settings.cloudinary_api_secret,
            required=settings.cloudinary_required,
        )
    )


def get_pickup_request_image_service(
    uploader: CloudinaryUploader = Depends(get_image_uploader),
    classifier: AIClassifierProvider = Depends(get_ai_classifier),
) -> PickupRequestImageService:
    return PickupRequestImageService(uploader=uploader, classifier=classifier)


def get_pickup_request_creation_service(
    image_service: PickupRequestImageService = Depends(get_pickup_request_image_service),
) -> PickupRequestCreationService:
    return PickupRequestCreationService(image_service=image_service)


_rate_limit_store: dict[str, list[float]] = defaultdict(list)
_rate_limit_lock = Lock()


def reset_rate_limit_store() -> None:
    with _rate_limit_lock:
        _rate_limit_store.clear()


def rate_limit(requests: int, window: int):
    """Limit requests from each client within a rolling time window."""

    if requests <= 0:
        raise ValueError("requests must be greater than 0")
    if window <= 0:
        raise ValueError("window must be greater than 0")

    def dependency(request: Request) -> None:
        client_id = request.client.host if request.client else "unknown"
        now = time.monotonic()
        cutoff = now - window

        with _rate_limit_lock:
            timestamps = _rate_limit_store[client_id]
            timestamps[:] = [timestamp for timestamp in timestamps if timestamp > cutoff]

            if len(timestamps) >= requests:
                retry_after = max(1, int(window - (now - timestamps[0])))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests. Please try again later.",
                    headers={"Retry-After": str(retry_after)},
                )

            timestamps.append(now)

    return dependency
