#!/usr/bin/env python3
import builtins
import os
import shlex
import subprocess
import sys
from pathlib import Path

DEBUG = os.environ.get("DEBUG")

URL = "https://images.linuxcontainers.org/images/"


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
    from lxml.html import fromstring as string2html

    try:
        result = subprocess.run(
            ["curl", "-s", "--max-time", "3", url],
            capture_output=True,
            text=True,
            check=True,
        )
        html = string2html(result.stdout)
        directories = html.xpath("//a/text()")
        latest = [x.rstrip("/") for x in sorted(directories, reverse=True)]
        return latest
    except Exception:
        if DEBUG:
            raise


def _images_iter_available():
    images = _images_index_fetch(URL)
    if images is None:
        print("Oops, can not query rootfs directory")
        return
    for distribution in images:
        releases = _images_index_fetch(URL + distribution)
        if releases is None:
            continue
        for release in releases:
            for arch in ["amd64", "arm64"]:
                yield from _images_iter_available_version(distribution, release, arch)


def _images_iter_available_version(distribution, release, arch):
    builds = _images_index_fetch(
        URL + distribution + "/" + release + "/" + arch + "/default/"
    )
    if builds is None:
        return
    for build in builds:
        url = "{URL}{distribution}/{release}/{arch}/default/{build}/".format(
            URL=URL, distribution=distribution, release=release, arch=arch, build=build
        )
        yield url


def cli_images_available():
    for url in _images_iter_available():
        print(url)


def usage():
    print(
        """Usage:

  ing0 baggify
  ing0 summary
  ing0 fastapi routes
  ing0 vm available
  ing0 vm create DIRECTORY DISTRIBUTION RELEASE ARCH
  ing0 vm exec DIRECTORY [COMMAND ...]
  ing0 vm spawn DIRECTORY
  ing0 sqli NAME
"""
    )
    return -1


def _images_latest(distribution, release, arch):
    out = list(_images_iter_available_version(distribution, release, arch))
    try:
        return out[-1]
    except IndexError:
        return None


def cli_create(directory, distribution, release, arch):
    print("* ing0: making {}".format(directory))
    work = Path(directory).resolve()
    work.mkdir(parents=True, exist_ok=True)
    root = _images_latest(distribution, release, arch)
    url = root + "rootfs.tar.xz"
    run("cd {} && wget {}".format(shlex.quote(str(work)), shlex.quote(url)))
    url = root + "SHA256SUMS"
    run("cd {} && wget {}".format(shlex.quote(str(work)), shlex.quote(url)))
    run(
        "cd {} && grep -F rootfs.tar.xz SHA256SUMS | sha256sum -c -".format(shlex.quote(str(work)))
    )
    run("cd {} && tar xf rootfs.tar.xz".format(shlex.quote(str(work))))
    # XXX: delete machine-id because it clash with systemd-d128 later in exec
    run("cd {} && rm -f etc/machine-id".format(shlex.quote(str(work))))
    # XXX: delete resolve.conf, and copy the host one when needed in exec
    run("cd {} && rm -f etc/resolv.conf".format(shlex.quote(str(work))), verbose=True)
    run(
        "cd {} && echo {} > etc/hostname".format(shlex.quote(str(work)), shlex.quote(work.name)),
        verbose=True,
    )
    print("* ing0: what is done is not to be done!")
    return 0


def cli_exec(directory, *extra):
    work = Path(directory).resolve()
    print("* ing0: exec {}".format(work.name))
    print("** prepare...")
    run("cd {} && cp /etc/resolv.conf etc/resolv.conf".format(shlex.quote(str(work))))
    print("** exec in progress: {}".format(" ".join(extra)))
    print("** mounting `{}` at `/mnt/`".format(Path.cwd()))

    command = "systemd-nspawn --background= --uuid=$(systemd-id128 new) -D {} --bind={}:/mnt".format(
        shlex.quote(str(work)), shlex.quote(str(Path.cwd()))
    )
    if not extra:
        extra = ["bash"]
    command += (
        " "
        + "/usr/bin/env PATH=/usr/local/bin/:/usr/bin/:/bin/:/sbin/ "
        + " ".join(shlex.quote(a) for a in extra)
    )
    code = subprocess.run(command, shell=True).returncode
    # forward systemd-nspawn exit code
    return code


def cli_spawn(path):
    work = Path(path).resolve()
    print("* ing0: booting {}".format(work))
    print("** prepare...")
    run("cd {} && cp /etc/resolv.conf etc/resolv.conf".format(shlex.quote(str(work))))
    print("** spawning in progress...")
    print("** mounting `{}` at `/mnt/`".format(Path.cwd()))
    # legacy
    # command = "systemd-nspawn --machine={name} --boot --capability=CAP_NET_ADMIN --network-veth --uuid=$(systemd-id128 new) -D '{work}' --bind={cwd}:/mnt"

    # new for docker within nspawn
    command = "systemd-nspawn --background= --machine={} --boot --system-call-filter='@keyring bpf' --capability=CAP_SYS_ADMIN,CAP_NET_ADMIN --network-veth --uuid=$(systemd-id128 new) -D {} --bind={}:/mnt".format(
        shlex.quote(work.name), shlex.quote(str(work)), shlex.quote(str(Path.cwd()))
    )
    code = subprocess.run(command, shell=True).returncode
    # forward systemd-nspawn exit code
    return code




def sqli(uri, output, includes):
    try:
        from eralchemy2 import render_er
    except ImportError:
        print("Try: pip install eralchemy2")
        return 42

    render_er(uri, output, include_tables=includes)
    return 0


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
        out = out.format(route=route, methods=" ".join(sorted(route.methods)))
        print(out)


def baggify(path, count=None, reverse=True):
    """Glimpsing over the code base, big words first"""
    import pathlib
    import sys
    from collections import Counter

    IGNORED = "data return None dict self from import class name value Optional else"
    IGNORED = set(IGNORED.split())
    BUILTINS = set(dir(builtins))

    path = pathlib.Path(path).resolve()
    bag = Counter()
    for py in path.rglob("*.py"):
        with py.open() as py:
            string = py.read()
            string = "".join([x if x.isalnum() else " " for x in string])
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
        if name in BUILTINS:
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
    if "/." in path:
        return False
    if "node_modules" in path:
        return False
    if "__pycache__" in path:
        return False
    return True


def _iter_directories(root):
    for subdir, dirs, files in os.walk(root):
        if not is_interesting(subdir):
            continue
        yield Path(subdir).resolve()


def sloc(directory):
    files = 0
    lines = 0
    for py in directory.rglob("*.py"):
        with py.open() as py:
            files += 1
            for line in py:
                if line.strip():
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


def main():
    match sys.argv[1:]:
        case ["baggify", directory]:
            return baggify(directory)
        case ["summary", root]:
            return summary(root)
        case ["fastapi", "routes"]:
            return fastapi_routes()
        case ["vm", "available", *args]:
            return cli_images_available()
        case ["vm", "create", *args]:
            return cli_create(*args)
        case ["vm", "exec", *args]:
            return cli_exec(*args)
        case ["vm", "spawn", name]:
            return cli_spawn(name)
        case ["sqli", uri, *includes]:
            return sqli(uri, "out.png", includes)
        case _:
            return usage()


if __name__ == "__main__":
    sys.exit(main())
