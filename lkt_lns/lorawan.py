import base64
import logging
import struct

from Crypto.Cipher import AES
from Crypto.Hash import CMAC

from lkt_lns.packets import (
    DOWNLINK_FREQUENCIES,
    UPLINK_FREQUENCIES,
    Direction,
    Rxpk,
    Txpk,
)


class LoRaWAN:
    @staticmethod
    def encrypt(
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

    @staticmethod
    def decrypt(
        payload: bytes,
        app_session_key: bytes,
        dev_addr: str,
        f_cnt: int,
        direction: int,
    ) -> bytes:
        aes = AES.new(app_session_key, AES.MODE_ECB)  # pyright: ignore[reportUnknownMemberType]
        size = len(payload)
        s_value = b""
        i = 1
        while len(s_value) < size:
            Ai = (
                b"\x01\x00\x00\x00\x00"
                + bytes([direction])
                + bytes.fromhex(dev_addr)[::-1]
                + f_cnt.to_bytes(4, "little")
                + b"\x00"
                + bytes([i])
            )
            si_value = aes.encrypt(Ai)
            s_value += si_value
            i += 1
        return bytes([a ^ b for a, b in zip(payload, s_value)])

    @staticmethod
    def mic(
        network_session_key: bytes,
        dev_addr: bytes,
        fcnt: int,
        direction: int,
        msg: bytes,
    ) -> bytes:
        """Compute MIC (AES-CMAC with NwkSKey)."""
        dev_addr_le = dev_addr[::-1]
        B0 = (
            b"\x49\x00\x00\x00\x00"
            + struct.pack("<B", direction)
            + dev_addr_le
            + struct.pack("<I", fcnt)
            + b"\x00"
            + struct.pack("<B", len(msg))
        )
        cmac = CMAC.new(network_session_key, ciphermod=AES)
        _ = cmac.update(B0 + msg)
        return cmac.digest()[:4]

    @staticmethod
    def downlink_freq(freq: float) -> float:
        return float(DOWNLINK_FREQUENCIES[UPLINK_FREQUENCIES.index(f"{freq:.1f}")])

    @staticmethod
    def build_downlink(
        dev_addr_hex: str,
        network_session_key_hex: str,
        application_session_key_hex: str,
        payload: bytes,
        fcnt: int = 1,
        fport: int = 1,
        confirmed: bool = False,
    ) -> tuple[str, int]:
        """Build LoRaWAN PHYPayload (Base64 encoded)."""
        dev_addr = bytes.fromhex(dev_addr_hex)
        nwk_session_key = bytes.fromhex(network_session_key_hex)
        app_session_key = bytes.fromhex(application_session_key_hex)

        # MHDR (1 byte)
        mhdr = (
            b"\xa0" if confirmed else b"\x60"
        )  # Confirmed=4, Unconfirmed=2 (downlink)

        # FHDR (DevAddr LE + FCtrl + FCnt)
        f_ctrl = 0x00
        fhdr = dev_addr[::-1] + struct.pack("<B", f_ctrl) + struct.pack("<H", fcnt)

        # Encrypt payload
        frm_payload = LoRaWAN.encrypt(
            app_session_key, dev_addr, fcnt, Direction.DOWN, payload
        )

        # MACPayload = FHDR + FPort + FRMPayload
        mac_payload = fhdr + struct.pack("<B", fport) + frm_payload

        # MIC
        mic = LoRaWAN.mic(nwk_session_key, dev_addr, fcnt, 1, mhdr + mac_payload)

        # PHYPayload
        phy = mhdr + mac_payload + mic
        return (base64.b64encode(phy).decode(), len(phy))

    @staticmethod
    def parse_downlink(
        dev_addr: str,
        network_session_key: str,
        application_session_key: str,
        fcnt: int,
        rxpk: Rxpk,
        payload: bytes,
    ) -> Txpk | None:
        # LoRaWAN downlink
        fcnt += 1
        txpk = Txpk(freq=LoRaWAN.downlink_freq(rxpk.freq))

        try:
            phy_raw = base64.b64decode(rxpk.data)
        except Exception as e:
            logging.error(f"[red]❌ Failed to decode Base64 data: {e}[/red]")
            return None

        # Minimum packet size check (MHDR + DevAddr + FCnt + MIC = 1 + 4 + 2 + 4 = 11 bytes)
        if len(phy_raw) < 12:
            logging.error(f"[red]❌ Invalid packet length: {len(phy_raw)} bytes[/red]")
            return None

        # DevAddr (4 bytes, little-endian) starts at index 1
        uplink_dev_addr_le = phy_raw[1:5]
        # Convert to big-endian hex string
        uplink_dev_addr_hex = uplink_dev_addr_le[::-1].hex()

        # FCnt (2 bytes, little-endian) starts at index 6
        uplink_fcnt_raw = phy_raw[6:8]
        uplink_fcnt = struct.unpack("<H", uplink_fcnt_raw)[0]  # pyright: ignore[reportAny]

        # FPort is at index 8 (assuming FOptsLen=0)
        fport_index = 8
        uplink_fport = phy_raw[fport_index]

        # FRMPayload starts at index 9 and ends 4 bytes before the end (MIC)
        frm_payload_encrypted = phy_raw[fport_index + 1 : -4]
        logging.info(
            f"[yellow]DevAddr in packet: {uplink_dev_addr_hex}, FCnt: {uplink_fcnt}, FPort: {uplink_fport}[/yellow]"
        )

        if not uplink_fport or not frm_payload_encrypted:
            logging.info(
                "[yellow]No application payload (FPort 0 or empty FRMPayload).[/yellow]"
            )
            return
        # Use the hardcoded AppSKey for decryption
        app_session_key_bytes = bytes.fromhex(application_session_key)

        decrypted_payload = LoRaWAN.decrypt(
            frm_payload_encrypted,
            app_session_key_bytes,
            uplink_dev_addr_hex,
            uplink_fcnt,  # pyright: ignore[reportAny]
            Direction.UP.value,  # 0 for UP
        )
        logging.info(
            f"[bold green]Decrypted Application Payload (Hex)[/bold green]: {decrypted_payload.hex()}",
        )

        fcnt += 1

        # Schedule the downlink (RX1 window)
        # Typically tmst is 5 seconds after the uplink for RX1
        txpk.tmst = rxpk.tmst + 5_000_000  # 5,000,000 us = 5 seconds
        txpk.tmms = txpk.tmms or 0 + 5_000

        print(
            f"LoRaWAN: Downlink Fcnt: {fcnt}, Freq: {txpk.freq} MHz, Scheduled TMST: {txpk.tmst} us"
        )

        txpk.ipol = True
        txpk.datr = "SF10BW500"
        txpk.data, txpk.size = LoRaWAN.build_downlink(
            dev_addr,
            network_session_key,
            application_session_key,
            payload,
            fcnt=fcnt,
            fport=57,
        )
        return txpk
