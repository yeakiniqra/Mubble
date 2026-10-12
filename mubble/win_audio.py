"""Bass level on Windows: the same glow as audio.py, fed by WASAPI loopback.

Loopback taps the default output (never the microphone). Windows converts the
mix to exactly what pw-record gives on Linux, s16 mono at RATE, so the
measuring in audio.Bass is shared unchanged. Plain ctypes: the four COM calls
needed do not justify a dependency.
"""

import ctypes
import logging
from ctypes import POINTER, byref, c_uint32, c_void_p, c_wchar_p
from ctypes.wintypes import DWORD, WORD

from . import audio
from .audio import FRAME, RATE

log = logging.getLogger("mubble")

CLSCTX_ALL       = 0x17
SHARED           = 0
LOOPBACK         = 0x00020000                # AUDCLNT_STREAMFLAGS_LOOPBACK
CONVERT          = 0x80000000 | 0x08000000   # AUTOCONVERTPCM | SRC_DEFAULT_QUALITY
SILENT           = 0x2                       # AUDCLNT_BUFFERFLAGS_SILENT
BUFFER           = 10_000_000                # 1 s, in 100 ns units; read every TICK
RECHECK          = 60                        # ticks between checks for a new default output
MMDEVICE_ENUM    = "{BCDE0395-E52F-467C-8E3D-C4579291692E}"
I_DEVICE_ENUM    = "{A95664D2-9614-4F35-A746-DE8DB63617E6}"
I_AUDIO_CLIENT   = "{1CB9AD4C-DBFA-4C32-B178-C2F568A703B2}"
I_CAPTURE_CLIENT = "{C8ADBD64-E71E-48A0-A4DE-185C395CD317}"

ole32 = ctypes.windll.ole32
ole32.CoCreateInstance.restype = ctypes.HRESULT


class GUID(ctypes.Structure):
    _fields_ = [("data", ctypes.c_byte * 16)]

    def __init__(self, text):
        super().__init__()
        ole32.CLSIDFromString(c_wchar_p(text), byref(self))


class WAVEFORMATEX(ctypes.Structure):
    _fields_ = [("wFormatTag", WORD), ("nChannels", WORD), ("nSamplesPerSec", DWORD),
                ("nAvgBytesPerSec", DWORD), ("nBlockAlign", WORD),
                ("wBitsPerSample", WORD), ("cbSize", WORD)]


def _com(obj, index, *args):
    """Call method `index` of a COM interface. Failed HRESULTs raise OSError."""
    vtable = ctypes.cast(obj, POINTER(POINTER(c_void_p))).contents
    # CFUNCTYPE takes any number of arguments, passed as given. On 64-bit
    # Windows there is one calling convention, so it is the COM one too.
    return ctypes.CFUNCTYPE(ctypes.HRESULT, c_void_p)(vtable[index])(obj, *args)


def _default_output(enumerator):
    device = c_void_p()
    _com(enumerator, 4, 0, 0, byref(device))   # GetDefaultAudioEndpoint(eRender, eConsole)
    return device


def _device_id(device):
    text = c_wchar_p()
    _com(device, 5, byref(text))   # IMMDevice::GetId
    try:
        return text.value
    finally:
        ole32.CoTaskMemFree(text)


class Loopback:
    """One capture of the default output. Raises OSError when it cannot start."""

    def __init__(self):
        ole32.CoInitializeEx(None, 0x2)   # Qt has usually done this; then it is a no-op
        self._objects = []   # released in reverse on close
        try:
            self._enum = self._keep(c_void_p())
            ole32.CoCreateInstance(byref(GUID(MMDEVICE_ENUM)), None, CLSCTX_ALL,
                                   byref(GUID(I_DEVICE_ENUM)), byref(self._enum))
            device = self._keep(_default_output(self._enum))
            self.device = _device_id(device)
            self._client = self._keep(c_void_p())
            _com(device, 3, byref(GUID(I_AUDIO_CLIENT)), CLSCTX_ALL, None,
                 byref(self._client))   # IMMDevice::Activate
            fmt = WAVEFORMATEX(1, 1, RATE, RATE * 2, 2, 16, 0)   # PCM s16 mono
            _com(self._client, 3, SHARED, DWORD(LOOPBACK | CONVERT),
                 ctypes.c_longlong(BUFFER), ctypes.c_longlong(0), byref(fmt), None)
            self._capture = self._keep(c_void_p())
            _com(self._client, 14, byref(GUID(I_CAPTURE_CLIENT)), byref(self._capture))
            _com(self._client, 10)   # Start
        except OSError:
            self.close()
            raise

    def _keep(self, pointer):
        self._objects.append(pointer)
        return pointer

    def read(self):
        """Everything captured since the last read, as s16 mono bytes."""
        out = bytearray()
        data, frames, flags = c_void_p(), c_uint32(), DWORD()
        size = c_uint32()
        while True:
            _com(self._capture, 5, byref(size))   # GetNextPacketSize
            if not size.value:
                return bytes(out)
            _com(self._capture, 3, byref(data), byref(frames), byref(flags), None, None)
            n = frames.value * 2
            out += bytes(n) if flags.value & SILENT else ctypes.string_at(data, n)
            _com(self._capture, 4, frames)   # ReleaseBuffer

    def is_default(self):
        """Still the default output? Earbuds connecting take that over."""
        device = _default_output(self._enum)
        try:
            return _device_id(device) == self.device
        finally:
            _com(device, 2)

    def close(self):
        for pointer in reversed(self._objects):
            if pointer:
                _com(pointer, 2)   # Release
        self._objects.clear()


class Bass(audio.Bass):
    """audio.Bass with Loopback as its source instead of pw-record."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loop   = None
        self._ticks  = 0
        self._failed = ""   # last reason it could not listen, said once

    def set_running(self, on):
        self._want = on
        if on and not self._loop:
            try:
                self._loop = Loopback()
            except OSError as e:
                if str(e) != self._failed:
                    self._failed = str(e)
                    log.warning("cannot listen to the output; the edge glow will not react: %s", e)
                return
            self._failed = ""
            self._tick.start()
        elif not on and self._loop:
            self._drop()

    def stop(self):
        self.set_running(False)

    def _drop(self):
        self._loop.close()
        self._loop = None
        self._ended()   # resets the glow, and reopens in a second if still wanted

    def _measure(self):
        self._ticks += 1
        try:
            if self._ticks % RECHECK == 0 and not self._loop.is_default():
                raise OSError("default output changed")
            pcm = self._loop.read()
        except OSError as e:
            log.info("reopening the output capture: %s", e)
            self._drop()
            return
        # Loopback delivers nothing at all while nothing plays; that is silence,
        # and the glow must fall away rather than hold its last level.
        self._buf += pcm or bytes(FRAME * 2)
        super()._measure()
