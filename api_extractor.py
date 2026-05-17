#!/usr/bin/env python3
"""
Vytiahne API signatúry z dekompilovaných .java súborov.
Odstraňuje telá metód, komentáre a ponecháva len štruktúru.

Použitie:
    python api_extractor.py ./decompiled output.txt
    python api_extractor.py ./decompiled output.txt hypixel   <- filter podľa cesty
"""

import sys
import os
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed


def extract_signatures(java_file: Path) -> str:
    try:
        text = java_file.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return ''

    lines = text.splitlines()
    result = []
    brace_depth = 0
    in_method_body = False
    method_brace_start = 0
    skip_block_comment = False

    for line in lines:
        stripped = line.strip()

        # Preskoc blokové komentáre /* ... */
        if skip_block_comment:
            if '*/' in stripped:
                skip_block_comment = False
            continue
        if stripped.startswith('/*'):
            if '*/' not in stripped:
                skip_block_comment = True
            continue

        # Preskoc riadkové komentáre
        if stripped.startswith('//'):
            continue

        # Počítaj zložené závorky
        opens = line.count('{')
        closes = line.count('}')

        if in_method_body:
            brace_depth += opens - closes
            if brace_depth <= method_brace_start:
                in_method_body = False
                if stripped == '}' and brace_depth == method_brace_start:
                    pass  # zatvárajúca závorka metódy, preskočíme
            continue

        # Zachovaj package, import, class, interface, enum deklarácie
        if (stripped.startswith('package ')
                or stripped.startswith('import ')
                or re.match(r'.*(public|protected|private|static|final|abstract|class|interface|enum|record).*', stripped)):

            # Ak riadok obsahuje { a vyzerá ako začiatok metódy (nie triedy)
            if '{' in stripped and not re.match(
                r'\s*(public|protected|private)?\s*(static\s+)?(final\s+)?(abstract\s+)?(class|interface|enum|record)\s+', line
            ):
                # Je to metóda s telom na jednom riadku alebo začiatok tela
                result.append(stripped.split('{')[0].strip() + ';')
                in_method_body = True
                method_brace_start = brace_depth
                brace_depth += opens - closes
                continue

            result.append(stripped)
            brace_depth += opens - closes
        else:
            brace_depth += opens - closes

    if result:
        return f"// FILE: {java_file}\n" + '\n'.join(result) + '\n'
    return ''


def process_directory(input_dir: str, output_path: str, filter_str: str = None):
    input_dir = Path(input_dir)
    if not input_dir.exists():
        print(f"Priečinok {input_dir} neexistuje.")
        sys.exit(1)

    java_files = list(input_dir.rglob('*.java'))

    if filter_str:
        java_files = [f for f in java_files if filter_str in str(f)]

    print(f"Nájdených .java súborov: {len(java_files)}")

    results = []
    processed = 0

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(extract_signatures, f): f for f in java_files}
        for future in as_completed(futures):
            result = future.result()
            if result:
                results.append(result)
            processed += 1
            if processed % 2000 == 0:
                print(f"  {processed}/{len(java_files)}")

    output = '\n'.join(results)
    Path(output_path).write_text(output, encoding='utf-8')

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"\nHotovo! {len(results)} súborov → {output_path} ({size_mb:.2f} MB)")


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    process_directory(
        sys.argv[1],
        sys.argv[2],
        sys.argv[3] if len(sys.argv) > 3 else None
    )