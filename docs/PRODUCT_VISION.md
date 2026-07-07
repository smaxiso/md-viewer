# PRODUCT_VISION.md

# mdview — Product Vision

## Mission

Build the fastest, simplest, and most enjoyable local-first documentation browser for software engineers.

The goal is to make browsing project documentation feel as effortless as navigating source code inside an IDE while remaining significantly lighter, faster, and focused exclusively on documentation.

---

# Vision

`mdview` is **not** a Markdown editor.

It is **not** a static site generator.

It is **not** a knowledge management system.

It is **not** a note-taking application.

It is a **local-first documentation browser**.

Its only purpose is to help developers browse, navigate, search, read, and maintain documentation that already exists inside software projects.

Every feature should strengthen this purpose.

Anything that doesn't should be questioned.

---

# Product Philosophy

The product should disappear.

The user should never think about the application itself.

The user should only think about the documentation.

The experience should feel:

* Instant
* Natural
* Lightweight
* Reliable
* Familiar
* Unobtrusive

Running

```bash
cd my-project
mdview
```

should immediately open a beautiful documentation browser.

No setup.

No project configuration.

No indexing wizard.

No login.

No cloud.

No waiting.

---

# Local First

This product is completely local.

Everything remains on the user's machine.

Nothing is uploaded.

Nothing is synchronized.

Nothing is tracked.

Nothing is analyzed.

The application must work without an internet connection.

If a renderer exists for a supported document type, it should run locally whenever reasonably possible.

The product should never silently send documentation to external services.

Privacy is a core feature.

---

# Core Principles

## 1. Reading First

The primary experience is reading documentation.

Everything else is secondary.

Editing exists only to improve documentation maintenance.

The application should never evolve into a full IDE.

---

## 2. Navigation First

Developers navigate documentation similarly to how they navigate source code.

The navigation experience should feel comparable to modern IDEs.

The sidebar is a permanent project explorer.

The content pane is the current document.

The navigation tree should never lose context.

---

## 3. Performance is a Feature

Performance is not an optimization.

Performance is part of the product.

Users should never feel that the application is "loading."

Target goals:

* Cold startup < 300ms
* Cached document open < 20ms
* Uncached document open < 100ms
* Search < 50ms
* Sidebar interactions < 16ms
* Smooth navigation in repositories containing 100,000+ files

These are aspirational engineering goals that guide architectural decisions.

---

## 4. Simplicity Over Features

A smaller product with exceptional execution is better than a larger product with mediocre execution.

Every new feature must answer:

Does this improve documentation browsing?

If the answer is no,

it probably doesn't belong.

---

## 5. Opinionated Defaults

The application should work immediately.

Good defaults are preferred over endless configuration.

Configuration should exist only when it genuinely improves flexibility.

---

# Primary Workflow

The current working directory becomes the project root.

Example

```bash
cd ~/workspace/my-project
mdview
```

The application should immediately:

* discover the project
* build navigation
* open the default document
* become interactive

No additional steps should be required.

---

# Core Features

## Documentation Rendering

Supported document types should render using their native renderer whenever possible.

Examples include:

* Markdown
* Mermaid
* PlantUML
* AsciiDoc
* HTML
* Plain Text
* reStructuredText

Future formats should be easy to add.

The application should never display raw syntax if a rendered representation is available unless the user explicitly requests it.

---

## Raw / Rendered Mode

Every supported document should support:

* Rendered View
* Raw View

Raw View exists primarily for:

* editing
* debugging
* copying
* reviewing generated output

Users should be able to switch instantly.

---

## Editing

Editing is intentionally lightweight.

The goal is not to compete with VS Code.

Editing should make documentation maintenance convenient.

Possible save modes:

* Auto Save
* Manual Save
* Save Confirmation

Changes should always modify the original source file.

---

## Navigation

The sidebar always represents the complete project.

Requirements:

* unlimited nesting
* expand/collapse
* remembered state
* search
* filtering
* keyboard navigation
* scalable to large repositories

Only the content pane changes.

---

## Search

Search is one of the product's defining features.

The application should support:

* filename search
* folder search
* content search
* fuzzy matching
* keyboard-first workflow

Searching should feel instantaneous.

---

## Filtering

Users control what appears.

Support:

Hide folders by name.

Hide folders by path.

Hide extensions.

Show only selected extensions.

Filters should apply immediately.

No restart should be required.

---

# What This Product Is NOT

The application should never become:

* a source code editor
* a Git client
* a terminal emulator
* a debugger
* a notebook platform
* a documentation generator
* a CMS
* a wiki platform
* a project management tool

These are intentionally out of scope.

---

# User Experience Principles

The interface should feel:

Minimal.

Predictable.

Fast.

Readable.

Comfortable for long reading sessions.

Large documents should remain smooth.

Large repositories should remain responsive.

Keyboard users should feel first-class.

Mouse users should never need excessive clicks.

---

# Engineering Principles

Favor:

* simplicity
* readability
* maintainability
* composability
* clear module boundaries

Avoid:

* premature optimization
* speculative abstractions
* unnecessary dependencies
* framework-driven architecture
* feature creep

Profile before optimizing.

Measure before rewriting.

---

# Architecture Direction

The current implementation may evolve.

The preferred long-term architecture is:

Backend

Python

Responsible for:

* filesystem
* rendering
* caching
* search
* configuration
* plugin execution
* document processing

If backend complexity eventually justifies it, migrating to FastAPI is encouraged because it provides:

* async support
* clean routing
* dependency injection
* modularity
* testing
* extensibility
* WebSockets

Frontend

A lightweight modern frontend such as:

* React
* TypeScript
* Vite

responsible only for:

* UI
* navigation
* interaction
* rendering state
* virtualization
* keyboard shortcuts

Migration should happen only when justified by product complexity—not simply because newer frameworks exist.

---

# Decision Framework

Before implementing any feature, ask:

Does this improve documentation browsing?

Does it keep the application lightweight?

Does it preserve simplicity?

Does it scale?

Can it be maintained easily?

Would developers expect this behavior?

If the answer to most of these questions is "No", the feature should probably not be added.

---

# Definition of Success

A developer should be able to:

```bash
cd project
mdview
```

and within seconds:

* understand the project structure
* find documentation instantly
* navigate effortlessly
* read comfortably
* edit documentation when needed
* never think about the tool itself

The tool succeeds when it becomes invisible.

The documentation becomes the focus.

Everything else is implementation detail.
