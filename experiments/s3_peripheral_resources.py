"""ESP-IDF 5.5.1 S3 peripheral allocation necessary conditions.

Full-duplex I2S clock sharing applies within one controller and requires
matching clock/slot configurations. This does not synchronize RX/TX payloads.
SPI drivers reserve a complete GDMA TX/RX pair, even for one-way use.
LCD and I2S allocate directional channels; SDMMC uses its own DMA engine.
No simultaneous-memory bandwidth or electrical timing proof is implied.
"""

def pin_count(ports,share_i2s_clock=True):
 names={p['name'] for p in ports}
 shared=[ctl for ctl in (0,1) if {f'I2S{ctl}_RX40',f'I2S{ctl}_TX40'}<=names]
 return sum(p['pin_lower_bound'] for p in ports)-(2*len(shared) if share_i2s_clock else 0)

def shared_i2s_controllers(ports):
 names={p['name'] for p in ports}
 return [ctl for ctl in (0,1) if {f'I2S{ctl}_RX40',f'I2S{ctl}_TX40'}<=names]

def gdma_allocation(ports,reserved_pairs=0):
 if not 0<=reserved_pairs<=5:raise ValueError('invalid reservation')
 spi=[p['name'] for p in ports if p['name'].startswith('SPI')]
 tx=[p['name'] for p in ports if p['name'].startswith('LCD') or '_TX' in p['name']]
 rx=[p['name'] for p in ports if p['name'].startswith('CAM') or '_RX' in p['name']]
 tx_used=reserved_pairs+len(spi)+len(tx);rx_used=reserved_pairs+len(spi)+len(rx)
 fits=max(tx_used,rx_used)<=5
 allocation=[dict(pair=i,tx='reserved',rx='reserved') for i in range(reserved_pairs)]
 allocation += [dict(pair=i+reserved_pairs,tx=name,rx=name) for i,name in enumerate(spi)]
 for i in range(max(len(tx),len(rx))):
  allocation.append(dict(pair=reserved_pairs+len(spi)+i,
   tx=tx[i] if i<len(tx) else None,rx=rx[i] if i<len(rx) else None))
 return dict(TX_channels=tx_used,RX_channels=rx_used,pairs_lower_bound=max(tx_used,rx_used),
  available_pairs=5,reserved_pairs=reserved_pairs,selected_driver_capacity_pass=fits,
  allocation=allocation if fits else None,
  SDMMC_DMA_hosts=sum(p['name'].startswith(('SDIO','eMMC')) for p in ports),
  DMA_memory_bandwidth_verified=False)

def constraints(ports):
 pins=pin_count(ports);shared=shared_i2s_controllers(ports)
 return dict(signal_pins=pins,I2S_shared_clock_controllers=shared,
  I2S_shared_clock_requires_matching_clock_and_slots=bool(shared),
  I2S_40MHz_role='S3 master design scenario; FPGA slave endpoint and IO timing unverified',
  I2S_40MHz_master_clock=dict(source_Hz=160000000,sample_rate_Hz=625000,
   slots=2,slot_bits=32,mclk_multiple=128,MCLK_Hz=80000000,BCLK_Hz=40000000,
   source_divider=2,BCLK_divider=2,MCLK_pin_used=False),
  gdma=gdma_allocation(ports),pin_mapping_verified=False,IO_STA_verified=False)
