"""Addresses of this application: one rule for every place that sends a person somewhere it was told."""


def is_local(address: str) -> bool:
    """A path of this application, and never another site: two slashes, or a slash and a backslash, are another site
    to a browser."""
    return address.startswith("/") and not address.startswith(("//", "/\\"))
