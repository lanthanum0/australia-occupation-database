#!/usr/bin/env python3
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def cell_text(cell):
    parts = []
    for node in cell.iter():
        if node.tag == f"{{{NS['w']}}}t":
            parts.append(node.text or "")
        elif node.tag == f"{{{NS['w']}}}tab":
            parts.append("\t")
        elif node.tag == f"{{{NS['w']}}}br":
            parts.append("\n")
    return " ".join("".join(parts).split())


def tables(path):
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    for table in root.findall(".//w:tbl", NS):
        rows = []
        for tr in table.findall("w:tr", NS):
            rows.append([cell_text(tc) for tc in tr.findall("w:tc", NS)])
        yield rows


def main():
    for arg in sys.argv[1:]:
        path = Path(arg)
        print(f"\n== {path} ==")
        for index, rows in enumerate(tables(path), 1):
            width = max((len(row) for row in rows), default=0)
            print(f"table {index}: {len(rows)} rows x {width} cols")
            for row in rows[:5]:
                print("  " + " | ".join(row))


if __name__ == "__main__":
    main()
