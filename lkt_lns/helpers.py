import base64
import struct

from Crypto.Cipher import AES
from Crypto.Hash import CMAC

from lkt_lns.packets import (
    DOWNLINK_FREQUENCIES,
    UPLINK_FREQUENCIES,
    Direction,
    GatewayPacketType,
    Rxpk,
    Txpk,
)


def uplink_freq_to_downlink_freq(freq: float) -> float:
    return float(DOWNLINK_FREQUENCIES[UPLINK_FREQUENCIES.index(f"{freq:.1f}")])


def update_downlink(downlink: bytes, token: bytearray) -> bytes:
    """Update downlink ACK packet"""
    dl = bytearray(downlink)
    dl[1] = token[0]
    dl[2] = token[1]
    return bytes(dl)


def lorawan_encrypt(
    application_session_key: bytes,
    dev_addr: bytes,
    fcnt: int,
    direction: int,
    data: bytes,
) -> bytes:
    """
    Encrypt FRMPayload with LoRaWAN spec (AppSKey for downlinks).
    https://lora-alliance.org/wp-content/uploads/2020/11/2015_-_lorawan_specification_1r0_611_1.pdf
    page 23
    """
    dev_addr_le = dev_addr[::-1]
    size = len(data)
    s = b""
    block_num = 1
    while size > 0:
        ai = (
            b"\x01\x00\x00\x00\x00"
            + struct.pack("<B", direction)
            + dev_addr_le
            + struct.pack("<I", fcnt)
            + b"\x00"
            + struct.pack("<B", block_num)
        )
        block = AES.new(application_session_key, AES.MODE_ECB).encrypt(ai)  # pyright: ignore[reportUnknownMemberType]
        s += block[: min(16, size)]
        size -= 16
        block_num += 1
    return bytes([d ^ s[i] for i, d in enumerate(data)])


def lorawan_mic(
    network_session_key: bytes, dev_addr: bytes, fcnt: int, direction: int, msg: bytes
) -> bytes:
    """Compute MIC (AES-CMAC with NwkSKey)."""
    dev_addr_le = dev_addr[::-1]
    b0 = (
        b"\x49\x00\x00\x00\x00"
        + struct.pack("<B", direction)
        + dev_addr_le
        + struct.pack("<I", fcnt)
        + b"\x00"
        + struct.pack("<B", len(msg))
    )
    cmac = CMAC.new(network_session_key, ciphermod=AES)
    _ = cmac.update(b0 + msg)
    return cmac.digest()[:4]


def build_p2p_downlink(cnt: int, lora_id: bytes, data: bytes) -> str:
    payload_data = bytearray()
    payload_data.extend(cnt.to_bytes(1, "little"))
    payload_data.extend(lora_id)
    payload_data.extend(data)
    return base64.b64encode(payload_data).decode()


def lorawan_decrypt(
    payload: bytes, key: bytes, dev_addr: str, f_cnt: int, direction: int
):
    aes = AES.new(key, AES.MODE_ECB)  # pyright: ignore[reportUnknownMemberType]
    size = len(payload)
    s_value = b""
    i = 1
    while len(s_value) < size:
        ai = (
            b"\x01\x00\x00\x00\x00"
            + bytes([direction])
            + bytes.fromhex(dev_addr)[::-1]
            + f_cnt.to_bytes(4, "little")
            + b"\x00"
            + bytes([i])
        )
        si_value = aes.encrypt(ai)
        s_value += si_value
        i += 1
    return bytes([a ^ b for a, b in zip(payload, s_value)])


def build_lorawan_downlink(
    dev_addr_hex: str,
    network_session_key_hex: str,
    application_session_key_hex: str,
    payload: bytes,
    fcnt: int = 1,
    fport: int = 1,
    confirmed: bool = False,
) -> str:
    """Build LoRaWAN PHYPayload (Base64 encoded)."""
    dev_addr = bytes.fromhex(dev_addr_hex)
    nwk_session_key = bytes.fromhex(network_session_key_hex)
    app_session_key = bytes.fromhex(application_session_key_hex)

    # MHDR (1 byte)
    mhdr = b"\xa0" if confirmed else b"\x60"  # Confirmed=4, Unconfirmed=2 (downlink)

    # FHDR (DevAddr LE + FCtrl + FCnt)
    f_ctrl = 0x00
    fhdr = dev_addr[::-1] + struct.pack("<B", f_ctrl) + struct.pack("<H", fcnt)

    # Encrypt payload
    frm_payload = lorawan_encrypt(
        app_session_key, dev_addr, fcnt, Direction.DOWN, payload
    )

    # MACPayload = FHDR + FPort + FRMPayload
    mac_payload = fhdr + struct.pack("<B", fport) + frm_payload

    # MIC
    mic = lorawan_mic(nwk_session_key, dev_addr, fcnt, 1, mhdr + mac_payload)

    # PHYPayload
    phy = mhdr + mac_payload + mic
    return base64.b64encode(phy).decode()


def generate_header(
    version: bytes,
    token: bytearray,
    pkt_type: GatewayPacketType,
    gateway_id: str,
) -> bytes:
    return version + token + struct.pack("!B", pkt_type) + bytes.fromhex(gateway_id)


def parse_uplink(
    data: bytes,
) -> tuple[bytes, bytearray, GatewayPacketType, str, Rxpk | None]:
    """Parse raw packet into header + JSON payload"""
    version = data[0]
    token = bytearray(data[1:3])
    ptype = GatewayPacketType(data[3])
    gateway_id = data[4:12].hex()

    payload = None
    if len(data) > 12:
        try:
            payload = Rxpk.model_validate_json(data[12:])
        except Exception:
            payload = None

    return bytes(version), token, ptype, gateway_id, payload


def build_pull_resp(
    token: bytearray,
    gateway_id: str,
    downlink: Txpk,
) -> bytes:
    """Wrap LoRaWAN downlink in Semtech PULL_RESP."""
    version = b"\x02"
    pkt_type = b"\x03"  # PULL_RESP
    header = version + token + pkt_type + bytes.fromhex(gateway_id)
    return header + (downlink.model_dump_json().replace(" ", "")).encode()
