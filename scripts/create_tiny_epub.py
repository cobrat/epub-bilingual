from __future__ import annotations

from pathlib import Path
import zipfile


def main() -> None:
    output = Path("books/tiny.epub")
    output.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(output, "w") as zf:
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        zf.writestr(info, "application/epub+zip")
        zf.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>""",
        )
        zf.writestr(
            "OPS/content.opf",
            """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf"
         xmlns:dc="http://purl.org/dc/elements/1.1/"
         version="3.0"
         unique-identifier="bookid">
  <metadata>
    <dc:identifier id="bookid">urn:uuid:00000000-0000-4000-8000-000000000002</dc:identifier>
    <dc:title>Tiny Test</dc:title>
    <dc:language>en</dc:language>
    <meta property="dcterms:modified">2026-04-27T00:00:00Z</meta>
  </metadata>
  <manifest>
    <item id="chap1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
  </manifest>
  <spine>
    <itemref idref="chap1"/>
  </spine>
</package>""",
        )
        zf.writestr(
            "OPS/chapter1.xhtml",
            """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>Tiny Test</title></head>
  <body>
    <h1>Tiny Test Book</h1>
    <p>Hello, this is a short test book.</p>
    <p>The moon rose over the quiet river.</p>
  </body>
</html>""",
        )
        zf.writestr(
            "OPS/nav.xhtml",
            """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:epub="http://www.idpf.org/2007/ops">
  <head><title>Table of Contents</title></head>
  <body>
    <nav epub:type="toc" id="toc">
      <h1>Table of Contents</h1>
      <ol>
        <li><a href="chapter1.xhtml">Tiny Test Book</a></li>
      </ol>
    </nav>
  </body>
</html>""",
        )

    print(output)


if __name__ == "__main__":
    main()
