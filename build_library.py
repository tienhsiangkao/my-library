import os
import ebooklib
from ebooklib import epub
import yaml

# Directories
BOOKS_DIR = 'static/books'
HUGO_CONTENT_DIR = 'content/books'

def extract_metadata(epub_path):
    try:
        book = epub.read_epub(epub_path)
        title_list = book.get_metadata('DC', 'title')
        author_list = book.get_metadata('DC', 'creator')
        
        title = title_list[0][0] if title_list else "Unknown Title"
        author = author_list[0][0] if author_list else "Unknown Author"
        return {"title": title, "author": author}
    except Exception as e:
        print(f"Error reading {epub_path}: {e}")
        return {"title": "Unknown Title", "author": "Unknown Author"}

def generate_hugo_markdown():
    for filename in os.listdir(BOOKS_DIR):
        if filename.endswith('.epub'):
            filepath = os.path.join(BOOKS_DIR, filename)
            metadata = extract_metadata(filepath)
            
            slug = filename.replace('.epub', '').replace(' ', '-').lower()
            md_filepath = os.path.join(HUGO_CONTENT_DIR, f"{slug}.md")
            
            frontmatter = {
                "title": metadata["title"],
                "author": metadata["author"],
                "type": "book",
                "epub_file": filename
            }
            
            with open(md_filepath, 'w', encoding='utf-8') as f:
                f.write("---\n")
                yaml.dump(frontmatter, f, allow_unicode=True)
                f.write("---\n\n")
                f.write(f"Click below to read **{metadata['title']}** by {metadata['author']}.")
                
            print(f"Added to library: {metadata['title']}")

if __name__ == "__main__":
    print("Scanning library...")
    generate_hugo_markdown()
    print("Update complete!")
