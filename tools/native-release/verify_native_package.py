"""Validate a public package using file hashes and the Debug core, without device input."""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import sys

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--folder',type=Path,required=True)
p.add_argument('--debug-dll',type=Path,required=True)
p.add_argument('--version',required=True)
a=p.parse_args();root=a.folder.resolve()
manifest=json.loads((root/'文件校验-SHA256.json').read_text(encoding='utf8'))
for name,digest in manifest.items():
    path=(root/name).resolve()
    assert path.is_relative_to(root),name
    assert hashlib.sha256(path.read_bytes()).hexdigest()==digest,name
j=json.loads((root/'config/gui.new.json').read_text(encoding='utf8'))
for profile in j['Configurations'].values():
    assert all(not item['IsEnable'] for item in profile['TaskQueue'])
    assert not profile['Gui']['StartUpSettings']['RunDirectly']
    c=profile['Gui']['ConnectSettings'];assert not c['Address'] and not c['AddressHistory']
    assert (root/c['AdbPath']).is_file()
for name in ['data','cache','debug']:
    assert not (root/name).exists(),name
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from maa_core_eval import CoreEval
core=CoreEval(dll_dir=a.debug_dll.resolve(),resource=root)
try:
    core._lib.AsstGetVersion.restype=ctypes.c_char_p
    actual=core._lib.AsstGetVersion().decode()
    assert actual==a.version,(actual,a.version)
finally:
    core.close()
print(f'PASS: {len(manifest)} files, self-contained package, clean configuration and Debug resource load for {a.version}')
