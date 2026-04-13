from __future__ import annotations

import argparse
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

import yaml


BOOKS_DIR = Path("static/books")
CONTENT_DIR = Path("content/books")
INDEX_FILE = CONTENT_DIR / "_index.md"
GENERATED_COVERS_DIR = Path("static/generated-covers")


def slugify_filename(filename: str) -> str:
    stem = Path(filename).stem.strip()
    stem = stem.replace("_", " ").replace(".", " ")
    stem = re.sub(r"\s+", "-", stem)
    stem = re.sub(r"[^\w\-\u4e00-\u9fff]+", "", stem, flags=re.UNICODE)
    stem = re.sub(r"-{2,}", "-", stem).strip("-")
    return stem.lower() or "book"


def parse_xml_bytes(data: bytes) -> ET.Element:
    return ET.fromstring(data)


def read_epub_package(epub_path: Path) -> tuple[zipfile.ZipFile, str, ET.Element]:
    zf = zipfile.ZipFile(epub_path, "r")

    try:
        container_xml = zf.read("META-INF/container.xml")
    except KeyError as exc:
        zf.close()
        raise RuntimeError(f"Missing META-INF/container.xml in {epub_path.name}") from exc

    container_root = parse_xml_bytes(container_xml)
    rootfile = None

    for elem in container_root.iter():
        if elem.tag.endswith("rootfile"):
            rootfile = elem
            break

    if rootfile is None:
        zf.close()
        raise RuntimeError(f"Could not locate OPF rootfile in {epub_path.name}")

    opf_path = rootfile.attrib.get("full-path", "").strip()
    if not opf_path:
        zf.close()
        raise RuntimeError(f"Invalid OPF path in {epub_path.name}")

    try:
        opf_xml = zf.read(opf_path)
    except KeyError as exc:
        zf.close()
        raise RuntimeError(f"OPF file not found: {opf_path}") from exc

    opf_root = parse_xml_bytes(opf_xml)
    return zf, opf_path, opf_root


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def text_or_none(elem: ET.Element | None) -> str | None:
    if elem is None or elem.text is None:
        return None
    value = elem.text.strip()
    return value or None


def read_epub_metadata(epub_path: Path) -> dict[str, str]:
    title = epub_path.stem
    author = "Unknown Author"

    try:
        zf, _, opf_root = read_epub_package(epub_path)
        try:
            for elem in opf_root.iter():
                name = local_name(elem.tag)
                if name == "title" and text_or_none(elem):
                    title = text_or_none(elem) or title
                    break

            for elem in opf_root.iter():
                name = local_name(elem.tag)
                if name == "creator" and text_or_none(elem):
                    author = text_or_none(elem) or author
                    break
        finally:
            zf.close()
    except Exception as exc:
        print(f"⚠️ Metadata read failed for {epub_path.name}: {exc}")

    return {"title": title, "author": author}


def guess_reader_mode(title: str, filename: str) -> str:
    hay = f"{title} {filename}".lower()
    keywords = [
        "math", "mathematics", "theory", "game theory", "poker",
        "algebra", "geometry", "analysis", "probability", "statistics",
        "economics", "physics", "chemistry", "computer", "programming",
        "algorithm", "machine learning", "deep learning", "calculus",
    ]
    return "rendition" if any(k in hay for k in keywords) else "flow"


def media_type_to_ext(media_type: str | None) -> str:
    mapping = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/svg+xml": ".svg",
    }
    return mapping.get((media_type or "").lower(), "")


def pick_cover_item(manifest: list[dict[str, str]], metadata_meta: list[ET.Element]) -> dict[str, str] | None:
    by_id = {item.get("id", ""): item for item in manifest}

    # 1. EPUB3 cover-image property
    for item in manifest:
        props = item.get("properties", "")
        if "cover-image" in props.split():
            return item

    # 2. EPUB2 <meta name="cover" content="cover-image-id" />
    for meta in metadata_meta:
        name = (meta.attrib.get("name") or meta.attrib.get("property") or "").strip().lower()
        content = (meta.attrib.get("content") or "").strip()
        if name == "cover" and content and content in by_id:
            return by_id[content]

    # 3. manifest id heuristics
    for item in manifest:
        item_id = item.get("id", "").lower()
        href = item.get("href", "").lower()
        if item_id in {"cover", "coverimage", "cover-image"}:
            return item
        if "cover" in item_id and item.get("media-type", "").startswith("image/"):
            return item
        if ("cover" in href or "thumbnail" in href) and item.get("media-type", "").startswith("image/"):
            return item

    # 4. first image fallback
    for item in manifest:
        if item.get("media-type", "").startswith("image/"):
            return item

    return None


def extract_epub_cover(epub_path: Path, slug: str) -> str | None:
    try:
        zf, opf_path, opf_root = read_epub_package(epub_path)
    except Exception as exc:
        print(f"⚠️ Cover read failed for {epub_path.name}: {exc}")
        return None

    try:
        manifest: list[dict[str, str]] = []
        metadata_meta: list[ET.Element] = []

        for elem in opf_root.iter():
            name = local_name(elem.tag)
            if name == "item":
                manifest.append(
                    {
                        "id": elem.attrib.get("id", "").strip(),
                        "href": elem.attrib.get("href", "").strip(),
                        "media-type": elem.attrib.get("media-type", "").strip(),
                        "properties": elem.attrib.get("properties", "").strip(),
                    }
                )
            elif name == "meta":
                metadata_meta.append(elem)

        cover_item = pick_cover_item(manifest, metadata_meta)
        if not cover_item:
            return None

        href = cover_item.get("href", "").strip()
        media_type = cover_item.get("media-type", "").strip()

        if not href:
            return None

        opf_dir = posixpath.dirname(opf_path)
        zip_member = posixpath.normpath(posixpath.join(opf_dir, href))

        try:
            cover_bytes = zf.read(zip_member)
        except KeyError:
            # Retry with a looser search by basename
            target_name = posixpath.basename(href).lower()
            candidates = [name for name in zf.namelist() if posixpath.basename(name).lower() == target_name]
            if not candidates:
                return None
            zip_member = candidates[0]
            cover_bytes = zf.read(zip_member)

        ext = Path(href).suffix.lower() or media_type_to_ext(media_type) or ".jpg"

        GENERATED_COVERS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = GENERATED_COVERS_DIR / f"{slug}{ext}"
        out_path.write_bytes(cover_bytes)
        return out_path.as_posix().replace("static/", "", 1)
    except Exception as exc:
        print(f"⚠️ Cover extract failed for {epub_path.name}: {exc}")
        return None
    finally:
        zf.close()


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
    overwrite_auto_covers: bool = False,
) -> Path:
    metadata = read_epub_metadata(epub_path)
    md_path = choose_md_path(epub_path, existing_by_epub)
    slug = md_path.stem

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

    existing_cover = str(frontmatter.get("cover_image") or "").strip()
    should_generate_cover = (
        not existing_cover
        or existing_cover.startswith("generated-covers/")
        or overwrite_auto_covers
    )

    if should_generate_cover:
        cover_rel = extract_epub_cover(epub_path, slug)
        if cover_rel:
            frontmatter["cover_image"] = cover_rel
        elif existing_cover.startswith("generated-covers/"):
            frontmatter.pop("cover_image", None)

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


def prune_stale_markdown(existing_by_epub: dict[str, Path], current_epub_names: set[str]) -> list[str]:
    removed_md_stems: list[str] = []

    for epub_file, md_path in list(existing_by_epub.items()):
        if epub_file not in current_epub_names:
            if md_path.exists():
                removed_md_stems.append(md_path.stem)
                md_path.unlink()
                print(f"🗑 Deleted stale page: {md_path.name} (missing source {epub_file})")

    if not removed_md_stems:
        print("• No stale markdown pages to delete.")

    return removed_md_stems


def prune_generated_covers(valid_md_stems: set[str], removed_md_stems: list[str]) -> None:
    if not GENERATED_COVERS_DIR.exists():
        return

    removed = 0
    removed_md_stem_set = set(removed_md_stems)

    for cover_path in GENERATED_COVERS_DIR.iterdir():
        if not cover_path.is_file():
            continue

        stem = cover_path.stem
        if stem in removed_md_stem_set or stem not in valid_md_stems:
            cover_path.unlink()
            removed += 1
            print(f"🗑 Deleted stale cover: {cover_path.name}")

    if removed == 0:
        print("• No stale generated covers to delete.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync Hugo markdown pages with EPUB files in static/books and auto-extract covers."
    )
    parser.add_argument(
        "--overwrite-metadata",
        action="store_true",
        help="Overwrite existing title/author with EPUB metadata.",
    )
    parser.add_argument(
        "--overwrite-auto-covers",
        action="store_true",
        help="Regenerate covers even if a generated cover already exists.",
    )
    args = parser.parse_args()

    if not BOOKS_DIR.exists():
        raise SystemExit(f"Books directory not found: {BOOKS_DIR}")

    ensure_books_index()

    epub_files = sorted(BOOKS_DIR.glob("*.epub"))
    current_epub_names = {p.name for p in epub_files}

    existing_by_epub, _ = collect_existing_book_pages()

    synced_md_paths: list[Path] = []

    if not epub_files:
        print("No EPUB files found. Pruning stale markdown and generated covers...")
        removed_md_stems = prune_stale_markdown(existing_by_epub, current_epub_names)
        prune_generated_covers(valid_md_stems=set(), removed_md_stems=removed_md_stems)
        print("🎉 Library sync complete.")
        return

    for epub_path in epub_files:
        md_path = sync_book_page(
            epub_path,
            existing_by_epub=existing_by_epub,
            overwrite_metadata=args.overwrite_metadata,
            overwrite_auto_covers=args.overwrite_auto_covers,
        )
        synced_md_paths.append(md_path)

    removed_md_stems = prune_stale_markdown(existing_by_epub, current_epub_names)
    valid_md_stems = {p.stem for p in synced_md_paths if p.exists()}
    prune_generated_covers(valid_md_stems=valid_md_stems, removed_md_stems=removed_md_stems)

    print("🎉 Library sync complete.")


if __name__ == "__main__":
    main()
