
def decode_uint(ser):
    """
    Convert bytes to int
    """
    res = 0
    for v in ser:
        res = res * 256 + v
    return res
