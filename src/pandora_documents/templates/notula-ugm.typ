// Notula bentuk Peraturan Rektor UGM Nomor 21 Tahun 2023, Lampiran I butir 22. Dipakai Typst 0.13.
// Dibentuk oleh pandora_documents/notula.py; penanda berhuruf besar diisi pemanggil dan seluruh
// teks masuk sebagai string, sehingga isi notula tidak pernah ditafsirkan sebagai markup.
//   - A4; batas atas 3 cm, bawah 3,5 cm, kiri 2,5 cm, kanan 2 cm (butir 34)
//   - Times New Roman 12 (butir 32); Liberation Serif dipakai bila Times tidak terpasang
//   - kop: lambang 2 x 2 cm pada 1,5 cm dari tepi atas dan 2 cm dari tepi kiri, nama universitas
//     Times New Roman 16, alamat Arial 10, berwarna RGB 0,30,98 (butir 2)
//   - nomor halaman di tengah atas, tidak dicantumkan pada halaman pertama (Pasal 47)

#set page(
  paper: "a4",
  margin: (top: 3cm, bottom: 3.5cm, left: 2.5cm, right: 2cm),
  header: context {
    if counter(page).get().first() > 1 { align(center, counter(page).display("1")) }
  },
  header-ascent: 40%,
  // Catatan hasil AI tercetak di kaki setiap halaman, di dalam batas bawah 3,5 cm.
  footer: align(left, text(size: 9pt)[#__CATATAN__]),
  footer-descent: 25%,
)
#set text(font: ("Times New Roman", "Liberation Serif", "Libertinus Serif", "DejaVu Serif"), size: 12pt, lang: "id")
#set smartquote(enabled: false)
#set par(justify: false, leading: 0.6em, spacing: 0.7em)
#set list(indent: 0em, body-indent: 0.6em, spacing: 0.5em)
#set enum(indent: 0em, body-indent: 0.6em, spacing: 0.5em)
#set table(stroke: none, inset: (x: 4pt, y: 3pt))
#show table: set par(justify: false)
#show table: set text(size: 10.5pt)
#show table.cell.where(y: 0): set text(weight: "bold")

#let isian = box(width: 1fr, repeat[.])
__KOP__
#align(center, text(weight: "bold")[NOTULA])
#v(0.9em)

#set par(first-line-indent: 0em)
#grid(
  columns: (4.2cm, 0.5cm, 1fr),
  row-gutter: 0.55em,
__BARIS__
)

// Penutup di sisi kanan: pemimpin rapat, nama jabatan, tanda tangan dan cap, nama pejabat, NIP/NIKA.
#v(1.2em)
#block(breakable: false, width: 100%)[
  #set par(first-line-indent: 0em)
  #grid(
    columns: (1fr, 7cm),
    [],
    [
      Pemimpin Rapat \
      #isian, \
      #v(4.2em)
      #{ let p = __PEMIMPIN__; if p == "" { isian } else { p } } \
      NIP/NIKA #box(width: 1fr, repeat[.])
    ],
  )
]
