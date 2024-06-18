import argparse
import logging

from anyio import create_tcp_listener, run
import config

from src.milter import handle

from src import services
from src.utils import get_config_value


async def main():
    parser = argparse.ArgumentParser(
        prog="dmarcation",
        description="Milter handler for adjusting addresses for DMARC purposes"
    )
    parser.add_argument("-c", "--config-file", default="/etc/dmarcation.cfg", type=argparse.FileType())
    parser.add_argument("-p", "--port")

    args = parser.parse_args()

    # Load the configuration
    app_config = config.Config(args.config_file)

    # Set up the services registry
    services["app_config"] = app_config

    # Set up the root logger
    logging.basicConfig(level=get_config_value(app_config, "log.level", logging.WARNING))

    listen_port = args.port or get_config_value(app_config, "milter_port", 1999)
    listener = await create_tcp_listener(local_port=listen_port)
    await listener.serve(handle)


if __name__ == "__main__":
    run(main)
