#!/usr/bin/env python3
"""
Hytale Server API Documentation Scraper
========================================
Async scraper — rýchly vďaka aiohttp + asyncio (50 parallelných requestov).
Výstup: JSONL (1 riadok = 1 trieda) — ideálne pre RAG ingestion.

Inštalácia závislostí:
    pip install aiohttp aiofiles beautifulsoup4

Použitie:
    python3 scraper.py                          # defaultné nastavenia
    python3 scraper.py --concurrency 80         # agresívnejšie (ak server vydrží)
    python3 scraper.py --output moje_docs.jsonl
"""

import asyncio
import aiohttp
import aiofiles
import json
import re
import sys
import time
import argparse
from urllib.parse import urljoin
from bs4 import BeautifulSoup, Tag
from dataclasses import dataclass, asdict, field
from typing import Optional

BASE_URL = "https://release.server.docs.hytale.com/"

# ═══════════════════════════════════════════════════════════════════
#  Dátové modely
# ═══════════════════════════════════════════════════════════════════

@dataclass
class MemberDoc:
    name: str
    kind: str          # "method" | "field" | "constructor" | "enum_constant"
    signature: str
    description: str
    deprecated: bool = False
    tags: dict = field(default_factory=dict)  # @param, @return, @throws …


@dataclass
class ClassDoc:
    url: str
    package: str
    name: str
    qualified_name: str
    kind: str          # "class" | "interface" | "enum" | "annotation" | "record"
    description: str
    deprecated: bool = False
    deprecated_msg: str = ""
    superclass: Optional[str] = None
    interfaces: list = field(default_factory=list)
    members: list = field(default_factory=list)
    since: str = ""
    see_also: list = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════
#  HTML parsing
# ═══════════════════════════════════════════════════════════════════

def clean(tag) -> str:
    """Čistý text z BS4 tagu, zkolabovaný whitespace."""
    if tag is None:
        return ""
    return re.sub(r"\s+", " ", tag.get_text(" ", strip=True)).strip()


def parse_tags(block: Tag) -> dict:
    """Extrahuje Javadoc tagy (@param, @return, @throws …) z detail sekcie."""
    tags: dict[str, list] = {}
    for dl in block.select("dl"):
        current_key = None
        for child in dl.children:
            if not isinstance(child, Tag):
                continue
            if child.name == "dt":
                current_key = clean(child).rstrip(":").strip()
                tags.setdefault(current_key, [])
            elif child.name == "dd" and current_key:
                tags[current_key].append(clean(child))
    return tags


def detect_kind(title: str) -> str:
    low = title.lower()
    for kw in ("interface", "enum", "annotation", "record"):
        if kw in low:
            return kw
    return "class"


def parse_class_page(html: str, url: str, package: str) -> Optional[ClassDoc]:
    soup = BeautifulSoup(html, "html.parser")

    # ── Nadpis ──
    title_tag = (soup.find("h1", class_="title")
                 or soup.find("div", class_="header"))
    if title_tag is None:
        return None
    title_text = clean(title_tag)

    # Posledné slovo = meno triedy (napr. "Class PlayerEntity" → "PlayerEntity")
    parts = title_text.split()
    raw_name = parts[-1] if parts else title_text
    class_name = re.sub(r"<.*", "", raw_name).strip()  # odstráni <T>
    kind = detect_kind(title_text)
    qualified = f"{package}.{class_name}" if package else class_name

    # ── Popis triedy ──
    desc_block = (soup.find("section", class_="class-description")
                  or soup.find("div", class_="description"))

    description = ""
    deprecated = False
    deprecated_msg = ""
    superclass = None
    interfaces: list[str] = []
    since = ""
    see_also: list[str] = []

    if desc_block:
        dep = (desc_block.find(class_="deprecation-block")
               or desc_block.find("div", class_="deprecatedLabel"))
        if dep:
            deprecated = True
            deprecated_msg = clean(dep)

        blk = desc_block.find("div", class_="block")
        description = clean(blk) if blk else ""

        # Dedičnosť / implementácie
        inherit = (desc_block.find("div", class_="inheritance")
                   or desc_block.find("ul", class_="inheritance"))
        if inherit:
            items = inherit.find_all("a")
            if items:
                superclass = clean(items[-1])

        # Implements / superinterfaces
        in_impl = False
        for dl in desc_block.select("dl"):
            for child in dl.children:
                if not isinstance(child, Tag):
                    continue
                if child.name == "dt":
                    label = clean(child).lower()
                    in_impl = "implement" in label or "superinterface" in label
                elif child.name == "dd" and in_impl:
                    interfaces.extend(
                        a.get_text(strip=True) for a in child.find_all("a")
                    )

        tag_data = parse_tags(desc_block)
        since = ", ".join(tag_data.get("Since", tag_data.get("since", [])))
        see_also = tag_data.get("See Also", tag_data.get("see also", []))

    # ── Členovia (metódy, polia, konštruktory …) ──
    members: list[MemberDoc] = []

    for detail in soup.select("section.detail"):
        parent = detail.parent
        parent_class = " ".join((parent.get("class") or []) if parent else [])

        if "method" in parent_class:
            mk = "method"
        elif "constructor" in parent_class:
            mk = "constructor"
        elif "field" in parent_class:
            mk = "field"
        elif "enum-constant" in parent_class or "constant" in parent_class:
            mk = "enum_constant"
        else:
            mk = "member"

        member_id = detail.get("id", "")
        sig_tag = (detail.find("div", class_="member-signature")
                   or detail.find("pre"))
        signature = clean(sig_tag) if sig_tag else member_id

        blk2 = detail.find("div", class_="block")
        mem_desc = clean(blk2) if blk2 else ""

        mem_dep = bool(
            detail.find(class_="deprecation-block")
            or detail.find("span", class_="deprecatedLabel")
        )
        mem_tags = parse_tags(detail)

        members.append(MemberDoc(
            name=member_id,
            kind=mk,
            signature=signature,
            description=mem_desc,
            deprecated=mem_dep,
            tags=mem_tags,
        ))

    return ClassDoc(
        url=url,
        package=package,
        name=class_name,
        qualified_name=qualified,
        kind=kind,
        description=description,
        deprecated=deprecated,
        deprecated_msg=deprecated_msg,
        superclass=superclass,
        interfaces=interfaces,
        members=[asdict(m) for m in members],
        since=since,
        see_also=see_also,
    )


def extract_class_links(html: str, base_url: str) -> list[str]:
    """Všetky absolútne URL tried z package-summary stránky."""
    soup = BeautifulSoup(html, "html.parser")
    SKIP = {"package-summary", "package-tree", "index-", "overview-",
            "deprecated", "search", "allclasses", "allpackages"}
    links = set()
    for a in soup.select("a[href]"):
        href: str = a["href"]
        if not href.endswith(".html"):
            continue
        if any(s in href for s in SKIP):
            continue
        abs_url = urljoin(base_url, href)
        if abs_url.startswith(BASE_URL):
            links.add(abs_url)
    return list(links)


def extract_package_links(html: str) -> list[tuple[str, str]]:
    """Všetky (name, url) balíčkov z index stránky."""
    soup = BeautifulSoup(html, "html.parser")
    packages = []
    seen: set[str] = set()
    for a in soup.select("a[href]"):
        href: str = a["href"]
        if "package-summary.html" not in href:
            continue
        abs_url = urljoin(BASE_URL, href)
        if abs_url in seen:
            continue
        seen.add(abs_url)
        pkg_name = a.get_text(strip=True)
        if pkg_name:
            packages.append((pkg_name, abs_url))
    return packages


# ═══════════════════════════════════════════════════════════════════
#  Async engine
# ═══════════════════════════════════════════════════════════════════

async def fetch(session: aiohttp.ClientSession, url: str,
                sem: asyncio.Semaphore, retries: int = 3) -> Optional[str]:
    for attempt in range(retries):
        try:
            async with sem:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 200:
                        return await resp.text(errors="replace")
                    if resp.status == 404:
                        return None
                    await asyncio.sleep(0.5)
        except asyncio.TimeoutError:
            pass
        except Exception as e:
            if attempt == retries - 1:
                print(f"  [WARN] {url}: {e}", file=sys.stderr)
            await asyncio.sleep(0.3 * (attempt + 1))
    return None


class Stats:
    def __init__(self):
        self.classes = 0
        self.errors = 0
        self._lock = asyncio.Lock()

    async def inc(self, ok: bool = True):
        async with self._lock:
            if ok:
                self.classes += 1
            else:
                self.errors += 1
            if self.classes % 100 == 0 and self.classes:
                elapsed = time.time() - self.t0
                rate = self.classes / elapsed
                print(f"  ✓ {self.classes} tried  |  {rate:.0f} cls/s", flush=True)

    def start(self):
        self.t0 = time.time()


class AsyncWriter:
    def __init__(self, path: str):
        self.path = path
        self._lock = asyncio.Lock()
        self._f = None

    async def open(self):
        self._f = await aiofiles.open(self.path, "w", encoding="utf-8")

    async def write(self, line: str):
        async with self._lock:
            await self._f.write(line + "\n")

    async def close(self):
        if self._f:
            await self._f.close()


async def scrape_class(session, url: str, package: str,
                       sem: asyncio.Semaphore, writer: AsyncWriter,
                       stats: Stats):
    html = await fetch(session, url, sem)
    if not html:
        await stats.inc(ok=False)
        return
    doc = parse_class_page(html, url, package)
    if doc:
        await writer.write(json.dumps(asdict(doc), ensure_ascii=False))
    await stats.inc(ok=bool(doc))


async def scrape_package(session, pkg_name: str, pkg_url: str,
                         sem: asyncio.Semaphore, writer: AsyncWriter,
                         stats: Stats):
    html = await fetch(session, pkg_url, sem)
    if not html:
        return
    urls = extract_class_links(html, pkg_url)
    tasks = [scrape_class(session, u, pkg_name, sem, writer, stats) for u in urls]
    await asyncio.gather(*tasks)


# ═══════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════

async def main(concurrency: int, output: str):
    print(f"🚀  Hytale Scraper  |  concurrency={concurrency}  |  output={output}")

    connector = aiohttp.TCPConnector(
        limit=concurrency + 10,
        limit_per_host=concurrency,
        enable_cleanup_closed=True,
    )
    headers = {
        "User-Agent": "HytaleDocsScraper/2.0 (+RAG)",
        "Accept": "text/html,*/*",
        "Accept-Encoding": "gzip, deflate, br",
    }
    sem = asyncio.Semaphore(concurrency)
    writer = AsyncWriter(output)
    stats = Stats()
    stats.start()

    await writer.open()

    packages: list[tuple[str, str]] = []
    try:
        async with aiohttp.ClientSession(
            connector=connector, headers=headers
        ) as session:

            # ── 1. Index stránka ──
            print("📦  Sťahujem zoznam balíčkov …")
            html = await fetch(session, BASE_URL, sem)
            if not html:
                print("CHYBA: Nedá sa načítať index stránka.", file=sys.stderr)
                return

            packages = extract_package_links(html)
            print(f"📦  Nájdených {len(packages)} balíčkov — spúšťam scraping …\n")

            # ── 2. Všetky balíčky naraz ──
            pkg_tasks = [
                scrape_package(session, name, url, sem, writer, stats)
                for name, url in packages
            ]
            await asyncio.gather(*pkg_tasks)

    finally:
        await writer.close()

    elapsed = time.time() - stats.t0
    rate = stats.classes / elapsed if elapsed > 0 else 0

    print(f"\n{'═'*55}")
    print(f"  ✅  Hotovo!")
    print(f"  Balíčky  : {len(packages)}")
    print(f"  Triedy   : {stats.classes}")
    print(f"  Chyby    : {stats.errors}")
    print(f"  Čas      : {elapsed:.1f}s  ({rate:.0f} tried/s)")
    print(f"  Výstup   : {output}")
    print(f"{'═'*55}")

    # Manifest
    manifest_path = output.replace(".jsonl", "") + "_manifest.json"
    manifest = {
        "source": BASE_URL,
        "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "packages": len(packages),
        "classes_scraped": stats.classes,
        "errors": stats.errors,
        "elapsed_seconds": round(elapsed, 1),
        "output_format": "jsonl",
        "jsonl_schema": {
            "url": "URL stránky triedy",
            "package": "Java balíček (napr. com.hypixel.hytale.math)",
            "name": "Krátke meno (napr. Vec3f)",
            "qualified_name": "Plne kvalifikované meno",
            "kind": "class | interface | enum | annotation | record",
            "description": "Javadoc popis triedy",
            "deprecated": "boolean",
            "deprecated_msg": "Text deprecation správy ak existuje",
            "superclass": "Nadradená trieda",
            "interfaces": "Zoznam implementovaných interfacov",
            "members": "Zoznam metód/polí/konštruktorov",
            "since": "@since tag",
            "see_also": "@see tagy",
        },
        "members_schema": {
            "name": "ID člena (z HTML anchor)",
            "kind": "method | field | constructor | enum_constant | member",
            "signature": "Celá signatúra vrátane typov",
            "description": "Javadoc popis",
            "deprecated": "boolean",
            "tags": "Slovník @param/@return/@throws/…",
        },
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"  📋  Manifest  : {manifest_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Hytale Server API docs scraper → JSONL pre RAG",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--concurrency", type=int, default=50,
        help="Max paralelných HTTP requestov. Odporúča sa 30–80."
    )
    parser.add_argument(
        "--output", default="hytale_docs.jsonl",
        help="Výstupný JSONL súbor."
    )
    args = parser.parse_args()
    asyncio.run(main(args.concurrency, args.output))