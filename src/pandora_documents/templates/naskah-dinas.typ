// Bentuk halaman naskah dinas. Dipakai Typst 0.13.
//
// Perbedaan yang disengaja terhadap export/typst_converter.py:
//   1. tidak mencetak keterangan alat di setiap halaman;
//   2. tidak mencetak penanda akhir dokumen;
//   3. margin 2,5 cm pada keempat sisi, sesuai naskah dinas;
//   4. nomor halaman di bawah tengah, tanpa nama berkas;
//   5. paragraf menjorok, spasi tunggal, rata kiri-kanan, tanpa warna;
//   6. kepala dokumen dan ruang tanda tangan disediakan, nomor surat tidak.
//
// Penanda berhuruf besar diisi oleh render.py. Seluruh teks naskah masuk sebagai
// string, sehingga isi naskah tidak pernah ditafsirkan sebagai markup.

#set page(
  paper: "a4",
  margin: (top: 2.5cm, bottom: 2.5cm, left: 2.5cm, right: 2.5cm),
  numbering: "1",
  number-align: center,
)

#set text(font: ("DejaVu Serif", "Times New Roman", "Libertinus Serif"), size: 11pt, lang: "id")
#set smartquote(enabled: false)
#set par(justify: true, leading: 0.65em, spacing: 0.8em,
  first-line-indent: (amount: 1.2em, all: true))
#set heading(numbering: none)
#show heading: set par(first-line-indent: 0em, justify: false)
#show heading.where(level: 2): it => {
  set text(size: 11.5pt, weight: "bold")
  block(above: 1.3em, below: 0.7em, sticky: true, it)
}
#show heading.where(level: 3): it => {
  set text(size: 11pt, weight: "bold")
  block(above: 1em, below: 0.6em, sticky: true, it)
}
#set list(indent: 1.2em, body-indent: 0.5em, spacing: 0.6em)
#set enum(indent: 1.2em, body-indent: 0.5em, spacing: 0.6em)

// Tabel bergaris buku: garis mendatar di atas, di bawah kepala, dan di bawah.
#set table(stroke: none, inset: (x: 5pt, y: 4pt))
#show table: set par(justify: false, first-line-indent: 0em)
#show table: set text(size: 10pt)
#show table.cell.where(y: 0): set text(weight: "bold")

#let isian = box(width: 1fr, repeat[.])
#let jenis = __JENIS__
#let judul = __JUDUL__
#let kepala = (
__KEPALA__
)
#let tempat-tanggal = __TEMPAT_TANGGAL__

// Kepala dokumen
#align(center)[
  #set par(first-line-indent: 0em, justify: false)
  #text(size: 13pt, weight: "bold", tracking: 0.6pt, upper(jenis))
  #v(-0.2em)
  #text(size: 12pt, weight: "bold", judul)
]
#v(0.6em)
#if kepala.len() > 0 {
  set par(first-line-indent: 0em, justify: false)
  grid(
    columns: (auto, auto, 1fr),
    column-gutter: 0.6em,
    row-gutter: 0.7em,
    ..kepala.map(((label, nilai)) => (label, [:], if nilai == "" { isian } else { nilai })).flatten(),
  )
  v(0.3em)
}
#line(length: 100%, stroke: 0.8pt)

__BODY__

#v(0.8em)
#block[
  #set text(size: 9pt)
  #set par(first-line-indent: 0em)
  #__CATATAN__
]

// Ruang tanda tangan: nama dan jabatan dikosongkan untuk diisi tangan.
#v(1.2em)
#block(breakable: false, width: 100%)[
  #set par(first-line-indent: 0em, justify: false)
  #grid(
    columns: (1fr, 7cm),
    [],
    [
      #if tempat-tanggal == "" { isian } else { tempat-tanggal } \
      #__PENANDA_TANGAN__,
      #v(4.2em)
      #isian
    ],
  )
]
