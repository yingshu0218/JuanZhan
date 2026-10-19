"""Real transport/recovery plus hostile ZIP boundary cases, without extractall."""
import hashlib
import json
import stat
import zipfile

import pytest
from fastapi.testclient import TestClient

from test_parsing import pipeline, upload
from test_backup import login
from juanzhan.apps import create_app
from juanzhan.backup import create, restore
from juanzhan.backup_archive import export_bundle, import_bundle
from juanzhan.config import Settings


def members():
    raw = b'fixture database bytes'
    manifest = json.dumps({'format':'juanzhan-backup-1','external_sources_included':False,
        'files':[{'name':'database/archive.sqlite3','size':len(raw),
                  'sha256':hashlib.sha256(raw).hexdigest()}]}).encode()
    return {'database/archive.sqlite3':raw,'manifest.json':manifest,
            'COMPLETE':hashlib.sha256(manifest).hexdigest().encode()}


def write_zip(path, entries):
    with zipfile.ZipFile(path,'w') as archive:
        for name, body in entries:
            archive.writestr(name,body)


def test_transport_real_database_original_and_http_recovery(pipeline,tmp_path):
    settings, client, _, space = pipeline
    original = '通过网页传输恢复的原件'.encode()
    receipt = upload(pipeline,original,'网页恢复.txt')
    bundle = tmp_path/'bundle'
    create(settings,bundle)
    archive = tmp_path/'download.zip'
    result = export_bundle(bundle,archive)
    assert result['sha256'] == hashlib.sha256(archive.read_bytes()).hexdigest()
    assert archive.stat().st_mode & 0o777 == 0o600
    unpacked = tmp_path/'imported'
    import_bundle(archive,unpacked)
    restored = tmp_path/'recovered'
    assert restore(unpacked,restored)['credentials_revoked']
    with TestClient(create_app('archive',Settings(restored,'pipeline-token',cookie_secure=False))) as after:
        assert after.get('/api/v1/documents/'+receipt['document_id']+'/download').status_code == 401
        assert login(after).status_code == 200
        assert after.get('/api/v1/documents/'+receipt['document_id']+'/download').content == original
    # Recovery never replaces the active original database or bytes.
    assert client.get('/api/v1/documents/'+receipt['document_id']+'/download').content == original
    with pytest.raises(FileExistsError):
        import_bundle(archive,unpacked)
    assert (unpacked/'manifest.json').is_file()
    with pytest.raises(FileExistsError):
        export_bundle(bundle,archive)
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == result['sha256']


@pytest.mark.parametrize('fault',['traversal','absolute','symlink','duplicate','extra','checksum','incomplete','budget','count','directory'])
def test_untrusted_archives_leave_no_partial_bundle_or_escape(tmp_path,fault):
    entries = list(members().items())
    if fault=='traversal':entries.append(('../escape',b'bad'))
    elif fault=='absolute':entries.append(('/tmp/juanzhan-never-write',b'bad'))
    elif fault=='symlink':
        info=zipfile.ZipInfo('database/archive.sqlite3');info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16
        entries[0]=(info,b'/etc/passwd')
    elif fault=='duplicate':entries.append(entries[0])
    elif fault=='extra':entries.append(('derived/sha256/aa/'+'a'*64+'-1',b'x'))
    elif fault=='checksum':entries[0]=(entries[0][0],b'wrong bytes')
    elif fault=='incomplete':entries=[entry for entry in entries if entry[0]!='COMPLETE']
    elif fault=='directory':entries.append(('database/',b''))
    archive=tmp_path/'hostile.zip'
    with pytest.warns(UserWarning) if fault=='duplicate' else __import__('contextlib').nullcontext():
        write_zip(archive,entries)
    target=tmp_path/'new'
    options={'max_bytes':1} if fault=='budget' else {'max_files':0} if fault=='count' else {}
    with pytest.raises((ValueError,zipfile.BadZipFile)):
        import_bundle(archive,target,**options)
    assert not target.exists()
    assert not (tmp_path/'escape').exists()


def test_export_checks_corruption_before_creating_transport(tmp_path):
    bundle=tmp_path/'bundle';(bundle/'database').mkdir(parents=True)
    for name,body in members().items():(bundle/name).write_bytes(body)
    archive=tmp_path/'transport.zip'
    export_bundle(bundle,archive)
    archive.unlink()
    (bundle/'database/archive.sqlite3').write_bytes(b'changed')
    with pytest.raises(ValueError,match='checksum'):
        export_bundle(bundle,archive)
    assert not archive.exists()


@pytest.mark.parametrize('fault',['forged_count','central_size','trailing','nul_name','crc'])
def test_directory_preflight_rejects_ambiguous_or_unbounded_zip(tmp_path,fault):
    import struct
    archive=tmp_path/'bad-directory.zip'
    write_zip(archive,list(members().items()))
    raw=bytearray(archive.read_bytes())
    end=raw.rfind(b'PK\x05\x06')
    if fault=='forged_count':struct.pack_into('<HH',raw,end+8,1,1)
    elif fault=='central_size':struct.pack_into('<L',raw,end+12,65*1024**2)
    elif fault=='trailing':raw.extend(b'unexpected trailing bytes')
    elif fault=='crc':
        raw[raw.find(b'fixture database bytes')]=ord('X')
    else:
        # ZIP names containing NUL must not silently truncate to an allowed name.
        index=raw.find(b'database/archive.sqlite3',raw.find(b'PK\x01\x02'))
        raw[index+8]=0
    archive.write_bytes(raw)
    target=tmp_path/'new'
    with pytest.raises((ValueError,zipfile.BadZipFile)):
        import_bundle(archive,target)
    assert not target.exists()


def test_zip64_directory_transport_is_supported_without_large_fixture(tmp_path):
    import struct
    archive=tmp_path/'zip64.zip'
    write_zip(archive,list(members().items()))
    raw=archive.read_bytes();end=raw.rfind(b'PK\x05\x06')
    _,_,_,_,count,length,offset,_=struct.unpack('<4s4H2LH',raw[end:])
    record=struct.pack('<4sQ2H2L4Q',b'PK\x06\x06',44,45,45,0,0,count,count,length,offset)
    locator=struct.pack('<4sLQL',b'PK\x06\x07',0,end,1)
    eocd=struct.pack('<4s4H2LH',b'PK\x05\x06',0,0,65535,65535,0xffffffff,0xffffffff,0)
    archive.write_bytes(raw[:end]+record+locator+eocd)
    target=tmp_path/'imported'
    assert import_bundle(archive,target)['files']==1
    assert (target/'database/archive.sqlite3').read_bytes()==members()['database/archive.sqlite3']
