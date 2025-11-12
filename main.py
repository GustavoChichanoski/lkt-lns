import logging
import pathlib
import random
import threading

import click
from lkt_utils.everynet_http import EveryNetHTTP
from paho.mqtt.client import Client
from paho.mqtt.enums import CallbackAPIVersion, MQTTProtocolVersion
from rich.console import Console
from rich.logging import RichHandler

from lkt_lns.configs import Config
from lkt_lns.upstream import upstream_thread


@click.command()  # 2. Decorate main as a click command
@click.option(
    "--config-path",  # Define the command-line option name
    type=click.Path(
        exists=True, dir_okay=False, path_type=pathlib.Path
    ),  # Ensure it's a file path that exists
    default="config.json",  # Set the default value
    help="Path to the configuration JSON file.",
)
def main(config_path: pathlib.Path):
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger()
    logger.handlers.clear()
    rich_handler = RichHandler(
        console=Console(),  # Pass the Rich Console object
        level=logging.INFO,  # Default level for the handler
        show_time=False,  # Optional: Hide time in the log
        show_level=True,  # Show the log level
        show_path=True,  # Hide the source file path
        markup=True,  # Allow rich markup in the messages
    )
    logger.addHandler(rich_handler)

    config: Config = Config.model_validate_json(config_path.read_text())  # pyright: ignore[reportCallIssue, reportUndefinedVariable]
    everynet_http = EveryNetHTTP(config.everynet.url, config.everynet.token)

    mqtt: Client = Client(
        CallbackAPIVersion.VERSION2,
        f"TEST_{random.randint(100000, 999999)}",
        protocol=MQTTProtocolVersion.MQTTv5,
    )
    mqtt.tls_set()  # pyright: ignore[reportUnknownMemberType]
    mqtt.username_pw_set(config.mqtt.username, config.mqtt.password)

    err = mqtt.connect(config.mqtt.host, config.mqtt.port, 60)
    if err != 0:
        logger.error(f"Failed to connect to MQTT broker: {err.name}")
        return

    err = mqtt.loop_start()
    if err != 0:
        logger.error(f"Failed to start MQTT loop: {err.name}")
        return

    thread_upstream = threading.Thread(
        target=upstream_thread,
        args=(everynet_http, mqtt, config.mqtt.topics.subscriber),
    )
    thread_upstream.start()

    thread_upstream.join()
    _ = mqtt.loop_stop()


if __name__ == "__main__":
    main()
