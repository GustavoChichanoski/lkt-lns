import base64
import datetime
import hashlib
import json
import logging
import random
import socket
import struct
import time

from lkt_utils.devices import EverynetDevice
from lkt_utils.everynet_http import EveryNetColumn, EveryNetHTTP
from paho.mqtt.client import Client

from lkt_lns.messages import (
    EveryNetMqttMessage,
    ParamsLoRa,
    ParamsUplink,
    Radio,
    RadioModulation,
    TypeMessages,
)

from .helpers import generate_header
from .lorawan import LoRaWAN
from .packets import (
    UDP_IP,
    UPLINK_PORT,
    DataRate,
    Direction,
    GatewayPacketType,
    Rxpk,
    Txpk,
    UplinkPacket,
)


def build_downlink(
    tmst: float,
    phy_b64: str,
    freq: float,
    bw: int,
    sf: int,
    tmms: int,
    ipol: bool,
) -> Txpk:
    _ = tmms  # Not used, but kept for context

    # 1. Create the dictionary with the required TXPK data,
    #    nested under the 'txpk' key as per Semtech Packet Forwarder spec.
    packet_data = {
        "txpk": {
            "imme": False,
            "tmst": int(tmst),
            # "tmms": tmms, # Excluded for now as per your original code
            "freq": freq,
            "rfch": 0,
            "powe": 12,
            "modu": "LORA",
            "datr": f"SF{sf}BW{bw}",
            "codr": "4/5",
            "ipol": ipol,  # p2p false, lrw true
            "size": len(base64.b64decode(phy_b64)),
            "data": phy_b64,
        }
    }

    # 2. Extract the INNER dictionary (the Txpk fields) and pass it to model_validate.
    #    This is the crucial change.
    txpk_fields = packet_data["txpk"]

    # NOTE: You can also use Txpk(**txpk_fields) if you don't need a specific Pydantic validation mode
    return Txpk.model_validate(txpk_fields)


def parse_uplink(
    data: bytes,
) -> tuple[
    bytes,
    bytearray,
    GatewayPacketType,
    str,
    UplinkPacket | None,
]:
    """Parse raw packet into header + JSON payload"""
    version = data[0]
    token = bytearray(data[1:3])
    ptype = GatewayPacketType(data[3])
    gateway_id = data[4:12].hex()

    payload = None
    if len(data) > 12:
        try:
            payload = UplinkPacket.model_validate_json(data[12:])
        except Exception:
            payload = None

    return bytes(version), token, ptype, gateway_id, payload


def rxpk2everynet(
    rxpk: Rxpk,
    gateway_id: str,
    port: int,
    counter: int,
    device: EverynetDevice,
    payload: str,
) -> EveryNetMqttMessage:
    """Convert a LoRaWAN Txpk to Everynet format"""
    message = EveryNetMqttMessage()
    message.type_message = TypeMessages.UPLINK
    message.meta.gateway = gateway_id
    message.meta.application = device.app_eui or ""
    message.meta.device = device.dev_eui or ""
    message.meta.device_addr = device.dev_addr or ""
    message.meta.time = datetime.datetime.now().timestamp()
    message.meta.packet_id = hashlib.sha256(
        rxpk.model_dump_json(exclude_none=True).encode()
    ).hexdigest()[:16]
    message.meta.packet_hash = random.randbytes(16).hex()
    message.params = ParamsUplink()
    message.params.payload = payload
    message.params.port = port
    message.params.rx_time = rxpk.tmst
    message.params.duplicate = False
    message.params.counter_up = counter
    message.params.encrypted_payload = rxpk.data

    datarate = DataRate.from_str(rxpk.datr)
    message.params.radio = Radio()
    message.params.radio.delay = 0.0
    message.params.radio.freq = rxpk.freq
    message.params.radio.size = rxpk.size

    message.params.radio.modulation = RadioModulation()
    message.params.radio.modulation.coderate = rxpk.codr
    message.params.radio.modulation.bandwidth = datarate.get_bw()
    message.params.radio.modulation.spreading = datarate.get_sf()
    message.params.radio.modulation.type = rxpk.modu

    message.params.radio.hardware.status = 1
    message.params.radio.hardware.chain = 0
    message.params.radio.hardware.tmst = rxpk.tmst
    message.params.radio.hardware.snr = rxpk.lsnr
    message.params.radio.hardware.rssi = rxpk.rssi
    message.params.radio.hardware.channel = rxpk.chan
    message.params.radio.hardware.chain = rxpk.rfch

    message.params.lora = ParamsLoRa()
    message.params.lora.class_b = False
    message.params.lora.confirmed = False
    message.params.lora.lora_type = 2
    message.params.lora.adr = False
    message.params.lora.adr_ack_req = False
    message.params.lora.ack = False
    message.params.lora.version = 1

    return message


def update_devices(everynet_http: EveryNetHTTP) -> dict[str, EverynetDevice]:
    """Fetch the current device mapping from Everynet."""
    try:
        devices = everynet_http.get_by(None, None)
        logging.info(f"[green]✅ Updated device list ({len(devices)} devices)[/green]")
        return devices
    except Exception as e:
        logging.error(f"[red]❌ Failed to update device list:[/red] {e}")
        return {}


def upstream_thread(everynet_http: EveryNetHTTP, mqtt: Client, publish: str) -> None:
    """Listen for uplink packets and handle Everynet/LoRaWAN processing."""
    sock_up = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock_up.bind((UDP_IP, UPLINK_PORT))
    sock_up.settimeout(60.0)

    fcnt = 0
    logging.info("[cyan]📡 Uplink thread started[/cyan]")

    devices = update_devices(everynet_http)
    logging.debug(list(devices.keys()))
    last_update_time = time.time()

    while True:
        try:
            data, addr = sock_up.recvfrom(4096)
        except Exception as e:
            logging.error(f"[red]❌ Socket error:[/red] {e}")
            continue

        try:
            version, token_up, ptype, gw_id, payload = parse_uplink(data)
        except Exception as e:
            logging.warning(f"[yellow]⚠️ Failed to parse uplink:[/yellow] {e}")
            continue

        # Refresh devices periodically even with normal traffic
        if time.time() - last_update_time > 60:
            devices = update_devices(everynet_http)
            last_update_time = time.time()

        if ptype != GatewayPacketType.PKT_PUSH_DATA:
            continue

        # Send ACK
        try:
            _ = sock_up.sendto(
                generate_header(
                    version, token_up, GatewayPacketType.PKT_PUSH_ACK, gw_id
                ),
                addr,
            )
        except Exception as e:
            logging.error(f"[red]❌ Failed to send ACK:[/red] {e}")
            continue

        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logging.debug(
            f"{now} 📤 Uplink from {addr}, 🔑 Token: {token_up.hex(':')}, 🏷️ Gateway: {gw_id}, 📦 Type: {ptype}"
        )

        if not payload:
            continue

        logging.debug(f"rxpk: {payload.model_dump_json(indent=2)}")

        rx = payload.rxpk[-1]
        freq = rx.freq
        tmst = rx.tmst
        tmms = rx.tmms

        if freq < 903.5:
            # Handle P2P downlink
            raw = base64.b64decode(rx.data)
            if len(raw) < 4:
                logging.error("[red]Invalid P2P downlink[/red]")
                continue
            cnt = raw[0]
            lora_id = raw[1:4]
            tmst += 1_000_000
            tmms = (tmms or 0) + 1
            logging.info(
                f"P2P: cnt={cnt}, lora_id={lora_id.hex()}, data={raw[4:].hex()}"
            )
            continue

        # LoRaWAN downlink
        fcnt += 1
        freq = LoRaWAN.downlink_freq(freq)

        phy_raw = base64.b64decode(rx.data)
        uplink_dev_addr_hex = phy_raw[1:5][::-1].hex()  # little → big endian
        uplink_fcnt = int(struct.unpack("<H", phy_raw[6:8])[0])  # pyright: ignore[reportAny]
        uplink_fport = phy_raw[8]
        frm_payload_encrypted = phy_raw[9:-4]

        logging.info(
            f"[yellow]DevAddr={uplink_dev_addr_hex}, FCnt={uplink_fcnt}, FPort={uplink_fport}[/yellow]"
        )

        if not uplink_fport or not frm_payload_encrypted:
            logging.warning(
                "[yellow]No application payload (FPort 0 or empty FRMPayload).[/yellow]"
            )
            continue

        if uplink_dev_addr_hex not in devices:
            logging.warning(f"[yellow]Unknown device {uplink_dev_addr_hex}[/yellow]")
            new_devices = everynet_http.get_by(
                EveryNetColumn.DEVICE_ADDRESS, uplink_dev_addr_hex
            )
            if uplink_dev_addr_hex not in new_devices:
                continue
            devices[uplink_dev_addr_hex] = new_devices[uplink_dev_addr_hex]

        device = devices[uplink_dev_addr_hex]
        app_session_key_bytes = bytes.fromhex(device.appskey or "")
        decrypted_payload = LoRaWAN.decrypt(
            frm_payload_encrypted,
            app_session_key_bytes,
            uplink_dev_addr_hex,
            uplink_fcnt,
            Direction.UP.value,
        )

        logging.debug(
            f"[bold green]Decrypted Application Payload:[/bold green] {decrypted_payload.hex()}"
        )

        fcnt += 1
        tmst += 5_000_000
        tmms = (tmms or 0) + 5
        logging.debug(f"LoRaWAN: fcnt={fcnt}, freq={freq}, tmst={tmst}")

        decrypted_payload_b64 = base64.b64encode(decrypted_payload).decode()

        everynet_msg = rxpk2everynet(
            rx, gw_id, uplink_fport, fcnt, device, decrypted_payload_b64
        ).to_dict()

        # logging.debug(f"Send {everynet_msg} at {datetime.datetime.now()} to {publish}")
        err = mqtt.publish(publish, json.dumps(everynet_msg), qos=0)
        if err.rc != 0:
            logging.error(f"MQTT publish error: {err.rc.name}")
