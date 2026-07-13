from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from pydantic import BaseModel
import os
import json
import uvicorn
import aiofiles
from contextlib import asynccontextmanager
import asyncio
from fastapi.responses import StreamingResponse
from watchfiles import awatch, Change

# Import core config
from config import cfg

app = FastAPI(title="MdViewer Backend")

# Enable CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class EditRequest(BaseModel):
    content: str
    path: str

# Caching for nav tree
nav_cache = {
    "mtime": 0,
    "tree": []
}

# SSE Client queues
clients = set()

async def file_watcher():
    async for changes in awatch(cfg.docs_dir):
        for change, path in changes:
            if path.lower().endswith(".md"):
                # Invalidate cache if there's a new or deleted file
                if change in (Change.added, Change.deleted):
                    nav_cache["mtime"] = 0
                
                # Notify all clients
                for q in clients:
                    try:
                        q.put_nowait({"type": "file_change", "path": path})
                    except asyncio.QueueFull:
                        pass

@app.on_event("startup")
async def startup_event():
    target_dir = os.environ.get("MDVIEW_DIR", os.getcwd())
    cfg.docs_dir = Path(target_dir).resolve()
    print(f"Backend started, serving docs from {cfg.docs_dir}")
    asyncio.create_task(file_watcher())

@app.get("/api/events")
async def events(request: Request):
    q = asyncio.Queue(maxsize=100)
    clients.add(q)
    
    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                event = await q.get()
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            clients.remove(q)
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/api/nav")
def get_navigation():
    current_mtime = os.stat(cfg.docs_dir).st_mtime
    if nav_cache["mtime"] == current_mtime and nav_cache["tree"]:
        return nav_cache["tree"]

    def build_json_tree(dir_path, rel_path="", depth=0, visited=None):
        if visited is None:
            visited = set()
        real_path = os.path.realpath(dir_path)
        if real_path in visited:
            return []
        visited.add(real_path)

        items = []
        try:
            with os.scandir(dir_path) as it:
                for entry in it:
                    name = entry.name
                    if name.startswith('.'):
                        continue
                    if name.lower() in cfg.exclude_names:
                        continue
                        
                    is_dir = entry.is_dir(follow_symlinks=False)
                    if not is_dir and not name.lower().endswith('.md'):
                        continue
                        
                    full_path = entry.path
                    item_rel = f"{rel_path}/{name}" if rel_path else name
                    items.append((name, is_dir, item_rel, full_path))
        except OSError:
            pass

        items.sort(key=lambda x: (not x[1], x[0].lower()))

        result = []
        for name, is_dir, item_rel, full_path in items:
            if is_dir:
                children = build_json_tree(full_path, item_rel, depth + 1, visited.copy())
                if children:
                    result.append({"name": name, "path": item_rel, "is_dir": True, "children": children})
            else:
                result.append({"name": name, "path": item_rel, "is_dir": False})
        return result

    tree = build_json_tree(str(cfg.docs_dir))
    nav_cache["mtime"] = current_mtime
    nav_cache["tree"] = tree
    return tree

@app.get("/api/config")
async def get_config():
    return {
        "exclude_dirs": ",".join(cfg.exclude_dirs)
    }

class ConfigRequest(BaseModel):
    exclude_dirs: str

@app.post("/api/config")
async def update_config(req: ConfigRequest):
    cfg.reload_excludes(req.exclude_dirs)
    nav_cache["mtime"] = 0
    return {"status": "ok"}

@app.get("/api/file")
async def get_file(path: str = ""):
    if not path:
        path = cfg.default_file
        
    file_path = (cfg.docs_dir / path).resolve()
    try:
        file_path.relative_to(cfg.docs_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access Denied")

    if not file_path.exists() or file_path.suffix.lower() != '.md':
        raise HTTPException(status_code=404, detail="Markdown file not found")
        
    async with aiofiles.open(file_path, mode='r', encoding='utf-8') as f:
        md_content = await f.read()
    
    loop = asyncio.get_running_loop()
    
    def parse_markdown(content):
        import markdown
        import nh3
        import re
        
        md_content_fixed = content.replace('\r\n', '\n').replace('\r', '\n')
        lines = md_content_fixed.split('\n')
        
        # Pre-process lists to ensure they have a blank line before them (standard Markdown requirement)
        list_fixed_lines = []
        for i, line in enumerate(lines):
            is_list_item = re.match(r'^\s*[*+-]\s+', line) or re.match(r'^\s*\d+\.\s+', line)
            if is_list_item and i > 0 and lines[i-1].strip() != '':
                prev_is_list = re.match(r'^\s*[*+-]\s+', lines[i-1]) or re.match(r'^\s*\d+\.\s+', lines[i-1])
                if not prev_is_list:
                    list_fixed_lines.append('')
            list_fixed_lines.append(line)
        lines = list_fixed_lines

        processed_lines = []
        in_block = False
        indent = 0
        for line in lines:
            match = re.match(r'^(\s{2,})(```.*)$', line.rstrip())
            if match and not in_block:
                indent = len(match.group(1))
                processed_lines.append(match.group(2))
                in_block = True
            elif in_block:
                if line.strip() == '```':
                    processed_lines.append('```')
                    in_block = False
                else:
                    processed_lines.append(line[indent:] if line.startswith(' '*indent) else line.strip())
            else:
                processed_lines.append(line)
                
        md_content_fixed = '\n'.join(processed_lines)
        
        md = markdown.Markdown(extensions=['fenced_code', 'tables', 'toc', 'codehilite'])
        html_content = md.convert(md_content_fixed)
        html_content = nh3.clean(html_content, attributes={**nh3.ALLOWED_ATTRIBUTES, "*": {"class", "id", "style"}})
        
        # Replace python-markdown encoded mermaid blocks with actual divs
        html_content = re.sub(
            r'<pre[^>]*><code class="language-mermaid">(.*?)</code></pre>',
            lambda m: f'<div class="mermaid">\n{m.group(1).replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")}\n</div>',
            html_content,
            flags=re.DOTALL | re.IGNORECASE
        )
        
        # Fix double-escaped backslashes inside LaTeX math blocks
        # python-markdown escapes \ to \\ in paragraph text, which breaks KaTeX
        def fix_latex_escapes(m):
            return m.group(0).replace('\\\\', '\\')
        
        # Fix display math $$...$$
        html_content = re.sub(r'\$\$.*?\$\$', fix_latex_escapes, html_content, flags=re.DOTALL)
        # Fix inline math $...$  (but not $$)
        html_content = re.sub(r'(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)', fix_latex_escapes, html_content)
        
        return html_content

    html_content = await loop.run_in_executor(None, parse_markdown, md_content)
    
    return {
        "title": path,
        "html": html_content,
        "raw": md_content,
        "mtime": file_path.stat().st_mtime
    }

@app.post("/api/file")
async def save_file(req: EditRequest):
    file_path = (cfg.docs_dir / req.req_path).resolve() if hasattr(req, 'req_path') else (cfg.docs_dir / req.path).resolve()
    try:
        file_path.relative_to(cfg.docs_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access Denied")
        
    async with aiofiles.open(file_path, mode='w', encoding='utf-8') as f:
        await f.write(req.content)
    
    # Invalidate nav cache in case a new file was created
    nav_cache["mtime"] = 0
    return {"status": "ok"}

from fastapi.responses import FileResponse
import mimetypes

@app.get("/api/media")
async def get_media(path: str):
    file_path = (cfg.docs_dir / path).resolve()
    try:
        # Check if it's within docs_dir
        file_path.relative_to(cfg.docs_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access Denied")

    if not file_path.exists() or not file_path.is_file():
        # Fallback: if 'docs/images/sawtooth.png' fails, try 'images/sawtooth.png' in the root
        parts = path.split('/')
        found = False
        for i in range(1, len(parts)):
            fallback = (cfg.docs_dir / '/'.join(parts[i:])).resolve()
            if fallback.exists() and fallback.is_file():
                file_path = fallback
                found = True
                break
        if not found:
            raise HTTPException(status_code=404, detail="Media file not found")

    mime_type, _ = mimetypes.guess_type(str(file_path))
    return FileResponse(path=file_path, media_type=mime_type)

@app.get("/api/search")
async def search(q: str):
    import subprocess
    query = q.lower()
    results = []
    
    def run_search(search_query):
        res = []
        if search_query:
            import glob
            search_query_lower = search_query.lower()
            try:
                # Walk the docs_dir recursively
                for root, dirs, files in os.walk(cfg.docs_dir):
                    # Filter directories
                    dirs[:] = [d for d in dirs if not d.startswith('.') and d.lower() not in cfg.exclude_names]
                    
                    for name in files:
                        if not name.lower().endswith('.md') or name.startswith('.'):
                            continue
                            
                        file_path = Path(root) / name
                        if cfg.is_path_excluded(file_path):
                            continue
                            
                        try:
                            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read().lower()
                                if search_query_lower in content:
                                    rel_path = file_path.relative_to(cfg.docs_dir)
                                    res.append({
                                        'path': str(rel_path),
                                        'title': file_path.stem
                                    })
                                    if len(res) >= 50:
                                        return res
                        except Exception:
                            continue
            except Exception:
                pass
        return res

    loop = asyncio.get_running_loop()
    results = await loop.run_in_executor(None, run_search, query)
    
    return {"results": results}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
