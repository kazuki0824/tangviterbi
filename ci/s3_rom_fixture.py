"""Fetch only the IDF 5.5.1 recommended rev0 ROM ELF after archive hash validation."""
import argparse,hashlib,io,tarfile,urllib.request
from pathlib import Path
URL='https://github.com/espressif/esp-rom-elfs/releases/download/20241011/esp-rom-elfs-20241011.tar.gz'
SHA256='921f000164a421c7628fbfee55b173384aafaa51883adc65cd27bf9b0af9e9a9'
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    data=urllib.request.urlopen(URL).read()
    if hashlib.sha256(data).hexdigest()!=SHA256:raise ValueError('ROM archive hash mismatch')
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as tar:
        members=[m for m in tar.getmembers() if m.isfile() and Path(m.name).name=='esp32s3_rev0_rom.elf']
        if len(members)!=1:raise ValueError('ambiguous/missing S3 rev0 ROM')
        payload=tar.extractfile(members[0]).read()
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(payload)
    print('Verified S3 rev0 ROM ELF:',a.output)
if __name__=='__main__':main()
