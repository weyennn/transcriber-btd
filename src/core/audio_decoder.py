"""Audio decoding via system ffmpeg (WDAC-safe, no PyAV).

Menggantikan ``faster_whisper.audio.decode_audio`` yang bergantung PyAV
(terblokir kebijakan WDAC di mesin ini). Output float32 mono 16 kHz.
"""

import os
import subprocess

import numpy as np


def decode_audio(input_file, sampling_rate=16000, split_stereo=False):
    """Decode audio to float32 normalized NumPy array using system ffmpeg.

    Mirrors ``faster_whisper.audio.decode_audio`` signature and return type
    but uses subprocess+ffmpeg instead of PyAV to avoid unsigned-DLL block.

    Args:
      input_file: Path to audio file (str) or file-like object (BinaryIO).
      sampling_rate: Resample output to this sample rate (Hz).
      split_stereo: Return (left, right) tuple of arrays if True.

    Returns:
      Float32 NumPy array normalized to [-1.0, 1.0] (mono),
      or a 2-tuple (left, right) for stereo.
    """
    if isinstance(input_file, (str,)):
        input_path = input_file
    else:
        # Write BinaryIO content to temp file; ffmpeg needs a file path.
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".tmp", delete=False)
        try:
            tmp.write(input_file.read())
            tmp.close()
            input_path = tmp.name
        finally:
            pass

    channels = 2 if split_stereo else 1

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-f", "s16le",
        "-acodec", "pcm_s16le",
        "-ac", str(channels),
        "-ar", str(sampling_rate),
        "-loglevel", "quiet",
        "-",
    ]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = proc.communicate()

    if proc.returncode != 0:
        err_msg = stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"ffmpeg decode failed (code {proc.returncode}): {err_msg}")

    raw = np.frombuffer(stdout, dtype=np.int16)
    audio = raw.astype(np.float32) / 32768.0

    # Cleanup temp file if we used one
    if not isinstance(input_file, (str,)):
        try:
            os.unlink(input_path)
        except OSError:
            pass

    if split_stereo:
        left_channel = audio[0::2]
        right_channel = audio[1::2]
        return left_channel, right_channel

    return audio


def probe_duration(input_path):
    """Durasi berkas dalam detik menurut ffprobe; None bila tidak dapat dibaca."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", input_path],
            capture_output=True, text=True, timeout=60,
        )
        duration = float(result.stdout.strip())
        return duration if duration > 0 else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _quiet_cut(samples, sampling_rate, search_seconds):
    """Indeks sampel di titik paling senyap pada `search_seconds` terakhir.

    Potongan dibuat di jeda bicara supaya kata tidak terbelah di batas potongan.
    """
    frame = sampling_rate // 10            # 0,1 detik
    window = 5                             # jeda dicari selebar 0,5 detik
    tail_start = max(0, len(samples) - int(search_seconds * sampling_rate))
    tail = samples[tail_start:]
    frames = len(tail) // frame
    if frames <= window:
        return len(samples)
    energy = np.abs(tail[:frames * frame].astype(np.int32)).reshape(frames, frame).mean(axis=1)
    windowed = np.convolve(energy, np.ones(window), mode="valid")
    quietest = int(np.argmin(windowed))
    return tail_start + (quietest + window // 2) * frame


def iter_audio_chunks(input_path, chunk_seconds=600, search_seconds=30, sampling_rate=16000):
    """Dekode audio per potongan berurutan: yield (offset_detik, float32 mono).

    ffmpeg berjalan sekali dan PCM-nya dibaca sedikit demi sedikit dari pipa,
    sehingga memori yang terpakai mengikuti panjang satu potongan, bukan panjang
    rekaman. Potongan saling menyambung tanpa celah dan tanpa tumpang tindih:
    sisa setelah titik potong dibawa ke potongan berikutnya.
    """
    cmd = [
        "ffmpeg", "-nostdin", "-i", input_path,
        "-f", "s16le", "-acodec", "pcm_s16le", "-ac", "1", "-ar", str(sampling_rate),
        "-loglevel", "error", "-",
    ]
    chunk_samples = int(chunk_seconds * sampling_rate)
    # stderr ke berkas sementara: pipa stderr yang tidak dibaca dapat menghentikan ffmpeg.
    import tempfile
    with tempfile.TemporaryFile() as errors:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=errors)
        try:
            carry = np.empty(0, dtype=np.int16)
            position = 0  # sampel yang sudah diserahkan
            ended = False
            while not ended:
                need = chunk_samples - len(carry)
                data = proc.stdout.read(need * 2) if need > 0 else b""
                ended = need > 0 and len(data) < need * 2
                samples = np.concatenate([carry, np.frombuffer(data[:len(data) // 2 * 2], dtype=np.int16)])
                del data
                cut = len(samples) if ended else _quiet_cut(samples, sampling_rate, search_seconds)
                carry = samples[cut:].copy()
                if cut:
                    yield position / sampling_rate, samples[:cut].astype(np.float32) / 32768.0
                    position += cut
                del samples
            if proc.wait() != 0:
                errors.seek(0)
                message = errors.read().decode("utf-8", errors="replace").strip()
                raise RuntimeError(f"ffmpeg decode failed (code {proc.returncode}): {message}")
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.stdout.close()
            proc.wait()


def ffmpeg_available() -> bool:
    """Return True if system ffmpeg is on PATH."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, timeout=15
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False
