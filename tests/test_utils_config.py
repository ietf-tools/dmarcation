from config import Config
from io import StringIO

from src.utils.config import get_config_value


config = Config(StringIO("""
dmarc: {
    subkey: "subkey"
    toplevel: "error"
}

toplevel: "toplevel"
"""))


def test_get_config_value_uses_top_level_first():
    """
    The top level key should be returned if present.
    """
    assert get_config_value(config, "toplevel") == "toplevel"


def test_get_config_value_falls_back_to_dmarc():
    """
    The key under dmarc should be returned if present and there is no top level key.
    """
    assert get_config_value(config, "subkey") == "subkey"


def test_get_config_value_returns_a_default():
    """
    The default should be returned if there is no top level key or one under dmarc.
    """
    assert get_config_value(config, "nosuchkey") is None
    assert get_config_value(config, "nosuchkey", "default") == "default"
