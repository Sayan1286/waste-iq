import logging

logger = logging.getLogger(__name__)


class NotificationDispatcher:
    @staticmethod
    def reservation_expired(lot_id: int) -> None:
        logger.info(
            "Reservation expired notification sent for lot %s",
            lot_id,
        )

    @staticmethod
    def notify_admins(message: str) -> None:
        logger.warning(
            "ADMIN ALERT: %s",
            message,
        )