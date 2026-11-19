from datetime import datetime

import pytest

from database.db_manager import DatabaseManager
from services.attendance_service import AttendanceService
from services.outlook_service import OutlookService
from utils.date_utils import TZ

SENDER = "Vignesh.S@andortech.com"


class MockMailItem:
    def __init__(self):
        self.To = self.CC = self.Subject = self.Body = ""
        self.SendUsingAccount = None
        self.saved = self.displayed = self.sent = False

    def Save(self):
        self.saved = True

    def Display(self, modal=False):
        self.displayed = True

    def Send(self):  # must never be reached
        self.sent = True
        raise AssertionError("Send() was called - automatic sending is forbidden")


class MockAccount:
    def __init__(self, smtp):
        self.SmtpAddress = smtp


class MockAccounts:
    def __init__(self, addresses):
        self._items = [MockAccount(a) for a in addresses]
        self.Count = len(self._items)

    def Item(self, index):
        return self._items[index - 1]


class MockSession:
    def __init__(self, addresses):
        self.Accounts = MockAccounts(addresses)


class MockOutlookApp:
    def __init__(self, addresses=(SENDER,)):
        self.Session = MockSession(addresses)
        self.items = []

    def CreateItem(self, kind):
        assert kind == 0, "only MailItem drafts may be created"
        item = MockMailItem()
        self.items.append(item)
        return item


@pytest.fixture
def db(tmp_path):
    manager = DatabaseManager(tmp_path / "attendance.db", backup_dir=tmp_path / "bk")
    yield manager
    manager.close()


@pytest.fixture
def outlook_app():
    return MockOutlookApp()


@pytest.fixture
def outlook(outlook_app):
    return OutlookService(app_factory=lambda: outlook_app)


@pytest.fixture
def fixed_now():
    return datetime(2026, 11, 18, 11, 0, tzinfo=TZ)


@pytest.fixture
def service(db, outlook, fixed_now):
    return AttendanceService(db, outlook, clock=lambda: fixed_now)
