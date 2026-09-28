import os
import sys
from functools import lru_cache

RESERVED_PHYSICAL_CORES = 4

CONVERSION_WORKERS_SETTING_KEY = "max_concurrent_conversions"


def _windows_physical_cores():
    import ctypes
    from ctypes import wintypes

    relation_processor_core = 0
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    query = kernel32.GetLogicalProcessorInformationEx
    query.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
    query.restype = wintypes.BOOL

    length = wintypes.DWORD(0)
    query(relation_processor_core, None, ctypes.byref(length))
    if not length.value:
        return None
    buffer = ctypes.create_string_buffer(length.value)
    if not query(relation_processor_core, buffer, ctypes.byref(length)):
        return None

    raw = buffer.raw[:length.value]
    count = 0
    offset = 0
    while offset + 8 <= len(raw):
        relationship = int.from_bytes(raw[offset:offset + 4], "little")
        size = int.from_bytes(raw[offset + 4:offset + 8], "little")
        if size <= 0:
            break
        if relationship == relation_processor_core:
            count += 1
        offset += size
    return count or None


def _linux_physical_cores():
    cores = set()
    physical_id = core_id = None
    with open("/proc/cpuinfo", encoding="utf-8") as handle:
        for line in handle:
            key, _, value = line.partition(":")
            key = key.strip()
            if key == "physical id":
                physical_id = value.strip()
            elif key == "core id":
                core_id = value.strip()
            elif not line.strip():
                if core_id is not None:
                    cores.add((physical_id, core_id))
                physical_id = core_id = None
    if core_id is not None:
        cores.add((physical_id, core_id))
    return len(cores) or None


def _mac_physical_cores():
    import subprocess
    output = subprocess.run(["sysctl", "-n", "hw.physicalcpu"], capture_output=True, text=True, timeout=5)
    return int(output.stdout.strip()) or None


@lru_cache(maxsize=1)
def physical_core_count():
    try:
        if sys.platform == "win32":
            return _windows_physical_cores()
        if sys.platform.startswith("linux"):
            return _linux_physical_cores()
        if sys.platform == "darwin":
            return _mac_physical_cores()
    except Exception:
        return None
    return None


def max_conversion_workers():
    physical = physical_core_count()
    if not physical:
        return 1
    return max(1, physical - RESERVED_PHYSICAL_CORES)


def configured_conversion_workers(settings):
    limit = max_conversion_workers()
    try:
        value = int(settings.value(CONVERSION_WORKERS_SETTING_KEY, limit))
    except (TypeError, ValueError):
        value = limit
    return min(max(1, value), limit)
