import os
from pathlib import Path

class Config:
    def __init__(self):
        self.port = int(os.environ.get('PORT', 8000))
        self.default_file = 'README.md'
        self.docs_dir = Path.cwd()
        self.project_name = self.docs_dir.name.replace('_', ' ').replace('-', ' ').title()
        
        self.default_exclude = 'archive,node_modules,.git,__pycache__,venv,.venv,dist,build'
        self.exclude_dirs = []
        self.exclude_paths_abs = []
        self.exclude_names = []
        
        self.reload_excludes(os.environ.get('MDVIEW_EXCLUDE_DIRS', ''))
    
    def set_target(self, target_path: str):
        target = Path(target_path).resolve()
        if target.is_file():
            self.docs_dir = target.parent
            self.default_file = target.name
        else:
            self.docs_dir = target
            
        if not self.docs_dir.exists():
            raise FileNotFoundError(f"Directory does not exist: {self.docs_dir}")
        if not self.docs_dir.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {self.docs_dir}")
            
        self.project_name = self.docs_dir.name.replace('_', ' ').replace('-', ' ').title()

    def reload_excludes(self, exclude_str: str):
        raw_dirs = exclude_str.split(',') + self.default_exclude.split(',') if exclude_str else self.default_exclude.split(',')
        self.exclude_dirs = list(set([d.strip() for d in raw_dirs if d.strip()]))
        
        self.exclude_paths_abs.clear()
        self.exclude_names.clear()
        for d in self.exclude_dirs:
            d_lower = d.lower()
            if d.startswith('/') or d.startswith('~'):
                self.exclude_paths_abs.append(Path(os.path.expanduser(d)).resolve().as_posix().lower())
            else:
                self.exclude_names.append(d_lower)
                
    def is_path_excluded(self, file_path: Path) -> bool:
        try:
            rel_path = file_path.relative_to(self.docs_dir)
        except ValueError:
            return False
            
        path_parts = [p.lower() for p in rel_path.parts]
        rel_str = rel_path.as_posix().lower()
        
        if self.exclude_paths_abs:
            file_abs_str = file_path.resolve().as_posix().lower()
            docs_dir_str = self.docs_dir.resolve().as_posix().lower()
            for abs_path in self.exclude_paths_abs:
                if docs_dir_str.startswith(abs_path + '/') or docs_dir_str == abs_path:
                    continue
                if file_abs_str.startswith(abs_path + '/') or file_abs_str == abs_path:
                    return True
                    
        for name in self.exclude_names:
            if name in path_parts:
                return True
            elif '/' in name and (rel_str.startswith(name + '/') or rel_str == name):
                return True
                
        return False

# Global configuration instance
cfg = Config()
