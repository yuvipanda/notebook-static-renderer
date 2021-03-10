from nbconvert.exporters import HTMLExporter
from typing import Optional
import shutil
import os
import gzip
import hashlib
import tempfile
import nbformat

from fastapi import FastAPI, UploadFile, File, Request, Header
from fastapi.responses import HTMLResponse, Response, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from storage import FileBackend, S3Backend

app = FastAPI(root_path='/')

BASE_PATH = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.environ.get('DATA_DIR', os.getcwd())

templates = Jinja2Templates(directory=os.path.join(BASE_PATH, 'templates'))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_PATH, "static")), name="static")


backend = S3Backend()

@app.post("/upload")
async def upload(notebook: UploadFile = File(...), host: Optional[str] = Header(None), x_forwarded_proto: str = Header('http'), accept: str = Header('text/plain')):
    data = await notebook.read()

    sha256 = hashlib.sha256()
    sha256.update(data)
    hash = sha256.hexdigest()

    await backend.put(hash, data)

    # FIXME: is this really the best way?
    url = f'{x_forwarded_proto}://{host}{app.root_path}view/{hash}'
    if accept == 'application/json':
        return {
            'url': url
        }
    else:
        return Response(url + '\n')


@app.get('/view/{name}')
async def view(name: str, request: Request, download: bool = False):
    if download:
        return Response(await backend.get(name), headers={
            "Content-Type": "application/json",
            "Content-Disposition": f'attachment; filename={name}.ipynb'
        })
    return templates.TemplateResponse(
        'view.html.j2', { 'name': name, 'request': request }
    )

@app.get('/render/v1/{name}')
async def render(name: str):
    exporter = HTMLExporter(
        # Input / output prompts are empty left gutter space
        # Let's remove them. If we want gutters, we can CSS them.
        exclude_input_prompt=True,
        exclude_output_prompt=True
    )
    notebook = nbformat.reads(await backend.get(name), as_version=4)
    output, resources = exporter.from_notebook_node(notebook)
    return HTMLResponse(output)

@app.get('/')
async def render_front(request: Request):
    return templates.TemplateResponse('front.html.j2', {
        'request': request
    })
