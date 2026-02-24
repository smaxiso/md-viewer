#!/usr/bin/env python3
"""
Local Markdown Documentation Viewer
Serves markdown files as rendered HTML with navigation

Usage:
    python3 view-docs.py [directory]    # Serve specified directory
    python3 view-docs.py                # Serve current directory
    ./view-docs.py                      # If executable
    
    PORT=8001 python3 view-docs.py      # Use custom port

Then open: http://localhost:8000
"""

import http.server
import socketserver
import os
import re
import sys
from urllib.parse import unquote, urlparse
from pathlib import Path

try:
    import markdown
    from markdown.extensions import codehilite, toc, tables
except ImportError:
    print("📦 Installing required packages (markdown, pygments)...")
    import subprocess
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "markdown", "pygments"])
        import markdown
        from markdown.extensions import codehilite, toc, tables
        print("✅ Packages installed successfully\n")
    except subprocess.CalledProcessError:
        print("❌ Error: Failed to install required packages")
        print("💡 Please install manually: pip install markdown pygments")
        sys.exit(1)

# Handle --help
if len(sys.argv) > 1 and sys.argv[1] in ['-h', '--help']:
    print(__doc__)
    print("""
Arguments:
    [directory]     Directory containing markdown files
                    Default: script's directory (if it has .md files), otherwise current directory

Environment Variables:
    PORT            Server port (default: 8000)
    EXCLUDE_DIRS    Comma-separated list of directories to exclude from navigation
                    (default: archive,node_modules,.git,__pycache__,venv,.venv,dist,build)
                    Set to empty string to include all directories

Examples:
    # Run from anywhere - serves script's directory
    python3 /path/to/view-docs.py
    
    # Run with explicit directory
    python3 view-docs.py ./docs
    python3 view-docs.py /path/to/docs
    
    # Custom port
    PORT=3000 python3 view-docs.py
    
    # Include all directories (no exclusions)
    EXCLUDE_DIRS="" python3 view-docs.py
    
    # Custom exclusions
    EXCLUDE_DIRS="drafts,old,archive" python3 view-docs.py
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
elif list(SCRIPT_DIR.glob('*.md')):
    # Script's directory has .md files - use it (most common case)
    DOCS_DIR = SCRIPT_DIR
else:
    # Fallback to current directory
    DOCS_DIR = Path.cwd()

# Validate directory exists
if not DOCS_DIR.exists():
    print(f"❌ Error: Directory does not exist: {DOCS_DIR}")
    sys.exit(1)

if not DOCS_DIR.is_dir():
    print(f"❌ Error: Path is not a directory: {DOCS_DIR}")
    sys.exit(1)

# Check if directory has markdown files
md_files_in_dir = list(DOCS_DIR.glob('*.md'))
if not md_files_in_dir:
    print(f"⚠️  Warning: No markdown files found in {DOCS_DIR}")
    print(f"   The directory listing will be shown instead.")
    print(f"   💡 Tip: Specify a directory with .md files: python3 {Path(__file__).name} /path/to/docs")
    print()

# Get project name from directory for display
PROJECT_NAME = DOCS_DIR.name.replace('_', ' ').replace('-', ' ').title()

# Directories to exclude from navigation (comma-separated via env var, or default)
# Default excludes common non-doc directories
DEFAULT_EXCLUDE = 'archive,node_modules,.git,__pycache__,venv,.venv,dist,build'
EXCLUDE_DIRS = set(
    d.strip().lower() 
    for d in os.environ.get('EXCLUDE_DIRS', DEFAULT_EXCLUDE).split(',')
    if d.strip()
)

# HTML template with navigation sidebar
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - {project_name} Docs</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #24292e;
            background: #fff;
            display: flex;
        }}
        .sidebar {{
            width: 280px;
            background: #f6f8fa;
            border-right: 1px solid #e1e4e8;
            padding: 20px;
            position: fixed;
            height: 100vh;
            overflow-y: auto;
            font-size: 14px;
        }}
        .sidebar h2 {{
            font-size: 16px;
            margin-bottom: 15px;
            color: #0366d6;
            border-bottom: 1px solid #e1e4e8;
            padding-bottom: 10px;
            font-weight: 600;
        }}
        .sidebar ul {{
            list-style: none;
        }}
        .sidebar li {{
            margin: 5px 0;
        }}
        .sidebar a {{
            color: #586069;
            text-decoration: none;
            display: block;
            padding: 5px 10px;
            border-radius: 3px;
            transition: background 0.2s;
        }}
        .sidebar a:hover {{
            background: #e1e4e8;
            color: #0366d6;
        }}
        .sidebar a.active {{
            background: #0366d6;
            color: white;
            font-weight: 500;
        }}
        .content {{
            margin-left: 280px;
            padding: 40px;
            max-width: 900px;
            flex: 1;
        }}
        .content h1 {{
            font-size: 32px;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 1px solid #e1e4e8;
        }}
        .content h2 {{
            font-size: 24px;
            margin-top: 30px;
            margin-bottom: 15px;
            padding-top: 20px;
            border-top: 1px solid #e1e4e8;
        }}
        .content h3 {{
            font-size: 20px;
            margin-top: 25px;
            margin-bottom: 10px;
        }}
        .content h4 {{
            font-size: 16px;
            margin-top: 20px;
            margin-bottom: 10px;
        }}
        .content code {{
            background: #f6f8fa;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
            font-size: 85%;
        }}
        .content pre {{
            background: #f6f8fa;
            padding: 16px;
            border-radius: 6px;
            overflow-x: auto;
            margin: 16px 0;
        }}
        .content pre code {{
            background: none;
            padding: 0;
        }}
        .content table {{
            border-collapse: collapse;
            width: 100%;
            margin: 16px 0;
        }}
        .content table th,
        .content table td {{
            border: 1px solid #dfe2e5;
            padding: 8px 12px;
            text-align: left;
        }}
        .content table th {{
            background: #f6f8fa;
            font-weight: 600;
        }}
        .content blockquote {{
            border-left: 4px solid #dfe2e5;
            padding-left: 16px;
            margin: 16px 0;
            color: #6a737d;
        }}
        .content a {{
            color: #0366d6;
            text-decoration: none;
        }}
        .content a:hover {{
            text-decoration: underline;
        }}
        .content ul, .content ol {{
            margin: 16px 0;
            padding-left: 30px;
        }}
        .content li {{
            margin: 8px 0;
        }}
        .content hr {{
            border: none;
            border-top: 1px solid #e1e4e8;
            margin: 24px 0;
        }}
        .breadcrumb {{
            margin-bottom: 20px;
            font-size: 14px;
            color: #586069;
        }}
        .breadcrumb a {{
            color: #0366d6;
            text-decoration: none;
        }}
        .breadcrumb a:hover {{
            text-decoration: underline;
        }}
        .plantuml-container {{
            background: #fff;
            border: 1px solid #e1e4e8;
            border-radius: 6px;
            padding: 20px;
            margin: 20px 0;
            text-align: center;
            overflow-x: auto;
            position: relative;
        }}
        .plantuml-container img {{
            max-width: 100%;
            height: auto;
            display: block;
            margin: 0 auto;
            cursor: zoom-in;
            transition: opacity 0.2s;
        }}
        .plantuml-container img:hover {{
            opacity: 0.9;
        }}
        .plantuml-container::after {{
            content: "Click to view full screen";
            position: absolute;
            bottom: 5px;
            right: 10px;
            font-size: 11px;
            color: #586069;
            background: rgba(255, 255, 255, 0.9);
            padding: 2px 6px;
            border-radius: 3px;
            pointer-events: none;
        }}
        .plantuml-loading {{
            color: #586069;
            font-style: italic;
            padding: 40px;
        }}
        .plantuml-error {{
            color: #d73a49;
            padding: 20px;
            background: #fff5f5;
            border: 1px solid #fdb8c0;
            border-radius: 6px;
        }}
        .live-reload-indicator {{
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: #28a745;
            color: white;
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 12px;
            z-index: 1000;
            display: none;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        }}
        .live-reload-indicator.reloading {{
            background: #ffc107;
            color: #000;
        }}
        .live-reload-indicator.visible {{
            display: block;
        }}
        @media (max-width: 768px) {{
            .sidebar {{
                width: 100%;
                height: auto;
                position: relative;
            }}
            .content {{
                margin-left: 0;
            }}
        }}
    </style>
    <script src="https://cdn.jsdelivr.net/npm/plantuml-encoder@1.4.0/dist/plantuml-encoder.min.js"></script>
    <script>
        function renderPlantUML() {{
            // Find all code blocks
            const codeBlocks = document.querySelectorAll('pre code');
            codeBlocks.forEach(function(block) {{
                const codeText = block.textContent.trim();
                
                // Check if it's PlantUML: has plantuml class OR starts with @startuml
                const hasPlantUMLClass = block.className && 
                    (block.className.includes('plantuml') || block.className.includes('puml'));
                const startsWithStartUML = codeText.startsWith('@startuml');
                
                if (hasPlantUMLClass || startsWithStartUML) {{
                    // Create container for diagram
                    const container = document.createElement('div');
                    container.className = 'plantuml-container';
                    container.innerHTML = '<div class="plantuml-loading">Loading diagram...</div>';
                    
                    // Replace code block with container
                    const pre = block.parentElement;
                    pre.parentElement.replaceChild(container, pre);
                    
                    try {{
                        // Encode PlantUML code
                        const encoded = plantumlEncoder.encode(codeText);
                        const diagramUrl = 'https://www.plantuml.com/plantuml/svg/' + encoded;
                        
                        // Use PlantUML server to render (SVG format)
                        const img = document.createElement('img');
                        img.src = diagramUrl;
                        img.alt = 'PlantUML Diagram';
                        img.style.maxWidth = '100%';
                        img.style.height = 'auto';
                        
                        // Make image clickable to open in new tab
                        img.onclick = function() {{
                            window.open(diagramUrl, '_blank');
                        }};
                        
                        img.onerror = function() {{
                            container.innerHTML = '<div class="plantuml-error">Error loading diagram. Please check PlantUML syntax or try again later.</div>';
                        }};
                        
                        img.onload = function() {{
                            container.innerHTML = '';
                            container.appendChild(img);
                            
                            // Add title attribute for tooltip
                            img.title = 'Click to open in new tab';
                        }};
                    }} catch (e) {{
                        container.innerHTML = '<div class="plantuml-error">Error encoding PlantUML: ' + e.message + '</div>';
                    }}
                }}
            }});
        }}
        
        // Render PlantUML when page loads
        document.addEventListener('DOMContentLoaded', renderPlantUML);
        
        // Live reload functionality
        (function() {{
            const currentFile = window.location.pathname.replace('/', '') || 'README.md';
            let lastModified = null;
            let checkInterval = null;
            const indicator = document.createElement('div');
            indicator.className = 'live-reload-indicator';
            indicator.textContent = '🔄 Checking for updates...';
            document.body.appendChild(indicator);
            
            function checkForUpdates() {{
                fetch('/_check_update?file=' + encodeURIComponent(currentFile))
                    .then(response => response.json())
                    .then(data => {{
                        if (data.error) {{
                            console.error('Update check failed:', data.error);
                            return;
                        }}
                        
                        if (lastModified === null) {{
                            // First check - just store the timestamp
                            lastModified = data.modified;
                            return;
                        }}
                        
                        if (data.modified !== lastModified) {{
                            // File has changed!
                            indicator.className = 'live-reload-indicator visible reloading';
                            indicator.textContent = '🔄 Reloading...';
                            
                            // Wait a moment for file to be fully saved, then reload
                            setTimeout(() => {{
                                window.location.reload();
                            }}, 300);
                        }}
                    }})
                    .catch(error => {{
                        console.error('Update check error:', error);
                    }});
            }}
            
            // Start checking every 2 seconds
            checkInterval = setInterval(checkForUpdates, 2000);
            
            // Show indicator briefly on first load
            indicator.className = 'live-reload-indicator visible';
            setTimeout(() => {{
                if (!indicator.classList.contains('reloading')) {{
                    indicator.className = 'live-reload-indicator';
                }}
            }}, 2000);
            
            // Clean up on page unload
            window.addEventListener('beforeunload', () => {{
                if (checkInterval) {{
                    clearInterval(checkInterval);
                }}
            }});
        }})();
    </script>
</head>
<body>
    <div class="sidebar">
        <h2>{project_name}</h2>
        <ul>
            {nav_items}
        </ul>
    </div>
    <div class="content">
        <div class="breadcrumb">
            <a href="/">Home</a> / {breadcrumb}
        </div>
        {content}
    </div>
</body>
</html>
"""

class MarkdownHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DOCS_DIR), **kwargs)
    
    def do_GET(self):
        parsed_path = urlparse(self.path)
        path = unquote(parsed_path.path)
        
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
        
        file_path = DOCS_DIR / path
        
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
            
            # Render template
            html = HTML_TEMPLATE.format(
                title=title,
                project_name=PROJECT_NAME,
                nav_items=nav_items,
                breadcrumb=breadcrumb,
                content=html_content
            )
            
            self.wfile.write(html.encode('utf-8'))
        else:
            # Serve other files normally
            super().do_GET()
    
    def generate_nav(self, current_path):
        """Generate navigation sidebar dynamically from directory"""
        nav_html = []
        
        # Get all .md files in the directory (excluding configured directories)
        md_files = []
        for file_path in DOCS_DIR.glob('*.md'):
            # Check if any parent directory is in the exclude list
            path_parts = [p.lower() for p in file_path.parts]
            if not any(excluded in path_parts for excluded in EXCLUDE_DIRS):
                md_files.append(file_path.name)
        
        # Sort files: README.md first, then alphabetically
        def sort_key(filename):
            if filename == 'README.md':
                return (0, filename)
            return (1, filename)
        
        md_files.sort(key=sort_key)
        
        # Generate navigation items
        for doc_file in md_files:
            # Create display name (remove .md, format nicely)
            display_name = self.format_display_name(doc_file)
            
            # Try to extract title from file for tooltip
            description = self.get_file_description(doc_file)
            
            is_active = 'active' if doc_file == current_path else ''
            nav_html.append(
                f'<li><a href="/{doc_file}" class="{is_active}" title="{description}">{display_name}</a></li>'
            )
        
        return '\n'.join(nav_html)
    
    def format_display_name(self, filename):
        """Format filename for display (e.g., HLD_HIGH_LEVEL_DESIGN.md -> HLD - High Level Design)"""
        name = filename.replace('.md', '')
        
        # Special case: README stays as is
        if name.upper() == 'README':
            return 'README'
        
        # Split by underscore
        parts = name.split('_')
        
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
            return formatted_parts[0] + ' - ' + ' '.join(formatted_parts[1:])
        else:
            return ' '.join(formatted_parts)
    
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
        """Generate breadcrumb navigation"""
        if path == 'README.md':
            return 'README.md'
        return f'<a href="/{path}">{path}</a>'
    
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
                s.bind(('', port))
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
    
    # Check if port is available
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', requested_port))
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
                            s.bind(('', requested_port))
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
                                s.bind(('', requested_port))
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
        with socketserver.TCPServer(("", PORT), MarkdownHandler) as httpd:
            # Calculate port padding for alignment
            port_str = str(PORT)
            port_padding = ' ' * (4 - len(port_str))
            
            # Format excluded dirs for display
            exclude_display = ', '.join(sorted(EXCLUDE_DIRS)[:5])
            if len(EXCLUDE_DIRS) > 5:
                exclude_display += f' (+{len(EXCLUDE_DIRS) - 5} more)'
            if not EXCLUDE_DIRS:
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

