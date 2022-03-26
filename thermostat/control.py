import json
import threading
import time


from project_common.logger import logger
from project_common.mqtt import Mqtt, mqtt

from .config import Config
from . import sht3x
from . import relays
from . import fan


MODE_OFF = 'off'
MODE_AUTO = 'auto'
MODE_HEAT = 'heat'
MODE_COOL = 'cool'
MODE_ON = 'on'

FAN = 'fan'

TEMPERATURE = 'temperature'
HUMIDITY = 'humidity'
STATE = 'state'
STATE_IDLE = 'idle'
OUTPUT = 'output'
FAN_STATE = 'fan-state'
OOS = 'out-of-service'


class Control():
    __instance = None


    @staticmethod
    def instance():
        if Control.__instance is None:
            raise Exception('Instance has not been created.')

        return Control.__instance


    def __init__(self):
        if Control.__instance is not None:
            raise Exception('Singleton instance already created.')

        logger.info(f'Using {Config.instance().temp_samples()} temperature samples.')
        logger.info(f'Using {Config.instance().temp_hysteresis():.3f}C temperature hysteresis.')

        self.__sht = sht3x.Sht3x(Config.instance().sht3x_device(),sht3x.SHT3X_PERIODIC_1_HIGH,Config.instance().temp_samples())
        self.__relay = relays.Relays(Config.instance().i2c_device(),Config.instance().i2c_relay_addr())
        self.__fan = fan.Fan(Config.instance().fan_pwr_gpio(),Config.instance().fan_rpm_gpio(),Config.instance().fan_pwm_module(),Config.instance().fan_pwm_period())

        self.__topic = Config.instance().topic()

        Mqtt.instance().register_on_connect(self.__on_connect)
        Mqtt.instance().register_on_disconnect(self.__on_disconnect)
        Mqtt.instance().will_set(self.__topic,payload=OOS,qos=2)

        self.__mode = None
        self.__heat = None
        self.__cool = None
        self.__blower = MODE_AUTO

        self.__stop_event = threading.Event()
        self.__thread = threading.Thread(target=self.__thread_run,name='control')
        self.__thread.start()

        Control.__instance = self


    def stop(self):
        self.__stop_event.set()
        self.__thread.join()
        self.__relay.relay_all_off()
        self.__relay.close()
        self.__sht.stop()
        self.__fan.off()


    def set_mode(self, mode: str):
        self.__mode = mode


    def set_blower(self, blower: str):
        self.__blower = blower


    def set_heat(self, heat: float):
        self.__heat = heat


    def set_cool(self, cool: float):
        self.__cool = cool


    def __on_connect(self,client, userdata, flags, rc):
        if rc == mqtt.client.CONNACK_ACCEPTED:
            logger.info(f'Broker connected.')


    def __on_disconnect(self,client, userdata, rc):
        if rc != mqtt.client.MQTT_ERR_SUCCESS:
            # Broker was not asked to disconnect.
            logger.warning(f'Broker disconnected with rc={rc}')


    def __thread_run(self):
        self.__fan.on()
        self.__fan.set_pwm_duty(Config.instance().fan_pwm_duty())

        out_of_service = True

        last_status = {TEMPERATURE: 0.0, HUMIDITY: 0.0, STATE: STATE_IDLE, OUTPUT: relays.RELAY_STATUS_STR[relays.RELAY_STATUS_OFF], FAN: MODE_OFF, FAN_STATE: relays.RELAY_STATUS_STR[relays.RELAY_STATUS_OFF]}

        while not self.__stop_event.is_set():
            time_in = time.monotonic()

            fan_rpm = self.__fan.get_rpm()
            if not fan_rpm is None:
                logger.debug(f'Fan RPM = {fan_rpm}')

            try:
                relay_status = self.__relay.get_status()
            except Exception as ex:
                logger.critical(ex)
                time.sleep(1)
                continue

            self.__log_relay_status(relay_status)

            if relay_status[relays.MCUSR] != 0:
                logger.warning(f'Relay controller has reset with code {relay_status[relays.MCUSR]}')
                try:
                    mcusr = self.__relay.reset_mcusr()
                except Exception as ex:
                    logger.critical(ex)
                else:
                    if  mcusr != 0:
                        logger.error(f'Relay controller status did not reset code={mcusr}')

            temp = self.__sht.temperature(sht3x.UNITS_CELCIUS)
            if not temp is None and not self.__mode is None and not self.__blower is None and not self.__heat is None and not self.__cool is None:
                temp = round(temp + 0.0001,3)
                humid = round(self.__sht.humidity() + 0.01,1)
                self.__log_sht(temp,humid)

                state = last_status[STATE]

                fan_state = relays.RELAY_STATUS_STR[relay_status[relays.RELAY_FAN]]

                if relay_status[relays.RELAY_COOL] == relays.RELAY_STATUS_ON or relay_status[relays.RELAY_HEAT] == relays.RELAY_STATUS_ON:
                    output = relays.RELAY_STATUS_STR[relays.RELAY_STATUS_ON]
                elif relay_status[relays.RELAY_COOL] == relays.RELAY_STATUS_LOCKED or relay_status[relays.RELAY_HEAT] == relays.RELAY_STATUS_LOCKED:
                    output = relays.RELAY_STATUS_STR[relays.RELAY_STATUS_LOCKED]
                else:
                    output = relays.RELAY_STATUS_STR[relays.RELAY_STATUS_OFF]

                if self.__mode == MODE_OFF:
                    state = STATE_IDLE

                if self.__mode == MODE_COOL or self.__mode == MODE_AUTO:
                    if (self.__mode == MODE_COOL or state == MODE_COOL) and temp <= self.__cool:
                        state = STATE_IDLE
                    if temp >= (self.__cool + Config.instance().temp_hysteresis()):
                        state = MODE_COOL

                if self.__mode == MODE_HEAT or self.__mode == MODE_AUTO:
                    if (self.__mode == MODE_HEAT or state == MODE_HEAT) and temp >= self.__heat:
                        state = STATE_IDLE
                    if temp <= (self.__heat - Config.instance().temp_hysteresis()):
                        state = MODE_HEAT

                if state == MODE_COOL:
                    if relay_status[relays.RELAY_HEAT] == relays.RELAY_STATUS_ON:
                        state = STATE_IDLE
                        logger.warning('Cooling wanted while heat is on.')
                    elif relay_status[relays.RELAY_HEAT] == relays.RELAY_STATUS_LOCKED or relay_status[relays.RELAY_FAN] == relays.RELAY_STATUS_LOCKED:
                        # If heat/fan was on previously, wait for its lockout to clear before allowing cooling to be engaged.
                        output = relays.RELAY_STATUS_STR[relays.RELAY_STATUS_LOCKED]
                        if output != last_status[OUTPUT]:
                            logger.info(f'Cooling currently locked out.')
                    else:
                        output = self.__relay_on(relays.RELAY_COOL)
                        if state != last_status[STATE]:
                            logger.info(f'Cooling engaged at {temp:2.3f}C with relay status of {output}.')
                        elif output != last_status[OUTPUT]:
                            logger.info(f'Cooling relay changed state to {output}.')

                if state == MODE_HEAT:
                    if relay_status[relays.RELAY_COOL] == relays.RELAY_STATUS_ON:
                        state = STATE_IDLE
                        logger.warning('Heating wanted while cooling is on.')
                    elif relay_status[relays.RELAY_COOL] == relays.RELAY_STATUS_LOCKED or relay_status[relays.RELAY_FAN] == relays.RELAY_STATUS_LOCKED:
                        # If cooling/fan was on previously, wait for its lockout to clear before allowing heat to be engaged.
                        output = relays.RELAY_STATUS_STR[relays.RELAY_STATUS_LOCKED]
                        if output != last_status[OUTPUT]:
                            logger.info(f'Heating currently locked out.')
                    else:
                        output = self.__relay_on(relays.RELAY_HEAT)
                        if state != last_status[STATE]:
                            logger.info(f'Heating engaged at {temp:2.3f}C with relay status of {output}.')
                        elif output != last_status[OUTPUT]:
                            logger.info(f'Heating relay changed state to {output}.')

                if state == STATE_IDLE:
                    if relay_status[relays.RELAY_COOL] == relays.RELAY_STATUS_ON:
                        output = self.__relay_off(relays.RELAY_COOL)
                        if output != last_status[OUTPUT]:
                            logger.info('Cooling turned off.')
                    if relay_status[relays.RELAY_HEAT] == relays.RELAY_STATUS_ON:
                        output = self.__relay_off(relays.RELAY_HEAT)
                        if output != last_status[OUTPUT]:
                            logger.info('Heating turned off.')

                if (state == STATE_IDLE or output == relays.RELAY_STATUS_STR[relays.RELAY_STATUS_LOCKED]) and self.__blower == MODE_AUTO and relay_status[relays.RELAY_FAN] == relays.RELAY_STATUS_ON:
                    fan_state = self.__relay_off(relays.RELAY_FAN)
                    logger.info('Fan turned off.')
                if (state != STATE_IDLE and output != relays.RELAY_STATUS_STR[relays.RELAY_STATUS_LOCKED]) or self.__blower == MODE_ON:
                    fan_state = self.__relay_on(relays.RELAY_FAN)
                    if last_status[FAN_STATE] != relays.RELAY_STATUS_STR[relays.RELAY_STATUS_ON]:
                        logger.info(f'Fan turned on with relay status of {fan_state}.')

                status = {TEMPERATURE: temp if not temp is None else 0.0, HUMIDITY: humid if not humid is None else 0.0, STATE: state, OUTPUT: output, FAN: self.__blower, FAN_STATE: fan_state}

                if status != last_status:
                    self.__publish(status)
                    last_status = dict(status)
                    out_of_service = False

            else:
                if not out_of_service:
                    out_of_service = True
                    # Let the broker know something is wrong.
                    Mqtt.instance().publish(self.__topic,payload=OOS,qos=2)

            # Try and get close to once-per-second periodicity.
            time_left =  round(1.0 - (time.monotonic() - time_in),3)
            if time_left > 0:
                logger.debug(f'Sleeping for {time_left:1.3f}')
                time.sleep(time_left)
            else:
                logger.debug(f'Went over on time {time_left:1.3f}')
                time.sleep(0)

        # Let the broker know the thermostat is stopping.
        Mqtt.instance().publish(self.__topic,payload=OOS,qos=2)


    def __publish(self,dictionary: dict):
        try:
            p=json.dumps(dictionary)
            Mqtt.instance().publish(self.__topic,payload=p,qos=2)
            logger.debug(p)
        except Exception as ex:
            logger.warning(ex)


    def __relay_on(self,relay: int) -> str:
        try:
            _relay_status = self.__relay.relay_on(relay)
        except Exception as ex:
            logger.critical(ex)
            _relay_status = relays.RELAY_STATUS_LOCKED
        # else:
        #     if _relay_status != relays.RELAY_STATUS_ON:
        #         logger.warning(f'Relay {relays.RELAY_NAME_STR[relay]} failed to turn on.')
        return relays.RELAY_STATUS_STR[_relay_status]


    def __relay_off(self,relay: int) -> str:
        try:
            _relay_status = self.__relay.relay_off(relay)
        except Exception as ex:
            logger.critical(ex)
            _relay_status = relays.RELAY_STATUS_ON
        # else:
        #     if _relay_status == relays.RELAY_STATUS_ON:
        #         logger.warning(f'Relay {relays.RELAY_NAME_STR[relay]} failed to turn off.')
        return relays.RELAY_STATUS_STR[_relay_status]


    def __log_relay_status(self,status: bytearray):
        s = []
        for relay in [relays.RELAY_COOL,relays.RELAY_HEAT,relays.RELAY_FAN]:
            s.append(f'{relays.RELAY_NAME_STR[relay]}::{relays.RELAY_STATUS_STR[status[relay]]}')
        logger.debug(','.join(s))


    def __log_sht(self,temp: float, humid: float):
        if not temp is None:
            logger.debug(f'Temp: {temp:2.3f}  Humidity: {humid:2.1f}')
