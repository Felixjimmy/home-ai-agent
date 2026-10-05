"""Bounded extraction and deterministic section-aware character chunking."""
import hashlib
import json
import re
import subprocess
import sys
import os
from pathlib import Path
from app.config import DOCUMENT_MAX_CHARS, DOCUMENT_MAX_PAGES

CHUNK_CHARS = 1600
OVERLAP_CHARS = 240


def extract_source(path: Path, suffix: str) -> list[dict]:
    if suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise ValueError("Encrypted PDFs are unsupported. Upload an unlocked text PDF.")
        if len(reader.pages) > DOCUMENT_MAX_PAGES:
            raise ValueError("PDF page limit exceeded.")
        blocks=[]
        count=0
        for i,page in enumerate(reader.pages,1):
            text=page.extract_text() or ""
            count+=len(text)
            if count>DOCUMENT_MAX_CHARS:
                raise ValueError("Extracted text limit exceeded.")
            if text.strip():
                blocks.append({"text":text.strip(),"section":None,"page_start":i,"page_end":i})
    else:
        text=path.read_text(encoding="utf-8-sig")
        if len(text)>DOCUMENT_MAX_CHARS or "\x00" in text:
            raise ValueError("Text is too large or contains binary data.")
        blocks=[]
        heading=None
        parts=[]
        for line in text.splitlines():
            if suffix==".md" and re.match(r"^#{1,6}\s",line):
                if parts:
                    blocks.append({"text":"\n".join(parts),"section":heading,"page_start":None,"page_end":None})
                heading=line.lstrip("# ").strip()
                parts=[line]
            else:
                parts.append(line)
        if parts:
            blocks.append({"text":"\n".join(parts),"section":heading,"page_start":None,"page_end":None})
    if not blocks or not any(b["text"].strip() for b in blocks):
        raise ValueError("No usable text. Scanned PDFs require OCR, which is not enabled.")
    return blocks


def bounded_extract(path: Path, suffix: str) -> list[dict]:
    environment={**os.environ,"PYTHONPATH":str(Path(__file__).resolve().parents[1])}
    result=subprocess.run([sys.executable,"-m","app.document_processing",str(path),suffix],capture_output=True,text=True,encoding="utf-8",timeout=30,env=environment)
    if result.returncode:
        raise ValueError("Extraction failed: " + result.stderr.strip()[-600:])
    return json.loads(result.stdout)


def chunk_blocks(blocks, size=CHUNK_CHARS, overlap=OVERLAP_CHARS):
    if size<=overlap or overlap<0:
        raise ValueError("Invalid chunk configuration")
    chunks=[]
    for block in blocks:
        text=block["text"].strip()
        start=0
        while start<len(text):
            end=min(start+size,len(text))
            if end<len(text):
                boundary=text.rfind("\n",start+size//2,end)
                if boundary<0:
                    boundary=text.rfind(" ",start+size//2,end)
                if boundary>start:
                    end=boundary
            part=text[start:end].strip()
            if block.get("section") and not part.startswith("#"):
                part=block["section"]+"\n"+part
            if part:
                chunks.append({**block,"text":part,"ordinal":len(chunks),"char_count":len(part),"text_hash":hashlib.sha256(part.encode()).hexdigest()})
            if end==len(text):
                break
            start=max(start+1,end-overlap)
    return chunks


if __name__=="__main__":
    try:
        print(json.dumps(extract_source(Path(sys.argv[1]),sys.argv[2]),ensure_ascii=True))
    except Exception as error:
        print(str(error),file=sys.stderr)
        sys.exit(1)
