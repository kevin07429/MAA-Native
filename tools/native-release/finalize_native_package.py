"""Finalize the portable archive after applying the app's resource preparation hook."""
import argparse
import hashlib
import json
from pathlib import Path
from package_native import archive_tree

p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--version',required=True)
a=p.parse_args();root=a.output.resolve();folder=root/('portable-'+a.version)
manifest={f.relative_to(folder).as_posix():hashlib.sha256(f.read_bytes()).hexdigest()
          for f in sorted(folder.rglob('*')) if f.is_file() and f.name!='文件校验-SHA256.json'}
(folder/'文件校验-SHA256.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
name=f'MAA-{a.version}-win-x64.zip';digest=archive_tree(folder,root/name)
p=root/'native-release.json';release=json.loads(p.read_text(encoding='utf8'));release['artifacts'][name]=digest;p.write_text(json.dumps(release,indent=2),encoding='utf8')
print('Final portable archive and checksums updated')
