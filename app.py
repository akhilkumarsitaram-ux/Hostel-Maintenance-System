"""University Hostel Maintenance System — Flask application."""

from __future__ import annotations

import logging
import os
import sys
from functools import wraps
from typing import Callable, TypeVar

from flask import (
    Flask,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_wtf import FlaskForm
from wtforms import PasswordField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional

import models

F = TypeVar("F", bound=Callable)

APP_NAME = "hostel-maintenance-system"


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


logger = logging.getLogger(APP_NAME)


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    is_testing = test_config is not None
    flask_env = (test_config or {}).get("FLASK_ENV") or os.environ.get("FLASK_ENV", "development")
    is_production = flask_env == "production" and not is_testing

    secret = os.environ.get("SECRET_KEY", "")
    if is_production and (not secret or len(secret) < 16):
        raise RuntimeError(
            "SECRET_KEY must be set to a strong value (16+ characters) when FLASK_ENV=production."
        )
    if not secret:
        secret = "dev-only-insecure-key-change-in-production"
        if not is_testing:
            logger.warning("Using development SECRET_KEY fallback. Set SECRET_KEY in production.")

    app.config.update(
        SECRET_KEY=secret,
        WTF_CSRF_ENABLED=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true",
    )
    if test_config:
        app.config.update(test_config)

    @app.before_request
    def load_logged_in_user() -> None:
        user_id = session.get("user_id")
        g.user = models.get_user_by_id(user_id) if user_id else None

    @app.context_processor
    def inject_globals() -> dict:
        return {
            "current_user": g.get("user"),
            "categories": models.CATEGORIES,
            "priorities": models.PRIORITIES,
            "statuses": models.STATUSES,
        }

    def login_required(view: F) -> F:
        @wraps(view)
        def wrapped(*args, **kwargs):
            if g.get("user") is None:
                flash("Please log in to continue.", "error")
                return redirect(url_for("login", next=request.path))
            return view(*args, **kwargs)

        return wrapped  # type: ignore[return-value]

    def role_required(*roles: str) -> Callable[[F], F]:
        def decorator(view: F) -> F:
            @wraps(view)
            def wrapped(*args, **kwargs):
                user = g.get("user")
                if user is None:
                    flash("Please log in to continue.", "error")
                    return redirect(url_for("login"))
                if user["role"] not in roles:
                    abort(403)
                return view(*args, **kwargs)

            return wrapped  # type: ignore[return-value]

        return decorator

    class LoginForm(FlaskForm):
        username = StringField("Username", validators=[DataRequired(), Length(max=64)])
        password = PasswordField("Password", validators=[DataRequired(), Length(max=128)])
        submit = SubmitField("Log in")

    class ComplaintForm(FlaskForm):
        category = SelectField(
            "Category",
            choices=[(c, c) for c in models.CATEGORIES],
            validators=[DataRequired()],
        )
        hostel = StringField("Hostel / Building", validators=[DataRequired(), Length(max=120)])
        room_number = StringField("Room number", validators=[DataRequired(), Length(max=32)])
        priority = SelectField(
            "Priority",
            choices=[(p, p) for p in models.PRIORITIES],
            validators=[DataRequired()],
        )
        description = TextAreaField(
            "Description",
            validators=[DataRequired(), Length(min=10, max=2000)],
        )
        submit = SubmitField("Submit complaint")

    class StaffUpdateForm(FlaskForm):
        status = SelectField(
            "Status",
            choices=[("In Progress", "In Progress"), ("Resolved", "Resolved")],
            validators=[DataRequired()],
        )
        note = TextAreaField(
            "Resolution note",
            validators=[DataRequired(), Length(min=5, max=2000)],
        )
        submit = SubmitField("Update complaint")

    class AdminAssignForm(FlaskForm):
        staff_id = SelectField("Assign to staff", coerce=int, validators=[DataRequired()])
        assign_submit = SubmitField("Assign")

    class AdminManageForm(FlaskForm):
        status = SelectField(
            "Status",
            choices=[("", "— No change —")] + [(s, s) for s in models.STATUSES],
            validators=[Optional()],
        )
        priority = SelectField(
            "Priority",
            choices=[("", "— No change —")] + [(p, p) for p in models.PRIORITIES],
            validators=[Optional()],
        )
        note = TextAreaField("Admin note", validators=[Optional(), Length(max=2000)])
        manage_submit = SubmitField("Save changes")

    @app.route("/health")
    def health():
        db_ok = models.check_database_connection()
        payload = {
            "status": "healthy" if db_ok else "unhealthy",
            "database": "connected" if db_ok else "disconnected",
            "application": APP_NAME,
        }
        if db_ok:
            return jsonify(payload), 200
        return jsonify(payload), 503

    @app.route("/")
    def index():
        user = g.get("user")
        if user is None:
            return redirect(url_for("login"))
        if user["role"] == "resident":
            return redirect(url_for("resident_dashboard"))
        if user["role"] == "staff":
            return redirect(url_for("staff_dashboard"))
        return redirect(url_for("admin_dashboard"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if g.get("user"):
            return redirect(url_for("index"))
        form = LoginForm()
        if form.validate_on_submit():
            username = form.username.data.strip()
            user = models.get_user_by_username(username)
            if user and models.verify_password(user, form.password.data):
                session.clear()
                session["user_id"] = user["id"]
                session["role"] = user["role"]
                logger.info("Successful login for user %s", username)
                flash(f"Welcome, {user['full_name']}!", "success")
                next_url = request.args.get("next")
                if next_url and next_url.startswith("/"):
                    return redirect(next_url)
                return redirect(url_for("index"))
            logger.warning("Failed login attempt for username %s", username)
            flash("Invalid username or password.", "error")
        return render_template("login.html", form=form)

    @app.route("/logout")
    @login_required
    def logout():
        username = g.user["username"]
        session.clear()
        logger.info("User %s logged out", username)
        flash("You have been logged out.", "success")
        return redirect(url_for("login"))

    def filter_params() -> dict:
        return {
            "search": request.args.get("search", "").strip(),
            "status": request.args.get("status", "").strip() or None,
            "category": request.args.get("category", "").strip() or None,
            "priority": request.args.get("priority", "").strip() or None,
        }

    @app.route("/resident/dashboard", methods=["GET", "POST"])
    @role_required("resident")
    def resident_dashboard():
        form = ComplaintForm()
        if form.validate_on_submit():
            cid = models.create_complaint(
                g.user["id"],
                form.category.data,
                form.hostel.data,
                form.room_number.data,
                form.priority.data,
                form.description.data,
            )
            if cid:
                logger.info("Complaint %s created by resident %s", cid, g.user["username"])
                flash("Your complaint was submitted successfully.", "success")
                return redirect(url_for("resident_dashboard"))
            flash("Could not submit complaint. Please check your input.", "error")
        fp = filter_params()
        if fp["status"] and fp["status"] not in models.STATUSES:
            fp["status"] = None
        complaints = models.list_complaints(resident_id=g.user["id"], **fp)
        return render_template(
            "resident_dashboard.html",
            form=form,
            complaints=complaints,
            filters=fp,
        )

    @app.route("/staff/dashboard")
    @role_required("staff")
    def staff_dashboard():
        fp = filter_params()
        if fp["status"] and fp["status"] not in models.STATUSES:
            fp["status"] = None
        complaints = models.list_complaints(assigned_staff_id=g.user["id"], **fp)
        return render_template("staff_dashboard.html", complaints=complaints, filters=fp)

    @app.route("/admin/dashboard")
    @role_required("admin")
    def admin_dashboard():
        fp = filter_params()
        staff_filter_raw = request.args.get("staff", "").strip()
        staff_filter: int | None = None
        if staff_filter_raw == "unassigned":
            staff_filter = 0
        elif staff_filter_raw.isdigit():
            staff_filter = int(staff_filter_raw)
        if fp["status"] and fp["status"] not in models.STATUSES:
            fp["status"] = None
        if fp["category"] and fp["category"] not in models.CATEGORIES:
            fp["category"] = None
        if fp["priority"] and fp["priority"] not in models.PRIORITIES:
            fp["priority"] = None
        complaints = models.list_complaints(
            assigned_staff_filter=staff_filter,
            status=fp["status"],
            category=fp["category"],
            priority=fp["priority"],
            search=fp["search"],
        )
        counts = models.admin_complaint_counts()
        staff_list = models.list_staff_users()
        return render_template(
            "admin_dashboard.html",
            complaints=complaints,
            filters=fp,
            staff_filter=staff_filter_raw,
            counts=counts,
            staff_list=staff_list,
        )

    def can_view_complaint(complaint: dict) -> bool:
        user = g.user
        if user["role"] == "admin":
            return True
        if user["role"] == "resident":
            return complaint["resident_id"] == user["id"]
        if user["role"] == "staff":
            return complaint["assigned_staff_id"] == user["id"]
        return False
    @app.route("/complaints/<int:complaint_id>", methods=["GET", "POST"])
    @login_required
    def complaint_detail(complaint_id: int):
        complaint = models.get_complaint_by_id(complaint_id)
        if not complaint:
            abort(404)

        if not can_view_complaint(complaint):
            abort(403)

        staff_form = None
        admin_assign_form = None
        admin_manage_form = None
        closed = complaint["status"] == "Closed"

        if g.user["role"] == "staff" and closed and request.method == "POST":
            flash("Closed complaints cannot be edited by staff.", "error")
            return redirect(
                url_for("complaint_detail", complaint_id=complaint_id)
            )

        if g.user["role"] == "staff" and not closed:
            staff_form = StaffUpdateForm()

            if staff_form.validate_on_submit():
                ok, msg = models.update_complaint_staff_status(
                    complaint_id,
                    g.user["id"],
                    staff_form.status.data,
                    staff_form.note.data or "",
                )

                if ok:
                    logger.info(
                        "Staff %s updated complaint %s to %s",
                        g.user["username"],
                        complaint_id,
                        staff_form.status.data,
                    )
                    flash(msg, "success")
                    return redirect(
                        url_for(
                            "complaint_detail",
                            complaint_id=complaint_id,
                        )
                    )

                flash(msg, "error")

        if g.user["role"] == "admin":
            staff_users = models.list_staff_users()
            admin_assign_form = AdminAssignForm()
            admin_assign_form.staff_id.choices = [
                (s["id"], s["full_name"]) for s in staff_users
            ]
            admin_manage_form = AdminManageForm()

            if (
                admin_assign_form.assign_submit.data
                and admin_assign_form.validate_on_submit()
            ):
                ok, msg = models.admin_assign_complaint(
                    complaint_id,
                    g.user["id"],
                    admin_assign_form.staff_id.data,
                )

                if ok:
                    logger.info(
                        "Admin assigned complaint %s to staff id %s",
                        complaint_id,
                        admin_assign_form.staff_id.data,
                    )
                    flash(msg, "success")
                    return redirect(
                        url_for(
                            "complaint_detail",
                            complaint_id=complaint_id,
                        )
                    )

                flash(msg, "error")

            elif (
                admin_assign_form.assign_submit.data
                and admin_assign_form.staff_id.errors
            ):
                logger.warning(
                    "Admin %s attempted to assign complaint %s "
                    "to an invalid staff id",
                    g.user["username"],
                    complaint_id,
                )
                flash(
                    "Invalid staff account. Please select a valid staff member.",
                    "error",
                )

            if (
                admin_manage_form.manage_submit.data
                and admin_manage_form.validate_on_submit()
            ):
                new_status = admin_manage_form.status.data or None
                new_priority = admin_manage_form.priority.data or None

                ok, msg = models.admin_update_complaint(
                    complaint_id,
                    g.user["id"],
                    new_status=new_status,
                    new_priority=new_priority,
                    note=admin_manage_form.note.data or "",
                )

                if ok:
                    logger.info(
                        "Admin updated complaint %s",
                        complaint_id,
                    )
                    flash(msg, "success")
                    return redirect(
                        url_for(
                            "complaint_detail",
                            complaint_id=complaint_id,
                        )
                    )

                flash(msg, "error")

        updates = models.get_complaint_updates(complaint_id)

        return render_template(
            "complaint_detail.html",
            complaint=complaint,
            updates=updates,
            staff_form=staff_form,
            admin_assign_form=admin_assign_form,
            admin_manage_form=admin_manage_form,
            closed=closed,
        )

    @app.errorhandler(403)
    def forbidden(_e):
        return render_template("403.html"), 403

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def server_error(_e):
        logger.exception("Unexpected server error")
        return render_template("404.html"), 500

    return app


def main() -> None:
    configure_logging()
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "init-db":
            models.init_db()
            logger.info("Database initialized at %s", models.get_database_path())
            print(f"Database initialized: {models.get_database_path()}")
            return
        if cmd == "seed-demo":
            models.seed_demo()
            logger.info("Demo data seeded (skipped existing records)")
            print("Demo data seeded successfully.")
            return
        print(f"Unknown command: {cmd}")
        print("Usage: python app.py | python app.py init-db | python app.py seed-demo")
        sys.exit(1)

    app = create_app()
    logger.info("Application startup — %s", APP_NAME)
    host = os.environ.get("FLASK_HOST", "127.0.0.1")
    port = int(os.environ.get("FLASK_PORT", "5000"))
    debug = os.environ.get("FLASK_ENV", "development") == "development"
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
