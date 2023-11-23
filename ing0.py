#!/usr/bin/env python3
import sys
import os
from pathlib import Path
import shlex
import subprocess

from lxml.html import fromstring as string2html
import requests


DEBUG = os.environ.get("DEBUG")

URL = 'https://uk.lxd.images.canonical.com/images/'


def test_nop():
    assert True

def run(command, verbose=False):
    print("** subprocess.run({})".format(command))
    if verbose:
        return subprocess.run(command, shell=True, check=True, capture_output=True)
    else:
        return subprocess.run(
            command,
            shell=True,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def _images_index_fetch(url):
    try:
        response = requests.get(url, timeout=3)
        html = string2html(response.text)
        directories = html.xpath('//tr/td/a/text()')
        directories.remove('Parent Directory')
        latest = [x.rstrip('/') for x in sorted(directories, reverse=True)]
        return latest
    except Exception:
        if DEBUG:
            raise


def _images_iter_available():
    images = _images_index_fetch(URL)
    if images is None:
        print("Oops, can not query rootfs directory")
        return 42
    for distribution in images:
        releases = _images_index_fetch(URL + distribution)
        for release in releases:
            for arch in ['amd64', 'arm64']:
                yield from _images_iter_available_version(distribution, release, arch)


def _images_iter_available_version(distribution, release, arch):
    builds = _images_index_fetch(URL + distribution + '/' + release + '/' + arch + '/default/')
    if builds is None:
        return
    url = "{URL}{distribution}/{release}/{arch}/default/{build}/"
    for build in builds:
        url = url.format(
            URL=URL,
            distribution=distribution,
            release=release,
            arch=arch,
            build=build
        )
        yield url


def cli_images_available():
    for url in _images_iter_available():
        print(url)


def usage():
    print("""Usage:

  ing0 baggify
  ing0 summary
  ing0 fastapi routes
  ing0 vm available
  ing0 vm create NAME DISTRIBUTION RELEASE ARCH
  ing0 vm exec NAME [COMMAND ...]
  ing0 vm spawn NAME
  ing0 vm boot NAME
  ing0 sqli NAME
""")
    return -1


def _images_latest(distribution, release, arch):
    out = list(_images_iter_available_version(distribution, release, arch))
    try:
        return out[-1]
    except IndexError:
        return None


def cli_create(name, distribution, release, arch):
    print("* ing0: making {}".format(name))
    work = Path.home() / '.local' / 'ing0' / name
    work.mkdir(parents=True, exist_ok=True)
    root = _images_latest(distribution, release, arch)
    url = root + 'rootfs.tar.xz'
    run("cd {work} && wget '{url}'".format(work=work, url=url))
    url = root + 'SHA256SUMS'
    run("cd {work} && wget '{url}'".format(work=work, url=url))
    run("cd {work} && fgrep rootfs.tar.xz SHA256SUMS | sha256sum -c -".format(work=work))
    run("cd {work} && tar xf rootfs.tar.xz".format(work=work))
    # XXX: delete machine-id because it clash with systemd-d128 later in exec
    run("cd {work} && rm etc/machine-id".format(work=work))
    # XXX: delete resolve.conf, and copy the host one when needed in exec
    run("cd {work} && rm etc/resolv.conf".format(work=work), verbose=True)
    run("cd {work} && echo {name} > etc/hostname".format(work=work, name=name), verbose=True)
    print("* ing0: what is done is not to be done!")
    return 0


def cli_exec(name, *extra):
    print("* ing0: spawning {}".format(name))
    work = Path.home() / '.local' / 'ing0' / name
    print("** prepare...")
    run("cd {work} && cp /etc/resolv.conf etc/resolv.conf".format(work=work))
    print("** spawn in progress: {}".format(' '.join(extra)))
    command = "systemd-nspawn --uuid=$(systemd-id128 new) -D '{work}' --bind={cwd}:/mnt"
    command = command.format(name=name, work=work, cwd=Path.cwd())
    if not extra:
        extra = ['bash']
    command += ' ' + '/usr/bin/env PATH=/usr/local/bin/:/usr/bin/:/bin/:/sbin/ ' + ' '.join(extra)
    code = subprocess.run(command, shell=True).returncode
    # foward systemd-nspawn exit code
    return code


def cli_spawn(name):
    print("* ing0: booting {}".format(name))
    work = Path.home() / '.local' / 'ing0' / name
    print("** prepare...")
    run("cd {work} && cp /etc/resolv.conf etc/resolv.conf".format(work=work))
    print("** booting in progress...")
    command = "systemd-nspawn --machine={name} --boot --capability=CAP_NET_ADMIN --uuid=$(systemd-id128 new) -D '{work}' --bind={cwd}:/mnt"
    command = command.format(name=name, work=work, cwd=Path.cwd())
    code = subprocess.run(shlex.split(command)).returncode
    # foward systemd-nspawn exit code
    return code


# XXX: Guest rootfs is a host directory, without image indirection.
QEMU_ROOTFS_BARE = """
qemu-system-x86_64 \
    -enable-kvm \
    -machine pc,accel=kvm,usb=off,dump-guest-core=off -m 2048 \
    -smp 4,sockets=4,cores=1,threads=1 -rtc base=utc \
    -boot strict=on -kernel {kernel} \
    -initrd {initrd} \
    -append 'init=/usr/lib/systemd/systemd root=fsRoot rw rootfstype=9p rootflags=trans=virtio,version=9p2000.L,msize=5000000,posixacl console=ttyS0' \
    -fsdev local,security_model=none,multidevs=remap,id=fsdev-fsRoot,path={root} \
    -device virtio-9p-pci,id=fsRoot,fsdev=fsdev-fsRoot,mount_tag=fsRoot \
    -nographic
"""


def cli_boot(name):
    print("* ing0: emulate {}".format(name))
    work = Path.home() / '.local' / 'ing0' / name
    print("** setup initramfs with kernel drivers 9p @ {}".format(work))
    run("cd {work} && cp /etc/resolv.conf etc/resolv.conf".format(work=work))
    print("** emulation in progress...")
    kernel = work / 'boot' / 'vmlinuz'
    initrd = work / 'boot' / 'initrd.img'
    command = QEMU_ROOTFS_BARE.format(root=work, kernel=kernel, initrd=initrd)
    code = subprocess.run(shlex.split(command)).returncode
    return code


def sqli(uri, output, includes):
    try:
        from eralchemy2 import render_er
    except ImportError:
        print("Try: pip install eralchemy2")
        exit(42)

    render_er(uri, output, include_tables=includes)
    exit(0)


def fastapi_routes():
    """Available HTTP routes"""
    from app import app
    routes = sorted(app.routes, key=lambda x: x.path)
    # See also:
    #
    #  $ curl https://127.0.0.1:8000 > openapi.json
    #  $ api2thml openapi.json -o index.html
    #  $ python3 -m http.server
    #
    for route in routes:
        out = "{route.path}\t{methods}\t{route.endpoint.__module__}:{route.endpoint.__name__}"
        out = out.format(route=route, methods=' '.join(sorted(route.methods)))
        print(out)


def baggify(path, count=None, reverse=True):
    """Glimpsing over the code base, big words first"""
    import pathlib, sys
    from collections import Counter

    IGNORED = 'data return None dict self from import class name value Optional else'
    IGNORED = set(IGNORED.split())

    path = pathlib.Path(path).resolve()
    bag = Counter()
    for py in path.rglob("*.py"):
        with py.open() as py:
            string = py.read()
            string = ''.join([x if x.isalnum() else ' ' for x in string])
            tokens = string.split()
            bag.update(tokens)

    if count is None:
        count = len(bag)

    bag = bag.most_common(len(bag))

    if reverse:
        bag = list(reversed(bag))

    for name, total in bag:
        if len(name) <= 3:
            continue
        if name in set([str(x) for x in dir(__builtins__)]):
            continue
        if name in IGNORED:
            continue
        print(name, total)
        count -= 1
        if count == 0:
            break
    return 0


def is_interesting(path):
    path = str(path)
    if '/.' in path:
        return False
    if 'node_modules' in path:
        return False
    if '__pycache__' in path:
        return False
    return True


def _iter_directories(root):
    import os
    from pathlib import Path
    for subdir, dirs, files in os.walk(root):
        if not is_interesting(subdir):
            continue
        path = Path(root) / subdir
        path = path.resolve()
        yield path


def sloc(directory):
    files = 0
    lines = 0
    for py in directory.rglob('*.py'):
        with py.open() as py:
            files += 1
            for line in py:
                if not line.strip().isspace():
                     lines += 1
    return files, lines


def summary(root):
    """Number of files, lines of python code, and bag per directory"""
    from pathlib import Path
    root = Path(root).resolve()

    for directory in _iter_directories(root):
        files, lines = sloc(directory)
        if files == 0 or lines == 0:
            continue
        print("\n* summary {}".format(directory))
        print("** file count: {} ".format(files))
        print("** line count: {} ".format(lines))
        print("** bag\n")
        baggify(directory, 10, reverse=False)


def __main__():
    match sys.argv[1:]:
        case ["baggify", directory]:
            sys.exit(baggify(directory))
        case ["summary", root]:
            sys.exit(summary(root))
        case ["fastapi", "routes"]:
            sys.exit(fastapi_routes())
        case ['vm', 'available', *args]:
            return cli_images_available()
        case ['vm', 'create', *args]:
            return cli_create(*args)
        case ['vm', 'exec', *args]:
            return cli_exec(*args)
        case ['vm', 'spawn', name]:
            return cli_spawn(name)
        case ['vm', 'boot', name]:
            return cli_boot(name)
        case ['sqli', uri, *includes]:
            return sqli(uri, 'out.png', includes)
        case _:
            return usage()


if __name__ == "__main__":
    exit(__main__())
