"""The application. tools/remove_demo.py deletes app/demo and the lines marked `# demo`."""

from fastapi import FastAPI

from app.core.application import create_core, install_home
from app.core.settings import Settings, get_settings
from app.demo import install as install_demo  # demo


def create_app(settings: Settings | None = None) -> FastAPI:
    application = create_core(settings or get_settings())
    install_demo(application)  # demo
    install_home(application)
    return application


app = create_app()
