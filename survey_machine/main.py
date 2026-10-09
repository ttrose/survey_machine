"""Conventional ASGI entry point; Workers use worker.py instead."""

from dotenv import load_dotenv

from .application import create_app

load_dotenv()
app = create_app()
