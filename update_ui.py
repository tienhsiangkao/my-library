import os

html_content = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kindle Reader Pro - {{ .Title }}</title>
    <script src="https://cdn.jsdelivr.net/npm/jszip@3.10.1/dist/jszip.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/epubjs@0.3.93/dist/epub.min.js"></script>
    <style>
        :root { --bg: #f4f4f4; --panel: #ffffff; --text: #333; --accent: #007aff; }
        body.dark { --bg: #121212; --panel: #1e1e1e; --text: #e0e0e0; --accent: #0a84ff; }
        body.sepia { --bg: #f4ecd8; --panel: #fdf6e3; --text: #5b4636; --accent: #8b6d5c; }

        body { margin: 0; background: var(--bg); color: var(--text); font-family: -apple-system, sans-serif; transition: background 0.3s; display: flex; height: 100vh; overflow: hidden; }
        
        #toc-sidebar { width: 300px; background: var(--panel); border-right: 1px solid rgba(0,0,0,0.1); display: flex; flex-direction: column; transition: 0.3s; }
        #toc-sidebar.hidden { transform: translateX(-300px); margin-left: -300px; }
        .sidebar-header { padding: 20px; font-weight: bold; border-bottom: 1px solid rgba(0,0,0,0.1); display: flex; justify-content: space-between; }
        #toc-list { flex: 1; overflow-y: auto; padding: 10px; font-size: 14px; list-style: none; margin: 0; }
        #toc-list li { padding: 8px 15px; cursor: pointer; border-radius: 4px; border-bottom: 1px solid rgba(0,0,0,0.05); }
        #toc-list li:hover { background: rgba(0,122,255,0.1); color: var(--accent); }

        #main-container { flex: 1; display: flex; flex-direction: column; position: relative; }
        #viewer { flex: 1; background: white; margin: 15px; border-radius: 8px; box-shadow: 0 4px 20px rgba(0,0,0,0.1); }

        .top-bar { height: 50px; background: var(--panel); display: flex; align-items: center; justify-content: space-between; padding: 0 20px; border-bottom: 1px solid rgba(0,0,0,0.1); }
        .controls-group { display: flex; gap: 8px; }
        button { padding: 6px 12px; border: 1px solid #ddd; background: white; border-radius: 5px; cursor: pointer; font-size: 12px; }

        .bottom-bar { height: 40px; background: var(--panel); display: flex; align-items: center; justify-content: center; font-size: 12px; border-top: 1px solid rgba(0,0,0,0.1); }
        #progress-slider { width: 60%; margin: 0 15px; }
    </style>
</head>
<body>
    <div id="toc-sidebar">
        <div class="sidebar-header">
            <span>CONTENTS</span>
            <button onclick="toggleSidebar()">✕</button>
        </div>
        <ul id="toc-list"></ul>
    </div>

    <div id="main-container">
        <div class="top-bar">
            <div class="controls-group">
                <button onclick="toggleSidebar()">☰</button>
                <a href="../../" style="text-decoration:none; font-size:12px; margin-left:10px; color:var(--accent)">LIBRARY</a>
            </div>
            
            <div class="controls-group">
                <button onclick="changeFontSize(-2)">A-</button>
                <button onclick="changeFontSize(2)">A+</button>
                <button onclick="setTheme('light')">☀️</button>
                <button onclick="setTheme('sepia')">☕</button>
                <button onclick="setTheme('dark')">🌙</button>
            </div>
        </div>

        <div id="viewer"></div>

        <div class="bottom-bar">
            <input type="range" id="progress-slider" min="0" max="100" value="0" step="1">
            <span id="pos-info">0%</span>
        </div>
    </div>

    <script>
        const bookPath = '../../books/{{ .Params.epub_file }}';
        const book = ePub(bookPath);
        
        // 【核心修改点】：添加 allowScriptedContent: true
        const rendition = book.renderTo("viewer", {
            width: "100%",
            height: "100%",
            flow: "paginated",
            manager: "default",
            allowScriptedContent: true 
        });

        let currentFontSize = 100;

        book.ready.then(() => {
            const tocList = document.getElementById('toc-list');
            book.navigation.toc.forEach(chapter => {
                const li = document.createElement('li');
                li.textContent = chapter.label.trim();
                li.onclick = () => {
                    rendition.display(chapter.href);
                    if(window.innerWidth < 768) toggleSidebar();
                };
                tocList.appendChild(li);
            });
            return book.locations.generate(1024);
        }).then(() => {
            rendition.display();
        });

        rendition.on("relocated", location => {
            const percent = book.locations.percentageFromCfi(location.start.cfi);
            const rounded = Math.round(percent * 100);
            document.getElementById('pos-info').innerText = rounded + '%';
            document.getElementById('progress-slider').value = rounded;
        });

        document.getElementById('progress-slider').onchange = (e) => {
            const cfi = book.locations.cfiFromPercentage(e.target.value / 100);
            rendition.display(cfi);
        };

        function toggleSidebar() {
            document.getElementById('toc-sidebar').classList.toggle('hidden');
        }

        function changeFontSize(delta) {
            currentFontSize += delta;
            rendition.themes.fontSize(currentFontSize + "%");
        }

        function setTheme(t) {
            document.body.className = t;
            const colors = {
                dark: { bg: '#121212', text: '#e0e0e0' },
                sepia: { bg: '#f4ecd8', text: '#5b4636' },
                light: { bg: '#ffffff', text: '#333333' }
            };
            rendition.themes.register(t, { 
                body: { "background-color": colors[t].bg + " !important", "color": colors[t].text + " !important" } 
            });
            rendition.themes.select(t);
        }

        window.addEventListener("keydown", e => {
            if (e.key === "ArrowLeft") rendition.prev();
            if (e.key === "ArrowRight") rendition.next();
        });
    </script>
</body>
</html>
"""

target_path = os.path.join("layouts", "_default", "single.html")
os.makedirs(os.path.dirname(target_path), exist_ok=True)
with open(target_path, "w", encoding="utf-8") as f:
    f.write(html_content)
print(f"✅ Kindle UI 已修复并重新部署。")