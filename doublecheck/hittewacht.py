"""De hittewacht: een zware run pauzeert zodra de Mac warm wordt.

De PO (2026-10-21): "zorg erin dat de GPU en CPU niet overhitten". De
processor is al begrensd (twee kernen per proces, B37); de grafische chip
niet, en een zeefrun duurt uren. De wacht start het commando in een eigen
procesgroep en leest elke `--interval` seconden de thermische toestand die
macOS zelf bijhoudt (`NSProcessInfo.thermalState`, zonder sudo): bij *licht
verhoogd* of erger stopt hij de hele groep (SIGSTOP, ook een lopend
Tesseract), en hij laat haar pas verder lopen als de Mac `KOEL_NODIG`
metingen op rij nominaal is. Er gaat niets verloren: een gestopt proces
staat stil en loopt daarna gewoon door, ook midden in P1.

    python -m doublecheck.hittewacht [--interval 30] [--log pad] -- <commando>

Het log meldt elke pauze en elke hervatting, en elke tien minuten de stand:
thermische toestand, CPU van de groep, benutting van de grafische chip en
swap. Een signaal aan de wacht (Ctrl-C, kill) gaat naar het commando, na
een SIGCONT, zodat het nooit gestopt achterblijft.
"""

from __future__ import annotations

# Vanaf welke toestand de run pauzeert: 1 is "fair" (licht verhoogd), 2
# "serious", 3 "critical". Bewust de laagste: liever een langere run dan een
# hete Mac (PO 2026-10-21).
GRENS = 1
# Zoveel metingen op rij nominaal voor de run verder mag.
KOEL_NODIG = 2
_NAMEN = ("nominaal", "licht verhoogd", "ernstig", "kritiek")
STAND_ELKE = 600  # seconden tussen twee standregels in het log


def beslis(toestand: int, gepauzeerd: bool, koel_op_rij: int) -> tuple[str, int]:
    """(actie, koel_op_rij) bij een nieuwe meting. Lopend: `pauzeer` vanaf
    `GRENS`, anders `door`. Gepauzeerd: `hervat` na `KOEL_NODIG` nominale
    metingen op rij, anders `wacht`; een warme meting zet de telling op 0."""
    if not gepauzeerd:
        return ("pauzeer", 0) if toestand >= GRENS else ("door", 0)
    koel = koel_op_rij + 1 if toestand == 0 else 0
    return ("hervat", 0) if koel >= KOEL_NODIG else ("wacht", koel)


def naam(toestand: int) -> str:
    return _NAMEN[toestand] if 0 <= toestand < len(_NAMEN) else f"onbekend ({toestand})"


def thermische_toestand() -> int:  # pragma: no cover - leest macOS
    """`NSProcessInfo.processInfo.thermalState` via de Objective-C-runtime:
    0 nominaal, 1 licht verhoogd, 2 ernstig, 3 kritiek."""
    import ctypes
    import ctypes.util

    objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
    ctypes.cdll.LoadLibrary("/System/Library/Frameworks/Foundation.framework/Foundation")
    objc.objc_getClass.restype = ctypes.c_void_p
    objc.objc_getClass.argtypes = [ctypes.c_char_p]
    objc.sel_registerName.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    zend = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(("objc_msgSend", objc))
    zend_long = ctypes.CFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p)(("objc_msgSend", objc))
    proces = zend(objc.objc_getClass(b"NSProcessInfo"), objc.sel_registerName(b"processInfo"))
    return int(zend_long(proces, objc.sel_registerName(b"thermalState")))


def _uitvoer(*commando: str) -> str:  # pragma: no cover
    import subprocess

    try:
        return subprocess.run(commando, capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _stand(groep: int) -> str:  # pragma: no cover - leest de machine
    import re

    cpu = sum(float(p) for g, p in (r.split() for r in _uitvoer("ps", "-A", "-o", "pgid=,pcpu=").splitlines()
                                    if r.strip()) if int(g) == groep)
    gpu = re.search(r'"Device Utilization %"=(\d+)', _uitvoer("ioreg", "-r", "-d", "1", "-c", "IOAccelerator"))
    swap = re.search(r"used = ([\d.]+)M", _uitvoer("sysctl", "-n", "vm.swapusage"))
    return (f"CPU van de run {cpu:.0f}% · grafische chip {gpu.group(1) + '%' if gpu else '?'}"
            f" · swap {f'{float(swap.group(1)) / 1024:.1f} GB' if swap else '?'}")


def wachten(commando: list[str], interval: float, log) -> int:  # pragma: no cover - start een proces
    import os
    import signal
    import subprocess
    import time

    def schrijf(tekst: str) -> None:
        print(f"[hitte {time.strftime('%H:%M:%S')}] {tekst}", file=log, flush=True)

    kind = subprocess.Popen(commando, start_new_session=True)
    groep = kind.pid
    gepauzeerd, koel, pauzes, gepauzeerd_sinds, stil = False, 0, 0, 0.0, 0.0
    laatste_stand = time.time()

    def doorgeven(signum, _frame):
        os.killpg(groep, signal.SIGCONT)
        os.killpg(groep, signum)

    signal.signal(signal.SIGINT, doorgeven)
    signal.signal(signal.SIGTERM, doorgeven)
    schrijf(f"start, pauze vanaf {naam(GRENS)}, verder na {KOEL_NODIG} koele metingen; {naam(thermische_toestand())}")
    try:
        while kind.poll() is None:
            time.sleep(interval)
            if kind.poll() is not None:
                break
            toestand = thermische_toestand()
            actie, koel = beslis(toestand, gepauzeerd, koel)
            if actie == "pauzeer":
                os.killpg(groep, signal.SIGSTOP)
                gepauzeerd, pauzes, gepauzeerd_sinds = True, pauzes + 1, time.time()
                schrijf(f"pauze ({naam(toestand)}); {_stand(groep)}")
            elif actie == "hervat":
                os.killpg(groep, signal.SIGCONT)
                gepauzeerd, stil = False, stil + time.time() - gepauzeerd_sinds
                schrijf(f"verder na {time.time() - gepauzeerd_sinds:.0f} s ({naam(toestand)})")
            if time.time() - laatste_stand >= STAND_ELKE:
                laatste_stand = time.time()
                schrijf(f"{'gepauzeerd' if gepauzeerd else 'loopt'}, {naam(toestand)}; {_stand(groep)}")
    finally:
        if kind.poll() is None:
            os.killpg(groep, signal.SIGCONT)
    schrijf(f"klaar (uitgang {kind.returncode}); {pauzes} pauzes, samen {stil / 60:.1f} min stil")
    return kind.returncode


def main() -> None:  # pragma: no cover
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Een zware run pauzeren zodra de Mac warm wordt")
    parser.add_argument("--interval", type=float, default=30.0, help="seconden tussen twee metingen")
    parser.add_argument("--log", help="schrijf het log naar dit bestand in plaats van naar stderr")
    parser.add_argument("commando", nargs=argparse.REMAINDER, help="na --: het commando dat de wacht bewaakt")
    args = parser.parse_args()
    commando = args.commando[1:] if args.commando[:1] == ["--"] else args.commando
    if not commando:
        parser.error("geen commando; zet het achter --")
    log = open(args.log, "a", encoding="utf-8") if args.log else sys.stderr
    raise SystemExit(wachten(commando, args.interval, log))


if __name__ == "__main__":
    main()
