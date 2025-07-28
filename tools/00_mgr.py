#!/usr/bin/env python3
import logging
import os
import os.path
import subprocess
from sys import platform

log = logging.getLogger("run-fontlab")
loghandler = logging.StreamHandler()
loghandler.setLevel(logging.WARNING)
logformatter = logging.Formatter("[%(name)s.%(levelname)s] %(message)s")
loghandler.setFormatter(logformatter)
log.addHandler(loghandler)


def shell(arglist):
    try:
        out = subprocess.check_output(arglist).decode("utf-8").splitlines()
    except subprocess.CalledProcessError:
        out = []
    if len(out):
        return out
    else:
        log.warn("No results for command: %s" % (" ".join(arglist)))
        return None


def locateFontLabApp(app_path=None):
    if platform == "linux" or platform == "linux2":
        wineexe = shell(["which", "wine"])
        if not wineexe:
            log.error("You must install Wine")
        if not app_path:
            wineprefix = os.path.realpath(
                os.environ.get(
                    "WINEPREFIX", os.path.join(os.path.expanduser("~"), ".wine")
                )
            )
            if not os.path.isdir(wineprefix):
                log.error("You must specify the FontLab path")
            else:
                app_path = os.path.join(
                    wineprefix,
                    "drive_c",
                    "Program Files",
                    "Fontlab",
                    "FontLab 7",
                    "FontLab 7.exe",
                )
                if not os.path.isfile(app_path):
                    app_path = os.path.join(
                        wineprefix,
                        "drive_c",
                        "Program Files (x86)",
                        "Fontlab",
                        "FontLab 7",
                        "FontLab 7.exe",
                    )
                    if not os.path.isfile(app_path):
                        log.error("You must specify the FontLab path")
        if wineexe and app_path:
            pass
    elif platform == "darwin":
        if not app_path:
            pass
    elif platform == "win32":
        pass


app_path = shell(["mdfind", "kMDItemCFBundleIdentifier=='com.fontlab.fontlab7'"])
if app_path:
    app_path = os.path.join(app_path[1], "Contents", "MacOS", "FontLab 7")
    print(app_path)
    print(
        shell(
            [
                app_path,
                "/Users/adam/Developer/vcs/github.twardoch/pub/lato-source/tools/test2.vfpy",
            ]
        )
    )
