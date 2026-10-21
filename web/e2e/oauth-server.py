"""Disposable OAuth browser server; no production volumes or external services."""
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'services'))
import uvicorn
from juanzhan.apps import create_app
from juanzhan.auth import set_password
from juanzhan.config import Settings
from juanzhan.database import migrate

with TemporaryDirectory(prefix='juanzhan-oauth-browser-') as root:
    settings=Settings(Path(root),'',cookie_secure=False,public_url='http://127.0.0.1:8767')
    settings.prepare_archive();migrate(settings.database)
    set_password(settings,os.environ['JUANZHAN_E2E_PASSWORD'])
    uvicorn.run(create_app('archive',settings),host='127.0.0.1',port=8767,log_level='warning')
