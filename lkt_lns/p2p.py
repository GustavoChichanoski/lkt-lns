import base64
import logging

from lkt_lns.packets import Rxpk, Txpk


# --- PEER TO PEER LOGIC ---
class Peer2Peer:
    @staticmethod
    def build_downlink(cnt: int, lora_id: bytes, data: bytes) -> tuple[str, int]:
        payload_data = bytearray()
        payload_data.extend(cnt.to_bytes(1, "little"))
        payload_data.extend(lora_id)
        payload_data.extend(data)
        # Return base64 encoded bytes and raw payload length
        return base64.b64encode(payload_data).decode(), len(payload_data)

    @staticmethod
    def parse_downlink(
        rxpk: Rxpk,
        freq: float = 904.0,
        datarate: str = "SF11BW500",
        payload: bytes = b"0123456789",
    ) -> Txpk | None:
        raw = base64.b64decode(rxpk.data)
        if len(raw) < 4:
            logging.warning("[red]Invalid[/red] P2P downlink")
            return
        txpk = Txpk()
        cnt = raw[0]
        lora_id = raw[1:4]
        txpk.tmst = rxpk.tmst + 1_000_000
        txpk.tmms = (rxpk.tmms or 0) + 1
        logging.info(f"P2P: cnt: {cnt}, lora_id: {lora_id}, data: {raw[4:].hex()}")
        txpk.data, txpk.size = Peer2Peer.build_downlink(cnt, lora_id, payload)
        txpk.freq = freq
        txpk.datr = datarate
        txpk.ipol = False
        return txpk
