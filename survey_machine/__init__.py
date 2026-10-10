"""Survey Machine's shared application package."""

__version__ = "0.1.0"

from .config import Settings

__all__ = ["Settings", "create_app", "mount_api", "__version__"]


def create_app(settings: Settings | None = None, *, worker: bool = False):
    """Create a standalone FastAPI service with optional web interface."""
    from .application import create_app as factory

    return factory(settings, worker=worker)


def mount_api(parent, settings: Settings | None = None, *, path: str = "/surveys"):
    """Mount the API in a FastAPI app, composing both applications' lifespans.

    Call before starting the parent app, after defining its lifespan. The mount
    serves API routes and /docs; the standalone web interface is disabled.
    """
    from .integration import mount_api as mount

    return mount(parent, settings, path=path)
