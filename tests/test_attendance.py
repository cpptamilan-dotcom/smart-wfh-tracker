from datetime import datetime

from services.attendance_service import AttendanceService, invalid_addresses, parse_addresses
from services.outlook_service import OutlookService
from utils.date_utils import TZ


def test_wfh_selection_saves(service, db):
    result = service.select("WFH")
    assert result.saved and result.draft_created
    record = db.get_attendance("2026-11-18")
    assert record["work_mode"] == "WFH"
    assert record["email_status"] == "DRAFT_CREATED"
    assert record["email_created_at"]


def test_leave_selection_saves_without_email(service, db, outlook_app):
    result = service.select("LEAVE")
    assert result.saved and not result.draft_created
    assert db.get_attendance("2026-11-18")["work_mode"] == "LEAVE"
    assert db.get_attendance("2026-11-18")["email_status"] == "NOT_REQUIRED"
    assert outlook_app.items == []  # Outlook never even touched for LEAVE


def test_duplicate_daily_selection_prevented(service, db, outlook_app):
    service.select("WFH")
    again = service.select("LEAVE")
    assert again.duplicate and not again.saved
    assert db.get_attendance("2026-11-18")["work_mode"] == "WFH"
    assert len(outlook_app.items) == 1


def test_recent_attendance_can_be_edited_without_permission(service, db, outlook_app):
    service.select("LEAVE")
    result = service.edit_attendance("2026-11-18", "WFH")
    assert result.saved and result.draft_created
    assert db.get_attendance("2026-11-18")["work_mode"] == "WFH"
    assert len(outlook_app.items) == 1


def test_editing_wfh_to_leave_does_not_create_or_send_email(service, db, outlook_app):
    service.select("WFH")
    result = service.edit_attendance("2026-11-18", "LEAVE")
    assert result.saved and not result.draft_created
    assert db.get_attendance("2026-11-18")["email_status"] == "NOT_REQUIRED"
    assert len(outlook_app.items) == 1


def test_invalid_mode_rejected(service):
    import pytest
    with pytest.raises(ValueError):
        service.select("HOLIDAY")


def test_duplicate_drafts_prevented(service, outlook_app):
    service.select("WFH")
    retry = service.retry_draft()
    assert retry.duplicate and not retry.saved
    assert len(outlook_app.items) == 1


def test_retry_after_outlook_failure_creates_single_draft(db, fixed_now):
    state = {"app": None}

    def factory():
        if state["app"] is None:
            raise OSError("Outlook not installed")
        return state["app"]

    svc = AttendanceService(db, OutlookService(app_factory=factory), clock=lambda: fixed_now)
    first = svc.select("WFH")
    assert first.saved and not first.draft_created
    assert db.get_attendance("2026-11-18")["email_status"] == "FAILED_OUTLOOK_UNAVAILABLE"

    from tests.conftest import MockOutlookApp
    state["app"] = MockOutlookApp()
    assert svc.retry_draft().draft_created
    assert svc.retry_draft().duplicate
    assert len(state["app"].items) == 1


def test_works_without_outlook_installed(db, fixed_now):
    def boom():
        raise ImportError("No module named win32com")

    svc = AttendanceService(db, OutlookService(app_factory=boom), clock=lambda: fixed_now)
    result = svc.select("WFH")
    assert result.saved                      # attendance still recorded
    assert result.email_status == "FAILED_OUTLOOK_UNAVAILABLE"
    assert db.get_attendance("2026-11-18")["work_mode"] == "WFH"


def test_sender_mismatch_creates_no_draft(db, fixed_now):
    from tests.conftest import MockOutlookApp
    app = MockOutlookApp(addresses=("someone.else@example.com",))
    svc = AttendanceService(db, OutlookService(app_factory=lambda: app), clock=lambda: fixed_now)
    result = svc.select("WFH")
    assert result.email_status == "FAILED_SENDER_MISMATCH"
    assert app.items == []


def test_draft_uses_current_local_date_and_recipients(service, outlook_app):
    service.select("WFH")
    mail = outlook_app.items[0]
    assert mail.Subject == "Work From Home Request - 18/11/2026"
    assert "throughout the 18/11/2026" in mail.Body
    assert mail.To == "Bhagya.S@andortech.com"
    assert mail.CC == "Anjali.Kumari@andortech.com; Prangya.Priyadarshini@andortech.com"
    assert mail.SendUsingAccount.SmtpAddress == "Vignesh.S@andortech.com"
    assert "{DD/MM/YYYY}" not in mail.Body + mail.Subject


def test_date_rolls_over_with_clock(db, outlook):
    day1 = AttendanceService(db, outlook, clock=lambda: datetime(2026, 11, 18, 11, 0, tzinfo=TZ))
    day2 = AttendanceService(db, outlook, clock=lambda: datetime(2026, 11, 19, 11, 0, tzinfo=TZ))
    assert day1.select("WFH").saved
    assert day2.select("LEAVE").saved


def test_address_helpers():
    assert parse_addresses("a@x.com; b@x.com,c@x.com") == ["a@x.com", "b@x.com", "c@x.com"]
    assert invalid_addresses("a@x.com; nonsense") == ["nonsense"]
