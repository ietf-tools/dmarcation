import logging

from config import Config, ConfigError

logger = logging.getLogger(__name__)


def get_config_value(cfg: Config, key: str, default: any = None) -> any:
    try:
        value = cfg[key]

        logger.debug(
            "Found entry for %(key)s at %(key)s: %(value)s",
            {"key": key, "value": value},
        )

        return value
    except (ConfigError, KeyError):
        pass

    try:
        legacy_key = f"dmarc.{key}"
        value = cfg[legacy_key]

        logger.debug(
            "Found entry for %(key)s at %(legacy_key)s: %(value)s",
            {"key": key, "legacy_key": legacy_key, "value": value},
        )

        return value
    except (ConfigError, KeyError):
        return default
