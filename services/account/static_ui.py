"""Serve one coherent UI revision, including after an application upgrade."""
import hashlib
from pathlib import Path

from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles


class AccountUI(StaticFiles):
    def is_not_modified(self, response_headers, request_headers):
        # A previously cached shell must not hide newly introduced form fields.
        return False

    async def get_response(self, path, scope):
        if path in ('', '.', 'index.html'):
            root=Path(self.directory)
            html=(root/'index.html').read_text(encoding='utf8')
            assets=sorted([*root.glob('*.js'), *root.glob('*.css')])
            digest=hashlib.sha256(html.encode())
            for asset in assets:
                digest.update(asset.name.encode())
                digest.update(asset.read_bytes())
            revision=digest.hexdigest()[:16]
            for asset in assets:
                html=html.replace(f'"./{asset.name}"',f'"./{asset.name}?v={revision}"')
            response=HTMLResponse(html,headers={'X-UI-Version':revision})
        else:
            response=await super().get_response(path,scope)
        response.headers['Cache-Control']='no-store, max-age=0'
        response.headers['Pragma']='no-cache'
        response.headers['Expires']='0'
        return response
