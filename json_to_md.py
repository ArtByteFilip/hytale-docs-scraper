"""
Hytale JSON Dokumentácia → Markdown konvertor
Použitie:
    python json_to_md.py --input docs.json --output docs_md/
    python json_to_md.py --input docs.json --output docs.md --single-file
"""

import json
import argparse
import os
from pathlib import Path


def member_to_md(member: dict) -> str:
    lines = []

    name = member.get("name", "")
    # Skráť dlhé názvy konštruktorov na čitateľnejší tvar
    short_name = name.split("(")[0] if "(" in name else name

    sig = member.get("signature", "").strip()
    desc = member.get("description", "").strip()
    deprecated = member.get("deprecated", False)
    tags = member.get("tags", {})

    lines.append(f"#### `{short_name}`")

    if deprecated:
        lines.append("> ⚠️ **DEPRECATED**")

    if sig:
        lines.append(f"```java\n{sig}\n```")

    if desc:
        lines.append(desc)

    # Tagy (Returns, See Also, Overrides...)
    for tag_key, tag_vals in tags.items():
        if tag_vals:
            vals = ", ".join(tag_vals) if isinstance(tag_vals, list) else tag_vals
            lines.append(f"- **{tag_key}:** {vals}")

    return "\n".join(lines)


def entry_to_md(entry: dict) -> str:
    lines = []

    name = entry.get("name", "Unknown")
    package = entry.get("package", "")
    qualified = entry.get("qualified_name", "")
    kind = entry.get("kind", "class").capitalize()
    desc = entry.get("description", "").strip()
    deprecated = entry.get("deprecated", False)
    deprecated_msg = entry.get("deprecated_msg", "").strip()
    superclass = entry.get("superclass")
    interfaces = entry.get("interfaces", [])
    members = entry.get("members", [])
    since = entry.get("since", "").strip()
    see_also = entry.get("see_also", [])
    url = entry.get("url", "")

    # ── Hlavička ──────────────────────────────────────────────
    lines.append(f"# {kind}: {name}")
    lines.append("")

    # ── Metadáta ──────────────────────────────────────────────
    if package:
        lines.append(f"**Package:** `{package}`")
    if qualified:
        lines.append(f"**Qualified Name:** `{qualified}`")
    if superclass:
        lines.append(f"**Extends:** `{superclass}`")
    if interfaces:
        lines.append(f"**Implements:** {', '.join(f'`{i}`' for i in interfaces)}")
    if since:
        lines.append(f"**Since:** {since}")
    if url:
        lines.append(f"**Docs:** {url}")

    lines.append("")

    # ── Deprecated upozornenie ────────────────────────────────
    if deprecated:
        msg = f" – {deprecated_msg}" if deprecated_msg else ""
        lines.append(f"> ⚠️ **DEPRECATED**{msg}")
        lines.append("")

    # ── Popis triedy ─────────────────────────────────────────
    if desc:
        lines.append("## Description")
        lines.append(desc)
        lines.append("")

    # ── See Also ─────────────────────────────────────────────
    if see_also:
        filtered = [s for s in see_also if s and s != "Serialized Form"]
        if filtered:
            lines.append("## See Also")
            for s in filtered:
                lines.append(f"- {s}")
            lines.append("")

    # ── Members ───────────────────────────────────────────────
    if members:
        lines.append("## Members")
        lines.append("")
        for m in members:
            lines.append(member_to_md(m))
            lines.append("")

    return "\n".join(lines)


def convert(input_path: str, output_path: str, single_file: bool):
    input_file = Path(input_path)
    output = Path(output_path)

    if not input_file.exists():
        print(f"❌ Súbor nenájdený: {input_path}")
        return

    entries = []
    errors = 0

    with open(input_file, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"⚠️  Riadok {line_num}: JSON chyba – {e}")
                errors += 1

    print(f"✅ Načítaných: {len(entries)} tried | Chyby: {errors}")

    # ── Single file mód ───────────────────────────────────────
    if single_file:
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w", encoding="utf-8") as out:
            for i, entry in enumerate(entries):
                out.write(entry_to_md(entry))
                out.write("\n\n---\n\n")
                if (i + 1) % 500 == 0:
                    print(f"  ... spracovaných {i+1}/{len(entries)}")
        print(f"📄 Uložené do: {output}")

    # ── Multi-file mód (jeden .md na triedu) ─────────────────
    else:
        output.mkdir(parents=True, exist_ok=True)
        for i, entry in enumerate(entries):
            # Organizuj do podpriečinkov podľa package
            pkg = entry.get("package", "unknown").replace(".", "/")
            name = entry.get("name", f"unknown_{i}").replace(".", "_")

            pkg_dir = output / pkg
            pkg_dir.mkdir(parents=True, exist_ok=True)

            md_file = pkg_dir / f"{name}.md"
            with open(md_file, "w", encoding="utf-8") as out:
                out.write(entry_to_md(entry))

            if (i + 1) % 500 == 0:
                print(f"  ... spracovaných {i+1}/{len(entries)}")

        print(f"📁 Uložené do priečinka: {output}")

    print(f"\n🎉 Hotovo! {len(entries)} tried konvertovaných.")


def main():
    parser = argparse.ArgumentParser(
        description="Konvertuje Hytale JSON dokumentáciu na Markdown pre RAG"
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Vstupný JSON súbor (jeden JSON objekt na riadok)"
    )
    parser.add_argument(
        "--output", "-o",
        required=True,
        help="Výstupný súbor (.md) alebo priečinok"
    )
    parser.add_argument(
        "--single-file",
        action="store_true",
        help="Ulož všetko do jedného .md súboru (pre malé databázy)"
    )

    args = parser.parse_args()
    convert(args.input, args.output, args.single_file)


if __name__ == "__main__":
    main()