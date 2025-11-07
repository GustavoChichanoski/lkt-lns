from pydantic import BaseModel


class ConfigTraccar(BaseModel):
    url: str = ""
    token: str = ""
    username: str = ""
    password: str = ""


class ConfigMqttTopics(BaseModel):
    subscriber: str = ""
    publisher: str = ""


class ConfigMqtt(BaseModel):
    host: str = ""
    port: int = 0
    username: str = ""
    password: str = ""
    topics: ConfigMqttTopics = ConfigMqttTopics()


class ConfigEverynet(BaseModel):
    url: str = ""
    token: str = ""


class Config(BaseModel):
    traccar: ConfigTraccar = ConfigTraccar()
    mqtt: ConfigMqtt = ConfigMqtt()
    everynet: ConfigEverynet = ConfigEverynet()
