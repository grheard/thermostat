import os
import time
import threading

from project_common.logger import logger


PWM_PERIOD_DEFAULT = 1000000
PWM_DUTY_DEFAULT = 0


class Fan():
    def __init__(self,pwr: str, rpm: str, pwm: str, pwm_period: int):

        self.__pwr = f'/sys/class/gpio/gpio{pwr}'
        self.__rpm = None
        self.__pwm = None
        self.__pwm_period = PWM_PERIOD_DEFAULT

        if not pwm_period is None:
            self.__pwm_period = pwm_period

        self.__rpm_value = None

        self.__on = False

        try:
            if not os.path.exists(self.__pwr):
                logger.debug(f'Exporting gpio{pwr}')
                with open('/sys/class/gpio/export','w') as export:
                    export.write(pwr)
                os.sync()
                time.sleep(0.5)

            logger.debug(f'Setting direction of {self.__pwr}')
            with open(f'{self.__pwr}/direction','w') as direction:
                direction.write('out')

        except Exception as e:
            self.__pwr = None
            logger.critical(e)

        if not rpm is None:
            self.__rpm = f'/sys/class/gpio/gpio{rpm}'

            try:
                if not os.path.exists(self.__rpm):
                    logger.debug(f'Exporting gpio{rpm}')
                    with open('/sys/class/gpio/export','w') as export:
                        export.write(rpm)
                    os.sync()
                    time.sleep(0.5)

                logger.debug(f'Setting direction of {self.__rpm}')
                with open(f'{self.__rpm}/direction','w') as direction:
                    direction.write('in')

                self.__rpm_thread_event = threading.Event()
                self.__rpm_thread = threading.Thread(target=self.__rpm_thread_run,name='rpm')

            except Exception as e:
                self.__rpm = None
                logger.critical(e)


        if not pwm is None:
            self.__pwm = f'/sys/class/pwm/pwmchip0/pwm{pwm}'
            self.__duty = 0

            try:
                if not os.path.exists(self.__pwm):
                    logger.debug(f'Exporting {self.__pwm}')
                    with open('/sys/class/pwm/pwmchip0/export','w') as export:
                        export.write(pwm)
                    os.sync()
                    time.sleep(0.5)

                logger.debug(f'Setting {self.__pwm} period to {self.__pwm_period}')
                with open(f'{self.__pwm}/period','w') as period:
                    period.write(f'{self.__pwm_period}')

                os.sync()
                time.sleep(0.5)

                self.set_pwm_duty(PWM_DUTY_DEFAULT)
                self.set_pwm_enable(True)

            except Exception as e:
                self.__pwm = None
                logger.critical(e)


    def on(self):
        if self.__pwr is None:
            return

        if not self.__on:
            try:
                with open(f'{self.__pwr}/value','w') as gpio:
                    gpio.write('1')
                self.__on = True
            except Exception as e:
                logger.critical(e)
                return

            if not self.__rpm is None:
                self.__rpm_thread.start()

            self.set_pwm_enable(True)


    def off(self):
        if self.__pwr is None:
            return

        if self.__on:
            try:
                with open(f'{self.__pwr}/value','w') as gpio:
                    gpio.write('0')
                self.__on = False
            except Exception as e:
                logger.critical(f'Exception encoutered attempting to turn off {self.__pwr}: {e}')

            if not self.__rpm is None:
                self.__rpm_thread_event.set()
                self.__rpm_thread.join()

            self.set_pwm_enable(False)


    def set_pwr(self, enable: bool):
        if not enable is None:
            self.on() if enable else self.off()


    def get_rpm(self) -> int:
        return self.__rpm_value


    def set_pwm_enable(self, enable: bool):
        if not self.__pwm is None:
            try:
                logger.debug(f'{"Enabling" if enable else "Disabling"} {self.__pwm}')
                with open(f'{self.__pwm}/enable','w') as enable:
                    enable.write('1' if enable else '0')
                os.sync()
            except Exception as e:
                logger.critical(f'Exception encoutered attempting to{"enable" if enable else "disable"} {self.__pwm}: {e}')


    def set_pwm_duty(self, duty: int):
        if self.__pwm is None:
            return

        if duty is None or duty < 0 or duty > 100:
            return

        if duty != self.__duty:
            try:
                _duty = int(self.__pwm_period / 100 * duty)
                logger.debug(f'Setting {self.__pwm} duty cycle to {_duty}')
                with open(f'{self.__pwm}/duty_cycle','w') as pwm:
                    pwm.write(f'{_duty}')
                self.__duty = duty
            except Exception as e:
                logger.critical(e)


    def __rpm_thread_run(self):
        while not self.__rpm_thread_event.is_set():
            time_in = time.monotonic()
            pulse = 0

            try:
                with open(f'{self.__rpm}/value','r') as gpio:
                    last_pin_state = gpio.read().strip()

                while (round(0.5 - (time.monotonic() - time_in),3) > 0):
                    with open(f'{self.__rpm}/value','r') as gpio:
                        pin_state = gpio.read().strip()

                    if pin_state != last_pin_state:
                        last_pin_state = pin_state
                        if pin_state == '1':
                            pulse += 1

                    time.sleep(0.0005)

                self.__rpm_value = pulse * 60

            except Exception as e:
                logger.critical(e)
                self.__rpm_value = None

            time.sleep(0.5)
