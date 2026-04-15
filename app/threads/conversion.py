import os
import av
from PySide6.QtCore import QThread, Signal


class ConversionThread(QThread):
    completed = Signal(str)
    error = Signal(str)
    progress = Signal(int)

    def __init__(self, input_path, output_path, codec, container, sample_format,
                 bitrate=None, sample_rate=44100, channels=2):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.codec = codec
        self.container = container
        self.sample_format = sample_format
        self.bitrate = bitrate
        self.sample_rate = sample_rate
        self.channels = channels
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        input_container = None
        output_container = None
        success = False
        try:
            input_container = av.open(self.input_path)
            output_container = av.open(self.output_path, mode="w", format=self.container)

            in_stream = input_container.streams.audio[0]
            total_duration = in_stream.duration
            time_base = in_stream.time_base
            if total_duration and time_base:
                total_seconds = float(total_duration * time_base)
            else:
                total_seconds = 0

            out_stream = output_container.add_stream(self.codec, rate=self.sample_rate)

            if self.bitrate and self.codec not in ("pcm_s16le", "flac"):
                out_stream.bit_rate = self.bitrate

            layout = "stereo" if self.channels == 2 else "mono"

            resampler = av.AudioResampler(
                format=self.sample_format,
                layout=layout,
                rate=self.sample_rate,
            )

            last_percent = -1
            for frame in input_container.decode(in_stream):
                if self._cancelled:
                    raise RuntimeError("Conversion cancelled.")
                if total_seconds > 0 and frame.pts is not None:
                    current_seconds = float(frame.pts * time_base)
                    percent = min(int((current_seconds / total_seconds) * 100), 99)
                    if percent != last_percent:
                        self.progress.emit(percent)
                        last_percent = percent

                resampled_frames = resampler.resample(frame)
                for resampled_frame in resampled_frames:
                    for packet in out_stream.encode(resampled_frame):
                        output_container.mux(packet)

            for packet in out_stream.encode(None):
                output_container.mux(packet)

            self.progress.emit(100)
            success = True
        except Exception as e:
            if self._cancelled:
                self.error.emit("Conversion cancelled.")
            else:
                self.error.emit(str(e))
        finally:
            for container in (output_container, input_container):
                if container is not None:
                    try:
                        container.close()
                    except Exception:
                        pass
            if not success and self._cancelled and self.output_path and os.path.exists(self.output_path):
                try:
                    os.remove(self.output_path)
                except OSError:
                    pass
        if success:
            self.completed.emit(self.output_path)
