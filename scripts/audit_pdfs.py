"""Check submission PDF text and save current render evidence."""
import hashlib
import json
from pathlib import Path

import pypdfium2 as pdfium
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]


def main():
    renders = ROOT / "tmp/pdfs/final"
    renders.mkdir(parents=True, exist_ok=True)
    receipt = {}
    for name in ("proposal-2020-2026.pdf", "project-report.pdf"):
        source = ROOT / "output/pdf" / name
        reader = PdfReader(source)
        texts = [page.extract_text() or "" for page in reader.pages]
        if not all(text.strip() for text in texts):
            raise RuntimeError(f"Blank PDF page: {name}")
        text = "\n".join(texts)
        for required in ("References (2020-2026)", "2607.14482", "2506.22470",
                         "fi17070297", "3658383", "draft-zheng-quic-fec-extension-02",
                         "TNET.2022.3195611", "2024", "2020"):
            if required not in text:
                raise RuntimeError(f"Missing PDF content in {name}: {required}")
        document = pdfium.PdfDocument(str(source))
        pages = []
        try:
            for index in range(len(document)):
                page = document[index]
                bitmap = page.render(scale=1.25)
                target = renders / f"{source.stem}-{index + 1}.png"
                bitmap.to_pil().save(target)
                pages.append({"page": index + 1, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
                bitmap.close()
                page.close()
        finally:
            document.close()
        receipt[name] = {"pages": len(reader.pages), "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                         "nonblank_pages": True, "required_reference_text": True, "renders": pages}
    output = ROOT / "output/verification/pdf-render.json"
    output.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print("PDF content and render receipt current:", {name: data["pages"] for name, data in receipt.items()})


if __name__ == "__main__":
    main()
