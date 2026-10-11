"""Automated tests for the hostel maintenance Flask application."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import models
from app import create_app


class HostelMaintenanceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.db"
        os.environ["DATABASE_PATH"] = str(self.db_path)
        os.environ["FLASK_ENV"] = "development"
        os.environ["SECRET_KEY"] = "test-secret-key-for-unit-tests"
        models.init_db(self.db_path)
        self._seed_users()
        self.app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False})
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()
        os.environ.pop("DATABASE_PATH", None)

    def _seed_users(self) -> None:
        models.create_user("resident_a", "pass1234", "Resident A", "resident", self.db_path)
        models.create_user("resident_b", "pass1234", "Resident B", "resident", self.db_path)
        models.create_user("staff_a", "pass1234", "Staff A", "staff", self.db_path)
        models.create_user("staff_b", "pass1234", "Staff B", "staff", self.db_path)
        models.create_user("admin_a", "pass1234", "Admin A", "admin", self.db_path)

    def _login(self, username: str, password: str = "pass1234") -> None:
        response = self.client.post(
            "/login",
            data={"username": username, "password": password},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)

    def _logout(self) -> None:
        self.client.get("/logout", follow_redirects=True)

    def _complaint_for_resident_a(self) -> int:
        user = models.get_user_by_username("resident_a", self.db_path)
        assert user
        cid = models.create_complaint(
            user["id"],
            "Electrical",
            "Clarks Hall",
            "101",
            "Medium",
            "Light flickering in room.",
            self.db_path,
        )
        assert cid
        return cid

    def test_login_success(self) -> None:
        response = self.client.post(
            "/login",
            data={"username": "resident_a", "password": "pass1234"},
            follow_redirects=True,
        )
        self.assertIn(b"Welcome", response.data)

    def test_login_failure(self) -> None:
        response = self.client.post(
            "/login",
            data={"username": "resident_a", "password": "wrong"},
            follow_redirects=True,
        )
        self.assertIn(b"Invalid username or password", response.data)

    def test_logout(self) -> None:
        self._login("resident_a")
        response = self.client.get("/logout", follow_redirects=True)
        self.assertIn(b"logged out", response.data.lower())

    def test_unauthenticated_dashboard_redirect(self) -> None:
        for path in ("/resident/dashboard", "/staff/dashboard", "/admin/dashboard"):
            response = self.client.get(path, follow_redirects=False)
            self.assertEqual(response.status_code, 302)
            self.assertIn("/login", response.location or "")

    def test_resident_submit_valid_complaint(self) -> None:
        self._login("resident_a")
        response = self.client.post(
            "/resident/dashboard",
            data={
                "category": "Plumbing",
                "hostel": "Paul Kent Hall",
                "room_number": "22",
                "priority": "High",
                "description": "Tap leaking continuously near sink.",
            },
            follow_redirects=True,
        )
        self.assertIn(b"submitted successfully", response.data)

    def test_resident_invalid_complaint_rejected(self) -> None:
        self._login("resident_a")
        response = self.client.post(
            "/resident/dashboard",
            data={
                "category": "Plumbing",
                "hostel": "Paul Kent Hall",
                "room_number": "22",
                "priority": "High",
                "description": "short",
            },
            follow_redirects=True,
        )
        self.assertNotIn(b"submitted successfully", response.data)

    def test_resident_sees_own_complaints(self) -> None:
        cid = self._complaint_for_resident_a()
        self._login("resident_a")
        response = self.client.get("/resident/dashboard")
        self.assertIn(f"#{cid}".encode(), response.data)

    def test_resident_cannot_view_other_complaint(self) -> None:
        cid = self._complaint_for_resident_a()
        self._login("resident_b")
        response = self.client.get(f"/complaints/{cid}")
        self.assertEqual(response.status_code, 403)

    def test_resident_cannot_modify_other_complaint(self) -> None:
        cid = self._complaint_for_resident_a()
        staff = models.get_user_by_username("staff_a", self.db_path)
        assert staff
        models.admin_assign_complaint(cid, 1, staff["id"], self.db_path)
        self._login("resident_b")
        response = self.client.post(
            f"/complaints/{cid}",
            data={"status": "Resolved", "note": "Trying to hijack complaint."},
            follow_redirects=True,
        )
        complaint = models.get_complaint_by_id(cid, self.db_path)
        assert complaint
        self.assertNotEqual(complaint["status"], "Resolved")
        self.assertIn(response.status_code, (403, 200))

    def test_staff_views_assigned_complaint(self) -> None:
        cid = self._complaint_for_resident_a()
        staff = models.get_user_by_username("staff_a", self.db_path)
        admin = models.get_user_by_username("admin_a", self.db_path)
        assert staff and admin
        models.admin_assign_complaint(cid, admin["id"], staff["id"], self.db_path)
        self._login("staff_a")
        response = self.client.get(f"/complaints/{cid}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Complaint", response.data)

    def test_staff_cannot_view_unassigned_complaint(self) -> None:
        cid = self._complaint_for_resident_a()
        self._login("staff_a")
        response = self.client.get(f"/complaints/{cid}")
        self.assertEqual(response.status_code, 403)

    def test_staff_updates_assigned_complaint(self) -> None:
        cid = self._complaint_for_resident_a()
        staff = models.get_user_by_username("staff_a", self.db_path)
        admin = models.get_user_by_username("admin_a", self.db_path)
        assert staff and admin
        models.admin_assign_complaint(cid, admin["id"], staff["id"], self.db_path)
        self._login("staff_a")
        response = self.client.post(
            f"/complaints/{cid}",
            data={
                "status": "In Progress",
                "note": "Inspected room and ordered replacement parts.",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Status updated", response.data)
        complaint = models.get_complaint_by_id(cid, self.db_path)
        assert complaint
        self.assertEqual(complaint["status"], "In Progress")

    def test_staff_cannot_update_other_staff_complaint(self) -> None:
        cid = self._complaint_for_resident_a()
        staff_a = models.get_user_by_username("staff_a", self.db_path)
        staff_b = models.get_user_by_username("staff_b", self.db_path)
        admin = models.get_user_by_username("admin_a", self.db_path)
        assert staff_a and staff_b and admin
        models.admin_assign_complaint(cid, admin["id"], staff_a["id"], self.db_path)
        self._login("staff_b")
        response = self.client.post(
            f"/complaints/{cid}",
            data={"status": "In Progress", "note": "Should not be allowed."},
            follow_redirects=True,
        )
        complaint = models.get_complaint_by_id(cid, self.db_path)
        assert complaint
        self.assertNotEqual(complaint["status"], "In Progress")
        self.assertEqual(response.status_code, 403)

    def test_admin_assigns_to_valid_staff(self) -> None:
        cid = self._complaint_for_resident_a()
        staff = models.get_user_by_username("staff_a", self.db_path)
        assert staff
        self._login("admin_a")
        response = self.client.post(
            f"/complaints/{cid}",
            data={"staff_id": str(staff["id"]), "assign_submit": "Assign"},
            follow_redirects=True,
        )
        self.assertIn(b"Complaint assigned", response.data)
        complaint = models.get_complaint_by_id(cid, self.db_path)
        assert complaint
        self.assertEqual(complaint["assigned_staff_id"], staff["id"])

    def test_admin_cannot_assign_to_non_staff(self) -> None:
        cid = self._complaint_for_resident_a()
        resident = models.get_user_by_username("resident_a", self.db_path)
        assert resident
        self._login("admin_a")
        response = self.client.post(
            f"/complaints/{cid}",
            data={"staff_id": str(resident["id"]), "assign_submit": "Assign"},
            follow_redirects=True,
        )
        self.assertIn(b"Invalid staff account", response.data)

    def test_non_admin_cannot_access_admin_dashboard(self) -> None:
        self._login("resident_a")
        response = self.client.get("/admin/dashboard")
        self.assertEqual(response.status_code, 403)

    def test_status_changes_recorded_in_history(self) -> None:
        cid = self._complaint_for_resident_a()
        staff = models.get_user_by_username("staff_a", self.db_path)
        admin = models.get_user_by_username("admin_a", self.db_path)
        assert staff and admin
        models.admin_assign_complaint(cid, admin["id"], staff["id"], self.db_path)
        self._login("staff_a")
        self.client.post(
            f"/complaints/{cid}",
            data={"status": "In Progress", "note": "Work started on site."},
            follow_redirects=True,
        )
        updates = models.get_complaint_updates(cid, self.db_path)
        statuses = [u["new_status"] for u in updates if u["new_status"]]
        self.assertIn("In Progress", statuses)

    def test_health_endpoint(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        assert payload
        self.assertEqual(payload["status"], "healthy")
        self.assertEqual(payload["database"], "connected")
        self.assertEqual(payload["application"], "hostel-maintenance-system")

    def test_closed_complaint_not_editable_by_staff(self) -> None:
        cid = self._complaint_for_resident_a()
        staff = models.get_user_by_username("staff_a", self.db_path)
        admin = models.get_user_by_username("admin_a", self.db_path)
        assert staff and admin
        models.admin_assign_complaint(cid, admin["id"], staff["id"], self.db_path)
        models.admin_update_complaint(
            cid,
            admin["id"],
            new_status="Closed",
            note="Closing for test.",
            db_path=self.db_path,
        )
        self._login("staff_a")
        response = self.client.post(
            f"/complaints/{cid}",
            data={"status": "In Progress", "note": "Should be blocked."},
            follow_redirects=True,
        )
        complaint = models.get_complaint_by_id(cid, self.db_path)
        assert complaint
        self.assertEqual(complaint["status"], "Closed")
        self.assertIn(b"cannot be edited", response.data.lower())


if __name__ == "__main__":
    unittest.main()
