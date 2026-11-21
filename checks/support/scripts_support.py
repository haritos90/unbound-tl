import struct

def words(*values):
    return struct.pack("<" + "H" * len(values), *values)
