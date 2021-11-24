import fcntl
import os


I2C_SLAVE = 0x0703  # Use this slave address


MCUSR = 0
RELAY_FAN = 1
RELAY_HEAT = 2
RELAY_COOL = 3

MCUSR_POR = 0x01
MCUSR_EXT = 0x02
MCUSR_BOR = 0x04
MCUSR_WDT = 0x08

RELAY_NO_CHANGE = 0
RELAY_OFF = 1
RELAY_ON = 2

RELAY_STATUS_OFF = 0
RELAY_STATUS_ON = 1
RELAY_STATUS_LOCKED = 2

RELAY_NAME_STR = {RELAY_FAN: 'fan', RELAY_COOL: 'cool', RELAY_HEAT: 'heat'}
RELAY_STATUS_STR = {RELAY_STATUS_OFF: 'off', RELAY_STATUS_ON: 'on', RELAY_STATUS_LOCKED: 'locked'}


class Relays():
    def __init__(self,i2c: str, addr: int):
        self.__device = f'/dev/{i2c}'
        self.__addr = addr
        self.__fd = None


    def open(self):
        if self.__fd is None:
            self.__fd = os.open(self.__device,os.O_RDWR)
            if fcntl.ioctl(self.__fd,I2C_SLAVE,self.__addr) != 0:
                self.close()
                raise IOError(f'Could net set slave address to 0x{self.__addr:#02X}')


    def close(self):
        if not self.__fd is None:
            os.close(self.__fd)
            self.__fd = None


    def get_status(self) -> bytearray:
        self.open()
        return os.read(self.__fd,4)


    def reset_mcusr(self) -> int:
        self.open()
        mcusr = bytearray(b'\x0f\x00\x00\x00')
        os.write(self.__fd,mcusr)
        return self.get_mcusr()


    def get_mcusr(self) -> int:
        self.open()
        return self.get_status()[MCUSR]


    def relay_on(self,relay: int) -> int:
        self.open()
        packet = bytearray(b'\x00\x00\x00\x00')
        packet[relay] = RELAY_ON
        os.write(self.__fd,packet)
        return self.get_status()[relay]


    def relay_off(self,relay: int) -> int:
        self.open()
        packet = bytearray(b'\x00\x00\x00\x00')
        packet[relay] = RELAY_OFF
        os.write(self.__fd,packet)
        return self.get_status()[relay]


    def relay_all_off(self) -> bytearray:
        self.open()
        os.write(self.__fd,bytearray(b'\x00\x01\x01\x01'))
        return self.get_status()
