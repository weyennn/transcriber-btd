"""Catatan kaki AI dan instruksi terjemahan ke Bahasa Indonesia."""

from src.notulen import ai_generator
from src.pandora_documents import composer
from src.utils.ai_notice import CATATAN_AI, CATATAN_TRANSKRIP, aturan_terjemahan


def test_translation_rule_only_for_non_indonesian():
    assert aturan_terjemahan("id") == "" and aturan_terjemahan(None) == "" and aturan_terjemahan("auto") == ""
    aturan = aturan_terjemahan("en")
    assert "Inggris" in aturan and "kata per kata" in aturan and "Bahasa Indonesia baku" in aturan


def test_cleanup_prompt_translates_english_but_not_indonesian():
    _, inggris = ai_generator.build_cleanup_prompt("hello team", {"source_name": "x", "language": "en"})
    _, indonesia = ai_generator.build_cleanup_prompt("halo tim", {"source_name": "x", "language": "id"})
    assert "berbahasa Inggris" in inggris and "7." in inggris
    assert "berbahasa" not in indonesia and "7." not in indonesia


def test_notulen_prompt_gets_translation_rule_for_english():
    meta = {"source_name": "x", "audio_duration": 10, "language": "en"}
    assert "berbahasa Inggris" in ai_generator.build_prompt("hello", meta)[1]
    meta["language"] = "id"
    assert "berbahasa Inggris" not in ai_generator.build_prompt("halo", meta)[1]


def test_load_transcript_reports_detected_language(tmp_path):
    (tmp_path / "transkrip.txt").write_text("hello world", encoding="utf-8")
    (tmp_path / "transkrip.json").write_text('{"language": "en", "segments": []}', encoding="utf-8")
    _, meta = ai_generator.load_transcript(str(tmp_path))
    assert meta["language"] == "en"


def test_notulen_and_cleanup_outputs_carry_ai_footnote(tmp_path, monkeypatch):
    (tmp_path / "transkrip.txt").write_text("rapat membahas anggaran.", encoding="utf-8")
    monkeypatch.setattr(ai_generator, "call_llm", lambda *a, **k: "# Notulen\n\nIsi.")
    monkeypatch.setattr(ai_generator, "render_pdf", lambda *a, **k: str(tmp_path / "x.pdf"))
    ai_generator.generate_notulen_docx(str(tmp_path))
    assert CATATAN_AI in (tmp_path / "notulen_ai.md").read_text(encoding="utf-8")
    assert CATATAN_AI in (tmp_path / "notulen_ai.txt").read_text(encoding="utf-8")
    ai_generator.generate_cleanup(str(tmp_path))
    assert CATATAN_AI in (tmp_path / "transkrip_rapi_ai.md").read_text(encoding="utf-8")
    assert CATATAN_AI in (tmp_path / "transkrip_rapi_ai.txt").read_text(encoding="utf-8")


def test_official_document_source_note_mentions_ai():
    naskah = composer.Naskah("Judul", "laporan_kegiatan", [])
    assert "kecerdasan buatan (AI)" in naskah.catatan_sumber()
    assert naskah.catatan_sumber().startswith("Catatan sumber")


def test_transcript_notice_text_is_defined():
    assert "kecerdasan buatan" in CATATAN_TRANSKRIP
