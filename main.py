import random
import threading
import logging

from paho.mqtt.client import Client

from paho.mqtt.enums import CallbackAPIVersion, MQTTProtocolVersion
from rich.console import Console
from rich.logging import RichHandler

from lkt_utils.everynet_http import EveryNetHTTP
from lkt_lns.configs import Config
from lkt_lns.upstream import upstream_thread


def main():
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger()
    logger.handlers.clear()
    rich_handler = RichHandler(
        console=Console(),  # Pass the Rich Console object
        level=logging.DEBUG,  # Default level for the handler
        show_time=False,  # Optional: Hide time in the log
        show_level=True,  # Show the log level
        show_path=True,  # Hide the source file path
        markup=True,  # Allow rich markup in the messages
    )
    logger.addHandler(rich_handler)

    config: Config = Config.parse_file("config.json")  # pyright: ignore[reportDeprecated]
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
