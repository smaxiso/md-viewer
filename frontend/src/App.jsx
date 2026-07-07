import { useState, useEffect, useMemo, useRef } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import mermaid from 'mermaid'
import Editor from 'react-simple-code-editor'
import Prism from 'prismjs'
import 'prismjs/components/prism-markdown'
import 'prismjs/themes/prism-dark.css'
import './App.css'

const CodeEditor = Editor.default || Editor

function App() {
  const searchParams = new URLSearchParams(window.location.search)
  const [navItems, setNavItems] = useState([])
  const [currentFile, setCurrentFile] = useState(searchParams.get('path') || null)
  const [fileData, setFileData] = useState(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState([])
  
  // mode: 'rendered' | 'raw' | 'edit'
  const [mode, setMode] = useState(searchParams.get('mode') || 'rendered')
  const [editContent, setEditContent] = useState('')
  
  const [expandedFolders, setExpandedFolders] = useState(new Set())
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const parentRef = useRef()

  // Settings Modal State
  const [view, setView] = useState(searchParams.get('view') || 'document') // 'document' | 'settings'
  const [excludeDirs, setExcludeDirs] = useState('')

  useEffect(() => {
    const handlePopState = () => {
      const params = new URLSearchParams(window.location.search)
      setCurrentFile(params.get('path') || null)
      setMode(params.get('mode') || 'rendered')
      setView(params.get('view') || 'document')
    }
    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  useEffect(() => {
    const params = new URLSearchParams()
    if (currentFile) params.set('path', currentFile)
    if (mode !== 'rendered') params.set('mode', mode)
    if (view !== 'document') params.set('view', view)
    
    const newSearch = params.toString() ? `?${params.toString()}` : ''
    if (window.location.search !== newSearch) {
      window.history.pushState(null, '', `${window.location.pathname}${newSearch}`)
    }
  }, [currentFile, mode, view])

  useEffect(() => {
    mermaid.initialize({ startOnLoad: false, theme: 'dark' })
  }, [])

  const currentFileRef = useRef(currentFile)
  useEffect(() => {
    currentFileRef.current = currentFile
  }, [currentFile])

  useEffect(() => {
    fetch('/api/nav')
      .then(res => res.json())
      .then(data => setNavItems(data))
      
    const evtSource = new EventSource("/api/events")
    evtSource.onmessage = (event) => {
      const data = JSON.parse(event.data)
      if (data.type === 'file_change') {
        fetch('/api/nav').then(res => res.json()).then(data => setNavItems(data))
        const cFile = currentFileRef.current
        if (cFile && data.path.replace(/\\/g, '/').endsWith(cFile)) {
          fetch(`/api/file?path=${encodeURIComponent(cFile)}`)
            .then(res => {
              if (!res.ok) throw new Error("Not Found")
              return res.json()
            })
            .then(file => {
              setFileData(file)
              setEditContent(file.raw)
            })
            .catch(() => {})
        }
      }
    }
    return () => evtSource.close()
  }, [])
  const handleOpenSettings = async () => {
    const res = await fetch('/api/config')
    const data = await res.json()
    setExcludeDirs(data.exclude_dirs)
    setView('settings')
  }

  const handleSaveSettings = async () => {
    await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ exclude_dirs: excludeDirs })
    })
    setView('document')
    fetch('/api/nav').then(res => res.json()).then(data => setNavItems(data))
  }

  useEffect(() => {
    if (currentFile) {
      fetch(`/api/file?path=${encodeURIComponent(currentFile)}`)
        .then(res => {
          if (!res.ok) throw new Error("Not Found")
          return res.json()
        })
        .then(data => {
          setFileData(data)
          setEditContent(data.raw)
          setMode('rendered')
          setView('document')
        })
        .catch(() => {
          setFileData({title: 'Not Found', html: '<h1>File Not Found</h1><p>The requested file could not be found.</p>'})
          setView('document')
        })
    } else {
        fetch(`/api/file`)
        .then(res => {
          if (!res.ok) throw new Error("Not Found")
          return res.json()
        })
        .then(data => {
          setFileData(data)
          setEditContent(data.raw)
          setView('document')
        }).catch(() => {
          setFileData({title: 'Welcome', html: '<h1>Welcome to MdViewer</h1><p>Select a file from the sidebar</p>'})
          setView('document')
        })
    }
  }, [currentFile])

  useEffect(() => {
    if (mode === 'rendered' && fileData?.html && view === 'document') {
      setTimeout(() => {
        try {
          mermaid.run({ querySelector: '.mermaid' })
        } catch (e) {
          console.error("Mermaid error", e)
        }
      }, 0)
    }
  }, [fileData?.html, mode, view])

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedQuery(searchQuery)
    }, 300)
    return () => clearTimeout(handler)
  }, [searchQuery])

  useEffect(() => {
    if (debouncedQuery.length > 2) {
      fetch(`/api/search?q=${encodeURIComponent(debouncedQuery)}`)
        .then(res => res.json())
        .then(data => setSearchResults(data.results))
    } else {
      setSearchResults([])
    }
  }, [debouncedQuery])

  const handleSave = async () => {
    const res = await fetch('/api/file', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: currentFile || 'README.md', content: editContent })
    })
    if (res.ok) {
      setMode('rendered')
      setFileData({...fileData, html: '<p>Loading...</p>'})
      fetch(`/api/file?path=${encodeURIComponent(currentFile || 'README.md')}`)
        .then(res => res.json())
        .then(data => setFileData(data))
    }
  }

  const toggleFolder = (path) => {
    const newExpanded = new Set(expandedFolders)
    if (newExpanded.has(path)) {
      newExpanded.delete(path)
    } else {
      newExpanded.add(path)
    }
    setExpandedFolders(newExpanded)
  }

  const flattenedTree = useMemo(() => {
    const flat = []
    const flatten = (items, depth = 0) => {
      items.forEach(item => {
        flat.push({ ...item, depth })
        if (item.is_dir && expandedFolders.has(item.path) && item.children) {
          flatten(item.children, depth + 1)
        }
      })
    }
    flatten(navItems)
    return flat
  }, [navItems, expandedFolders])

  const rowVirtualizer = useVirtualizer({
    count: flattenedTree.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 28,
  })

  return (
    <div className="app-container dark-theme">
      <div className="sidebar">
        <div className="sidebar-header">
          <h2>Md Viewer</h2>
          <input 
            type="text" 
            placeholder="Search files..." 
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            className="search-input"
          />
          <button className="settings-btn" onClick={handleOpenSettings}>⚙️ Settings</button>
        </div>
        
        {searchResults.length > 0 ? (
          <div className="search-results">
            {searchResults.map(res => (
              <div key={res.path} className="search-result-item" onClick={() => setCurrentFile(res.path)}>
                <div className="res-title">{res.title}</div>
                <div className="res-path">{res.path}</div>
              </div>
            ))}
          </div>
        ) : (
          <div className="nav-container" ref={parentRef}>
            <div
              style={{
                height: `${rowVirtualizer.getTotalSize()}px`,
                width: '100%',
                position: 'relative',
              }}
            >
              {rowVirtualizer.getVirtualItems().map((virtualItem) => {
                const item = flattenedTree[virtualItem.index]
                const isExpanded = expandedFolders.has(item.path)
                return (
                  <div
                    key={virtualItem.key}
                    style={{
                      position: 'absolute',
                      top: 0,
                      left: 0,
                      width: '100%',
                      height: `${virtualItem.size}px`,
                      transform: `translateY(${virtualItem.start}px)`,
                      paddingLeft: `${10 + item.depth * 15}px`,
                      display: 'flex',
                      alignItems: 'center'
                    }}
                    className={`tree-row depth-${item.depth}`}
                  >
                    <div 
                      className={`tree-item ${currentFile === item.path ? 'active' : ''}`}
                      onClick={() => {
                        if (item.is_dir) {
                          toggleFolder(item.path)
                        } else {
                          setCurrentFile(item.path)
                        }
                      }}
                      style={{ width: '100%', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}
                    >
                      <span className="tree-icon">{item.is_dir ? (isExpanded ? '📂' : '📁') : '📄'}</span> {item.name}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>

      <div className="main-content">
        {view === 'settings' ? (
          <div className="settings-page">
            <div className="content-header">
              <div className="breadcrumb">Settings</div>
              <div className="actions">
                <button className="btn-secondary" onClick={() => setView('document')}>Back</button>
              </div>
            </div>
            <div className="content-wrapper settings-wrapper">
              <h3>Configuration</h3>
              <div className="form-group">
                <label>Exclude Directories (comma-separated)</label>
                <input 
                  type="text" 
                  value={excludeDirs} 
                  onChange={e => setExcludeDirs(e.target.value)} 
                  placeholder="node_modules, .git, venv"
                />
              </div>
              <div className="form-group">
                <label>Theme</label>
                <select className="settings-select" disabled>
                  <option>Dark Mode (Default)</option>
                  <option>Light Mode</option>
                </select>
                <small>More settings coming soon.</small>
              </div>
              <div className="modal-actions" style={{justifyContent: 'flex-start', marginTop: '20px'}}>
                <button className="btn-primary" onClick={handleSaveSettings}>Save & Reload Tree</button>
              </div>
            </div>
          </div>
        ) : (
          <>
            <div className="content-header">
              <div className="breadcrumb">{fileData?.title}</div>
              <div className="actions">
                <div className="toggle-group">
                  <button className={`toggle-btn ${mode === 'rendered' ? 'active' : ''}`} onClick={() => setMode('rendered')}>Rendered</button>
                  <button className={`toggle-btn ${mode === 'raw' ? 'active' : ''}`} onClick={() => setMode('raw')}>Raw</button>
                  <button className={`toggle-btn ${mode === 'edit' ? 'active' : ''}`} onClick={() => setMode('edit')}>Edit</button>
                </div>
              </div>
            </div>

            <div className="content-wrapper">
              {mode === 'edit' ? (
                <div className="editor-container">
                  <div className="editor-scroll-area">
                      <CodeEditor
                        value={editContent}
                        onValueChange={code => setEditContent(code)}
                        highlight={code => Prism.highlight(code, Prism.languages.markdown, 'markdown')}
                        padding={20}
                        style={{
                          fontFamily: '"Fira Code", "Consolas", monospace',
                          fontSize: 14,
                          minHeight: '100%',
                          backgroundColor: 'var(--bg-primary)',
                          color: 'var(--text-primary)'
                        }}
                      />
                  </div>
                  <div className="editor-actions">
                    <button className="btn-primary" onClick={handleSave}>Save Changes</button>
                  </div>
                </div>
              ) : mode === 'raw' ? (
                <div className="raw-container">
                    <pre><code className="language-markdown" dangerouslySetInnerHTML={{ __html: Prism.highlight(fileData?.raw || '', Prism.languages.markdown, 'markdown') }} /></pre>
                </div>
              ) : (
                <div 
                  className="markdown-body" 
                  dangerouslySetInnerHTML={{ __html: fileData?.html || '' }} 
                />
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

export default App
