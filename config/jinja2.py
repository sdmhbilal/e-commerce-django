from __future__ import annotations

from django.templatetags.static import static
from django.urls import reverse


def environment(**options):
    env = options.pop("environment", None)
    if env is not None:
        pass
    from jinja2 import Environment

    jinja_env = Environment(**options)
    jinja_env.globals.update(
        {
            "static": static,
            "url": reverse,
        }
    )
    return jinja_env

