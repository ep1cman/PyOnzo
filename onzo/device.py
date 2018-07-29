import struct
import random
import hid
import datetime
from enum import Enum, IntEnum
from collections import OrderedDict


REQUEST_HEADER_FORMAT = '< HQ H H BB'


class NetworkID(IntEnum):
    CLAMP = 1
    DISPLAY = 2


class RequestType(IntEnum):
    GET_REGISTER = 1
    SET_REGISTER = 2
    GET_BULK_DATA = 3
    GET_NETWORK_LIST = 4
    CMD_RESET = 5
    WRITE_BULK_DATA = 6
    LDM_COMMAND = 160


class ResponseType(IntEnum):
    GET_REGISTER = 1
    SET_REGISTER = 2
    GET_BULK_DATA = 3
    GET_NETWORK_LIST = 4
    LDM_COMMAND = 160
    ERROR = 240
    END_OF_TRANSFER = 241


class StreamType(Enum):
    ENERGY_HIGH_RES = 'E'
    ENERGY_LOW_RES = 'e'
    POWER_REAL_FINE = 'P'
    POWER_REAL_STANDARD = 'p'
    POWER_REACTIVE_FINE = 'Q'
    POWER_REACTIVE_STANDARD = 'q'


class Connection(object):

    def __init__(self, vid=0x04D8, pid=0x003F, unit=0):
        self.vid = vid
        self.pid = pid
        self.unit = unit

    def connect(self):
        self.dev = hid.device()
        self.dev.open(vendor_id=self.vid, product_id=self.pid)

    def disconnect(self):
        self.dev.close()

    # Low level packet framing (64 byte)
    def message_send(self, data):
        while len(data) > 0:
            frame_size = 62
            frame_fin = 0

            if len(data) <= 62:
                frame_fin = 1
                if len(data) < 62:  # Pad with 0xFF
                    frame_size = len(data)
                    data += b'\xFF' * (62 - len(data))
            header = struct.pack('<BB', frame_fin, frame_size)
            i = self.dev.write(header + data[:62])
            if i != 64:  # All writes should be blocks of 64 bytes
                raise Exception("All bytes were not written")
            data = data[62:]

    def message_receive(self, timeout=5000):
        complete_payload = bytes()
        while True:
            frame = bytes(self.dev.read(64, timeout))
            frame_fin, frame_size = struct.unpack('<BB', frame[:2])
            payload = frame[2:(2+frame_size)]  # Remove header & padding
            complete_payload += payload
            if frame_fin:
                break
        return complete_payload


class Device(object):
    network_id = None

    def __init__(self, connection):
        self.conn = connection

    def _send_request(self, req_type, req_reg_id, req_payload=bytes(),
                      resp_parser=lambda payload: None):
        # Encode and send request
        req_trans_id = random.getrandbits(16)

        req_header = struct.pack(REQUEST_HEADER_FORMAT, 0, 0, req_trans_id,
                                 self.network_id, RequestType(req_type),
                                 req_reg_id)
        self.conn.message_send(req_header + req_payload)

        # Receive and parse response
        response = self.conn.message_receive()
        resp_header, resp_payload = response[:16], response[16:]
        resp_header = struct.unpack(REQUEST_HEADER_FORMAT, resp_header)
        enc_0 = resp_header[0]
        enc_1 = resp_header[1]
        resp_trans_id = resp_header[2]
        req_net_id  = NetworkID(resp_header[3])
        resp_type = ResponseType(resp_header[4])
        if resp_type == ResponseType.ERROR:
            raise Exception("Error occured during {} request".format(req_type.name))
        resp_reg_id = resp_header[5]
        resp_payload = resp_parser(resp_payload)
        if resp_trans_id != req_trans_id:
            raise Exception("Transaction IDs do not match")
        if resp_type != req_type:
            raise Exception("response type ({}) does not match request type ({})".format(resp_type, req_type))
        return resp_payload

    def get_register(self, register_id):
        if type(register_id) == int:
            parser = lambda payload: struct.unpack('<H', payload)[0]
            return self._send_request(RequestType.GET_REGISTER, register_id,
                                      resp_parser=parser)
        elif type(register_id) == str:
            addrs = self.registers[register_id]
            val = 0
            for addr in addrs[::-1]:
                val = (val << 16) + self.get_register(addr)
            return val

    def set_register(self, register_id, value):
        if type(register_id) == int:
            params = struct.pack('< H', value)
            parser = lambda payload: struct.unpack('<H', payload)[0]
            return self._send_request(RequestType.SET_REGISTER, register_id,
                                      req_payload=params, resp_parser=parser)
        elif type(register_id) == str:
            addrs = self.registers[register_id]
            for addr in addrs:
                out = value & 0xFFFF
                self.set_register(addr, out)
                value = value >> 16

    def get_bulk_data(self, block_type, block_id=0, max_blocks=1):
        params = struct.pack('< H H', block_id, max_blocks)
        parser = lambda payload: (struct.unpack('<H', payload[:2])[0],
                                  payload[2:])
        return self._send_request(RequestType.GET_BULK_DATA, block_type,
                                  req_payload=params, resp_parser=parser)

    # NOTE: This function is commented out because there is no documentation on
    # how to actually pass data to the devices, I have filled it what I could
    # figure out
    #def write_bulk_data(self, block_type, first_block_index, number_blocks, data):
    #    params = struct.pack('< H H', first_block_index, number_blocks)
    #    return self._send_request(RequestType.WRITE_BULK_DATA, block_type,
    #                              req_payload=params)

    def get_network_list(self):
        parser = lambda payload: (payload[2:],)
        return self._send_request(0, RequestType.GET_NETWORK_LIST,
                                  register_id, req_payload=params)

    def reset_device(self):
        return self._send_request(RequestType.CMD_RESET, 0)

    def __getattr__(self, name):

        if name.startswith("get_"):
            register_name = name[4:]
            if register_name not in self.registers:
                raise AttributeError(name)

            def getter():
                return self.get_register(register_name)
            return getter

        elif name.startswith("set_"):
            register_name = name[4:]
            if register_name not in self.registers:
                raise AttributeError(name)
            def setter(value):
                return self.set_register(register_name, value)
            return setter

        else:
            raise AttributeError(name)


class Display(Device):
    network_id = NetworkID.DISPLAY
    registers = {
         'min': [1],
         'hour': [2],
         'day': [3],
         'month': [4],
         'year': [5],
         # BULK DATA LIVES HERE
         'synched': [33],
         'version': [45],
         'hardware': [46],
         'configured': [83],
         'standingcharge': [129, 130],
         'unitcost': [131, 132],
         'EAC': [133, 134],
         'gridweekstart': [176],
         'gridweekstop': [177],
         'gridweekendstart': [178],
         'gridweekendstop': [179],
         'serial': [185, 186],
         'country': [187],
         'temp-offset': [192],
         'temp-gain': [193],
         'target': [222, 223],
         'cost0': [224],
         'cost1': [225],
         'cost2': [226],
         'cost3': [227],
         'start0': [228],
         'start1': [229],
         'start2': [230],
         'start3': [231],
    }

    def set_spend_rates(self, standing_charge, rate):
        standing_charge = max(min(int(standing_charge * 10000 + 0.5), 65534), 0)
        rate = max(min(int(rate * 10000 + 0.5), 65534), 0)
        return [
            self.set_register(self.registers["standingcharge"][0], standing_charge),
            self.set_register(self.registers["standingcharge"][1], 0),
            self.set_register(self.registers["unitcost"][0], rate),
            self.set_register(self.registers["unitcost"][1], 0)
        ]

    def get_spend_rates(self):
        standing_charge = self.get_register(self.registers["standingcharge"][0])
        standing_charge /= 10000
        rate = self.get_register(self.registers["unitcost"][0])
        rate /= 10000
        return (standing_charge, rate)

    def set_estimated_annual_consumption(self, eac_value):
        eac_value = int(eac_value / 3600000)
        eac_hi = eac_value >> 16
        eac_lo = eac_value & 65535
        return [
            self.set_register(self.registers["EAC"][0], eac_lo),
            self.set_register(self.registers["EAC"][1], eac_hi),
            self.set_register(self.CONFIGURED, 1)
        ]

    def get_estimated_annual_consumption(self):
        eac_lo = self.get_register(self.registers["EAC"][0])
        eac_hi = self.get_register(self.registers["EAC"][1])
        eac_value = (eac_hi << 16 + eac_lo)
        return eac_value


class Clamp(Device):
    network_id = NetworkID.CLAMP
    registers = {
        'type': [0],
        'version': [1],
        'serial': [2, 3],
        'status': [4],
        'power': [5],
        'readinginterval': [6],
        'sendinginterval': [7],
        'timestamp': [8, 9],
        'voltage': [10],
        'calphase0': [11],
        'calgain0': [12],
        'temperature': [13],
        'powervars': [14],
        'RSSI': [15],
        'EAR': [16, 17],
        'batteryvolts': [18],
        'txpower': [19],
        'instwatt': [23],
        'instvar': [24],
        'calgain1': [25],
        'calgain2': [26],
        'txperiodlimits': [27],
        'calgain3': [28],
        'calgain4': [29]
    }

    def get_cumulative_kwh(self):
        EAR = self.get_EAR()
        return EAR/10000
