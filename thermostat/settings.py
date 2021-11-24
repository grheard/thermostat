import os
import json

from project_common.logger import logger
from project_common.mqtt import Mqtt, mqtt
from .config import Config


MODE_OFF = 'off'
MODE_AUTO = 'auto'
MODE_HEAT = 'heat'
MODE_COOL = 'cool'
MODE_ON = 'on'

MODE = 'mode'
SETPOINT = 'setpoint'
FAN = 'fan'


class Settings():
    ACTION = 'action'

    CMD = 'cmd'
    RESULT = 'result'

    RESULT_OK = 'OK'
    RESULT_FAIL = 'FAIL'

    CMD_GET_SETTINGS = 'get-settings'
    CMD_PUT_SETTINGS = 'put-settings'

    CMD_GET_FAN = 'get-fan'
    CMD_PUT_FAN = 'put-fan'

    AUTO_TEMP_DELTA = 1.111

    DEFAULT_SETTINGS = {MODE: MODE_OFF, SETPOINT: {MODE_HEAT: 22.22, MODE_COOL: 23.889}}

    __instance = None


    @staticmethod
    def instance():
        if Settings.__instance is None:
            raise Exception('Instance has not been created.')

        return Settings.__instance


    def __init__(self):
        if Settings.__instance is not None:
            raise Exception('Singleton instance already created.')

        self.__topic = Config.instance().topic()

        self.__settings = Settings.DEFAULT_SETTINGS
        self.__fan = MODE_AUTO

        try:
            with open(Config.instance().settings_file(),'r') as f:
                s = json.load(f)
                self.__validate_mode(s)
                self.__validate_setpoint(s)
                self.__settings = dict(s)
        except Exception as ex:
            logger.warning(f'Could not read/interpret file: \'{Config.instance().settings_file()}\'')
            logger.debug(ex)

        Mqtt.instance().register_on_connect(self.__on_connect)

        Settings.__instance = self


    def get_mode(self) -> str:
        return self.__settings[MODE]


    def get_setpoint(self,mode: str) -> float:
        return self.__settings[SETPOINT][mode]


    def get_fan(self) -> str:
        return self.__fan


    def __on_connect(self,client, userdata, flags, rc):
        if rc == mqtt.client.CONNACK_ACCEPTED:
            self.__subscribe()


    def __subscribe(self):
        sub = f'{self.__topic}/{Settings.ACTION}'
        logger.info(f'Subscribing to {sub}')
        Mqtt.instance().subscribe(sub,qos=2)
        Mqtt.instance().message_callback_add(sub,self.__on_mqtt_message)


    def __on_mqtt_message(self,client,userdata,message):
        try:
            logger.debug(f'{message.topic} -> {message.payload}')
        except:
            try:
                logger.debug(f'{message.topic} has an unknown payload of type {type(message.payload)}')
            except:
                logger.debug('I give up... recieved a really broken mqtt message.')
                return

        if os.path.basename(message.topic) == Settings.ACTION:
            payload = {}
            try:
                payload = json.loads(message.payload)
            except:
                logger.warning(f'Received message payload is not valid json: "{message.payload}"')
                return

            if not Settings.CMD in payload:
                logger.warning('Action message missing command key.')
                return

            if payload[Settings.CMD] == Settings.CMD_GET_SETTINGS:
                self.__get_settings()
            elif payload[Settings.CMD] == Settings.CMD_PUT_SETTINGS:
                if not Settings.RESULT in payload:
                    logger.warning('Result key missing in \'{payload[Settings.CMD]}\'')
                    self.__publish({Settings.CMD: payload[Settings.CMD], Settings.RESULT: Settings.RESULT_FAIL})
                else:
                    self.__put_settings(payload[Settings.RESULT])
            elif payload[Settings.CMD] == Settings.CMD_GET_FAN:
                self.__get_fan()
            elif payload[Settings.CMD] == Settings.CMD_PUT_FAN:
                if not Settings.RESULT in payload:
                    logger.warning('Result key missing in \'{payload[Settings.CMD]}\'')
                    self.__publish({Settings.CMD: payload[Settings.CMD], Settings.RESULT: Settings.RESULT_FAIL})
                else:
                    self.__put_fan(payload[Settings.RESULT])
            else:
                logger.warning('Command is unknown: \'{payload[Settings.CMD]}\'')


    def __get_settings(self):
        payload = {Settings.CMD: Settings.CMD_GET_SETTINGS, Settings.RESULT: self.__settings}
        self.__publish(payload)


    def __put_settings(self,payload: dict):
        try:
            self.__validate_mode(payload)
            self.__validate_setpoint(payload)
            self.__validate_auto(payload)
        except Exception as ex:
            logger.warning(ex)
            logger.debug(f'Settings message is incorrect: \'{json.dumps(payload)}\'')
            self.__publish({Settings.CMD: Settings.CMD_PUT_SETTINGS, Settings.RESULT: Settings.RESULT_FAIL})
        else:
            self.__settings = dict(payload)
            self.__publish({Settings.CMD: Settings.CMD_PUT_SETTINGS, Settings.RESULT: Settings.RESULT_OK})
            # Save the settings file.
            try:
                with open(Config.instance().settings_file(),'w') as f:
                   json.dump(self.__settings,f)
            except Exception as ex:
                logger.warning(f'Could not write file: \'{Config.instance().settings_file()}\'')
                logger.debug(ex)


    def __get_fan(self):
        payload = {Settings.CMD: Settings.CMD_GET_FAN, Settings.RESULT: self.__fan}
        self.__publish(payload)


    def __put_fan(self,payload: dict):
        try:
            self.__validate_fan(payload)
        except Exception as ex:
            logger.warning(ex)
            logger.debug(f'Fan message is incorrect: \'{json.dumps(payload)}\'')
            self.__publish({Settings.CMD: Settings.CMD_PUT_FAN, Settings.RESULT: Settings.RESULT_FAIL})
        else:
            self.__fan = payload[FAN]
            self.__publish({Settings.CMD: Settings.CMD_PUT_FAN, Settings.RESULT: Settings.RESULT_OK})



    def __validate_mode(self,payload: dict):
        if not MODE in payload:
            raise KeyError('Mode key missing.')
        if not isinstance(payload[MODE],str):
            raise TypeError('Mode is not type string.')
        mode = payload[MODE]
        if mode != MODE_OFF \
            and mode != MODE_AUTO \
            and mode != MODE_COOL \
            and mode != MODE_HEAT:
            raise ValueError(f'Mode is unknown value \'{mode}\'')


    def __validate_setpoint(self,payload: dict):
        if not SETPOINT in payload:
            raise KeyError('Setpoint key missing.')
        if not isinstance(payload[SETPOINT],dict):
            raise TypeError('Setpoint is not type dict.')
        if not MODE_HEAT in payload[SETPOINT]:
            raise KeyError('Heat key missing in setpoint.')
        if not isinstance(payload[SETPOINT][MODE_HEAT],float):
            # Some json encoders (Qt) will turn doubles/floats into integers
            # if there is no decimal place (ie 25.0 becomes 25 in the json output)
            if not isinstance(payload[SETPOINT][MODE_HEAT],int):
                raise TypeError('Setpoint heat is not type float or integer.')
        if not MODE_COOL in payload[SETPOINT]:
            raise KeyError('Cool key missing in setpoint.')
        if not isinstance(payload[SETPOINT][MODE_COOL],float):
            # Some json encoders (Qt) will turn doubles/floats into integers
            # if there is no decimal place (ie 25.0 becomes 25 in the json output)
            if not isinstance(payload[SETPOINT][MODE_COOL],int):
                raise TypeError('Setpoint cool is not type float or integer.')


    def __validate_auto(self,payload: dict):
        if payload[MODE] == MODE_AUTO:
            if (payload[SETPOINT][MODE_COOL] - Settings.AUTO_TEMP_DELTA) <= payload[SETPOINT][MODE_HEAT]:
                raise ValueError(f'Setpoints do not meet the delta of {Settings.AUTO_TEMP_DELTA:1.2f}C')


    def __validate_fan(self,payload: dict):
        if not FAN in payload:
            raise KeyError('Fan key missing.')
        if not isinstance(payload[FAN],str):
            raise TypeError('Fan is not type str.')
        fan = payload[FAN]
        if fan != MODE_AUTO and fan != MODE_ON:
            raise ValueError(f'Fan is unknown value \'{fan}\'')


    def __publish(self,dictionary: dict):
        try:
            p=json.dumps(dictionary)
            Mqtt.instance().publish(self.__topic,payload=p,qos=2)
            logger.debug(p)
        except Exception as ex:
            logger.warning(ex)
