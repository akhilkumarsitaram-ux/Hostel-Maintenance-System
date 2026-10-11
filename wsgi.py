"""WSGI entry point for production servers such as Gunicorn."""

from app import create_app

application = create_app()
