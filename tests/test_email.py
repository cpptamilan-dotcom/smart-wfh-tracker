import re
from pathlib import Path

from services.outlook_service import EmailDraft, OutlookService

ROOT = Path(__file__).resolve().parent.parent
SEND_CALL = re.compile(r"\.\s*Send\s*\(|\bSendAndSave\b|\.\s*SendMail\b", re.IGNORECASE)


def _source_files():
    for path in ROOT.rglob("*.py"):
        parts = set(path.relative_to(ROOT).parts)
        if "tests" in parts or ".venv" in parts or "build" in parts or "dist" in parts:
            continue
        yield path


def draft():
    return EmailDraft("Vignesh.S@andortech.com", ["a@x.com"], ["b@x.com"], "Subj", "Body")


def test_draft_is_saved_and_displayed_but_never_sent(outlook, outlook_app):
    result = outlook.create_draft(draft())
    assert result.success
    mail = outlook_app.items[0]
    assert mail.saved and mail.displayed and not mail.sent


def test_no_outlook_send_operation_exists_in_source():
    offenders = [str(p) for p in _source_files() if SEND_CALL.search(p.read_text(encoding="utf-8"))]
    assert offenders == [], f"Forbidden send call found in: {offenders}"


def test_service_exposes_no_send_api():
    assert not [n for n in dir(OutlookService) if "send" in n.lower()]


def test_no_email_code_outside_outlook_service():
    for path in _source_files():
        if path.name == "outlook_service.py":
            continue
        text = path.read_text(encoding="utf-8")
        assert "CreateItem" not in text, f"{path} touches Outlook directly"
        assert "smtplib" not in text, f"{path} imports smtplib"


def test_scheduler_and_startup_never_reference_email_creation():
    for name in ("services/scheduler.py", "services/startup_service.py"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "create_draft" not in text and "outlook" not in text.lower()


def test_outlook_unavailable_returns_failure_not_exception():
    def boom():
        raise OSError("no outlook")
    result = OutlookService(app_factory=boom).create_draft(draft())
    assert not result.success and result.status == "FAILED_OUTLOOK_UNAVAILABLE"


def test_leave_never_creates_email(service, outlook_app):
    service.select("LEAVE")
    assert outlook_app.items == []


# ---------- Outlook on the web (deep link) ----------
from urllib.parse import parse_qs, urlparse

from services.outlook_service import RoutedOutlookService, WebOutlookService


def test_web_url_prefills_fields_with_proper_encoding():
    opened = []
    web = WebOutlookService(opener=lambda url: opened.append(url) or True)
    d = EmailDraft("v@x.com", ["a@x.com"], ["b@x.com", "c@x.com"],
                   "Work From Home Request - 18/11/2026", "Hi Team,\n\nPlease note.")
    result = web.create_draft(d)
    assert result.success and result.status == "DRAFT_CREATED"
    url = opened[0]
    assert url.startswith("https://outlook.cloud.microsoft/mail/deeplink/compose?")
    assert "+" not in url and "%20" in url and "%0A" in url
    q = parse_qs(urlparse(url).query)
    assert q["to"] == ["a@x.com"] and q["cc"] == ["b@x.com,c@x.com"]
    assert q["subject"] == ["Work From Home Request - 18/11/2026"]
    assert q["body"] == ["Hi Team,\n\nPlease note."]


def test_web_failure_to_open_browser_is_reported():
    web = WebOutlookService(opener=lambda url: False)
    assert not web.create_draft(draft()).success


def test_routing_follows_setting(outlook):
    settings = {"outlook_mode": "web"}
    opened = []
    routed = RoutedOutlookService(lambda k, d="": settings.get(k, d), classic=outlook,
                                  web=WebOutlookService(opener=lambda u: opened.append(u) or True))
    routed.create_draft(draft())
    assert len(opened) == 1 and routed.mode == "web"
    settings["outlook_mode"] = "classic"
    assert routed.mode == "classic"
    routed.create_draft(draft())
    assert len(opened) == 1


def test_web_mode_leave_opens_nothing_and_duplicate_blocked(db, fixed_now):
    from services.attendance_service import AttendanceService
    opened = []
    routed = RoutedOutlookService(db.get_setting,
                                  web=WebOutlookService(opener=lambda u: opened.append(u) or True))
    svc = AttendanceService(db, routed, clock=lambda: fixed_now)
    svc.select("WFH")
    assert svc.retry_draft().duplicate and len(opened) == 1
    assert svc.reopen_draft().draft_created and len(opened) == 2   # explicit user action only
