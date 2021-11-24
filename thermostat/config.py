
COMMON = 'common'
TOPIC_ROOT = 'topic-root'
LOGGER = 'logger'
THERMOSTAT = 'thermostat'
SHT3X_DEVICE = 'sht3x-device'
I2C_DEVICE = 'i2c-device'
I2C_RELAY_ADDR = 'relay-address'
FAN_PWR_GPIO = 'fan-pwr-gpio'
FAN_RPM_GPIO = 'fan-rpm-gpio'
FAN_PWM_MODULE = 'fan-pwm-module'
FAN_PWM_PERIOD = 'fan-pwm-period'
FAN_PWM_DUTY = 'fan-pwm-duty'
SETTINGS_FILE = 'settings-file'
TEMP_SAMPLES = 'temp-samples'
TEMP_HYSTERESIS = 'temp-hysteresis'
TEMP_SAMPLES_DEFAULT = 150
TEMP_HYSTERESIS_DEFAULT = 0.2778
FAN_PWM_DUTY_DEFAULT = 50


class Config():
    __instance = None


    @staticmethod
    def instance():
        if Config.__instance is None:
            raise Exception('Instance has not been created.')

        return Config.__instance


    def __init__(self,config):
        if Config.__instance is not None:
            raise Exception('Singleton instance already created.')

        self.__parse_config(config)

        Config.__instance = self


    def __parse_config(self, config):
        self.__topic = THERMOSTAT
        self.__logger_config = None
        self.__temp_samples = TEMP_SAMPLES_DEFAULT
        self.__temp_hysteresis = TEMP_HYSTERESIS_DEFAULT

        self.__fan_rpm_gpio = None
        self.__fan_pwm_module = None
        self.__fan_pwm_period = None
        self.__fan_pwm_duty = FAN_PWM_DUTY_DEFAULT

        if config is not None:
            if COMMON in config:
                if TOPIC_ROOT in config[COMMON]:
                    self.__topic = f"{config[COMMON][TOPIC_ROOT]}/{self.__topic}"

                if LOGGER in config[COMMON]:
                    self.__logger_config = config[COMMON]

            if THERMOSTAT in config:
                if SHT3X_DEVICE in config[THERMOSTAT]:
                    self.__sht3x_device = config[THERMOSTAT][SHT3X_DEVICE]

                if I2C_DEVICE in config[THERMOSTAT]:
                    self.__i2c_device = config[THERMOSTAT][I2C_DEVICE]

                if I2C_RELAY_ADDR in config[THERMOSTAT]:
                    self.__i2c_relay_addr = config[THERMOSTAT][I2C_RELAY_ADDR]

                if FAN_PWR_GPIO in config[THERMOSTAT]:
                    self.__fan_pwr_gpio = config[THERMOSTAT][FAN_PWR_GPIO]

                if FAN_RPM_GPIO in config[THERMOSTAT]:
                    self.__fan_rpm_gpio = config[THERMOSTAT][FAN_RPM_GPIO]

                if FAN_PWM_MODULE in config[THERMOSTAT]:
                    self.__fan_pwm_module = config[THERMOSTAT][FAN_PWM_MODULE]

                    if FAN_PWM_PERIOD in config[THERMOSTAT]:
                        self.__fan_pwm_period = config[THERMOSTAT][FAN_PWM_PERIOD]

                    if FAN_PWM_DUTY in config[THERMOSTAT]:
                        self.__fan_pwm_duty = config[THERMOSTAT][FAN_PWM_DUTY]

                if SETTINGS_FILE in config[THERMOSTAT]:
                    self.__settings_file = config[THERMOSTAT][SETTINGS_FILE]

                if LOGGER in config[THERMOSTAT]:
                    self.__logger_config = config[THERMOSTAT][LOGGER]

                if TEMP_SAMPLES in config[THERMOSTAT]:
                    self.__temp_samples = config[THERMOSTAT][TEMP_SAMPLES]

                if TEMP_HYSTERESIS in config[THERMOSTAT]:
                    self.__temp_hysteresis = config[THERMOSTAT][TEMP_HYSTERESIS]

        if not hasattr(self,'_Config__sht3x_device'):
            raise Exception('SHT3X device configuration must exist.')

        if not hasattr(self,'_Config__i2c_device'):
            raise Exception('I2C device configuration must exist.')

        if not hasattr(self,'_Config__i2c_relay_addr'):
            raise Exception('Relay address configuration must exist.')

        if not hasattr(self,'_Config__fan_pwr_gpio'):
            raise Exception('Fan gpio configuration must exist.')

        if not hasattr(self,'_Config__settings_file'):
            raise Exception('Settings file configuration must exist.')


    def topic(self) -> str:
        return self.__topic


    def sht3x_device(self) -> str:
        return self.__sht3x_device


    def i2c_device(self) -> str:
        return self.__i2c_device


    def i2c_relay_addr(self) -> int:
        return self.__i2c_relay_addr


    def fan_pwr_gpio(self) -> str:
        return self.__fan_pwr_gpio


    def fan_rpm_gpio(self) -> str:
        return self.__fan_rpm_gpio


    def fan_pwm_module(self) -> str:
        return self.__fan_pwm_module


    def fan_pwm_period(self) -> int:
        return self.__fan_pwm_period


    def fan_pwm_duty(self) -> int:
        return self.__fan_pwm_duty


    def settings_file(self) -> str:
        return self.__settings_file


    def logger_config(self) -> dict:
        return self.__logger_config


    def temp_samples(self) -> int:
        return self.__temp_samples


    def temp_hysteresis(self) -> float:
        return self.__temp_hysteresis
