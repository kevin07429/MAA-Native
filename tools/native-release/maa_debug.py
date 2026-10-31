"""Control the local MAA debug pipe without desktop input or focus changes."""
import argparse
import base64
import json
from pathlib import Path
import struct
import time


def request(command, **arguments):
    root = Path(__file__).resolve().parent.parent
    deadline = time.monotonic() + 15
    while True:
        try:
            descriptor = json.loads((root / 'cache/debug-control.json').read_text(encoding='utf-8-sig'))
            pipe_path = '\\\\.\\pipe\\' + descriptor['pipe']
            pipe = open(pipe_path, 'r+b', buffering=0)
            break
        except (OSError, json.JSONDecodeError):
            if time.monotonic() >= deadline:
                raise RuntimeError('MAA debug pipe is unavailable; start the updated MAA first')
            time.sleep(.05)
    with pipe:
        payload = json.dumps({'command': command, **arguments}, ensure_ascii=False).encode('utf-8')
        if len(payload) > 4096:
            raise ValueError('Request is too large')
        packet = memoryview(struct.pack('<I', len(payload)) + payload)
        while packet:
            count = pipe.write(packet)
            if not count:
                raise RuntimeError('Debug pipe disconnected while writing')
            packet = packet[count:]

        def read_exact(length):
            chunks = bytearray()
            while len(chunks) < length:
                chunk = pipe.read(length - len(chunks))
                if not chunk:
                    raise RuntimeError('Debug pipe disconnected while reading')
                chunks.extend(chunk)
            return chunks

        size = struct.unpack('<I', read_exact(4))[0]
        if not 0 < size <= 32 * 1024 * 1024:
            raise ValueError('Invalid response size')
        return json.loads(read_exact(size))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['status', 'connect', 'start', 'stop', 'pause', 'resume', 'screenshot', 'click', 'shutdown'])
    parser.add_argument('coordinates', nargs='*', type=int)
    parser.add_argument('--task', help='Start one configured task, e.g. Recruit, Infrast, Roguelike')
    parser.add_argument('--facility', nargs='+', help='Run only these facilities in a temporary Infrast task')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent / 'debug-phone.png')
    args = parser.parse_args()
    parameters = {}
    if args.command == 'click':
        if len(args.coordinates) != 2:
            parser.error('click needs x y in the returned screenshot coordinate space')
        parameters.update(zip(('x', 'y'), args.coordinates))
    if args.task:
        parameters['task'] = args.task
    if args.facility:
        parameters['facility'] = args.facility
    try:
        response = request(args.command, **parameters)
    except (OSError, RuntimeError, ValueError) as error:
        response = {'ok': False, 'error': str(error)}
    if 'png_base64' in response:
        args.output.write_bytes(base64.b64decode(response.pop('png_base64'), validate=True))
        response['image'] = str(args.output.resolve())
    print(json.dumps(response, ensure_ascii=False, indent=2))
    raise SystemExit(0 if response.get('ok') else 1)
