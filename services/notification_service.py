"""Tray balloon notifications, sound and the tray icon image."""
from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)


def make_icon_image(size: int = 64):
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((2, 2, size - 2, size - 2), fill=(22, 163, 74, 255))
    s = size / 64
    d.polygon([(32 * s, 14 * s), (12 * s, 32 * s), (52 * s, 32 * s)], fill="white")
    d.rectangle((18 * s, 32 * s, 46 * s, 50 * s), fill="white")
    d.rectangle((28 * s, 38 * s, 36 * s, 50 * s), fill=(22, 163, 74, 255))
    return img


class NotificationService:
    def __init__(self):
        self._tray = None

    def attach_tray(self, tray) -> None:
        self._tray = tray

    def notify(self, title: str, message: str, beep: bool = False) -> None:
        log.info("Notification: %s - %s", title, message)
        if self._tray is not None:
            try:
                self._tray.notify(message, title)
            except Exception:
                log.debug("Tray notification failed", exc_info=True)
        if beep and sys.platform == "win32":
            try:
                import winsound
                winsound.MessageBeep()
            except Exception:
                pass
