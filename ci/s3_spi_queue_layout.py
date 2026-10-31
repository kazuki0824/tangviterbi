"""Read actual saved ELF DWARF; layout/config evidence, not a WCET audit."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
from elftools.elf.elffile import ELFFile

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'reports/s3-raw-tasks/sdk-launcher/n16r8-late-stacks-no-phy-nvs-raw-only-spi'


def report():
    data = gzip.decompress((BASE/'s3_raw_probe.elf.gz').read_bytes())
    digest = hashlib.sha256(data).hexdigest()
    assert digest == '7ee25471a6dc96c056c2afd883cf4f70282fd186be920cced7dddefa40554fc7'
    config_bytes = gzip.decompress((BASE/'sdkconfig.json.gz').read_bytes())
    config = json.loads(config_bytes)
    assert config['FREERTOS_NUMBER_OF_CORES'] == 2
    assert config['FREERTOS_UNICORE'] is False
    assert config['SOC_SPI_SCT_SUPPORTED'] is True
    matches = []
    for cu in ELFFile(io.BytesIO(data)).get_dwarf_info().iter_CUs():
        for die in cu.iter_DIEs():
            name = die.attributes.get('DW_AT_name')
            if name and name.value == b'spi_trans_priv_t':
                struct = die.get_DIE_from_attribute('DW_AT_type')
                members = {member.attributes['DW_AT_name'].value.decode():
                           member.attributes['DW_AT_data_member_location'].value
                           for member in struct.iter_children() if member.tag == 'DW_TAG_member'}
                size = struct.attributes['DW_AT_byte_size'].value
                assert size == 20
                assert members == dict(trans=0, buffer_to_send=4, buffer_to_rcv=8, reserved=12)
                matches.append(dict(size=size, members=members))
    assert matches
    sources = ('reports/s3-spi-wait-audit/sources/queue.c',
               'reports/s3-spi-wait-audit/sources/spi_master.c',
               'experiments/s3_spi_transport.c','experiments/s3_parallel_spi.c')
    return dict(scope=__doc__, elf_sha256=digest,
                sdkconfig_sha256=hashlib.sha256(config_bytes).hexdigest(),
                config={key:config[key] for key in ('FREERTOS_NUMBER_OF_CORES',
                    'FREERTOS_UNICORE','SOC_SPI_SCT_SUPPORTED')},
                descriptor_layouts=matches,
                source_sha256={path:hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
                               for path in sources},
                elapsed_upper_cycles=None, receiver_adopted=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report(),indent=2)+'\n')
