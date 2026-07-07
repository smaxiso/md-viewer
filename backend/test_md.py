import markdown
md = markdown.Markdown(extensions=['fenced_code', 'codehilite'])
print(md.convert('```mermaid\ngraph TD\nA-->B\n```'))
