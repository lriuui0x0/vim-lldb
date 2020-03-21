def msg_pack_int(obj):
    return obj.to_bytes(8, 'little', signed=True)

def msg_pack_str(obj):
    data = bytearray()
    data.extend(msg_pack_int(len(obj)))
    data.extend(obj.encode())
    return data

type_encoding = {int: 0, str: 1, list: 2, dict: 3}
def msg_pack(obj):
    data = bytearray()
    data.extend(msg_pack_int(type_encoding[type(obj)]))

    if type(obj) == int:
        data.extend(msg_pack_int(obj))
    elif type(obj) == str:
        data.extend(msg_pack_str(obj))
    elif type(obj) == list:
        data.extend(msg_pack_int(len(obj)))
        for x in obj:
            data.extend(msg_pack(x))
    elif type(obj) == dict:
        data.extend(msg_pack_int(len(obj)))
        for k, v in obj.items():
            data.extend(msg_pack_str(k))
            data.extend(msg_pack(v))

    return bytes(data)

def msg_unpack_int(buf):
    obj = int.from_bytes(buf[:8], 'little', signed=True)
    return obj, buf[8:]

def msg_unpack_str(buf):
    length, buf = msg_unpack_int(buf)
    obj = buf[:length].decode()
    return obj, buf[length:]

type_decoding = [int, str, list, dict]
def msg_unpack(buf):
    type_value, buf = msg_unpack_int(buf)
    msg_type = type_decoding[type_value]

    if msg_type == int:
        obj, buf = msg_unpack_int(buf)
    elif msg_type == str:
        obj, buf = msg_unpack_str(buf)
    elif msg_type == list:
        length, buf = msg_unpack_int(buf)
        obj = []
        for _ in range(length):
            data, buf = msg_unpack(buf)
            obj.append(data)
    elif msg_type == dict:
        length, buf = msg_unpack_int(buf)
        obj = {}
        for _ in range(length):
            key, buf = msg_unpack_str(buf)
            value, buf = msg_unpack(buf)
            obj[key] = value

    return obj, buf

