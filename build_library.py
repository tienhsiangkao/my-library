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
        print(f"⚠️  Metadata read failed for {epub_path.name}: {exc}")
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


def build_book_page(epub_path: Path, overwrite_metadata: bool = False) -> None:
    metadata = read_epub_metadata(epub_path)
    slug = slugify_filename(epub_path.name)
    md_path = CONTENT_DIR / f"{slug}.md"

    old_frontmatter, old_body = load_front_matter(md_path)

    frontmatter: dict[str, Any] = dict(old_frontmatter)

    if overwrite_metadata or "title" not in frontmatter or not frontmatter["title"]:
        frontmatter["title"] = metadata["title"]

    if overwrite_metadata or "author" not in frontmatter or not frontmatter["author"]:
        frontmatter["author"] = metadata["author"]

    frontmatter["type"] = "book"
    frontmatter["epub_file"] = epub_path.name

    if "reader_mode" not in frontmatter or not frontmatter["reader_mode"]:
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
            return

    md_path.write_text(new_text, encoding="utf-8")
    print(f"✅ Synced: {md_path.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Hugo markdown pages for EPUB books.")
    parser.add_argument(
        "--overwrite-metadata",
        action="store_true",
        help="Overwrite existing title/author from EPUB metadata.",
    )
    args = parser.parse_args()

    if not BOOKS_DIR.exists():
        raise SystemExit(f"Books directory not found: {BOOKS_DIR}")

    ensure_books_index()

    epub_files = sorted(BOOKS_DIR.glob("*.epub"))
    if not epub_files:
        print("No EPUB files found.")
        return

    for epub_path in epub_files:
        build_book_page(epub_path, overwrite_metadata=args.overwrite_metadata)

    print("🎉 Library sync complete.")


if __name__ == "__main__":
    main()