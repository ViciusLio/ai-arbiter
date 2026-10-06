"""Exception hierarchy shared by every Arbiter package."""


class ArbiterError(Exception):
    """Base class for errors raised by Arbiter itself."""


class ConfigurationError(ArbiterError):
    """The configuration is missing, unreadable or invalid."""


class PluginError(ArbiterError):
    """A plugin could not be found or loaded."""


class SecretNotFoundError(ArbiterError):
    """A secret reference could not be resolved."""


class MissingExtraError(ArbiterError):
    """A feature needs an optional dependency group that is not installed."""

    def __init__(self, extra: str, feature: str) -> None:
        self.extra = extra
        self.feature = feature
        super().__init__(
            f"{feature} needs the '{extra}' extra. From a clone: uv sync --extra {extra}. "
            f'From PyPI: pip install "ai-arbiter[{extra}]"'
        )


class AuthenticationError(ArbiterError):
    """The caller could not be identified: no key, or a key that is not valid."""


class PermissionDeniedError(ArbiterError):
    """The caller is identified and is not allowed to do this."""


class NotFoundError(ArbiterError):
    """The thing asked for does not exist in the caller's tenant."""


class ConflictError(ArbiterError):
    """The change contradicts something that already exists."""
