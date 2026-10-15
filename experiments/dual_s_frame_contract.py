"""Conservation and traffic of the implemented conventional-S byte transpose.

ITU-R BO.1408-1 Annex 1 section 5 / Figure 6, 48 active TC8PSK slots.
This is the DMA layout's traffic, not a lower bound for every implementation.
"""
from fractions import Fraction
from functools import lru_cache


def scatter_blocks():
    """Independent transmitter-column enumeration, rather than RTL formulas."""
    result=[]
    for transmitted_frame in range(8):
        for original_frame in range(8):
            columns=[x//8+1 for x in range(transmitted_frame*203,(transmitted_frame+1)*203)
                     if x%8==original_frame]
            if transmitted_frame==0:columns.insert(0,0)  # restored MPEG sync
            result.append((transmitted_frame,original_frame,columns,sorted({b//32 for b in columns})))
    return result


@lru_cache(None)
def traffic():
    writes=48*sum(len(blocks) for _,_,_,blocks in scatter_blocks())
    reads=384*7
    bytes_per_cw=Fraction((writes+reads)*32,384)
    return dict(write_bursts_per_superframe=writes,read_bursts_per_superframe=reads,
                bytes_per_codeword=int(bytes_per_cw),
                peak_MBps=float(bytes_per_cw*Fraction(28860000,203*4)/1000000),
                sdram_bytes=2*384*224,packet_payload_capacity=2*203,
                packet_ram_logical_bytes=512,packet_BSRAM_blocks=1,
                output_fifo_words=512,output_fifo_word_bits=35,output_fifo_BSRAM_blocks=1,
                output_fifo_payload_bytes=2048,output_word_bytes=4,
                read_burst_holding_bytes=32,write_burst_holding_bytes=32)
