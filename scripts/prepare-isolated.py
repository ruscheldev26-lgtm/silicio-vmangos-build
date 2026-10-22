"""Stage a verified artifact in a NEW disposable folder; never starts a server."""
import argparse, importlib.util, io, pathlib, re, zipfile
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('artifact',type=pathlib.Path)
p.add_argument('destination',type=pathlib.Path)
p.add_argument('--sha256',required=True)
p.add_argument('--run-id',required=True)
p.add_argument('--commit',required=True)
a=p.parse_args()
import hashlib
if hashlib.sha256(a.artifact.read_bytes()).hexdigest()!=a.sha256: raise SystemExit('Archive digest mismatch')
spec=importlib.util.spec_from_file_location('verify',pathlib.Path(__file__).with_name('verify_artifact.py'))
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
v.verify(a.artifact,a.run_id,a.commit,'silicio')
d=a.destination.resolve()
if d.exists() or str(d).lower().startswith('c:\\vmangos'): raise SystemExit('Destination must be new and outside original installation')
z=zipfile.ZipFile(a.artifact)
src=zipfile.ZipFile(io.BytesIO(z.read('source/upstream-source.zip')))
world=src.read('src/mangosd/mangosd.conf.dist.in').decode()
realm=src.read('src/realmd/realmd.conf.dist.in').decode()
def setkey(text,key,value):
    pattern=r'(?m)^'+re.escape(key)+r'\s*=.*$'
    if not re.search(pattern,text): raise ValueError('Missing config key '+key)
    return re.sub(pattern,lambda _:key+' = '+value,text)
for key,value in {'BindIP':'"127.0.0.1"','WorldServerPort':'18085','DataDir':'"data"','Ra.Enable':'0','SOAP.Enabled':'0','RandomBot.Enable':'0','PlayerBot.AllowSaving':'1','PlayerBot.Debug':'1'}.items():
    world=setkey(world,key,value)
for key,db in {'LoginDatabase.Info':'realmd','WorldDatabase.Info':'world','CharacterDatabase.Info':'characters','LogsDatabase.Info':'logs'}.items():
    world=setkey(world,key,'"127.0.0.1;3308;silicio_test;CHANGE_ME;silicio_test_'+db+'"')
world+='\n# Disposable test only\nSilicio.Enable = 1\n'
for key,value in {'BindIP':'"127.0.0.1"','RealmServerPort':'13724','LoginDatabaseInfo':'"127.0.0.1;3308;silicio_test;CHANGE_ME;silicio_test_realmd"'}.items():
    realm=setkey(realm,key,value)
d.mkdir(parents=True)
(d/'data').mkdir()
for name in ['mangosd.exe','realmd.exe','libmySQL.dll','libeay32.dll']:
    (d/name).write_bytes(z.read('bin/'+name))
(d/'mangosd.conf').write_text(world,encoding='utf-8')
(d/'realmd.conf').write_text(realm,encoding='utf-8')
print('Staged only. No server started. Provide separate maps and disposable MySQL on 3308.')
