"""Build a self-contained Cloudflare Worker from the shared widget and MCP contract."""
import json
import runpy
from pathlib import Path

root = Path(__file__).parent
server = runpy.run_path(str(root / 'server.py'))
html = (root / 'public/widget.html').read_text(encoding='utf-8')
logic = (root / 'worker/logic.js').read_text(encoding='utf-8')
code = 'const HTML=' + json.dumps(html) + ';\nconst RESOURCE=' + json.dumps(server['RESOURCE']) + ';\nconst TOOL=' + json.dumps(server['TOOL']) + ';\n' + logic
(root / 'worker/index.js').write_text(code, encoding='utf-8')
print('Built worker/index.js')

