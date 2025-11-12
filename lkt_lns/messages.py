import abc
import time
from abc import abstractmethod
from enum import IntEnum, StrEnum
from typing import Any, TypeAlias, override

from lkt_utils.utils import try_bool, try_dict, try_float, try_int


class AbstractMqtt(abc.ABC):
    def __init__(self):
        pass

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:  # pyright: ignore[reportExplicitAny]
        return {}

    @classmethod
    @abstractmethod
    def from_dict(cls, data: dict[str, Any]) -> "AbstractMqtt":  # pyright: ignore[reportExplicitAny]
        return cls()


class MQTTPorts(IntEnum):
    """
    Enumeration of MQTT ports

    - TCP: standard MQTT port (1883)
    - TLS: secure MQTT port (8883)
    - WebSocket: WebSocket port for MQTT (8083)
    - SecureWebSocket: secure WebSocket port for MQTT (8084)
    """

    TCP = 1883
    TLS = 8883
    WebSocket = 8083
    SecureWebSocket = 8084


class TypeMessages(StrEnum):
    """
    Type of message sent and received through MQTT

    - DOWNLINK_REQUEST: sent to request a downlink data
    - DOWNLINK_RESPONSE: sent as response to a DOWNLINK_REQUEST
    - DOWNLINK: downlink data received from the network server
    - UPLINK: uplink data received from the device
    - ERROR: error message
    """

    DOWNLINK_REQUEST = "downlink_request"
    DOWNLINK_RESPONSE = "downlink_response"
    DOWNLINK = "downlink"
    UPLINK = "uplink"
    ERROR = "error"

    def to_type(self) -> type[AbstractMqtt]:
        """
        Return the corresponding parameter class type for the message type.

        :returns: The class type associated with the message type.
        :rtype: type

        :raises: ValueError: If the message type is not recognized.
        """

        match self:
            case TypeMessages.DOWNLINK_REQUEST:
                return ParamsDownlinkRequest
            case TypeMessages.DOWNLINK_RESPONSE:
                return ParamsDownlinkResponse
            case TypeMessages.DOWNLINK:
                return ParamsDownlink
            case TypeMessages.UPLINK:
                return ParamsUplink
            case TypeMessages.ERROR:
                return ParamsError
            case _:
                raise ValueError(f"Unknown message type: {self}")


class ParamsDownlinkRequest(AbstractMqtt):
    def __init__(
        self, counter_down: int = 0, max_size: int = 0, tx_time: float = 0.0
    ) -> None:
        super().__init__()
        self.counter_down: int = counter_down
        self.max_size: int = max_size
        self.tx_time: float = tx_time

    @override
    def to_dict(self) -> dict[str, int | float]:
        return {
            "counter_down": self.counter_down,
            "max_size": self.max_size,
            "tx_time": self.tx_time,
        }

    @override
    @classmethod
    def from_dict(cls, data: dict[str, int | float]) -> "ParamsDownlinkRequest":
        return cls(
            counter_down=int(data.get("counter_down", 0)),
            max_size=int(data.get("max_size", 0)),
            tx_time=data.get("tx_time", 0.0),
        )


DictGPS = dict[str, float]


class GPS(AbstractMqtt):
    def __init__(self, lat: float, lng: float):
        super().__init__()
        self.lat: float = lat
        self.lng: float = lng

    @override
    @classmethod
    def from_dict(cls, data: DictGPS | None) -> "GPS":
        if data is None:
            return cls(0.0, 0.0)
        return cls(data.get("lat", 0.0), data.get("lng", 0.0))

    @override
    def to_dict(self) -> DictGPS:
        return {"lat": self.lat, "lng": self.lng}


DictHardware = dict[str, int | float | DictGPS]

DictRadioModulation = dict[str, int | str]


class RadioModulation(AbstractMqtt):
    def __init__(
        self,
        bandwidth: int = 0,
        type: str = "LORA",
        coderate: str = "4/5",
        spreading: int = 10,
    ) -> None:
        super().__init__()
        self.bandwidth: int = bandwidth
        self.type: str = type
        self.coderate: str = coderate
        self.spreading: int = spreading

    @override
    @classmethod
    def from_dict(cls, data: DictRadioModulation) -> "RadioModulation":
        if not data:
            return cls()
        return cls(
            int(data.get("bandwidth", 0)),
            str(data.get("type", "LORA")),
            str(data.get("coderate", "4/5")),
            int(data.get("spreading", 10)),
        )

    @override
    def to_dict(self) -> DictRadioModulation:
        return {
            "bandwidth": self.bandwidth,
            "type": self.type,
            "coderate": self.coderate,
            "spreading": self.spreading,
        }


class Hardware(AbstractMqtt):
    def __init__(
        self,
        status: int = 0,
        chain: int = 0,
        tmst: int = 0,
        snr: int = 0,
        rssi: float = 0,
        channel: int = 0,
        gps: dict[str, float] | None = None,
    ):
        super().__init__()
        self.status: int = int(status)
        self.chain: int = int(chain)
        self.tmst: int = int(tmst)
        self.channel: int = int(channel)
        self.snr: float = float(snr)
        self.rssi: float = float(rssi)
        self.gps: GPS = GPS.from_dict(gps or {})

    @override
    @classmethod
    def from_dict(cls, data: DictHardware) -> "Hardware":
        return cls(
            try_int(data, "status", 0),
            try_int(data, "chain", 0),
            try_int(data, "tmst", 0),
            try_int(data, "snr", 0),
            try_float(data, "rssi", 0.0),
            try_int(data, "channel", 0),
            gps=try_dict(data, "gps", {}),
        )

    @override
    def to_dict(self) -> DictHardware:
        return {
            "status": self.status,
            "chain": self.chain,
            "tmst": self.tmst,
            "snr": self.snr,
            "rssi": self.rssi,
            "channel": self.channel,
            "gps": self.gps.to_dict(),
        }


DictRadio = dict[str, float | int | DictHardware | DictRadioModulation]


class Radio(AbstractMqtt):
    def __init__(
        self,
        freq: float = 0,
        datarate: int = 0,
        radio_time: float = 0,
        hardware: Hardware | None = None,
        modulation: RadioModulation | None = None,
        gps_time: float | None = None,
        delay: float | None = None,
        size: int | None = None,
    ) -> None:
        super().__init__()
        hardware = hardware or Hardware()
        self.freq: float = freq
        self.datarate: int = datarate
        self.radio_time: float = radio_time
        self.hardware: Hardware = hardware
        self.modulation: RadioModulation | None = modulation
        self.delay: float | None = delay
        self.gps_time: float = gps_time or time.time()
        self.size: int = size or 0

    @override
    def to_dict(
        self,
    ) -> DictRadio:
        data: DictRadio = {
            "freq": self.freq,
            "datarate": self.datarate,
            "time": self.radio_time,
        }
        if self.hardware:
            data["hardware"] = self.hardware.to_dict()
        if self.modulation:
            data["modulation"] = self.modulation.to_dict()
        return data

    @override
    @classmethod
    def from_dict(cls, data: DictRadio) -> "Radio":
        return cls(
            try_float(data, "freq", 0.0),
            try_int(data, "datarate", 0),
            try_float(data, "time", 0.0),
            Hardware.from_dict(try_dict(data, "hardware", {})),
            RadioModulation.from_dict(try_dict(data, "modulation", {})),
        )


DictParamsLoRa = dict[str, dict[str, bool | int] | list[dict[str, str]]]


class ParamsLoRa(AbstractMqtt):
    def __init__(
        self,
        class_b: bool = False,
        confirmed: bool = False,
        adr: bool = False,
        adr_ack_req: bool = False,
        ack: bool = False,
        version: int = 1,
        lora_type: int = 2,
        datarate: str = "SF12BW125",
    ) -> None:
        super().__init__()
        self.class_b: bool = class_b
        self.confirmed: bool = confirmed
        self.adr: bool = adr
        self.ack: bool = ack
        self.adr_ack_req: bool = adr_ack_req
        self.version: int = version
        self.lora_type: int = lora_type
        self.datarate: str = datarate

    @override
    @classmethod
    def from_dict(cls: type["ParamsLoRa"], data: DictParamsLoRa) -> "ParamsLoRa":
        if "header" not in data:
            return cls()
        header = data["header"]
        if not isinstance(header, dict):
            return cls()
        return cls(
            try_bool(header, "class_b", False),
            try_bool(header, "confirmed", False),
            try_bool(header, "adr", False),
            try_bool(header, "adr_ack_req", False),
            try_bool(header, "ack", False),
            try_int(header, "version", 1),
            try_int(header, "lora_type", 2),
            str(data.get("datarate", "SF12BW125")),
        )

    @override
    def to_dict(self) -> DictParamsLoRa:
        return {
            "header": {
                "class_b": self.class_b,
                "confirmed": self.confirmed,
                "adr": self.adr,
                "adr_ack_req": self.adr_ack_req,
                "ack": self.ack,
                "version": self.version,
                "lora_type": self.lora_type,
            },
            "mac_commands": [{}],
        }


DictParamsUplink = dict[str, float | int | str | DictRadio | DictParamsLoRa]


class ParamsUplink(AbstractMqtt):
    def __init__(
        self,
        port: int = 0,
        payload: str = "",
        encrypted_payload: str = "",
        rx_time: float = 0.0,
        counter_up: int = 0,
        radio: Radio | None = None,
        duplicate: bool = False,
        lora: ParamsLoRa | None = None,
    ):
        super().__init__()
        self.port: int = port
        self.payload: str = payload
        self.encrypted_payload: str = encrypted_payload
        self.rx_time: float = rx_time
        self.counter_up: int = counter_up
        self.radio: Radio | None = radio
        self.duplicate: bool = duplicate
        self.lora: ParamsLoRa | None = lora

    @override
    def to_dict(self) -> DictParamsUplink:
        data: DictParamsUplink = {
            "port": self.port,
            "rx_time": self.rx_time,
            "counter_up": self.counter_up,
            "payload": self.payload,
            "encrypted_payload": self.encrypted_payload,
            "duplicate": self.duplicate,
        }
        if self.radio:
            data["radio"] = self.radio.to_dict()
        if self.lora:
            data["lora"] = self.lora.to_dict()
        return data

    @override
    @classmethod
    def from_dict(cls, data: DictParamsUplink) -> "ParamsUplink":
        return cls(
            try_int(data, "port"),
            str(data.get("payload", "")),
            str(data.get("encrypted_payload", "")),
            try_float(data, "rx_time"),
            try_int(data, "counter_up"),
            radio=Radio.from_dict(try_dict(data, "radio", {})),
        )


DictDownlink = dict[str, int | str | float]


class ParamsDownlinkResponse(AbstractMqtt):
    def __init__(
        self,
        pending: bool | None = False,
        confirmed: bool | None = False,
        counter_down: int | None = 0,
        port: int | None = 1,
        payload: str | None = "",
        encrypted_payload: str | None = "",
        queue_if_late: bool | None = False,
    ):
        super().__init__()
        self.pending: bool = pending or False
        self.confirmed: bool = confirmed or False
        self.counter_down: int = counter_down or 0
        self.port: int = port or 1
        self.payload: str = payload or ""
        self.encrypted_payload: str = encrypted_payload or ""
        self.queue_if_late: bool = queue_if_late or False

    @override
    def to_dict(self) -> DictDownlink:
        return {
            "port": self.port,
            "payload": self.payload,
        }

    @override
    @classmethod
    def from_dict(cls, data: DictDownlink) -> "ParamsDownlinkResponse":
        inst = cls()
        keys = inst.__dict__.keys()
        for k in keys:
            if not k.startswith("_") and k in data:
                setattr(inst, k, data[k])
        return inst


class ParamsError(AbstractMqtt):
    def __init__(self, message: str | None = None, code: int | None = None):
        super().__init__()
        self.message: str = message or ""
        self.code: int = code or 0

    @override
    def to_dict(self) -> DictDownlink:
        return {"message": self.message, "code": self.code}

    @override
    @classmethod
    def from_dict(cls, data: DictDownlink) -> "ParamsError":
        return cls(str(data.get("message", "") or ""), try_int(data, "code"))


DictHardwareRadio = dict[str, int | float]


class HardwareRadio(AbstractMqtt):
    def __init__(
        self,
        status: int = 0,
        chain: int = 0,
        power: float = 0,
        tmst: int = 0,
        channel: int = 0,
    ):
        super().__init__()
        self.status: int = status
        self.chain: int = chain
        self.tmst: int = tmst
        self.channel: int = channel
        self.power: float = power

    @override
    def to_dict(self) -> DictHardwareRadio:
        return {
            "status": self.status,
            "chain": self.chain,
            "power": self.power,
            "tmst": self.tmst,
            "channel": self.channel,
        }

    @override
    @classmethod
    def from_dict(cls, data: DictHardwareRadio) -> "HardwareRadio":
        chain = try_int(data, "chain", 0)
        channel = try_int(data, "channel", 0)
        status = try_int(data, "status", 0)
        tmst = try_int(data, "tmst", 0)
        power = try_float(data, "power", 0.0)
        return cls(status, chain, power, tmst, channel)


DictModulation = dict[str, int | str | bool]


class Modulation(AbstractMqtt):
    def __init__(
        self,
        bandwidth: int = 0,
        modu: int = 0,
        coderate: str = "",
        spreading: int = 0,
        inverted: bool = False,
    ):
        super().__init__()
        self.bandwidth: int = bandwidth
        self.modu: int = modu
        self.spreading: int = spreading
        self.coderate: str = coderate
        self.inverted: bool = inverted

    @override
    @classmethod
    def from_dict(cls, data: DictModulation | None) -> "Modulation":
        """Create a Modulation object from a dict."""
        if data is None:
            return cls(0, 0, "", 0, False)

        return cls(
            bandwidth=try_int(data, "bandwidth", 0),
            modu=try_int(data, "type", 0),
            spreading=try_int(data, "spreading", 0),
            coderate=str(data.get("coderate", "") or ""),
            inverted=try_bool(data, "inverted", False),
        )

    @override
    def to_dict(self) -> DictModulation:
        return {
            "bandwidth": self.bandwidth,
            "type": self.modu,
            "coderate": self.coderate,
            "spreading": self.spreading,
            "inverted": self.inverted,
        }


DictRadioParams = dict[str, DictHardwareRadio | DictModulation]


class RadioParams(AbstractMqtt):
    """
    Radio parameters class

    Class to represent the radio parameters of a Everynet packet.

    :attr hardware: (HardwareRadio): Hardware radio parameters
    :attr modulation: (Modulation): Modulation parameters
    """

    def __init__(
        self,
        hardware: HardwareRadio | None = None,
        modulation: Modulation | None = None,
    ):
        super().__init__()
        self.hardware: HardwareRadio = hardware or HardwareRadio()
        self.modulation: Modulation = modulation or Modulation()

    @override
    def to_dict(self) -> DictRadioParams:
        """Convert radio parameters to a dictionary"""
        return {
            "modulation": self.modulation.to_dict(),
            "hardware": self.hardware.to_dict(),
        }

    @override
    @classmethod
    def from_dict(cls, data: DictRadioParams) -> "RadioParams":
        """
        Create a RadioParams object from a dictionary

        Args:
            data (dict): Dictionary with the parameters

        Returns:
            RadioParams: Radio parameters object
        """
        return cls(
            HardwareRadio.from_dict(try_dict(data, "hardware", {})),
            Modulation.from_dict(try_dict(data, "modulation", {})),
        )


DictParamsDownlink: TypeAlias = dict[str, float | str | DictRadioParams]


class ParamsDownlink(AbstractMqtt):
    """
    Downlink parameters class

    Class to represent the downlink parameters of a Everynet packet.

    Attributes:
        freq (float): Frequency of the downlink in Hz
        datarate (str): Data rate of the downlink
        time (float): Timestamp of the downlink in Unix time (seconds)
        radio (RadioParams): Radio parameters of the downlink
        payload (str): Payload of the downlink
    """

    def __init__(
        self,
        freq: float | None = None,
        datarate: str | None = None,
        time: float | None = None,
        payload: str | None = None,
        encrypted_payload: str | None = None,
        radio: RadioParams | None = None,
        port: int | None = None,
        counter_down: int | None = None,
    ) -> None:
        super().__init__()
        self.freq: float = freq or 0
        self.datarate: str = datarate or ""
        self.time: float = time or 0
        self.payload: str = payload or ""
        self.encrypted_payload: str = encrypted_payload or ""
        self.radio: RadioParams | None = radio
        self.port: int = port or 0

    @override
    def to_dict(
        self,
    ) -> DictParamsDownlink:
        """
        Returns a dictionary representation of the downlink parameters.

        Returns:
            dict: Dictionary with downlink parameters
        """
        data: DictParamsDownlink = {
            "freq": self.freq,
            "datarate": self.datarate,
            "time": self.time,
            "payload": self.payload,
        }
        if self.radio:
            data["radio"] = self.radio.to_dict()
        return data

    @override
    @classmethod
    def from_dict(cls, data: DictParamsDownlink) -> "ParamsDownlink":
        """
        Creates a ParamsDownlink object from a dictionary.

        :param data: (dict) Dictionary with downlink parameters

        :returns: ParamsDownlink object
        :rtype: ParamsDownlink
        """
        radio_data = try_dict(data, "radio", {})

        return cls(
            radio=RadioParams.from_dict(radio_data) if radio_data else None,
            freq=try_float(data, "freq", 0.0),
            datarate=str(data.get("datarate", "") or ""),
            time=try_float(data, "time", 0.0),
            payload=str(data.get("payload", "")),
        )


DictMeta: TypeAlias = dict[str, str | bool | float]


class Meta(AbstractMqtt):
    """
    Meta information class

    Class to represent the meta information of a Everynet packet.
    """

    def __init__(self):
        super().__init__()
        self.application: str = ""
        self.device: str = ""
        self.device_addr: str = ""
        self.gateway: str = ""
        self.history: bool = False
        self.network: str = ""
        self.packet_hash: str = ""
        self.packet_id: str = ""
        self.version: int = 1
        self.outdated: bool = False
        self.time: float = 0.0

    @override
    def to_dict(self) -> DictMeta:
        """
        Creates a dictionary representation of the Meta

        Returns
        -------
        Dict[str, Union[str, Dict[str, Union[bool, int, str]]]]
            Dictionary with Meta fields
        """
        return {
            key: value
            for key, value in {
                "device": str(self.device),
                "device_addr": str(self.device_addr),
                "application": str(self.application),
                "packet_hash": str(self.packet_hash),
            }.items()
        }

    @override
    @classmethod
    def from_dict(cls, data: DictMeta) -> "Meta":
        """
        Creates an instance of Meta from a dictionary

        :param data: (dict) Dictionary with Meta fields

        :return: Instance of Meta
        :rtype: Meta

        """
        inst = cls()
        inst.time = try_float(data, "time", 0.0)
        inst.version = try_int(data, "version", 1)
        inst.network = str(data.get("network", ""))
        inst.packet_hash = str(data.get("packet_hash", ""))
        inst.application = str(data.get("application", ""))
        inst.device_addr = str(data.get("device_addr", ""))
        inst.device = str(data.get("device", ""))
        inst.packet_id = str(data.get("packet_id", ""))
        inst.gateway = str(data.get("gateway", ""))
        inst.history = try_bool(data, "history", False)
        inst.outdated = try_bool(data, "outdated", False)
        return inst


DictMessage = dict[str, str | DictMeta | DictParamsDownlink | DictParamsUplink]


class EveryNetMqttMessage(AbstractMqtt):
    def __init__(
        self,
        type_message: TypeMessages = TypeMessages.ERROR,
        meta: DictMeta | None = None,
        params: DictParamsUplink | DictParamsDownlink | None = None,
    ) -> None:
        super().__init__()
        params = params or {}
        meta = meta or {}
        self.type_message: TypeMessages = type_message
        self.meta: Meta = Meta.from_dict(meta)
        self.params: AbstractMqtt = type_message.to_type().from_dict(params)

    @override
    def to_dict(self) -> DictMessage:
        """
        Convert EveryNetMqttMessage instance to dict with typed values

        Returns:
            dict[str, Any]: EveryNet message as dict with typed values

        Raises:
            ValueError: If type_message is not one of the expected enum values
        """
        message: DictMessage = {}
        message["type"] = self.type_message.value

        if self.type_message not in TypeMessages:
            raise ValueError(f"Unknown message type: {self.type_message}")
        message["meta"] = self.meta.to_dict()
        message["params"] = self.params.to_dict()

        return message

    @override
    @classmethod
    def from_dict(cls, data: DictMessage) -> "EveryNetMqttMessage":
        type_message = TypeMessages(data.get("type", ""))
        meta: DictMeta = data.get("meta")  # pyright: ignore[reportAssignmentType]
        params: DictParamsUplink | DictParamsDownlink = data.get("params")  # pyright: ignore[reportAssignmentType]
        return cls(type_message, meta, params)
