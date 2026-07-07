#!/usr/bin/env python3
"""
Local Markdown Documentation Viewer
Serves markdown files as rendered HTML with navigation

Usage:
    mdview [directory]                 # Serve specified directory
    mdview                             # Serve current directory

Then open: http://localhost:8000
"""

import http.server
import socketserver
import os
import re
import sys
import urllib.parse
from urllib.parse import unquote, urlparse
from pathlib import Path

import markdown
from markdown.extensions import codehilite, toc, tables
import jinja2

# Handle --help
if len(sys.argv) > 1 and sys.argv[1] in ['-h', '--help']:
    print(__doc__)
    print("""
Arguments:
    [directory]     Directory containing markdown files
                    Default: current working directory

Environment Variables:
    PORT                    Server port (default: 8000)
    MDVIEW_EXCLUDE_DIRS     Comma-separated list of directories to exclude from navigation
                            (default: archive,node_modules,.git,__pycache__,venv,.venv,dist,build)
                            Set to empty string to include all directories

Examples:
    # Run from anywhere - serves current directory
    mdview
    
    # Run with explicit directory
    mdview ./docs
    mdview /path/to/docs
    
    # Custom port
    PORT=3000 mdview
    
    # Include all directories (no exclusions)
    MDVIEW_EXCLUDE_DIRS="" mdview
    
    # Custom exclusions
    MDVIEW_EXCLUDE_DIRS="drafts,old,archive" mdview
""")
    sys.exit(0)

# Configuration
PORT = int(os.environ.get('PORT', 8000))
DEFAULT_FILE = 'README.md'

# Determine docs directory:
# 1. Command line argument (if provided)
# 2. Script's directory (if it has .md files)
# 3. Current working directory (fallback)
SCRIPT_DIR = Path(__file__).parent.resolve()

if len(sys.argv) > 1 and not sys.argv[1].startswith('-'):
    # Explicit path provided (can be file or directory)
    target = Path(sys.argv[1]).resolve()
    if target.is_file():
        DOCS_DIR = target.parent
        DEFAULT_FILE = target.name
    else:
        DOCS_DIR = target
else:
    # Use current directory (most natural for terminal tool)
    DOCS_DIR = Path.cwd()
    # If CWD has no md files but the script dir does, and we are NOT in the script dir, 
    # we could potentially fallback to script dir, but let's keep it simple and stick to CWD.

# Validate directory exists
if not DOCS_DIR.exists():
    print(f"❌ Error: Directory does not exist: {DOCS_DIR}")
    sys.exit(1)

if not DOCS_DIR.is_dir():
    print(f"❌ Error: Path is not a directory: {DOCS_DIR}")
    sys.exit(1)

# Check if directory has markdown files
md_files_in_dir = list(DOCS_DIR.rglob('*.md'))
if not md_files_in_dir:
    print(f"⚠️  Warning: No markdown files found in {DOCS_DIR}")
    print(f"   The directory listing will be shown instead.")
    print(f"   💡 Tip: Specify a directory with .md files: mdview /path/to/docs")
    print()

# Get project name from directory for display
PROJECT_NAME = DOCS_DIR.name.replace('_', ' ').replace('-', ' ').title()

# Directories to exclude from navigation (comma-separated via env var, or default)
# Default excludes common non-doc directories
DEFAULT_EXCLUDE = 'archive,node_modules,.git,__pycache__,venv,.venv,dist,build'
user_exclude = os.environ.get('MDVIEW_EXCLUDE_DIRS', '')
raw_dirs = user_exclude.split(',') + DEFAULT_EXCLUDE.split(',') if user_exclude else DEFAULT_EXCLUDE.split(',')
MDVIEW_EXCLUDE_DIRS = list(set([d.strip() for d in raw_dirs if d.strip()]))

EXCLUDE_PATHS_ABS = []
EXCLUDE_NAMES = []
for d in MDVIEW_EXCLUDE_DIRS:
    d_lower = d.lower()
    if d.startswith('/') or d.startswith('~'):
        EXCLUDE_PATHS_ABS.append(Path(os.path.expanduser(d)).resolve().as_posix().lower())
    else:
        EXCLUDE_NAMES.append(d_lower)

try:
    from pygments.formatters import HtmlFormatter
    pygments_css = HtmlFormatter(style='monokai').get_style_defs('.codehilite')
except ImportError:
    pygments_css = ""

def get_html_template():
    import importlib.resources
    from pathlib import Path
    try:
        return importlib.resources.files('md_viewer').joinpath('template.html').read_text()
    except (AttributeError, ModuleNotFoundError, ImportError):
        template_path = Path(__file__).parent / 'template.html'
        if template_path.exists():
            return template_path.read_text()
        return "<html><body><h1>Error: template.html not found</h1></body></html>"

HTML_TEMPLATE = get_html_template()
JINJA_TEMPLATE = jinja2.Template(HTML_TEMPLATE)
def is_path_excluded(file_path):
    """Check if a path is excluded by MDVIEW_EXCLUDE_DIRS"""
    try:
        rel_path = file_path.relative_to(DOCS_DIR)
    except ValueError:
        return False
        
    path_parts = [p.lower() for p in rel_path.parts]
    rel_str = rel_path.as_posix().lower()
    
    # Check absolute paths first
    if EXCLUDE_PATHS_ABS:
        file_absolute = file_path.resolve()
        file_abs_str = file_absolute.as_posix().lower()
        for abs_path in EXCLUDE_PATHS_ABS:
            if file_abs_str.startswith(abs_path + '/') or file_abs_str == abs_path:
                return True
                
    # Check simple names or relative paths
    for name in EXCLUDE_NAMES:
        if name in path_parts:
            return True
        elif '/' in name and (rel_str.startswith(name + '/') or rel_str == name):
            return True
            
    return False

# Nav tree cache (rebuilt on first request or admin reload)
_nav_cache = {"html": None, "mtime": 0}

# File type icon SVGs (compact, 16x16)
ICON_FOLDER = '<svg class="icon" viewBox="0 0 16 16" fill="var(--folder-color)"><path d="M1.75 1A1.75 1.75 0 0 0 0 2.75v10.5C0 14.216.784 15 1.75 15h12.5A1.75 1.75 0 0 0 16 13.25v-8.5A1.75 1.75 0 0 0 14.25 3H7.5a.25.25 0 0 1-.2-.1l-.9-1.2C6.07 1.26 5.55 1 5 1H1.75Z"></path></svg>'
ICON_FOLDER_OPEN = '<svg class="icon" viewBox="0 0 16 16" fill="var(--folder-color)"><path d="M.513 1.513A1.75 1.75 0 0 1 1.75 1h3.5c.55 0 1.07.26 1.4.7l.9 1.2a.25.25 0 0 0 .2.1H13a2 2 0 0 1 2 2v.5H2.75A1.75 1.75 0 0 0 1 7.25v5.25L.513 1.513ZM2.75 7a.75.75 0 0 0-.75.75v5.5c0 .414.336.75.75.75h11.5c.355 0 .666-.249.735-.598l1.06-5.293A.75.75 0 0 0 15.309 7H2.75Z"></path></svg>'

FILE_ICONS = {
    '.md': '<svg class="icon" viewBox="0 0 16 16" fill="var(--md-color)"><path d="M14.85 3H1.15C.52 3 0 3.52 0 4.15v7.69C0 12.48.52 13 1.15 13h13.69c.64 0 1.15-.52 1.15-1.15V4.15C16 3.52 15.48 3 14.85 3ZM9 11H7V8L5.5 9.92 4 8v3H2V5h2l1.5 2L7 5h2v6Zm2.99.5L9.5 8H11V5h2v3h1.5l-2.51 3.5Z"></path></svg>',
    '.py': '<svg class="icon" viewBox="0 0 16 16" fill="var(--py-color)"><path d="M2 1.75C2 .784 2.784 0 3.75 0h6.586c.464 0 .909.184 1.237.513l2.914 2.914c.329.328.513.773.513 1.237v9.586A1.75 1.75 0 0 1 13.25 16h-9.5A1.75 1.75 0 0 1 2 14.25Zm1.75-.25a.25.25 0 0 0-.25.25v12.5c0 .138.112.25.25.25h9.5a.25.25 0 0 0 .25-.25V6h-2.75A1.75 1.75 0 0 1 9 4.25V1.5Zm6.75.062V4.25c0 .138.112.25.25.25h2.688Z"></path></svg>',
    '.json': '<svg class="icon" viewBox="0 0 16 16" fill="var(--json-color)"><path d="M2 1.75C2 .784 2.784 0 3.75 0h6.586c.464 0 .909.184 1.237.513l2.914 2.914c.329.328.513.773.513 1.237v9.586A1.75 1.75 0 0 1 13.25 16h-9.5A1.75 1.75 0 0 1 2 14.25Zm1.75-.25a.25.25 0 0 0-.25.25v12.5c0 .138.112.25.25.25h9.5a.25.25 0 0 0 .25-.25V6h-2.75A1.75 1.75 0 0 1 9 4.25V1.5Zm6.75.062V4.25c0 .138.112.25.25.25h2.688Z"></path></svg>',
    '.yaml': '<svg class="icon" viewBox="0 0 16 16" fill="var(--yaml-color)"><path d="M2 1.75C2 .784 2.784 0 3.75 0h6.586c.464 0 .909.184 1.237.513l2.914 2.914c.329.328.513.773.513 1.237v9.586A1.75 1.75 0 0 1 13.25 16h-9.5A1.75 1.75 0 0 1 2 14.25Zm1.75-.25a.25.25 0 0 0-.25.25v12.5c0 .138.112.25.25.25h9.5a.25.25 0 0 0 .25-.25V6h-2.75A1.75 1.75 0 0 1 9 4.25V1.5Zm6.75.062V4.25c0 .138.112.25.25.25h2.688Z"></path></svg>',
    '.yml': '<svg class="icon" viewBox="0 0 16 16" fill="var(--yaml-color)"><path d="M2 1.75C2 .784 2.784 0 3.75 0h6.586c.464 0 .909.184 1.237.513l2.914 2.914c.329.328.513.773.513 1.237v9.586A1.75 1.75 0 0 1 13.25 16h-9.5A1.75 1.75 0 0 1 2 14.25Zm1.75-.25a.25.25 0 0 0-.25.25v12.5c0 .138.112.25.25.25h9.5a.25.25 0 0 0 .25-.25V6h-2.75A1.75 1.75 0 0 1 9 4.25V1.5Zm6.75.062V4.25c0 .138.112.25.25.25h2.688Z"></path></svg>',
    '.sh': '<svg class="icon" viewBox="0 0 16 16" fill="var(--sh-color)"><path d="M2 1.75C2 .784 2.784 0 3.75 0h6.586c.464 0 .909.184 1.237.513l2.914 2.914c.329.328.513.773.513 1.237v9.586A1.75 1.75 0 0 1 13.25 16h-9.5A1.75 1.75 0 0 1 2 14.25Zm1.75-.25a.25.25 0 0 0-.25.25v12.5c0 .138.112.25.25.25h9.5a.25.25 0 0 0 .25-.25V6h-2.75A1.75 1.75 0 0 1 9 4.25V1.5Zm6.75.062V4.25c0 .138.112.25.25.25h2.688Z"></path></svg>',
}
DEFAULT_FILE_ICON = '<svg class="icon" viewBox="0 0 16 16" fill="var(--file-color)"><path d="M2 1.75C2 .784 2.784 0 3.75 0h6.586c.464 0 .909.184 1.237.513l2.914 2.914c.329.328.513.773.513 1.237v9.586A1.75 1.75 0 0 1 13.25 16h-9.5A1.75 1.75 0 0 1 2 14.25Zm1.75-.25a.25.25 0 0 0-.25.25v12.5c0 .138.112.25.25.25h9.5a.25.25 0 0 0 .25-.25V6h-2.75A1.75 1.75 0 0 1 9 4.25V1.5Zm6.75.062V4.25c0 .138.112.25.25.25h2.688Z"></path></svg>'
TOGGLE_ICON = '<svg class="toggle-icon" viewBox="0 0 16 16" fill="currentColor"><path d="M6.22 3.22a.75.75 0 0 1 1.06 0l4.25 4.25a.75.75 0 0 1 0 1.06l-4.25 4.25a.75.75 0 0 1-1.06-1.06L9.94 8 6.22 4.28a.75.75 0 0 1 0-1.06Z"></path></svg>'

def get_file_icon(filename):
    """Return the appropriate SVG icon for a file type"""
    ext = os.path.splitext(filename)[1].lower()
    return FILE_ICONS.get(ext, DEFAULT_FILE_ICON)

class MarkdownHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DOCS_DIR), **kwargs)
    
    def do_GET(self):
        parsed_path = urlparse(self.path)
        path = unquote(parsed_path.path)
        
        # Handle admin page
        if path == '/_admin':
            self.serve_admin_page()
            return
        
        # Handle update check endpoint
        if path == '/_check_update':
            self.handle_update_check(parsed_path.query)
            return
        
        # Default to configured DEFAULT_FILE (usually README.md)
        if path == '/' or path == '/index.html':
            path = '/' + DEFAULT_FILE
        
        # Remove leading slash
        if path.startswith('/'):
            path = path[1:]
        
        file_path = (DOCS_DIR / path).resolve()
        
        # Security: Prevent path traversal attacks
        try:
            file_path.relative_to(DOCS_DIR.resolve())
        except ValueError:
            self.send_error(403, "Access Denied: Path outside of documentation directory")
            return
        
        # If it's a markdown file, render it
        if file_path.suffix == '.md' and file_path.exists():
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            
            # Read markdown content
            with open(file_path, 'r', encoding='utf-8') as f:
                md_content = f.read()
            
            # Pre-process code blocks inside list items
            # Simply remove leading spaces from lines that start ``` (code block markers)
            # This makes indented code blocks work properly
            
            # Normalize line endings
            md_content = md_content.replace('\r\n', '\n').replace('\r', '\n')
            
            lines = md_content.split('\n')
            processed_lines = []
            in_indented_block = False
            indent_to_remove = 0
            
            for i, line in enumerate(lines):
                # Remove trailing whitespace for matching purposes
                line_stripped_right = line.rstrip()
                
                # Check if this line is an indented code block start (spaces before ```)
                # Pattern: 2+ spaces, then ```, optionally followed by language name
                match = re.match(r'^(\s{2,})(```.*)$', line_stripped_right)
                if match and not in_indented_block:
                    # Found indented code block start - remove the indent
                    indent_to_remove = len(match.group(1))
                    code_fence = match.group(2)  # Just the ```language part
                    processed_lines.append(code_fence)
                    in_indented_block = True
                elif in_indented_block:
                    # We're inside an indented code block
                    stripped = line.strip()
                    if stripped == '```':
                        # Found closing ``` - end block
                        processed_lines.append('```')
                        in_indented_block = False
                        indent_to_remove = 0
                    else:
                        # Code content - remove the indent if present
                        if line.startswith(' ' * indent_to_remove):
                            processed_lines.append(line[indent_to_remove:])
                        elif line.strip() == '':
                            processed_lines.append('')
                        else:
                            processed_lines.append(line)
                else:
                    # Normal line - keep as is
                    processed_lines.append(line)
            
            md_content = '\n'.join(processed_lines)
            
            # Pre-process PlantUML code blocks
            # Mark PlantUML blocks with a special class for JavaScript detection
            md_content = re.sub(
                r'```(?:plantuml|puml)\n(.*?)```',
                lambda m: f'```plantuml\n{m.group(1)}```',
                md_content,
                flags=re.DOTALL
            )
            
            # Convert markdown to HTML
            md = markdown.Markdown(
                extensions=[
                    'codehilite',
                    'toc',
                    'tables',
                    'fenced_code',
                ]
            )
            html_content = md.convert(md_content)
            
            # Post-process: Add plantuml class to PlantUML code blocks
            # This helps JavaScript identify them
            html_content = re.sub(
                r'<pre><code class="language-plantuml">',
                r'<pre><code class="language-plantuml plantuml">',
                html_content
            )
            
            # Generate navigation
            nav_items = self.generate_nav(path)
            
            # Generate breadcrumb
            breadcrumb = self.generate_breadcrumb(path)
            
            # Get title
            title_match = re.search(r'^#\s+(.+)$', md_content, re.MULTILINE)
            title = title_match.group(1) if title_match else file_path.stem
            
            html = JINJA_TEMPLATE.render(
                title=title,
                project_name=PROJECT_NAME,
                nav_items=nav_items,
                breadcrumb=breadcrumb,
                content=html_content,
                pygments_style_block=f"<style>\n{pygments_css}\n</style>" if pygments_css else ""
            )
            
            self.wfile.write(html.encode('utf-8'))
        else:
            # Serve other files normally
            super().do_GET()
            
    def list_directory(self, path):
        """Override to filter directory listings with MDVIEW_EXCLUDE_DIRS"""
        import html
        import io
        import urllib.parse
        
        try:
            list_dir = os.listdir(path)
        except OSError:
            self.send_error(404, "No permission to list directory")
            return None
            
        filtered_list = []
        for name in list_dir:
            item_path = Path(path) / name
            if not is_path_excluded(item_path):
                filtered_list.append(name)
                
        list_dir = filtered_list
        list_dir.sort(key=lambda a: a.lower())
        
        r = []
        try:
            displaypath = urllib.parse.unquote(self.path, errors='surrogatepass')
        except AttributeError:
            displaypath = urllib.parse.unquote(self.path)
        displaypath = html.escape(displaypath)
        
        folder_icon = '<svg viewBox="0 0 16 16" width="16" height="16"><path d="M1.75 1A1.75 1.75 0 0 0 0 2.75v10.5C0 14.216.784 15 1.75 15h12.5A1.75 1.75 0 0 0 16 13.25v-8.5A1.75 1.75 0 0 0 14.25 3H7.5a.25.25 0 0 1-.2-.1l-.9-1.2C6.07 1.26 5.55 1 5 1H1.75Z"></path></svg>'
        file_icon = '<svg viewBox="0 0 16 16" width="16" height="16"><path d="M2 1.75C2 .784 2.784 0 3.75 0h6.586c.464 0 .909.184 1.237.513l2.914 2.914c.329.328.513.773.513 1.237v9.586A1.75 1.75 0 0 1 13.25 16h-9.5A1.75 1.75 0 0 1 2 14.25Zm1.75-.25a.25.25 0 0 0-.25.25v12.5c0 .138.112.25.25.25h9.5a.25.25 0 0 0 .25-.25V6h-2.75A1.75 1.75 0 0 1 9 4.25V1.5Zm6.75.062V4.25c0 .138.112.25.25.25h2.688l-.011-.013-2.914-2.914-.013-.011Z"></path></svg>'
        
        html_content = [f'<h1>Directory listing for {displaypath}</h1>', '<div class="dir-list">']
        
        for name in list_dir:
            fullname = os.path.join(path, name)
            displayname = linkname = name
            
            is_dir = os.path.isdir(fullname)
            icon = folder_icon if is_dir else file_icon
            if is_dir:
                displayname = name + "/"
                linkname = name + "/"
                
            try:
                escaped_link = urllib.parse.quote(linkname, errors='surrogatepass')
            except AttributeError:
                escaped_link = urllib.parse.quote(linkname)
                
            html_content.append(f'<a class="dir-item" href="{escaped_link}">{icon}{html.escape(displayname)}</a>')
            
        html_content.append('</div>')
        
        # Generate the sidebar nav
        nav_items = self.generate_nav(displaypath)
        

        html_out = JINJA_TEMPLATE.render(
            title=f"Directory: {displaypath}",
            project_name=PROJECT_NAME,
            nav_items=nav_items,
            breadcrumb=displaypath,
            content="\n".join(html_content),
            pygments_style_block=""
        )
        
        encoded = html_out.encode('utf-8', 'surrogateescape')
        f = io.BytesIO(encoded)
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        return f
    
    def generate_nav(self, current_path):
        """Generate navigation tree with caching for performance"""
        global _nav_cache
        from urllib.parse import quote
        import html as html_mod

        # Build the structural tree once and cache it
        if _nav_cache["html"] is None:
            _nav_cache["html"] = self._build_nav_tree()

        # Inject active states into the cached tree based on current_path
        nav_html = _nav_cache["html"]
        # Reset all active states
        nav_html = nav_html.replace(' active', '')
        nav_html = nav_html.replace(' has-active', '')

        if current_path:
            # Mark active file/folder
            safe_path = current_path.strip('/')
            try:
                escaped = quote(safe_path, errors='surrogatepass')
            except (AttributeError, TypeError):
                escaped = quote(safe_path)

            # Mark exact match active
            nav_html = nav_html.replace(
                f'data-path="{escaped}" class="tree-item"',
                f'data-path="{escaped}" class="tree-item active"'
            )

            # Mark parent folders as has-active
            parts = safe_path.split('/')
            for i in range(len(parts) - 1):
                parent_path = '/'.join(parts[:i+1])
                try:
                    parent_escaped = quote(parent_path, errors='surrogatepass')
                except (AttributeError, TypeError):
                    parent_escaped = quote(parent_path)
                nav_html = nav_html.replace(
                    f'class="folder" data-path="{parent_escaped}"',
                    f'class="folder has-active" data-path="{parent_escaped}"'
                )

        return nav_html

    def _build_nav_tree(self):
        """Build the full nav tree HTML (cached)"""
        from urllib.parse import quote
        import html as html_mod

        def build_tree(dir_path, rel_path="", depth=0, visited=None):
            if visited is None:
                visited = set()

            real_path = os.path.realpath(dir_path)
            if real_path in visited:
                return ""
            visited.add(real_path)

            html_list = [f'<ul class="nav-tree" data-depth="{min(depth, 3)}">']
            try:
                list_dir = os.listdir(dir_path)
            except OSError:
                list_dir = []

            items = []
            for name in list_dir:
                name_lower = name.lower()
                if name_lower in EXCLUDE_NAMES:
                    continue

                full_path_str = os.path.join(dir_path, name).lower()
                is_excluded = False
                for abs_path in EXCLUDE_PATHS_ABS:
                    if full_path_str.startswith(abs_path + '/') or full_path_str == abs_path:
                        is_excluded = True
                        break
                if is_excluded:
                    continue

                item_rel = f"{rel_path}/{name}" if rel_path else name
                item_rel_lower = item_rel.lower()

                for ex_name in EXCLUDE_NAMES:
                    if '/' in ex_name and (item_rel_lower.startswith(ex_name + '/') or item_rel_lower == ex_name):
                        is_excluded = True
                        break
                if is_excluded:
                    continue

                full_path = os.path.join(dir_path, name)
                is_dir = os.path.isdir(full_path)
                items.append((name, is_dir, item_rel, full_path))

            items.sort(key=lambda x: (not x[1], x[0].lower()))

            for name, is_dir, item_rel, full_path in items:
                try:
                    escaped_link = quote(item_rel, errors='surrogatepass')
                except (AttributeError, TypeError):
                    escaped_link = quote(item_rel)
                escaped_name = html_mod.escape(name)

                if is_dir:
                    child_html = build_tree(full_path, item_rel, depth + 1, visited.copy())
                    html_list.append(f'<li class="folder" data-path="{escaped_link}">')
                    html_list.append(f'<div data-path="{escaped_link}" class="tree-item">{TOGGLE_ICON}{ICON_FOLDER}<span class="label">{escaped_name}</span></div>')
                    html_list.append(f'<div class="folder-content">{child_html}</div>')
                    html_list.append('</li>')
                else:
                    icon = get_file_icon(name)
                    html_list.append(f'<li class="file" data-path="{escaped_link}">')
                    html_list.append(f'<a data-path="{escaped_link}" class="tree-item" href="/{escaped_link}">{icon}<span class="label">{escaped_name}</span></a>')
                    html_list.append('</li>')

            html_list.append('</ul>')
            return "\n".join(html_list)

        return build_tree(str(DOCS_DIR))
    
    def format_display_name(self, filename):
        """Format filename for display (e.g., docs/API_REFERENCE.md -> docs / API Reference)"""
        # Split into directory parts and the base filename
        path_parts = filename.split('/')
        base_name = path_parts[-1].replace('.md', '')
        dir_prefix = ""
        
        if len(path_parts) > 1:
            # We have directories in the path
            dirs = " / ".join([p for p in path_parts[:-1]])
            dir_prefix = f"<span style='color: #888; font-size: 0.9em;'>{dirs} / </span>"
        
        # Special case: README stays as is
        if base_name.upper() == 'README':
            formatted_base = 'README'
        else:
            # Split by underscore
            parts = base_name.split('_')
            
            # Check if first part is a short abbreviation (like HLD, LLD, API, etc.)
            first_is_abbrev = len(parts) > 1 and parts[0].isupper() and len(parts[0]) <= 5
            
            formatted_parts = []
            for i, part in enumerate(parts):
                # Keep abbreviations as-is (all caps, short)
                if part.isupper() and len(part) <= 5:
                    formatted_parts.append(part)
                else:
                    # Title case for other parts
                    formatted_parts.append(part.capitalize())
            
            # Join with " - " after abbreviation prefix, space for the rest
            if first_is_abbrev and len(formatted_parts) > 1:
                formatted_base = formatted_parts[0] + ' - ' + ' '.join(formatted_parts[1:])
            else:
                formatted_base = ' '.join(formatted_parts)
                
        return dir_prefix + formatted_base
    
    def get_file_description(self, filename):
        """Get description/title from markdown file"""
        try:
            file_path = DOCS_DIR / filename
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    # Read first few lines to get title
                    first_lines = ''.join([f.readline() for _ in range(5)])
                    # Try to extract from first heading
                    title_match = re.search(r'^#\s+(.+)$', first_lines, re.MULTILINE)
                    if title_match:
                        title = title_match.group(1).strip()
                        # Remove emojis and extra formatting
                        title = re.sub(r'[⭐🏗️🔧📋❓🔍📊📖]', '', title).strip()
                        return title
        except Exception:
            pass
        return filename.replace('.md', '')
    
    def generate_breadcrumb(self, path):
        """Generate breadcrumb navigation with nice styling"""
        import html
        from urllib.parse import quote
        
        breadcrumb_html = ['<div class="breadcrumb">']
        root_name = DOCS_DIR.name
        breadcrumb_html.append(f'<a href="/" class="breadcrumb-item">{html.escape(root_name)}</a>')
        
        if path and path != '/':
            parts = Path(path).parts
            current_rel = ""
            for part in parts:
                breadcrumb_html.append('<svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor"><path d="M6.22 3.22a.75.75 0 0 1 1.06 0l4.25 4.25a.75.75 0 0 1 0 1.06l-4.25 4.25a.75.75 0 0 1-1.06-1.06L9.94 8 6.22 4.28a.75.75 0 0 1 0-1.06Z"></path></svg>')
                
                if current_rel:
                    current_rel += "/" + part
                else:
                    current_rel = part
                    
                escaped_link = quote(current_rel)
                breadcrumb_html.append(f'<a href="/{escaped_link}" class="breadcrumb-item">{html.escape(part)}</a>')
            
        breadcrumb_html.append('</div>')
        return '\n'.join(breadcrumb_html)
    
    def handle_update_check(self, query_string):
        """Handle file modification time check for live reload"""
        import json
        from urllib.parse import parse_qs
        
        try:
            params = parse_qs(query_string)
            filename = params.get('file', ['README.md'])[0]
            
            file_path = DOCS_DIR / filename
            
            if file_path.exists() and file_path.suffix == '.md':
                # Get file modification time
                modified_time = file_path.stat().st_mtime
                
                response = {
                    'modified': str(modified_time),
                    'file': filename
                }
            else:
                response = {
                    'error': 'File not found',
                    'file': filename
                }
        except Exception as e:
            response = {
                'error': str(e)
            }
        
        # Send JSON response
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode('utf-8'))
    
    def do_POST(self):
        """Handle POST requests for admin actions"""
        parsed_path = urlparse(self.path)
        path = unquote(parsed_path.path)
        
        if path == '/_admin/save':
            self.handle_admin_save()
            return
        
        self.send_error(404)
    
    def handle_admin_save(self):
        """Save admin settings and reload config"""
        import json
        global MDVIEW_EXCLUDE_DIRS, EXCLUDE_NAMES, EXCLUDE_PATHS_ABS, _nav_cache
        
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode('utf-8'))
            
            # Update exclusions
            new_excludes = [d.strip() for d in data.get('exclude_dirs', '').split(',') if d.strip()]
            # Always merge with defaults
            default_list = DEFAULT_EXCLUDE.split(',')
            merged = list(set(new_excludes + [d.strip() for d in default_list if d.strip()]))
            
            MDVIEW_EXCLUDE_DIRS = merged
            EXCLUDE_PATHS_ABS.clear()
            EXCLUDE_NAMES.clear()
            for d in MDVIEW_EXCLUDE_DIRS:
                d_lower = d.lower()
                if d.startswith('/') or d.startswith('~'):
                    EXCLUDE_PATHS_ABS.append(Path(os.path.expanduser(d)).resolve().as_posix().lower())
                else:
                    EXCLUDE_NAMES.append(d_lower)
            
            # Invalidate nav cache
            _nav_cache["html"] = None
            
            # Reload template
            global HTML_TEMPLATE, JINJA_TEMPLATE
            HTML_TEMPLATE = get_html_template()
            JINJA_TEMPLATE = jinja2.Template(HTML_TEMPLATE)
            
            response = {'status': 'ok', 'excludes': MDVIEW_EXCLUDE_DIRS}
        except Exception as e:
            response = {'status': 'error', 'message': str(e)}
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode('utf-8'))
    
    def serve_admin_page(self):
        """Serve the admin/settings page"""
        import html as html_mod
        
        exclude_list = ', '.join(sorted(MDVIEW_EXCLUDE_DIRS))
        docs_dir_display = html_mod.escape(str(DOCS_DIR))
        
        admin_html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Settings - {PROJECT_NAME}</title>
    <style>
        :root {{
            --bg-primary: #ffffff; --bg-secondary: #f6f8fa; --text-primary: #24292e;
            --text-muted: #586069; --border-color: #e1e4e8; --accent-color: #0366d6;
            --hover-bg: #e1e4e8; --code-bg: #f6f8fa;
        }}
        @media (prefers-color-scheme: dark) {{
            :root {{
                --bg-primary: #0d1117; --bg-secondary: #161b22; --text-primary: #c9d1d9;
                --text-muted: #8b949e; --border-color: #30363d; --accent-color: #58a6ff;
                --hover-bg: #21262d; --code-bg: #161b22;
            }}
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            color: var(--text-primary); background: var(--bg-primary);
            display: flex; justify-content: center; padding: 40px 20px;
        }}
        .admin-container {{ max-width: 700px; width: 100%; }}
        .admin-header {{
            display: flex; align-items: center; justify-content: space-between;
            margin-bottom: 32px; padding-bottom: 16px; border-bottom: 1px solid var(--border-color);
        }}
        .admin-header h1 {{ font-size: 24px; display: flex; align-items: center; gap: 10px; }}
        .back-link {{
            color: var(--accent-color); text-decoration: none; font-size: 14px;
            display: flex; align-items: center; gap: 4px;
        }}
        .back-link:hover {{ text-decoration: underline; }}
        .section {{
            background: var(--bg-secondary); border: 1px solid var(--border-color);
            border-radius: 8px; padding: 20px; margin-bottom: 20px;
        }}
        .section h2 {{ font-size: 16px; margin-bottom: 12px; }}
        .section p {{ font-size: 13px; color: var(--text-muted); margin-bottom: 12px; }}
        .field {{ margin-bottom: 16px; }}
        .field label {{ display: block; font-size: 13px; font-weight: 600; margin-bottom: 6px; }}
        .field input, .field textarea {{
            width: 100%; padding: 8px 12px; border: 1px solid var(--border-color);
            border-radius: 6px; background: var(--bg-primary); color: var(--text-primary);
            font-family: 'SFMono-Regular', Consolas, monospace; font-size: 13px; outline: none;
        }}
        .field input:focus, .field textarea:focus {{
            border-color: var(--accent-color); box-shadow: 0 0 0 3px rgba(3,102,214,0.2);
        }}
        .field textarea {{ resize: vertical; min-height: 80px; }}
        .info-row {{
            display: flex; justify-content: space-between; padding: 8px 0;
            border-bottom: 1px solid var(--border-color); font-size: 13px;
        }}
        .info-row:last-child {{ border-bottom: none; }}
        .info-label {{ color: var(--text-muted); }}
        .info-value {{ font-family: monospace; }}
        .btn {{
            display: inline-flex; align-items: center; gap: 6px; padding: 8px 16px;
            border: 1px solid var(--border-color); border-radius: 6px;
            background: var(--accent-color); color: white; cursor: pointer;
            font-size: 14px; font-weight: 500; transition: all 0.15s;
        }}
        .btn:hover {{ opacity: 0.9; }}
        .btn-secondary {{ background: var(--bg-primary); color: var(--text-primary); }}
        .btn-secondary:hover {{ background: var(--hover-bg); }}
        .btn-group {{ display: flex; gap: 8px; margin-top: 16px; }}
        .toast {{
            position: fixed; bottom: 20px; right: 20px; padding: 12px 20px;
            background: #2ea043; color: white; border-radius: 8px; font-size: 14px;
            opacity: 0; transition: opacity 0.3s; pointer-events: none;
        }}
        .toast.visible {{ opacity: 1; }}
        .toast.error {{ background: #da3633; }}
    </style>
</head>
<body>
    <div class="admin-container">
        <div class="admin-header">
            <h1>⚙️ Settings</h1>
            <a href="/" class="back-link">← Back to docs</a>
        </div>

        <div class="section">
            <h2>Server Info</h2>
            <div class="info-row">
                <span class="info-label">Serving Directory</span>
                <span class="info-value">{docs_dir_display}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Port</span>
                <span class="info-value">{PORT}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Default File</span>
                <span class="info-value">{DEFAULT_FILE}</span>
            </div>
        </div>

        <div class="section">
            <h2>Exclusions</h2>
            <p>Comma-separated list of directory/file names to exclude from navigation. Changes are applied immediately.</p>
            <div class="field">
                <label for="exclude-dirs">Excluded Directories</label>
                <textarea id="exclude-dirs" rows="3">{exclude_list}</textarea>
            </div>
            <div class="btn-group">
                <button class="btn" id="btn-save" onclick="saveSettings()">Save &amp; Reload</button>
                <button class="btn btn-secondary" id="btn-reset" onclick="resetDefaults()">Reset to Defaults</button>
            </div>
        </div>

        <div class="section">
            <h2>Actions</h2>
            <p>Refresh the nav tree cache without restarting the server.</p>
            <div class="btn-group">
                <button class="btn btn-secondary" onclick="reloadCache()">🔄 Rebuild Nav Cache</button>
            </div>
        </div>
    </div>

    <div class="toast" id="toast"></div>

    <script>
        function showToast(msg, isError) {{
            const t = document.getElementById('toast');
            t.textContent = msg;
            t.className = 'toast visible' + (isError ? ' error' : '');
            setTimeout(() => t.className = 'toast', 3000);
        }}

        function saveSettings() {{
            const excludes = document.getElementById('exclude-dirs').value;
            fetch('/_admin/save', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ exclude_dirs: excludes }})
            }})
            .then(r => r.json())
            .then(data => {{
                if (data.status === 'ok') {{
                    showToast('✅ Settings saved! Nav cache rebuilt.');
                }} else {{
                    showToast('❌ ' + data.message, true);
                }}
            }})
            .catch(e => showToast('❌ Failed: ' + e.message, true));
        }}

        function resetDefaults() {{
            document.getElementById('exclude-dirs').value = '{DEFAULT_EXCLUDE}';
            showToast('Reset to defaults. Click Save to apply.');
        }}

        function reloadCache() {{
            fetch('/_admin/save', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ exclude_dirs: document.getElementById('exclude-dirs').value }})
            }})
            .then(r => r.json())
            .then(data => {{
                if (data.status === 'ok') showToast('✅ Nav cache rebuilt!');
                else showToast('❌ ' + data.message, true);
            }})
            .catch(e => showToast('❌ Failed: ' + e.message, true));
        }}
    </script>
</body>
</html>'''
        
        encoded = admin_html.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)
    
    def log_message(self, format, *args):
        """Suppress default logging"""
        pass

def find_available_port(start_port=8000, max_attempts=10):
    """Find an available port starting from start_port"""
    import socket
    for i in range(max_attempts):
        port = start_port + i
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', port))
                return port
        except OSError:
            continue
    return None

def get_port_process_info(port):
    """Get information about the process using the port"""
    import subprocess
    try:
        # Get process ID
        result = subprocess.run(
            ['lsof', '-ti', f':{port}'],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0 and result.stdout.strip():
            pid = result.stdout.strip().split('\n')[0]
            
            # Get process details
            ps_result = subprocess.run(
                ['ps', '-p', pid, '-o', 'pid,comm,args'],
                capture_output=True,
                text=True,
                timeout=2
            )
            if ps_result.returncode == 0:
                lines = ps_result.stdout.strip().split('\n')
                if len(lines) > 1:
                    return {
                        'pid': pid,
                        'info': lines[1] if len(lines) > 1 else 'Unknown process'
                    }
            return {'pid': pid, 'info': f'Process {pid}'}
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        pass
    return None

def kill_port_process(port):
    """Kill the process using the specified port"""
    import subprocess
    killed_any = False
    
    try:
        # Get all PIDs using the port
        result = subprocess.run(
            ['lsof', '-ti', f':{port}'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            pids = result.stdout.strip().split('\n')
            for pid in pids:
                pid = pid.strip()
                if pid:
                    try:
                        kill_result = subprocess.run(
                            ['kill', '-9', pid],
                            capture_output=True,
                            text=True,
                            timeout=2
                        )
                        if kill_result.returncode == 0:
                            killed_any = True
                    except Exception:
                        continue
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        pass
    
    # Fallback: try fuser (alternative to lsof on some systems)
    if not killed_any:
        try:
            result = subprocess.run(
                ['fuser', '-k', f'{port}/tcp'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                killed_any = True
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
            pass
    
    return killed_any

def handle_port_conflict(requested_port):
    """Handle port conflict with user interaction"""
    import socket
    
    # Check if port is in use
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', requested_port))
            return requested_port  # Port is available
    except OSError:
        pass  # Port is in use, continue to conflict handling
    
    # Port is in use, get process info
    print(f"\n⚠️  Port {requested_port} is already in use.\n")
    
    process_info = get_port_process_info(requested_port)
    if process_info:
        print("📋 Process using the port:")
        print(f"   PID: {process_info['pid']}")
        print(f"   Info: {process_info['info']}")
        print()
        kill_command = f"lsof -ti:{requested_port} | xargs kill -9"
        print(f"💡 Kill command: {kill_command}")
    else:
        print("   (Could not retrieve process information)")
        kill_command = f"lsof -ti:{requested_port} | xargs kill -9"
        print(f"💡 Kill command: {kill_command}")
    
    print("\n📌 Options:")
    print("   1. Kill the process and use port", requested_port)
    print("   2. Use an alternate port (auto-detect)")
    print("   3. Exit")
    
    # Check if running in interactive terminal
    if not os.isatty(0):
        # Non-interactive mode, use alternate port
        print("\n⚠️  Non-interactive mode detected. Using alternate port...")
        alt_port = find_available_port(requested_port + 1)
        if alt_port:
            return alt_port
        return None
    
    # Interactive mode
    while True:
        try:
            choice = input("\n👉 Your choice (1/2/3): ").strip()
            
            if choice == '1':
                # Kill process - try even if we don't have detailed process info
                if process_info:
                    print(f"\n🔄 Killing process {process_info['pid']}...")
                else:
                    print(f"\n🔄 Attempting to kill process on port {requested_port}...")
                
                if kill_port_process(requested_port):
                    print("✅ Process killed successfully")
                    # Wait a moment for port to be released
                    import time
                    time.sleep(0.5)
                    # Verify port is now available
                    try:
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                            s.bind(('127.0.0.1', requested_port))
                            return requested_port
                    except OSError:
                        print("⚠️  Port still in use. Trying alternate port...")
                        alt_port = find_available_port(requested_port + 1)
                        if alt_port:
                            return alt_port
                        return None
                else:
                    # Try a more aggressive approach using shell
                    print("⚠️  Standard kill failed. Trying shell command...")
                    import subprocess
                    try:
                        # Use shell=True for pipe support
                        result = subprocess.run(
                            f"lsof -ti:{requested_port} | xargs kill -9 2>/dev/null",
                            shell=True,
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        import time
                        time.sleep(0.5)
                        # Check if port is now free
                        try:
                            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                                s.bind(('127.0.0.1', requested_port))
                                print("✅ Port is now available")
                                return requested_port
                        except OSError:
                            pass
                    except Exception:
                        pass
                    
                    print("❌ Failed to kill process. Trying alternate port...")
                    alt_port = find_available_port(requested_port + 1)
                    if alt_port:
                        return alt_port
                    return None
            
            elif choice == '2':
                # Use alternate port
                print(f"\n🔍 Looking for an available port...")
                alt_port = find_available_port(requested_port + 1)
                if alt_port:
                    print(f"✅ Found available port: {alt_port}")
                    return alt_port
                else:
                    print("❌ Could not find an available port")
                    return None
            
            elif choice == '3':
                # Exit
                print("\n👋 Exiting...")
                return None
            
            else:
                print("❌ Invalid choice. Please enter 1, 2, or 3.")
        
        except (EOFError, KeyboardInterrupt):
            print("\n\n👋 Exiting...")
            return None

def main():
    global PORT
    
    os.chdir(DOCS_DIR)
    
    # Handle port conflict with user interaction
    final_port = handle_port_conflict(PORT)
    if final_port is None:
        print("\n❌ Could not start server. Exiting.")
        return
    
    PORT = final_port
    
    try:
        with socketserver.TCPServer(("127.0.0.1", PORT), MarkdownHandler) as httpd:
            # Calculate port padding for alignment
            port_str = str(PORT)
            port_padding = ' ' * (4 - len(port_str))
            
            # Format excluded dirs for display
            exclude_display = ', '.join(sorted(MDVIEW_EXCLUDE_DIRS)[:5])
            if len(MDVIEW_EXCLUDE_DIRS) > 5:
                exclude_display += f' (+{len(MDVIEW_EXCLUDE_DIRS) - 5} more)'
            if not MDVIEW_EXCLUDE_DIRS:
                exclude_display = '(none)'
            
            print(f"""
╔══════════════════════════════════════════════════════════════╗
║     Markdown Documentation Viewer                            ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  📁 Serving: {str(DOCS_DIR)[-42:]:<42}      ║
║  🚫 Excluding: {exclude_display[:40]:<40}      ║
║                                                              ║
║  🌐 Open in browser:                                         ║
║     http://localhost:{PORT}{port_padding}                                    ║
║                                                              ║
║  📝 Default page: README.md                                  ║
║                                                              ║
║  ✨ Features:                                                ║
║     • Live reload on file changes                            ║
║     • PlantUML diagram rendering                             ║
║     • Syntax highlighting                                    ║
║                                                              ║
║  Press Ctrl+C to stop the server                             ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
            """)
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("\n\n👋 Server stopped. Goodbye!")
    except OSError as e:
        print(f"\n❌ Error: {e}")
        print(f"💡 Try using a different port: PORT=8001 python3 {Path(__file__).name}")

if __name__ == '__main__':
    main()

