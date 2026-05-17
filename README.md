# hytale-docs-scraper

This collection of Python tools is designed to capture, process, and convert Hytale Server API documentation. It provides a high-performance way to scrape the official web docs and extract clean API signatures from decompiled source code for use in development or RAG ingestion.

## Features

- **Asynchronous Scraping**: Uses `aiohttp` and `asyncio` to scrape the entire Hytale API documentation in seconds via parallel requests.
- **JSONL Output**: Saves documentation in JSONL format (one object per line), which is memory-efficient and ideal for large-scale data processing.
- **Markdown Conversion**: Includes a flexible converter to transform JSON data into clean, readable Markdown files organized by package.
- **API Extraction**: Extracts structural API signatures (classes, methods, fields) from decompiled `.java` files while stripping away implementation details.

## Use Case

This tool is designed for developers who want to build third-party tools, plugins, or documentation sites for Hytale. It is especially useful for creating local searchable databases or feeding API context into LLMs (RAG) before the official server release.

## How It Works

1. **Scraping**: The `scraper.py` script crawls the official Hytale documentation site, following package and class links to gather Javadoc content.
2. **Parsing**: HTML content is parsed using `BeautifulSoup4` to extract structured data including signatures, descriptions, and Javadoc tags (@param, @return).
3. **Storage**: Data is stored in a structured JSONL format along with a manifest file containing metadata about the scrape session.
4. **Processing**: Users can then use `json_to_md.py` to generate human-readable documentation.
5. **API Extraction (Optional)**: If you possess the `HytaleServer.jar`, you can use a Java decompiler (like [CFR](https://www.benf.org/other/cfr/)) to extract the source code. The `api_extractor.py` then processes these files to create a clean API overview.

### Decompilation Workflow
To use the `api_extractor.py`, you first need to decompile the server JAR:
1. Download `cfr.jar`.
2. Run decompiler: `java -jar cfr.jar HytaleServer.jar --outputdir ./decompiled`
3. Extract API: `python api_extractor.py ./decompiled output_api.txt`

## Requirements

- [Python 3.8+](https://www.python.org/)
- `aiohttp`, `aiofiles`, `beautifulsoup4` (installable via pip)
- (Optional) Decompiled Hytale source code for the API extractor

## Commands

**Install dependencies:**
```bash
pip install aiohttp aiofiles beautifulsoup4
```

**Scrape the official documentation:**
```bash
python scraper.py --concurrency 50 --output hytale_docs.jsonl
```

**Convert JSONL to organized Markdown files:**
```bash
python json_to_md.py --input hytale_docs.jsonl --output docs_md/
```

**Extract clean API signatures from decompiled source:**
```bash
python api_extractor.py ./path_to_decompiled output_api.txt hypixel
```

## Disclaimer

This project is intended for educational and development purposes only. It is not affiliated with Hypixel Studios or Hytale. Decompiled source code should never be shared publicly.

## License

[MIT](LICENSE)
