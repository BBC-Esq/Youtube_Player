import os
import av
from PySide6.QtCore import QThread, Signal


class MuxThread(QThread):
    completed = Signal(str)
    error = Signal(str)
    progress = Signal(int)

    def __init__(self, video_path, audio_path, output_path, container_format):
        super().__init__()
        self.video_path = video_path
        self.audio_path = audio_path
        self.output_path = output_path
        self.container_format = container_format
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        video_input = None
        audio_input = None
        output = None
        try:
            video_input = av.open(self.video_path)
            audio_input = av.open(self.audio_path)
            output = av.open(self.output_path, mode="w", format=self.container_format)

            video_in_stream = video_input.streams.video[0]
            audio_in_stream = audio_input.streams.audio[0]

            video_out_stream = output.add_stream_from_template(video_in_stream, opaque=True)
            audio_out_stream = output.add_stream_from_template(audio_in_stream, opaque=True)

            total_duration = video_in_stream.duration
            time_base = video_in_stream.time_base
            if total_duration and time_base:
                total_seconds = float(total_duration * time_base)
            else:
                total_seconds = 0

            last_percent = -1
            for packet in video_input.demux(video_in_stream):
                if self._cancelled:
                    raise RuntimeError("Muxing cancelled.")
                if packet.dts is None:
                    continue
                if total_seconds > 0 and packet.pts is not None:
                    current_seconds = float(packet.pts * time_base)
                    percent = min(int((current_seconds / total_seconds) * 50), 49)
                    if percent != last_percent:
                        self.progress.emit(percent)
                        last_percent = percent
                packet.stream = video_out_stream
                output.mux(packet)

            audio_time_base = audio_in_stream.time_base
            audio_duration = audio_in_stream.duration
            if audio_duration and audio_time_base:
                audio_total_seconds = float(audio_duration * audio_time_base)
            else:
                audio_total_seconds = 0

            for packet in audio_input.demux(audio_in_stream):
                if self._cancelled:
                    raise RuntimeError("Muxing cancelled.")
                if packet.dts is None:
                    continue
                if audio_total_seconds > 0 and packet.pts is not None:
                    current_seconds = float(packet.pts * audio_time_base)
                    percent = 50 + min(int((current_seconds / audio_total_seconds) * 50), 49)
                    if percent != last_percent:
                        self.progress.emit(percent)
                        last_percent = percent
                packet.stream = audio_out_stream
                output.mux(packet)

            self.progress.emit(100)
            success = True
        except Exception as e:
            success = False
            if self._cancelled:
                self.error.emit("Muxing cancelled.")
            else:
                self.error.emit(str(e))
        finally:
            for container in (output, audio_input, video_input):
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
