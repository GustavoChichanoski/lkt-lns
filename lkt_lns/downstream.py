import datetime
import json
import logging
import queue
import random
import socket
import time
from typing import Never

from lkt_utils.devices import EverynetDevice
from paho.mqtt.client import Client
from rich.panel import Panel

from lkt_lns.helpers import build_pull_resp, parse_uplink
from lkt_lns.messages import (
    EveryNetMqttMessage,
    Meta,
    ParamsDownlinkResponse,
    TypeMessages,
)
from lkt_lns.packets import GatewayPacketType, Txpk

TIME_STR = "%Y-%m-%d %H:%M:%S"
UDP_IP = "0.0.0.0"
UPLINK_PORT = 1730  # uplink PUSH_DATA
DOWNLINK_PORT = 1700  # downlink PULL_DATA


def downlink_response2downstream(
    message: EveryNetMqttMessage, device: EverynetDevice, gateway: str
) -> dict[str, str]:
    new_message = EveryNetMqttMessage()
    new_message.type_message = TypeMessages.DOWNLINK_RESPONSE
    new_message.meta = Meta()
    new_message.meta.application = device.app_eui or ""
    new_message.meta.device = device.dev_eui or ""
    new_message.meta.device_addr = device.dev_addr or ""
    new_message.meta.gateway = gateway
    new_message.meta.packet_hash = message.meta.packet_hash
    new_message.meta.packet_id = random.randbytes(16).hex()
    new_message.meta.time = datetime.datetime.now().timestamp()
    new_message.meta.outdated = False

    if not isinstance(message.params, ParamsDownlinkResponse):
        return {"status": "error", "message": "Invalid message type"}

    return {"status": "success"}


def downstream_task(queue: queue.Queue[tuple[Txpk, int]], mqtt: Client) -> Never:
    sock_down = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock_down.bind((UDP_IP, DOWNLINK_PORT))
    logging.info("[magenta]📡 Downstream thread started[/magenta]")

    while True:
        data, addr = sock_down.recvfrom(4096)  # pyright: ignore[reportAny]
        _, token, ptype, gw_id, _ = parse_uplink(data)
        now = int(time.time())
        timestamp = datetime.datetime.fromtimestamp(now).strftime(TIME_STR)

        logging.info(
            f"{timestamp} 📥 Downlink from {addr}, 🔑 Token: {token.hex(':')}, 🏷️ Gateway: {gw_id}, 📦 Type: {ptype}"
        )

        if ptype == GatewayPacketType.PKT_TX_ACK:
            logging.debug("Downlink sent to device")
            continue

        while ptype == GatewayPacketType.PKT_PULL_DATA and not queue.empty():
            time.sleep(0.1)
            downlink, tmms = queue.get()
            now = time.time()

            delay = tmms - now
            if 1 < delay:
                queue.put((downlink, tmms))
                continue
            elif delay < 0:
                logging.warning("Lost windows to send downlink")
                continue

            logging.info(
                Panel(json.dumps(downlink, indent=2), title="TXPK JSON", style="purple")
            )

            downlink = build_pull_resp(bytearray(token), gw_id, downlink)

            _ = sock_down.sendto(downlink, addr)  # pyright: ignore[reportAny]
            logging.info("[bold green]📤 Downlink sent![/bold green]")
            break
