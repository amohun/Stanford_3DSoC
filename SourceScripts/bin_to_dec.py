"""
Dec to Bin Converter
Convert Bin to Dec or Dec to Bin Easily
"""

input_bin_num = "100000000000000010010101"
input_dec_num = None

output_bin_num = None
output_dec_num = None

if type(input_bin_num) == str:
    print(input_bin_num)
    num = [int(n) for n in input_bin_num]
    num.reverse()
    dec = 0
    i = 0
    for i,n in enumerate(num):
        dec += (2**i)*n
    
    print(f"bin: {input_bin_num}\ndec: {dec}")
