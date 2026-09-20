# Third-party notices

This project vendors a modified copy of [caj2pdf](https://github.com/caj2pdf/caj2pdf)
(commit `e7bb0bfd43edb8ce29ea02771f3a1850ddef550d`) under `vendor/caj2pdf/`.

- `vendor/caj2pdf/LICENSE` — GLWT Public License
- `vendor/caj2pdf/pdfwutils.py` — GNU LGPL v3 or later, originally from img2pdf
  by Johannes Schauer, adapted by Hin-Tak Leung
- `vendor/caj2pdf/lib/JBigDecode.*`, `jbigdec.cc`, `decode_jbig2data_x.cc` —
  FreeType Project License, Copyright Hin-Tak Leung

This project also vendors a source subset of [jbig2dec](https://github.com/ArtifexSoftware/jbig2dec)
0.20 under `vendor/jbig2dec/`, used to build `libjbig2codec` without a system
`libjbig2dec` package.

- `vendor/jbig2dec/LICENSE`, `vendor/jbig2dec/COPYING` — GNU AGPL v3 or later
- Combining or distributing the built `libjbig2codec` shared library is subject
  to the AGPL terms of jbig2dec. The corresponding source is included in this
  repository.

PDF cleanup uses [PyMuPDF](https://pymupdf.readthedocs.io/) (AGPL) when installed
from `requirements.txt`. A system `mutool` binary is only an optional fallback.

Local changes to the vendored engine include:

- load JBIG shared libraries from the vendor directory on Windows, macOS, and Linux
- accept `pypdf` as well as `PyPDF2`
- skip obviously invalid HN page tables instead of aborting
- repair generated PDFs with PyMuPDF, then `mutool`, then a plain copy
- export decoder symbols on Windows (`__declspec(dllexport)`)
- compile `libjbig2codec` against the vendored jbig2dec sources
