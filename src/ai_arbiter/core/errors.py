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
            f"{feature} needs the '{extra}' extra. Install it with: "
            f'pip install "ai-arbiter[{extra}]"'
        )
