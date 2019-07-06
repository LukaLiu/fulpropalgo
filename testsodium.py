from ctypes import* 
import os 

lib = CDLL("/home/yliu7/Data/libsodium/lib/libsodium.so")

func = lib.crypto_vrf_is_valid_key
func.restype=c_int

input=b'sds'
print(func)
res =func(input).contents

print(res)
