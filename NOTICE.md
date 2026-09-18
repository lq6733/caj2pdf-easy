# Third-party notices

This project vendors a modified copy of [caj2pdf](https://github.com/caj2pdf/caj2pdf)
(commit `e7bb0bfd43edb8ce29ea02771f3a1850ddef550d`) under `vendor/caj2pdf/`.

- `vendor/caj2pdf/LICENSE` — GLWT Public License
- `vendor/caj2pdf/pdfwutils.py` — GNU LGPL v3 or later, originally from img2pdf
  by Johannes Schauer, adapted by Hin-Tak Leung
- `vendor/caj2pdf/lib/JBigDecode.*`, `jbigdec.cc`, `decode_jbig2data_x.cc` —
  FreeType Project License, Copyright Hin-Tak Leung
- `vendor/jbig2dec/jbig2.h` — minimal public API header used to link against
  the system `libjbig2dec` library

Local changes to the vendored engine include:

- load JBIG shared libraries from the vendor directory
- accept `pypdf` as well as `PyPDF2`
- skip obviously invalid HN page tables instead of aborting
- fall back when `mutool` or outline writing fails
