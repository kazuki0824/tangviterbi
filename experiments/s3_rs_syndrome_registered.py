"""Register end-of-input status to remove the count comparator from ROM muxes."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def source():
 s=(ROOT/'rtl/s3_rs_syndrome.sv').read_text()
 changes={
  'reg busy,reading,first_byte;':'reg busy,reading,first_byte,last_byte;',
  'accepted<204':'!last_byte',
  'accepted==204':'last_byte',
  'if(!resetn)begin busy<=0;':'if(!resetn)begin last_byte<=0;busy<=0;',
  'out_valid<=0;accepted<=0;end':'out_valid<=0;accepted<=0;last_byte<=0;end',
  'byte_q<=in_byte;first_byte<=':'last_byte<=accepted==203;byte_q<=in_byte;first_byte<=',
 }
 for old,new in changes.items():
  if s.count(old)!=1:raise ValueError('source contract changed: '+old)
  s=s.replace(old,new)
 return s
if __name__=='__main__':print(source())
