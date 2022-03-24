import os
import json
from threading import Timer

from project_common.logger import logger
from project_common.mqtt import Mqtt, mqtt
from .config import Config
from . import control
from .control import Control


MODE = 'mode'


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

    DEFAULT_SETTINGS = {MODE: control.MODE_OFF, control.MODE_HEAT: 22.22, control.MODE_COOL: 23.889}

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
        self.__fan = control.MODE_AUTO

        try:
            with open(Config.instance().settings_file(),'r') as f:
                s = json.load(f)
                self.__validate_mode(s)
                self.__validate_setpoint(s)
        except Exception as ex:
            logger.warning(f'Could not read/interpret file: \'{Config.instance().settings_file()}\'')
            logger.debug(ex)

        self.__push_timer = None
        self.__push_settings()

        Mqtt.instance().register_on_connect(self.__on_connect)

        Settings.__instance = self


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
        except Exception as ex:
            logger.warning(ex)
            logger.debug(f'Settings message is incorrect: \'{json.dumps(payload)}\'')
            self.__publish({Settings.CMD: Settings.CMD_PUT_SETTINGS, Settings.RESULT: Settings.RESULT_FAIL})
        else:
            self.__set_push()
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
            self.__fan = payload[control.FAN]
            Control.instance().set_blower(self.__fan)
            self.__publish({Settings.CMD: Settings.CMD_PUT_FAN, Settings.RESULT: Settings.RESULT_OK})



    def __validate_mode(self,payload: dict):
        if MODE in payload:
            if not isinstance(payload[MODE],str):
                raise TypeError('Mode is not type string.')
            mode = payload[MODE]
            if mode != control.MODE_OFF \
                and mode != control.MODE_AUTO \
                and mode != control.MODE_COOL \
                and mode != control.MODE_HEAT:
                raise ValueError(f'Mode is unknown value \'{mode}\'')
            self.__settings[MODE] = mode


    def __validate_setpoint(self,payload: dict):
        if control.MODE_HEAT in payload:
            if not isinstance(payload[control.MODE_HEAT],float):
                # Some json encoders (Qt) will turn doubles/floats into integers
                # if there is no decimal place (ie 25.0 becomes 25 in the json output)
                if not isinstance(payload[control.MODE_HEAT],int):
                    raise TypeError('Setpoint heat is not type float or integer.')
            self.__settings[control.MODE_HEAT] = payload[control.MODE_HEAT]

            # Correct cool setpoint for imposed delta.
            if self.__settings[control.MODE_HEAT] + Config.instance().auto_temp_delta() > self.__settings[control.MODE_COOL]:
                self.__settings[control.MODE_COOL] = self.__settings[control.MODE_HEAT] + Config.instance().auto_temp_delta()

        if control.MODE_COOL in payload:
            if not isinstance(payload[control.MODE_COOL],float):
                # Some json encoders (Qt) will turn doubles/floats into integers
                # if there is no decimal place (ie 25.0 becomes 25 in the json output)
                if not isinstance(payload[control.MODE_COOL],int):
                    raise TypeError('Setpoint cool is not type float or integer.')
            self.__settings[control.MODE_COOL] = payload[control.MODE_COOL]

            # Correct heat setpoint for imposed delta.
            if self.__settings[control.MODE_HEAT] + Config.instance().auto_temp_delta() > self.__settings[control.MODE_COOL]:
                self.__settings[control.MODE_HEAT] = self.__settings[control.MODE_COOL] - Config.instance().auto_temp_delta()


    def __validate_fan(self,payload: dict):
        if not control.FAN in payload:
            raise KeyError('Fan key missing.')
        if not isinstance(payload[control.FAN],str):
            raise TypeError('Fan is not type str.')
        fan = payload[control.FAN]
        if fan != control.MODE_AUTO and fan != control.MODE_ON:
            raise ValueError(f'Fan is unknown value \'{fan}\'')


    def __publish(self,dictionary: dict):
        try:
            p=json.dumps(dictionary)
            Mqtt.instance().publish(self.__topic,payload=p,qos=2)
            logger.debug(p)
        except Exception as ex:
            logger.warning(ex)


    def __push_settings(self):
        logger.debug('Pushing settings.')
        Control.instance().set_mode(self.__settings[MODE])
        Control.instance().set_cool(self.__settings[control.MODE_COOL])
        Control.instance().set_heat(self.__settings[control.MODE_HEAT])


    def __set_push(self):
        if not self.__push_timer is None:
            logger.debug('Cancelling push timer.')
            self.__push_timer.cancel()
        logger.debug('Setting push timer.')
        self.__push_timer = Timer(5.0,self.__push_settings)
        self.__push_timer.start()