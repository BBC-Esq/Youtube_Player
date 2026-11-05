import ctypes
import sys
import threading
import time
import uuid
from ctypes import wintypes

from PySide6.QtCore import QObject, Signal

SUPPORTED_DONGLES = ("vid_1532&pid_0583",)
REPORT_ID = 0x02
REPORT_SIZE = 64
CONNECTED_BIT = 0x08
SEND_ATTEMPTS = 3
HANDSHAKE = (0x06, bytes([0x0D, 0x00, 0x25, 0x34, 0x12, 0x5A, 0x5A, 0x01, 0x00, 0x00, 0x00, 0xF0, 0x00, 0x00, 0x00]))
STATUS_QUESTION = (0x0E, bytes([0x01, 0xE6]))
UPDATER_PROCESS_MARK = "firmwareupdater"

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ_WRITE = 0x3
OPEN_EXISTING = 3
FILE_FLAG_OVERLAPPED = 0x40000000
ERROR_IO_PENDING = 997
INFINITE = 0xFFFFFFFF
TH32CS_SNAPPROCESS = 0x2


class _Guid(ctypes.Structure):
    _fields_ = [("data", ctypes.c_ubyte * 16)]


class _PropertyKey(ctypes.Structure):
    _fields_ = [("fmtid", _Guid), ("pid", wintypes.DWORD)]


class _Overlapped(ctypes.Structure):
    _fields_ = [("Internal", ctypes.c_size_t), ("InternalHigh", ctypes.c_size_t),
                ("Offset", wintypes.DWORD), ("OffsetHigh", wintypes.DWORD), ("hEvent", wintypes.HANDLE)]


class _ProcessEntry(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                ("szExeFile", ctypes.c_wchar * 260)]


def _guid(text):
    return _Guid.from_buffer_copy(uuid.UUID(text).bytes_le)


if sys.platform == "win32":
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _hid = ctypes.WinDLL("hid", use_last_error=True)
    _cfgmgr = ctypes.WinDLL("cfgmgr32")
    _kernel32.CreateFileW.restype = wintypes.HANDLE
    _kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                      wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CreateEventW.restype = wintypes.HANDLE
    _kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    _kernel32.SetEvent.argtypes = [wintypes.HANDLE]
    _kernel32.ResetEvent.argtypes = [wintypes.HANDLE]
    _kernel32.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                                   ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(_Overlapped)]
    _kernel32.WriteFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                                    ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    _kernel32.WaitForMultipleObjects.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE),
                                                 wintypes.BOOL, wintypes.DWORD]
    _kernel32.GetOverlappedResult.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Overlapped),
                                              ctypes.POINTER(wintypes.DWORD), wintypes.BOOL]
    _kernel32.CancelIoEx.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Overlapped)]
    _kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    _kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    _kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry)]
    _kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry)]
    _hid.HidD_GetPreparsedData.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
    _hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
    _hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    _hid.HidD_GetInputReport.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_ulong]
    _INVALID_HANDLE = ctypes.c_void_p(-1).value
    _HID_INTERFACE = _guid("4d1e55b2-f16f-11cf-88cb-001111000030")
    _CONTAINER_KEY = _PropertyKey(_guid("8c7ed206-3f8a-4827-b3ab-ae9e1faefc6c"), 2)
    _INSTANCE_KEY = _PropertyKey(_guid("78c34fc8-104a-4aca-9ea4-524d52996e57"), 256)


def _open(path, access, flags=0):
    handle = _kernel32.CreateFileW(path, access, FILE_SHARE_READ_WRITE, None, OPEN_EXISTING, flags, None)
    return None if handle in (None, _INVALID_HANDLE) else handle


def _hid_paths():
    size = ctypes.c_ulong()
    if _cfgmgr.CM_Get_Device_Interface_List_SizeW(ctypes.byref(size), ctypes.byref(_HID_INTERFACE), None, 0):
        return []
    buffer = ctypes.create_unicode_buffer(size.value + 1)
    if _cfgmgr.CM_Get_Device_Interface_ListW(ctypes.byref(_HID_INTERFACE), None, buffer, size.value, 0):
        return []
    return [path for path in buffer[:size.value].split("\0") if path]


def _devnode_container(instance_id):
    devinst = wintypes.DWORD()
    if _cfgmgr.CM_Locate_DevNodeW(ctypes.byref(devinst), wintypes.LPCWSTR(instance_id), 0):
        return None
    kind = ctypes.c_ulong()
    size = ctypes.c_ulong(16)
    value = (ctypes.c_ubyte * 16)()
    if _cfgmgr.CM_Get_DevNode_PropertyW(devinst, ctypes.byref(_CONTAINER_KEY), ctypes.byref(kind),
                                        value, ctypes.byref(size), 0):
        return None
    return bytes(value)


def _interface_container(path):
    kind = ctypes.c_ulong()
    size = ctypes.c_ulong(0)
    _cfgmgr.CM_Get_Device_Interface_PropertyW(wintypes.LPCWSTR(path), ctypes.byref(_INSTANCE_KEY),
                                              ctypes.byref(kind), None, ctypes.byref(size), 0)
    if not size.value:
        return None
    buffer = ctypes.create_unicode_buffer(size.value // 2 + 1)
    if _cfgmgr.CM_Get_Device_Interface_PropertyW(wintypes.LPCWSTR(path), ctypes.byref(_INSTANCE_KEY),
                                                 ctypes.byref(kind), buffer, ctypes.byref(size), 0):
        return None
    return _devnode_container(buffer.value)


def _is_vendor_channel(path):
    handle = _open(path, 0)
    if not handle:
        return False
    try:
        preparsed = ctypes.c_void_p()
        if not _hid.HidD_GetPreparsedData(handle, ctypes.byref(preparsed)):
            return False
        caps = (ctypes.c_ushort * 32)()
        _hid.HidP_GetCaps(preparsed, caps)
        _hid.HidD_FreePreparsedData(preparsed)
        return caps[1] == 0xFF00 and caps[2] == REPORT_SIZE and caps[3] == REPORT_SIZE
    finally:
        _kernel32.CloseHandle(handle)


def find_headset_dongle(device_id):
    if sys.platform != "win32" or not device_id:
        return None
    try:
        candidates = [path for path in _hid_paths() if any(mark in path.lower() for mark in SUPPORTED_DONGLES)]
        if not candidates:
            return None
        container = _devnode_container("SWD\\MMDEVAPI\\{0.0.0.00000000}." + device_id.lower())
        if container is None:
            return None
        for path in candidates:
            if _interface_container(path) == container and _is_vendor_channel(path):
                return path
    except OSError:
        return None
    return None


def firmware_updater_running():
    snapshot = _kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot in (None, _INVALID_HANDLE):
        return False
    try:
        entry = _ProcessEntry()
        entry.dwSize = ctypes.sizeof(_ProcessEntry)
        found = _kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while found:
            if UPDATER_PROCESS_MARK in entry.szExeFile.lower():
                return True
            found = _kernel32.Process32NextW(snapshot, ctypes.byref(entry))
        return False
    finally:
        _kernel32.CloseHandle(snapshot)


def _crc16(data):
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def _report(message):
    report = bytearray(REPORT_SIZE)
    report[0], report[1], report[2] = REPORT_ID, 0x80, len(message)
    report[5:5 + len(message)] = message
    crc = _crc16(report)
    report[3], report[4] = crc & 0xFF, crc >> 8
    return bytes(report)


def _messages(report):
    if len(report) < 2 or report[0] != REPORT_ID:
        return []
    body = report[2:2 + report[1]]
    found = []
    while len(body) >= 10 and body[0] == 0x50 and body[1] == 0x49:
        length = body[8] | (body[9] << 8)
        found.append((body[2], body[10:10 + length]))
        body = body[10 + length:]
    return found


def _headset_state(kind, payload):
    if kind == 0x0E and len(payload) >= 2 and payload[0] == 0xE6:
        return bool(payload[1] & CONNECTED_BIT)
    if kind == 0x0E and len(payload) >= 2 and payload[0] == 0xE3:
        return bool(payload[1])
    if kind == 0x08 and len(payload) >= 4 and payload[0] == 0x20 and payload[1] == 0x02:
        return bool(payload[3])
    return None


class HeadsetLink(QObject):
    state_changed = Signal()

    def __init__(self, path, device_id):
        super().__init__()
        self.path = path
        self.device_id = device_id
        self._state = None
        self._seq = 0
        self._greeted = False
        self._writer = None
        self._reader = None
        self._stop_event = None
        self._ask_event = None
        self._thread = None

    @property
    def headset_on(self):
        return self._state

    def is_alive(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        self._reader = _open(self.path, GENERIC_READ, FILE_FLAG_OVERLAPPED)
        self._writer = _open(self.path, GENERIC_READ | GENERIC_WRITE)
        if not self._reader or not self._writer:
            self._close_device_handles()
            return False
        self._stop_event = _kernel32.CreateEventW(None, True, False, None)
        self._ask_event = _kernel32.CreateEventW(None, True, True, None)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def ask(self):
        if self._ask_event and self.is_alive():
            _kernel32.SetEvent(self._ask_event)

    def close(self):
        if self._stop_event:
            _kernel32.SetEvent(self._stop_event)
        if self._thread:
            self._thread.join(timeout=2)
            if self._thread.is_alive():
                return
        for handle in (self._stop_event, self._ask_event):
            if handle:
                _kernel32.CloseHandle(handle)
        self._stop_event = self._ask_event = None
        self._close_device_handles()

    def _close_device_handles(self):
        for handle in (self._reader, self._writer):
            if handle:
                _kernel32.CloseHandle(handle)
        self._reader = self._writer = None

    def _run(self):
        read_event = _kernel32.CreateEventW(None, True, False, None)
        try:
            self._listen(read_event)
        except OSError:
            pass
        finally:
            _kernel32.CloseHandle(read_event)
            self._set_state(None)

    def _listen(self, read_event):
        waits = (wintypes.HANDLE * 3)(read_event, self._stop_event, self._ask_event)
        buffer = (ctypes.c_ubyte * REPORT_SIZE)()
        got = wintypes.DWORD()
        while True:
            overlapped = _Overlapped()
            overlapped.hEvent = read_event
            if not _kernel32.ReadFile(self._reader, buffer, REPORT_SIZE, None, ctypes.byref(overlapped)):
                if ctypes.get_last_error() != ERROR_IO_PENDING:
                    return
            while True:
                signaled = _kernel32.WaitForMultipleObjects(3, waits, False, INFINITE)
                if signaled != 2:
                    break
                _kernel32.ResetEvent(self._ask_event)
                self._ask()
            if signaled != 0:
                _kernel32.CancelIoEx(self._reader, ctypes.byref(overlapped))
                _kernel32.GetOverlappedResult(self._reader, ctypes.byref(overlapped), ctypes.byref(got), True)
                return
            if not _kernel32.GetOverlappedResult(self._reader, ctypes.byref(overlapped), ctypes.byref(got), False):
                return
            for kind, payload in _messages(bytes(buffer[:got.value])):
                state = _headset_state(kind, payload)
                if state is not None:
                    self._set_state(state)

    def _ask(self):
        if firmware_updater_running():
            return
        if not self._greeted:
            self._greeted = self._send(*HANDSHAKE)
        self._send(*STATUS_QUESTION)

    def _send(self, kind, body):
        self._seq = self._seq % 127 + 1
        report = _report(bytes([0x50, 0x41, kind, self._seq]) + body)
        written = wintypes.DWORD()
        status = (ctypes.c_ubyte * REPORT_SIZE)()
        for _ in range(SEND_ATTEMPTS):
            if not _kernel32.WriteFile(self._writer, report, REPORT_SIZE, ctypes.byref(written), None):
                raise OSError(ctypes.get_last_error(), "headset dongle write failed")
            status[0] = REPORT_ID
            if not _hid.HidD_GetInputReport(self._writer, status, REPORT_SIZE):
                return False
            if status[1] == ord("O"):
                return True
            time.sleep(0.06)
        return False

    def _set_state(self, state):
        if state != self._state:
            self._state = state
            self.state_changed.emit()
