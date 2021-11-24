import os
import fcntl
import threading
import collections
import select

from project_common.logger import logger

# IOCTL base value
SHT3X_IOCTL_BASE = 0x40047800

# SHT3X IOCTLs
SHT3X_HEATER_CONTROL   = SHT3X_IOCTL_BASE + 0
SHT3X_MEASUREMENT_MODE = SHT3X_IOCTL_BASE + 1
SHT3X_BREAK            = SHT3X_IOCTL_BASE + 2
SHT3X_STATUS           = SHT3X_IOCTL_BASE + 3
SHT3X_CRC_CHECK        = SHT3X_IOCTL_BASE + 4

# SHT3X heater control argument
SHT3X_HEATER_DISABLE = 0
SHT3X_HEATER_ENABLE  = 1

# SHT3X measurement mode argument
SHT3X_SINGLE_SHOT_LOW    =  0
SHT3X_SINGLE_SHOT_MED    =  1
SHT3X_SINGLE_SHOT_HIGH   =  2
SHT3X_PERIODIC_0P5_LOW   =  3
SHT3X_PERIODIC_0P5_MED   =  4
SHT3X_PERIODIC_0P5_HIGH  =  5
SHT3X_PERIODIC_1_LOW     =  6
SHT3X_PERIODIC_1_MED     =  7
SHT3X_PERIODIC_1_HIGH    =  8
SHT3X_PERIODIC_2_LOW     =  9
SHT3X_PERIODIC_2_MED     = 10
SHT3X_PERIODIC_2_HIGH    = 11
SHT3X_PERIODIC_4_LOW     = 12
SHT3X_PERIODIC_4_MED     = 13
SHT3X_PERIODIC_4_HIGH    = 14
SHT3X_PERIODIC_10_LOW    = 15
SHT3X_PERIODIC_10_MED    = 16
SHT3X_PERIODIC_10_HIGH   = 17

# SHT3X status command argument
SHT3X_STATUS_READ  = 0
SHT3X_STATUS_CLEAR = 1

UNITS_CELCIUS = 0
UNITS_FARENHEIT = 1


class Sht3x():
    def __init__(self,device: str, mode: int, samples: int):
        self.__device = device
        self.__mode = mode
        self.__samples = samples
        self.__tempcounts = None
        self.__humidity = 0.0

        self.__event = threading.Event()
        self.__thread = threading.Thread(target=self.__run,name='sht3x')
        self.__thread.start()


    def __del__(self):
        self.stop()


    def stop(self):
        self.__event.set()
        self.__thread.join()


    def humidity(self) -> float:
        return self.__humidity


    def temperature(self,units: int) -> float:
        temp = None
        if not self.__tempcounts is None:
            if units == UNITS_CELCIUS:
                temp = -45.0 + (175 * (self.__tempcounts / 65535))
            elif units == UNITS_FARENHEIT:
                temp = -49.0 + (315 * (self.__tempcounts / 65535))
        return temp


    def __run(self):
        fd = None
        try:
            fd = os.open(f'/dev/{self.__device}',os.O_RDONLY)
        except Exception as ex:
            logger.critical(ex)
            return

        if fcntl.ioctl(fd,SHT3X_MEASUREMENT_MODE,self.__mode) != 0:
            logger.critical(f'device {self.__device} could not be set to measurement mode {self.__mode}')
            os.close(fd)
            return

        sample_array = collections.deque()

        logger.info(f'Started with temp sample size of {self.__samples}')

        while not self.__event.is_set():
            (rlist,_,_) = select.select([fd],[],[],3)
            if len(rlist) != 0:
                data = os.read(fd,6)
                if len(data) != 6:
                    logger.warning(f'Incorrect amount of data returned. Read {len(data)}, expected 6.')
                else:
                    tcounts = (data[0] << 8) | data[1]
                    sample_array.append(tcounts)

                    if len(sample_array) > self.__samples:
                        sample_array.popleft()

                    # if len(sample_array) == self.__samples:
                    tcounts = 0
                    for _counts in sample_array:
                        tcounts += _counts
                    tcounts /= len(sample_array)
                    self.__tempcounts = tcounts

                    self.__humidity = 100 * (((data[3] << 8) | data[4]) / 65535)

            else:
                # Log the unexpected timeout waiting for data to read.
                logger.warning('Unexpected timeout waiting for sensor data.')

        os.close(fd)
