"""Bass level of whatever the system is playing, for the edge glow.

PipeWire's `pw-record` taps the default output (never the microphone) and
follows it when the output device changes, e.g. when earbuds connect.
"""

import logging

import numpy as np
from PySide6.QtCore import QObject, QProcess, QTimer, Signal

log = logging.getLogger("mubble")

RATE   = 48000
FRAME  = 1024                 # ~21 ms per reading, 46.9 Hz per FFT bin
BASS   = slice(1, 4)          # bins 1-3: roughly 47-141 Hz, kick drum and bass line
FLOOR  = 8000.0               # below about -50 dBFS counts as silence
WINDOW = np.hanning(FRAME).astype(np.float32)

RECORD = ["-P", "{ stream.capture.sink = true }", "--raw", "--format", "s16",
          "--rate", str(RATE), "--channels", "1", "--latency", "20ms", "-"]


def bass_energy(pcm):
    """Mean spectrum magnitude in the bass band of one FRAME of s16 mono bytes."""
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    return float(np.abs(np.fft.rfft(samples * WINDOW))[BASS].mean())


class Bass(QObject):
    level = Signal(float)   # 0..1 envelope: jumps on a hit, falls away after it

    def __init__(self, parent=None):
        super().__init__(parent)
        self._want = False
        self._buf  = bytearray()
        self._peak = FLOOR
        self._env  = 0.0
        self._proc = QProcess(self)
        self._proc.readyReadStandardOutput.connect(self._read)
        self._proc.finished.connect(self._ended)
        self._proc.errorOccurred.connect(self._failed)

    def set_running(self, on):
        self._want = on
        running = self._proc.state() != QProcess.ProcessState.NotRunning
        if on and not running:
            self._proc.start("pw-record", RECORD)
        elif not on and running:
            self._proc.kill()

    def stop(self):
        """For shutdown: do not return until the recorder is gone."""
        self.set_running(False)
        self._proc.waitForFinished(500)

    def _ended(self):
        self._buf.clear()
        self._env = 0.0
        self.level.emit(0.0)
        if self._want:   # asked for again before the old process was gone, or it died
            QTimer.singleShot(1000, lambda: self.set_running(self._want))

    def _failed(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self._want = False
            log.warning("pw-record not found; the edge glow will not react to sound")

    def _read(self):
        buf = self._buf
        buf += self._proc.readAllStandardOutput().data()
        whole = len(buf) // 2 * 2   # never split a sample
        if whole < FRAME * 2:
            return
        # Only the newest frame: a late glow looks worse than a skipped reading.
        energy = bass_energy(bytes(buf[whole - FRAME * 2:whole]))
        del buf[:whole]

        # Gain follows the loudest recent hit and relaxes over ~10 s, so quiet
        # and loud tracks both use the full range.
        self._peak = max(energy, self._peak * 0.998, FLOOR)
        hit = (energy / self._peak) ** 2 if energy > FLOOR else 0.0
        env = max(hit, self._env * 0.82)
        if abs(env - self._env) > 0.004:
            self._env = env
            self.level.emit(env)


if __name__ == "__main__":
    # python -m mubble.audio — the bass band must hear a kick and ignore a whistle.
    t = np.arange(FRAME) / RATE

    def tone(hz):
        return (np.sin(2 * np.pi * hz * t) * 12000).astype(np.int16).tobytes()

    assert bass_energy(tone(70)) > 50 * bass_energy(tone(2000)), "treble leaks into bass band"
    assert bass_energy(tone(70)) > FLOOR > bass_energy(bytes(FRAME * 2)), "floor misplaced"
    print("ok")
