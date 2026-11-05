import ctypes
import sys

AUDIO_DEVICE_SETTING_KEY = "audio_output_device"
AUDIO_DEVICE_NAME_SETTING_KEY = "audio_output_device_name"


def output_devices():
    if sys.platform != "win32":
        return []
    found = []
    callback_type = ctypes.WINFUNCTYPE(
        ctypes.c_int, ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_void_p
    )

    def collect(guid, description, module, context):
        if guid:
            text = ctypes.create_unicode_buffer(64)
            ctypes.windll.ole32.StringFromGUID2(ctypes.c_void_p(guid), text, len(text))
            found.append((text.value, description))
        return 1

    try:
        ctypes.windll.dsound.DirectSoundEnumerateW(callback_type(collect), None)
    except (OSError, AttributeError):
        return []
    return found


def connected_device(device_id):
    if not device_id:
        return ""
    wanted = device_id.upper()
    return next((found for found, _ in output_devices() if found.upper() == wanted), "")
