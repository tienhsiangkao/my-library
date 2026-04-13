from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import yaml
from ebooklib import epub


BOOKS_DIR = Path("static/books")
CONTENT_DIR = Path("content/books")
INDEX_FILE = CONTENT_DIR / "_index.md"


def slugify_filename(filename: str) -> str:
    stem = Path(filename).stem.strip()
    stem = stem.replace("_", " ").replace(".", " ")
    stem = re.sub(r"\s+", "-", stem)
    stem = re.sub(r"[^\w\-\u4e00-\u9fff]+", "", stem, flags=re.UNICODE)
    stem = re.sub(r"-{2,}", "-", stem).strip("-")
    return stem.lower() or "book"


def read_epub_metadata(epub_path: Path) -> dict[str, str]:
    try:
        book = epub.read_epub(str(epub_path))
        title_list = book.get_metadata("DC", "title")
        author_list = book.get_metadata("DC", "creator")

        title = title_list[0][0].strip() if title_list and title_list[0][0] else epub_path.stem
        author = author_list[0][0].strip() if author_list and author_list[0][0] else "Unknown Author"

        return {"title": title, "author": author}
    except Exception as exc:
        print(f"⚠️ Metadata read failed for {epub_path.name}: {exc}")
        return {"title": epub_path.stem, "author": "Unknown Author"}


def guess_reader_mode(title: str, filename: str) -> str:
    hay = f"{title} {filename}".lower()
    keywords = [
        "math", "mathematics", "theory", "game theory", "poker",
        "algebra", "geometry", "analysis", "probability", "statistics",
        "economics", "physics", "chemistry", "computer", "programming",
        "algorithm", "machine learning", "deep learning", "calculus",
    ]
    return "rendition" if any(k in hay for k in keywords) else "flow"


def load_front_matter(md_path: Path) -> tuple[dict[str, Any], str]:
    if not md_path.exists():
        return {}, ""

    text = md_path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text

    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return {}, text

    _, yaml_block, body = parts
    data = yaml.safe_load(yaml_block) or {}
    if not isinstance(data, dict):
        data = {}
    return data, body.lstrip("\n")


def dump_markdown(frontmatter: dict[str, Any], body: str) -> str:
    yaml_text = yaml.safe_dump(
        frontmatter,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    ).strip()
    return f"---\n{yaml_text}\n---\n\n{body.strip()}\n"


def ensure_books_index() -> None:
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    if INDEX_FILE.exists():
        return

    INDEX_FILE.write_text(
        "---\n"
        "title: Library\n"
        "---\n\n"
        "My ebook library.\n",
        encoding="utf-8",
    )
    print(f"✅ Created {INDEX_FILE}")


def collect_existing_book_pages() -> tuple[dict[str, Path], dict[Path, dict[str, Any]]]:
    by_epub_file: dict[str, Path] = {}
    by_path_frontmatter: dict[Path, dict[str, Any]] = {}

    for md_path in CONTENT_DIR.glob("*.md"):
        if md_path.name == "_index.md":
            continue

        frontmatter, _ = load_front_matter(md_path)
        by_path_frontmatter[md_path] = frontmatter

        epub_file = frontmatter.get("epub_file")
        if isinstance(epub_file, str) and epub_file.strip():
            if epub_file not in by_epub_file:
                by_epub_file[epub_file] = md_path
            else:
                print(f"⚠️ Duplicate epub_file detected in existing pages: {epub_file}")
                print(f"   Keeping first: {by_epub_file[epub_file].name}")
                print(f"   Ignoring later: {md_path.name}")

    return by_epub_file, by_path_frontmatter


def choose_md_path(epub_path: Path, existing_by_epub: dict[str, Path]) -> Path:
    if epub_path.name in existing_by_epub:
        return existing_by_epub[epub_path.name]

    base_slug = slugify_filename(epub_path.name)
    candidate = CONTENT_DIR / f"{base_slug}.md"
    counter = 1

    while candidate.exists():
        frontmatter, _ = load_front_matter(candidate)
        existing_epub = frontmatter.get("epub_file")
        if existing_epub == epub_path.name:
            return candidate
        candidate = CONTENT_DIR / f"{base_slug}-{counter}.md"
        counter += 1

    return candidate


def sync_book_page(
    epub_path: Path,
    existing_by_epub: dict[str, Path],
    overwrite_metadata: bool = False,
) -> Path:
    metadata = read_epub_metadata(epub_path)
    md_path = choose_md_path(epub_path, existing_by_epub)

    old_frontmatter, old_body = load_front_matter(md_path)
    frontmatter: dict[str, Any] = dict(old_frontmatter)

    if overwrite_metadata or not frontmatter.get("title"):
        frontmatter["title"] = metadata["title"]

    if overwrite_metadata or not frontmatter.get("author"):
        frontmatter["author"] = metadata["author"]

    frontmatter["type"] = "book"
    frontmatter["epub_file"] = epub_path.name

    if not frontmatter.get("reader_mode"):
        frontmatter["reader_mode"] = guess_reader_mode(metadata["title"], epub_path.name)

    if not old_body.strip():
        body = f"Click below to read **{frontmatter['title']}** by {frontmatter['author']}."
    else:
        body = old_body

    new_text = dump_markdown(frontmatter, body)

    if md_path.exists():
        old_text = md_path.read_text(encoding="utf-8")
        if old_text == new_text:
            print(f"• Unchanged: {md_path.name}")
            existing_by_epub[epub_path.name] = md_path
            return md_path

    md_path.write_text(new_text, encoding="utf-8")
    existing_by_epub[epub_path.name] = md_path
    print(f"✅ Synced: {md_path.name}")
    return md_path


def prune_stale_markdown(existing_by_epub: dict[str, Path], current_epub_names: set[str]) -> None:
    removed = 0

    for epub_file, md_path in list(existing_by_epub.items()):
        if epub_file not in current_epub_names:
            if md_path.exists():
                md_path.unlink()
                print(f"🗑 Deleted stale page: {md_path.name} (missing source {epub_file})")
                removed += 1

    if removed == 0:
        print("• No stale markdown pages to delete.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync Hugo markdown pages with EPUB files in static/books."
    )
    parser.add_argument(
        "--overwrite-metadata",
        action="store_true",
        help="Overwrite existing title/author with EPUB metadata.",
    )
    args = parser.parse_args()

    if not BOOKS_DIR.exists():
        raise SystemExit(f"Books directory not found: {BOOKS_DIR}")

    ensure_books_index()

    epub_files = sorted(BOOKS_DIR.glob("*.epub"))
    current_epub_names = {p.name for p in epub_files}

    existing_by_epub, _ = collect_existing_book_pages()

    if not epub_files:
        print("No EPUB files found. Pruning stale markdown...")
        prune_stale_markdown(existing_by_epub, current_epub_names)
        print("🎉 Library sync complete.")
        return

    for epub_path in epub_files:
        sync_book_page(
            epub_path,
            existing_by_epub=existing_by_epub,
            overwrite_metadata=args.overwrite_metadata,
        )

    prune_stale_markdown(existing_by_epub, current_epub_names)
    print("🎉 Library sync complete.")


if __name__ == "__main__":
    main()