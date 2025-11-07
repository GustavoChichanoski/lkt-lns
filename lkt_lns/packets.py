# keep your existing enums, helpers, and functions (not repeated here for brevity)
import enum
from typing import override
from pydantic import BaseModel, Field

UDP_IP = "0.0.0.0"
UPLINK_PORT = 1730  # uplink PUSH_DATA
DOWNLINK_PORT = 1700  # downlink PULL_DATA


class MessageType(enum.IntEnum):
    JOIN_REQUEST = 0
    JOIN_ACCEPT = 1
    UNCONFIRMED_UP = 2
    UNCONFIRMED_DOWN = 3
    CONFIRMED_UP = 4
    CONFIRMED_DOWN = 5
    REJOIN_REQUEST = 6
    PROPRIETARY = 7


class Direction(enum.IntEnum):
    UP = 0
    DOWN = 1


class DataRate(enum.StrEnum):
    DR_0 = "SF12BW125"
    DR_1 = "SF11BW125"
    DR_2 = "SF10BW125"
    DR_3 = "SF9BW125"
    DR_4 = "SF8BW125"
    DR_5 = "SF7BW125"
    DR_6 = "SF8BW500"
    DR_7 = "SF12BW500"
    DR_8 = "SF12BW500"
    DR_9 = "SF11BW500"
    DR_10 = "SF10BW500"
    DR_11 = "SF9BW500"
    DR_12 = "SF8BW500"
    DR_13 = "SF7BW500"

    def get_bw(self) -> int:
        return int(self.value.split("BW")[1]) * 1000

    def get_sf(self) -> int:
        return int(self.value.split("BW")[0].split("SF")[1])

    @classmethod
    def from_str(cls, value: str) -> "DataRate":
        return cls(value)


class GatewayPacketType(enum.IntEnum):
    PKT_PUSH_DATA = 0
    PKT_PUSH_ACK = 1
    PKT_PULL_DATA = 2
    PKT_PULL_RESP = 3
    PKT_PULL_ACK = 4
    PKT_TX_ACK = 5

    @override
    def __str__(self):
        return self.name


class Txpk(BaseModel):
    imme: bool = Field(False, description="Immediate transmission flag")
    tmst: int = Field(0, description="Internal timestamp of the packet (microseconds)")
    tmms: int | None = Field(None, description="GPS time in milliseconds since epoch")
    freq: float = Field(916.2, description="TX central frequency in MHz")
    rfch: int = Field(0, description="Concentrator RF chain used for TX")
    powe: int = Field(12, description="TX power in dBm")
    datr: str = Field("SF10BW500", description="Datarate identifier (e.g., SF10BW125)")
    modu: str = Field("LORA", description="Modulation type, e.g., LORA or FSK")
    codr: str = Field("4/5", description="Coding rate identifier (e.g., 4/5)")
    ipol: bool = Field(False, description="Invert the signal polarity")
    size: int = Field(0, description="Size of the payload in bytes")
    data: str = Field("", description="Payload data")

    def __init__(
        self,
        imme: bool = False,
        tmst: int = 0,
        tmms: int = 0,
        freq: float = 916.2,
        rfch: int = 0,
        powe: int = 12,
        datr: str = "SF10BW500",
        modu: str = "LORA",
        codr: str = "4/5",
        ipol: bool = False,
        size: int = 0,
        data: str = "",
    ) -> None:
        super().__init__(
            imme=imme,
            tmst=tmst,
            tmms=tmms,
            freq=freq,
            rfch=rfch,
            powe=powe,
            datr=datr,
            modu=modu,
            codr=codr,
            ipol=ipol,
            size=size,
            data=data,
        )


class Rxpk(BaseModel):
    jver: int = Field(1, description="JSON version of the packet structure")
    tmst: int = Field(
        ..., description="Internal timestamp of the received packet (microseconds)"
    )
    tmms: int | None = Field(None, description="GPS time in milliseconds since epoch")
    chan: int = Field(..., description="Concentrator IF channel used for RX")
    rfch: int = Field(..., description="Concentrator RF chain used for RX")
    freq: float = Field(..., description="RX central frequency in MHz")
    mid: int = Field(..., description="Unique message identifier")
    stat: int = Field(..., description="CRC status: 1 = OK, -1 = fail, 0 = no CRC")
    modu: str = Field(..., description="Modulation type, e.g., LORA or FSK")
    datr: str = Field(..., description="Datarate identifier (e.g., SF10BW125)")
    codr: str = Field(..., description="Error coding rate (e.g., 4/5)")
    rssis: float = Field(..., description="RSSI at antenna connector in dBm")
    lsnr: float = Field(..., description="SNR in dB")
    foff: int = Field(..., description="Frequency offset in Hz")
    rssi: float = Field(..., description="RSSI in dBm")
    size: int = Field(..., description="Payload size in bytes")
    data: str = Field(..., description="Base64 encoded payload")


class GatewayPacket(BaseModel):
    rxpk: list[Rxpk] = Field(..., description="List of received packet(s)")


class UplinkPacket(BaseModel):
    rxpk: list[Rxpk] = Field(..., description="List of received packet(s)")


UPLINK_FREQUENCIES = [f"{915.2 + i * 0.2:.1f}" for i in range(8)]
DOWNLINK_FREQUENCIES = [f"{923.3 + i * 0.6:.1f}" for i in range(8)]
