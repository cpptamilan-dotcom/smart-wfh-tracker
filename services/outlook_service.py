"""Outlook COM integration (classic Outlook, via pywin32).

SECURITY: this module only creates, saves and displays drafts. It must never
call the mail item's send method. tests/test_email.py statically audits the
source tree to enforce that.
"""
from __future__ import annotations

import logging
import webbrowser
from urllib.parse import quote
from dataclasses import dataclass, field
from typing import Callable, Optional

import config

log = logging.getLogger(__name__)
OL_MAIL_ITEM = 0
PR_SEND_USING_ACCOUNT_DISPID = 64209


class OutlookUnavailable(Exception):
    pass


@dataclass
class EmailDraft:
    sender_email: str
    to: list = field(default_factory=list)
    cc: list = field(default_factory=list)
    subject: str = ""
    body: str = ""


@dataclass
class DraftResult:
    success: bool
    status: str
    message: str


def _default_factory():
    import pythoncom  # noqa: WPS433 (Windows only)
    import win32com.client

    pythoncom.CoInitialize()
    return win32com.client.Dispatch("Outlook.Application")


def _registry_probe() -> bool:
    """Passive check: is the classic Outlook COM class registered? Does not start Outlook."""
    try:
        import winreg
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Outlook.Application\CLSID"))
        return True
    except Exception:
        return False


class OutlookService:
    def __init__(self, app_factory: Optional[Callable] = None,
                 installed_probe: Optional[Callable[[], bool]] = None):
        self._factory = app_factory or _default_factory
        if installed_probe is not None:
            self._probe = installed_probe
        elif app_factory is not None:
            self._probe = self._probe_via_factory
        else:
            self._probe = _registry_probe

    def _probe_via_factory(self) -> bool:
        try:
            self._get_app()
            return True
        except OutlookUnavailable:
            return False

    def _get_app(self):
        try:
            return self._factory()
        except Exception as exc:  # ImportError off-Windows, COM errors, not installed...
            raise OutlookUnavailable(
                "Classic Outlook is not available (is it installed and is 'New Outlook' off?).") from exc

    def is_installed(self) -> bool:
        return bool(self._probe())

    @staticmethod
    def _find_account(app, sender_email: str):
        accounts = app.Session.Accounts
        wanted = (sender_email or "").strip().lower()
        for index in range(1, accounts.Count + 1):  # COM collections are 1-based
            account = accounts.Item(index)
            if str(account.SmtpAddress).strip().lower() == wanted:
                return account
        return None

    def check_status(self, sender_email: str = "") -> tuple:
        """Active check (may start Outlook). Returns (ok, message)."""
        try:
            app = self._get_app()
        except OutlookUnavailable as exc:
            return False, str(exc)
        if sender_email and self._find_account(app, sender_email) is None:
            return False, f"Outlook has no account for {sender_email}."
        return True, "Outlook is available and the sender account is configured."

    def create_draft(self, draft: EmailDraft) -> DraftResult:
        try:
            app = self._get_app()
        except OutlookUnavailable as exc:
            log.warning("Draft not created: %s", exc)
            return DraftResult(False, config.EmailStatus.FAILED_OUTLOOK_UNAVAILABLE, str(exc))
        try:
            account = self._find_account(app, draft.sender_email)
            if account is None:
                msg = f"No Outlook account matches the configured sender {draft.sender_email}."
                log.warning(msg)
                return DraftResult(False, config.EmailStatus.FAILED_SENDER_MISMATCH, msg)
            mail = app.CreateItem(OL_MAIL_ITEM)
            mail.To = "; ".join(draft.to)
            mail.CC = "; ".join(draft.cc)
            mail.Subject = draft.subject
            mail.Body = draft.body
            self._set_from_account(mail, account)
            mail.Save()      # keeps the draft in the Drafts folder
            mail.Display()   # user reviews, edits and sends manually
            log.info("Outlook draft created and displayed")
            return DraftResult(True, config.EmailStatus.DRAFT_CREATED,
                               "Outlook draft created. Review it and click Send yourself.")
        except Exception as exc:
            log.exception("Failed to create Outlook draft")
            return DraftResult(False, config.EmailStatus.FAILED, f"Could not create the draft: {exc}")

    @staticmethod
    def _set_from_account(mail, account) -> None:
        try:
            mail.SendUsingAccount = account
        except Exception:
            # Some pywin32 builds reject the property set; use the raw dispatch id.
            mail._oleobj_.Invoke(PR_SEND_USING_ACCOUNT_DISPID, 0, 8, 0, account)


class WebOutlookService:
    """Outlook on the web / PWA: opens a pre-filled compose window via a deep link.

    The link only fills a compose form in the user's own signed-in session. There is
    no credential handling and no API call that could send; the user presses Send.
    The sender cannot be chosen or verified from a link: the signed-in account is used.
    """

    def __init__(self, base_url: str = "https://outlook.cloud.microsoft/mail/deeplink/compose",
                 opener: Optional[Callable[[str], bool]] = None):
        self.base_url = base_url
        self._open = opener or (lambda url: webbrowser.open(url, new=1))

    def build_url(self, draft: EmailDraft) -> str:
        parts = []
        if draft.to:
            parts.append("to=" + quote(",".join(draft.to), safe="@,"))
        if draft.cc:
            parts.append("cc=" + quote(",".join(draft.cc), safe="@,"))
        parts.append("subject=" + quote(draft.subject, safe=""))   # %20, never '+'
        parts.append("body=" + quote(draft.body, safe=""))         # newlines -> %0A
        return self.base_url + "?" + "&".join(parts)

    def is_installed(self) -> bool:
        return True

    def check_status(self, sender_email: str = "") -> tuple:
        return True, ("Outlook on the web mode: a compose window opens in your browser/PWA "
                      "using the account you are signed in with.")

    def create_draft(self, draft: EmailDraft) -> DraftResult:
        try:
            opened = self._open(self.build_url(draft))
        except Exception as exc:
            log.exception("Could not open browser")
            return DraftResult(False, config.EmailStatus.FAILED, f"Could not open the browser: {exc}")
        if not opened:
            return DraftResult(False, config.EmailStatus.FAILED_OUTLOOK_UNAVAILABLE,
                               "No browser could be opened for Outlook on the web.")
        log.info("Outlook web compose opened")
        return DraftResult(True, config.EmailStatus.DRAFT_CREATED,
                           "Compose window opened in Outlook on the web. Check the fields, "
                           "then click Send yourself.")


class RoutedOutlookService:
    """Picks the web or classic backend from the saved 'outlook_mode' setting on every call."""

    def __init__(self, settings_getter: Callable[[str, str], str],
                 classic: Optional[OutlookService] = None,
                 web: Optional[WebOutlookService] = None):
        self._get = settings_getter
        self._classic = classic or OutlookService()
        self._web = web or WebOutlookService()

    def _backend(self):
        if self._get("outlook_mode", "web") == "classic":
            return self._classic
        self._web.base_url = self._get(
            "web_compose_url", self._web.base_url) or self._web.base_url
        return self._web

    @property
    def mode(self) -> str:
        return "classic" if self._backend() is self._classic else "web"

    def is_installed(self) -> bool:
        return self._backend().is_installed()

    def check_status(self, sender_email: str = "") -> tuple:
        return self._backend().check_status(sender_email)

    def create_draft(self, draft: EmailDraft) -> DraftResult:
        return self._backend().create_draft(draft)
