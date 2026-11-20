from typing import Optional

from chacc_api import BackboneContext

from . import models  # noqa: F401  (registers the shortlinks_links table)
from . import service
from .context_factory import get_context, set_module_context
from .routes import router as shortlinks_router


# --- Module Setup ---
def setup_plugin(context: Optional[BackboneContext] = None):
    """Called by the ChaCC backbone to initialize the module."""
    _module_context = get_context(context)
    set_module_context(_module_context)

    _module_context.logger.info("shortlinks: Setup initiated!")

    # Services other modules (e.g. linkstats) build on.
    _module_context.register_service("shortlinks.get_by_code", service.get_by_code)
    _module_context.register_service("shortlinks.add_visit_listener", service.add_visit_listener)
    _module_context.register_service("shortlinks.remove_visit_listener", service.remove_visit_listener)

    return shortlinks_router


def get_plugin_info():
    """Provides essential information about this module to the ChaCC API backbone."""
    return {
        "name": "shortlinks",
        "display_name": "Short Links",
        "version": "0.1.0",
        "author": "Jonas",
        "description": "Turn long URLs into short codes that redirect.",
        "status": "enabled",
    }
