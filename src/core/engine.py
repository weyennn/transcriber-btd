"""TranscribeEngine — wrapper faster-whisper + WDAC patch.

Dapat dipakai dari CLI maupun GUI. Semua call pemblokir harus dipanggil
dari background thread (bukan main/Qt thread).

Callback contract (semua opsional, dipanggil dari thread worker):
    on_log(message: str)
    on_progress(percent: int, message: str)
    on_segment(start: float, end: float, text: str)
    on_finished(output_dir: str, metadata: dict)
    on_error(error: str)
"""

import os
import re
import sys
import threading
import time
import types
from pathlib import Path


class CancelledError(Exception):
    """Transkripsi dibatalkan user (bukan error)."""


# Root state: dari paths.py (menghormati env DATA_DIR di Docker)
from src.utils.paths import HASIL_DIR  # noqa: E402


def _chunk_seconds_from_env(default=600.0, minimum=30.0) -> float:
    """Panjang potongan audio dari env; nilai rusak atau terlalu kecil diganti aman."""
    try:
        value = float(os.environ.get("TRANSCRIBE_CHUNK_SECONDS", "") or default)
    except ValueError:
        return default
    return value if value >= minimum else default


PARTIAL_NAME = "transkrip_sebagian.txt"
CHECKPOINT_NAME = "transkrip_sebagian.json"


def _write_partial(out_dir, text):
    """Simpan teks sejauh ini (atomik) supaya kegagalan di bagian akhir tidak membuang semuanya."""
    os.makedirs(out_dir, exist_ok=True)
    target = os.path.join(out_dir, PARTIAL_NAME)
    tmp = target + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, target)


def _write_checkpoint(out_dir, data):
    """Titik simpan untuk melanjutkan transkripsi: posisi terakhir dan segmen mentah."""
    import json
    os.makedirs(out_dir, exist_ok=True)
    target = os.path.join(out_dir, CHECKPOINT_NAME)
    tmp = target + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, target)


def _read_checkpoint(out_dir, signature):
    """Titik simpan bila ada dan cocok dengan berkas/pengaturan yang sama; selain itu None."""
    import json
    try:
        with open(os.path.join(out_dir, CHECKPOINT_NAME), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("signature") != signature:
        return None
    if not isinstance(data.get("segments"), list) or not isinstance(data.get("resume_seconds"), (int, float)):
        return None
    return data


def has_checkpoint(out_dir) -> bool:
    return os.path.isfile(os.path.join(out_dir, CHECKPOINT_NAME))


def _remove_partial(out_dir):
    for name in (PARTIAL_NAME, PARTIAL_NAME + ".tmp", CHECKPOINT_NAME, CHECKPOINT_NAME + ".tmp"):
        try:
            os.unlink(os.path.join(out_dir, name))
        except OSError:
            pass
    try:
        os.rmdir(out_dir)  # hanya berhasil bila kosong
    except OSError:
        pass


class TranscribeEngine:
    """Wraps faster-whisper with the WDAC fake-av workaround.

    Urutan import KRITIS:
      1. apply_wdac_patch() dipanggil PERTAMA
      2. baru import faster_whisper (dilakukan lazy di dalam method)
    Jangan pernah import faster_whisper di module-level GUI.
    """

    _model_cache = {}
    _model_lock = threading.Lock()
    _patch_applied = False
    _folder_lock = threading.Lock()

    # ── WDAC patch ────────────────────────────────────────────────────────
    @classmethod
    def apply_wdac_patch(cls):
        """Pasang fake `av` module + monkey-patch decode_audio ke ffmpeg.

        Harus dipanggil sekali sebelum import faster_whisper manapun.
        Aman dipanggil berulang (idempotent).
        """
        if cls._patch_applied:
            return
        cls._patch_applied = True

        fake_av = types.ModuleType("av")
        fake_av.audio = types.ModuleType("av.audio")
        sys.modules["av"] = fake_av
        sys.modules["av.audio"] = fake_av.audio

        from .audio_decoder import decode_audio  # noqa: E402

        import faster_whisper  # noqa: E402
        import faster_whisper.audio  # noqa: E402
        import faster_whisper.transcribe  # noqa: E402

        faster_whisper.audio.decode_audio = decode_audio
        faster_whisper.transcribe.decode_audio = decode_audio
        faster_whisper.decode_audio = decode_audio

    # ── Model ─────────────────────────────────────────────────────────────
    @classmethod
    def load_model(cls, model_name="medium", device="cpu", compute_type="int8"):
        """Load (dan cache) WhisperModel. Panggil dari worker thread."""
        key = (model_name, device, compute_type)
        # Dua job yang mulai bersamaan tidak boleh memuat model yang sama dua kali.
        with cls._model_lock:
            if key in cls._model_cache:
                return cls._model_cache[key]
            # Hanya satu model yang disimpan di cache. Job yang sedang berjalan
            # tetap memegang modelnya sendiri sampai selesai.
            cls._model_cache.clear()

            cls.apply_wdac_patch()
            from faster_whisper import WhisperModel  # noqa: E402
            from src.utils.config import max_concurrent_transcribe

            # num_workers: satu model melayani beberapa transkripsi paralel
            # (bobot dipakai bersama, VRAM hanya bertambah untuk aktivasi).
            model = WhisperModel(model_name, device=device, compute_type=compute_type,
                                 num_workers=max_concurrent_transcribe())
            cls._model_cache[key] = model
            return model

    @classmethod
    def is_model_cached(cls, model_name="medium") -> bool:
        """Cek cache Hugging Face tanpa memicu download."""
        hf_home = os.environ.get("HF_HOME", "").strip()
        if hf_home:
            cache_dir = Path(hf_home) / "hub"
        else:
            cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
        repo = f"models--Systran--faster-whisper-{model_name}"
        return (cache_dir / repo).is_dir()

    # ── Path helper ───────────────────────────────────────────────────────
    @staticmethod
    def _stem(path: str) -> str:
        name = os.path.splitext(os.path.basename(path))[0]
        while True:
            root, ext = os.path.splitext(name)
            if ext == "":
                break
            name = root
        return name

    @classmethod
    def auto_folder(cls, audio_stem: str, output_root: str | Path | None = None) -> str:
        """Return the next numbered output folder under output_root or HASIL_DIR."""
        root = Path(output_root) if output_root is not None else HASIL_DIR
        root.mkdir(parents=True, exist_ok=True)
        pattern = re.compile(r"^(\d{2,})_.*$")
        max_n = 0
        for entry in os.listdir(root):
            m = pattern.match(entry)
            if m and (root / entry).is_dir():
                max_n = max(max_n, int(m.group(1)))
        folder = root / f"{max_n + 1:02d}_{audio_stem}"
        return str(folder)

    @classmethod
    def reserve_folder(cls, audio_stem: str, output_root: str | Path | None = None) -> str:
        """Allocate and create the next numbered output folder.

        The folder is created here, under a lock, so two jobs that are queued
        at the same time can never be handed the same folder.
        """
        with cls._folder_lock:
            folder = cls.auto_folder(audio_stem, output_root)
            os.makedirs(folder, exist_ok=False)
        return folder

    # ── Transcribe ────────────────────────────────────────────────────────
    @classmethod
    def transcribe(cls, audio_path, config=None, callbacks=None):
        """Transkripsi satu file audio.

        Args:
          audio_path: path absolut file audio.
          config: dict opsional {model, language, device, compute_type,
                  output_dir, with_md, beam_size, chunk_seconds}
          callbacks: dict opsional {on_log, on_progress, on_segment,
                    on_finished, on_error}

        Returns:
          dict {"segments", "info", "full_text", "output_dir", "txt_path",
                "json_path", "md_path"}
        """
        cfg = {
            "model": "medium",
            "language": "id",
            "device": "cpu",
            "compute_type": "int8",
            "output_dir": None,
            "with_md": False,
            "beam_size": 1,
            # Anti-halusinasi / audio panjang (Phase 3)
            "vad_filter": True,                      # lewati bagian non-speech (silence panjang)
            "condition_on_previous_text": False,     # cegah loop halusinasi pada audio panjang
            "hallucination_silence_threshold": 2.0,  # drop segmen halusinasi setelah silence > 2s
            "no_speech_threshold": 0.6,
            "compression_ratio_threshold": 2.4,
            "log_prob_threshold": -1.0,
            # Panjang potongan audio yang diproses sekali jalan (detik).
            "chunk_seconds": _chunk_seconds_from_env(),
        }
        if config:
            cfg.update(config)
        cb = callbacks or {}

        def log(msg):
            if cb.get("on_log"):
                cb["on_log"](msg)

        def check_cancelled():
            # Pemuatan model dan audio senyap tidak memanggil on_segment, jadi
            # pembatalan juga diperiksa di antara tahap dan antar potongan.
            if cb.get("is_cancelled") and cb["is_cancelled"]():
                raise CancelledError()

        def progress(percent, message):
            if cb.get("on_progress"):
                cb["on_progress"](percent, message)

        try:
            audio = os.path.abspath(audio_path)
            if not os.path.exists(audio):
                raise FileNotFoundError(f"File audio tidak ditemukan: {audio}")

            stem = cls._stem(audio)
            out_dir = cfg["output_dir"] or cls.auto_folder(stem)

            load_started = time.time()
            progress(0, "Memuat model transkripsi...")
            log(f"Memuat model '{cfg['model']}' ({cfg['device']}/{cfg['compute_type']})...")
            model = cls.load_model(cfg["model"], cfg["device"], cfg["compute_type"])
            load_elapsed = time.time() - load_started
            check_cancelled()
            log(f"Model '{cfg['model']}' siap dalam {load_elapsed:.1f}s.")
            if load_elapsed >= 5:
                log("Catatan: pemuatan model pertama memang lebih lambat; proses berikutnya memakai cache RAM.")

            log("Transkripsi dimulai...")
            start = time.time()

            # Audio ditranskripsi per potongan supaya memori mengikuti panjang satu
            # potongan, bukan panjang rekaman. Rekaman panjang yang dimuat utuh
            # menghabiskan RAM container.
            from .audio_decoder import iter_audio_chunks, probe_duration

            total_duration = probe_duration(audio) or 0.0
            chunk_seconds = float(cfg["chunk_seconds"])
            if total_duration > chunk_seconds:
                log(f"Durasi {total_duration / 60:.0f} menit: diproses per potongan "
                    f"{chunk_seconds / 60:.0f} menit.")

            info = None
            decoded_duration = 0.0
            raw_segments = []
            full_text_parts = []
            part_no = 0
            # "auto": bahasa dideteksi di potongan pertama lalu dikunci untuk potongan berikutnya,
            # supaya satu rekaman tidak berganti bahasa di tengah jalan.
            locked_language = None if cfg["language"] == "auto" else cfg["language"]
            resume_from = 0.0
            elapsed_before = 0.0
            signature = {"size": os.path.getsize(audio), "model": cfg["model"],
                         "language": cfg["language"], "chunk_seconds": chunk_seconds}
            if cfg.get("resume"):
                saved = _read_checkpoint(out_dir, signature)
                if saved:
                    raw_segments = saved["segments"]
                    full_text_parts = [s["text"] for s in raw_segments]
                    resume_from = float(saved["resume_seconds"])
                    part_no = int(saved.get("parts_done", 0))
                    elapsed_before = float(saved.get("elapsed_s", 0.0))
                    decoded_duration = resume_from
                    info = types.SimpleNamespace(language=saved.get("language", cfg["language"]),
                                                 language_probability=float(saved.get("language_probability", 1.0)))
                    if cfg["language"] == "auto":
                        locked_language = saved.get("language") or None
                    log(f"Melanjutkan dari menit {resume_from / 60:.1f} ({part_no} bagian sudah selesai).")
                else:
                    log("Titik simpan tidak ditemukan atau tidak cocok; transkripsi dimulai dari awal.")
            chunks = iter_audio_chunks(audio, chunk_seconds=chunk_seconds, start_seconds=resume_from)
            parts_estimate = max(1, int(-(-total_duration // chunk_seconds))) if total_duration else 1
            try:
                for offset, samples in chunks:
                    check_cancelled()
                    part_no += 1
                    parts_total = max(parts_estimate, part_no)
                    part_label = f"Bagian {part_no}/{parts_total}: " if parts_total > 1 else ""
                    decoded_duration = offset + len(samples) / 16000
                    segments_iter, chunk_info = model.transcribe(
                        samples,
                        language=locked_language,
                        beam_size=cfg["beam_size"],
                        vad_filter=cfg["vad_filter"],
                        condition_on_previous_text=cfg["condition_on_previous_text"],
                        hallucination_silence_threshold=cfg["hallucination_silence_threshold"],
                        no_speech_threshold=cfg["no_speech_threshold"],
                        compression_ratio_threshold=cfg["compression_ratio_threshold"],
                        log_prob_threshold=cfg["log_prob_threshold"],
                    )
                    info = info or chunk_info
                    if locked_language is None:
                        locked_language = chunk_info.language
                        log(f"Bahasa terdeteksi: {locked_language} "
                            f"(keyakinan {float(chunk_info.language_probability):.0%}).")
                    for s in segments_iter:
                        seg = {
                            "start": round(offset + s.start, 2),
                            "end": round(offset + s.end, 2),
                            "text": s.text.strip(),
                        }
                        raw_segments.append(seg)
                        full_text_parts.append(s.text.strip())

                        if cb.get("on_segment"):
                            cb["on_segment"](seg["start"], seg["end"], seg["text"])
                        if cb.get("on_progress") and total_duration > 0:
                            pct = int((seg["end"] / total_duration) * 100)
                            cb["on_progress"](min(pct, 99), f"{part_label}Segmen {seg['start']:.0f}s")
                    del samples
                    if parts_total > 1:
                        _write_partial(out_dir, " ".join(full_text_parts).strip())
                        _write_checkpoint(out_dir, {
                            "signature": signature, "resume_seconds": decoded_duration,
                            "parts_done": part_no, "segments": raw_segments,
                            "language": info.language,
                            "language_probability": float(info.language_probability),
                            "elapsed_s": elapsed_before + (time.time() - start),
                        })
                        log(f"Bagian {part_no}/{parts_total} selesai; teks sementara disimpan.")
            finally:
                chunks.close()  # hentikan ffmpeg juga saat dibatalkan atau gagal

            check_cancelled()  # batal setelah segmen terakhir: jangan tulis hasil
            if info is None:
                raise RuntimeError("Audio tidak dapat didekode atau tidak berisi suara.")
            total_duration = decoded_duration or total_duration

            elapsed = elapsed_before + (time.time() - start)
            log(f"Selesai dalam {elapsed:.0f}s ({elapsed / 60:.1f}m)")
            progress(99, "Menyimpan hasil transkripsi...")

            # ── Output ──────────────────────────────────────────────────
            from .segment_merger import merge_segments
            from .output_writer import write_txt, write_json

            os.makedirs(out_dir, exist_ok=True)
            segments = merge_segments(raw_segments)
            full_text = " ".join(full_text_parts).strip()

            txt_path = write_txt(out_dir, full_text)
            for sisa in (PARTIAL_NAME, CHECKPOINT_NAME):  # hasil lengkap sudah ada
                try:
                    os.unlink(os.path.join(out_dir, sisa))
                except OSError:
                    pass
            json_path = write_json(
                out_dir, audio, cfg["model"],
                info.language, info.language_probability, elapsed, segments,
                audio_duration=total_duration,
            )

            md_path = None
            if cfg["with_md"]:
                from ..notulen.generator import write_notulen_md
                md_path = write_notulen_md(
                    full_text, stem, cfg["model"], info.language, out_dir
                )
                log(f"Notulen MD -> {md_path}")

            log(f"TXT  -> {txt_path}")
            log(f"JSON -> {json_path}")

            metadata = {
                "source": audio,
                "model": cfg["model"],
                "language": info.language,
                "language_probability": round(float(info.language_probability), 4),
                "duration_s": round(elapsed, 1),
                "audio_duration_s": round(total_duration, 1),
                "segment_count": len(segments),
            }

            if cb.get("on_finished"):
                cb["on_finished"](out_dir, metadata)

            return {
                "segments": segments,
                "info": info,
                "full_text": full_text,
                "output_dir": out_dir,
                "txt_path": txt_path,
                "json_path": json_path,
                "md_path": md_path,
                "metadata": metadata,
            }
        except CancelledError:
            _remove_partial(out_dir)  # dibatalkan pengguna: tidak ada hasil yang dipertahankan
            raise  # cancel bukan error — biarkan caller menanganinya
        except Exception as e:  # noqa: BLE001 — diteruskan ke callback
            if cb.get("on_error"):
                cb["on_error"](str(e))
            raise
