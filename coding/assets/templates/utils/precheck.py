from src.utils.config import PREFIX, ConfigError, Settings

from src.utils.logger import CustomLogger

logger = CustomLogger(__name__)


def precheck_all(settings: Settings) -> None:
    """Fail before serving traffic; extend here for service-specific dependencies."""
    logger.info("Starting startup precheck")
    for name, path in (
        (PREFIX + "CONFIG_YAML_PATH", settings.config_yaml_path),
        (PREFIX + "PROMPTS_PATH", settings.prompts_path),
    ):
        if not path.is_file():
            logger.error(f"Startup precheck failed: '{name}' is not a readable file")
            raise ConfigError(f"Configured file '{name}' does not exist or is not a file")
        try:
            with path.open("rb") as stream:
                stream.read(1)
        except OSError:
            logger.error(f"Startup precheck failed: '{name}' cannot be read")
            raise ConfigError(f"Configured file '{name}' cannot be read") from None
    logger.info("Startup precheck completed")
