"""Build only in this experiment and retain the exact source/compiler provenance."""
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent

def build():
    from catalog import source_hashes
    folder = HERE/'build'
    folder.mkdir(exist_ok=True)
    files = source_hashes()
    native_files = {name:digest for name,digest in files.items() if Path(name).suffix in {'.cpp','.hpp'} or Path(name).name=='CMakeLists.txt'}
    manifest = folder/'provenance.json'
    previous = json.loads(manifest.read_text()) if manifest.exists() else {}
    if previous.get('native_source_hashes') == native_files and (folder/'observe_cpp').exists():
        previous['source_hashes'] = files
        manifest.write_text(json.dumps(previous,ensure_ascii=False,indent=2))
        return previous
    with (folder/'build.log').open('a') as log:
        for command in [['cmake','-S',str(HERE),'-B',str(folder),'-DCMAKE_BUILD_TYPE=Release'],
                        ['cmake','--build',str(folder),'-j','1']]:
            subprocess.run(command,stdout=log,stderr=log,check=True)
    if source_hashes() != files:
        raise RuntimeError('Source changed during build; rebuild to obtain consistent provenance')
    data = dict(source_hashes=files, native_source_hashes=native_files, binary_sha256=hashlib.sha256((folder/'observe_cpp').read_bytes()).hexdigest(),
                compiler=subprocess.check_output(['c++','--version'],text=True).strip(),
                build_type='Release', compile_commands='build/compile_commands.json')
    manifest.write_text(json.dumps(data,ensure_ascii=False,indent=2))
    return data

if __name__ == '__main__':
    build()
    print('Observer ready: build/observe_cpp')
