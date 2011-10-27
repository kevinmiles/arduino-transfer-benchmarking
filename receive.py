#!/usr/bin/env python

from operator import itemgetter
import datetime
import json
import sys
import argparse
import usb.core
import string


class MessageDeviceBenchmarker(object):
    def read(self):
        if self.bytes_received >= self.MAX_BYTES:
            return None

        data = self._read()

        self.bytes_received += len(data)
        if self.bytes_received % (1000 * self.message_size) == 0:
            print "Received %d kilobytes so far..." % (
                    self.bytes_received / 1000),
            sys.stdout.flush()
            print "\r",
        self._validate(data)
        return data

    def set_message_size(self, message_size):
        self.message_size = message_size
        self.set_message_size_on_device(self.message_size)
        print "Message size switched to %d bytes" % self.message_size
        self.bytes_received = 0

    def throughput(self, elapsed_time):
        return (self.bytes_received / 1000 /
                max(1, elapsed_time.seconds + elapsed_time.microseconds /
                    1000000.0))

    def total_time(self, elapsed_time):
        return "Reading %s KB in %s byte chunks took %s" % (
                self.bytes_received / 1000, self.message_size, elapsed_time)

    def run_benchmark(self, message_size):
        self.set_message_size(message_size)

        data = self.read()
        starting_time = datetime.datetime.now()

        while data is not None:
            data = self.read()

        print
        print "Finished receiving."

        elapsed_time = datetime.datetime.now() - starting_time
        throughput = self.throughput(elapsed_time)
        print self.total_time(elapsed_time)
        print "The effective throughput for %d byte messages is %d KB/s" % (
                    message_size, throughput)
        return throughput

    def _validate(self, data):
        pass


class FtdiDevice(MessageDeviceBenchmarker):
    MAX_BYTES = 10 * 1000 * 10 * 5
    STARTING_MESSAGE_SIZE = 20
    ENDING_MESSAGE_SIZE = 100
    MESSAGE_SIZE_STEP = 20

    def __init__(self, device="/dev/ttyUSB0", baud=1152000):
        import serial
        self.device = serial.Serial(device, baud, timeout=10)
        self.device.flushInput()
        self.message_size = -1

    def set_message_size_on_device(self, message_size):
        self.message_size = message_size
        self.device.write(bytearray([self.message_size /
            self.MESSAGE_SIZE_STEP]))
        self.device.flushOutput()
        print "Message size switched to %d bytes" % self.message_size
        self.bytes_received = 0

    def _read(self):
        return self.device.read(self.message_size)

    def _validate(self, data):
        for character in string.ascii_lowercase[:self.message_size]:
            if character not in data:
                print "Corruption detection on line: %s" % data

class UsbDevice(MessageDeviceBenchmarker):
    DATA_ENDPOINT = 0x81
    MAX_BYTES = 10 * 1000 * 100
    STARTING_MESSAGE_SIZE = 64
    ENDING_MESSAGE_SIZE = 1024
    MESSAGE_SIZE_STEP = 128
    MESSAGE_SIZE_CONTROL_MESSAGE = 0x80

    def __init__(self, vendorId=0x04d8, endpoint=0x81):
        self.vendorId = vendorId
        self.endpoint = endpoint
        self.device = usb.core.find(idVendor=vendorId)
        if not self.device:
            print "Couldn't find a USB device from vendor %s" % self.vendorId
            sys.exit()
        self.device.set_configuration()

    def set_message_size_on_device(self, message_size):
        # USB device is just using max packet size of 64 - the variable is how
        # much we request to read at once. The more the merrier.
        pass

    def _read(self):
        return self.device.read(self.endpoint, self.message_size)

    def _validate(self, data):
        data = data.tostring()
        data = json.loads(data)
        assert "name" in data
        assert "value" in data


def parse_options():
    parser = argparse.ArgumentParser(description="Benchmark USB and FTDI "
            "transfer rates on the chipKIT")
    parser.add_argument("--usb",
            action="store_true",
            dest="run_usb_benchmark",
            default=True,
            help="run the USB benchmark")
    parser.add_argument("--ftdi",
            action="store_true",
            dest="run_ftdi_benchmark",
            default=False,
            help="run the FTDI benchmark")
    parser.add_argument("--tty",
            action="store",
            dest="tty",
            default="/dev/ttyUSB0")
    parser.add_argument("--vendor",
            action="store",
            dest="vendor",
            default=0x04d8)

    arguments = parser.parse_args()
    return arguments


def main():
    arguments = parse_options()

    if arguments.run_ftdi_benchmark:
        device = FtdiDevice(device=arguments.tty)
    else:
        device = UsbDevice(vendorId=arguments.vendor)

    results = {}
    for message_size in range(device.STARTING_MESSAGE_SIZE,
            device.ENDING_MESSAGE_SIZE + 1,
            device.MESSAGE_SIZE_STEP):
        results[message_size] = device.run_benchmark(message_size)

    print
    results = [(key, "%d byte messages -> %d KB/s" % (key, value))
            for key, value in results.iteritems()]

    for result in sorted(results, key=itemgetter(0)):
        print result[1]

if __name__ == '__main__':
    main();
