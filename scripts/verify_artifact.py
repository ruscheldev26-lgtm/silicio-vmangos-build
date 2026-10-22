"""Verifica artefato sem extrair nem executar binarios. Python 3.10+, stdlib."""
import argparse
import hashlib
import json
import re
import stat
import struct
import sys
import zipfile
from pathlib import Path, PurePosixPath

BASE='e968eae18407ea557064c32f4fdcea96464f5372'
REQUIRED={'bin/mangosd.exe','bin/realmd.exe','bin/libmySQL.dll','bin/libeay32.dll',
          'source/upstream-source.zip','source/resource.patch','evidence/Progression.h','LICENSE'}
ALLOWED=REQUIRED | {'manifest.json','source/silicio.patch','evidence/configure.log','evidence/build.log',
                   'recipe/build.ps1','recipe/verify_artifact.py','recipe/silicio-4449.yml'}

def safe_name(name):
    p=PurePosixPath(name)
    if not name or '\\' in name or ':' in name or p.is_absolute() or '..' in p.parts or str(p)!=name:
        raise ValueError('Caminho inseguro: '+name)
    return name

class Artifact:
    def __init__(self,path):
        self.path=Path(path)
        self.zip=zipfile.ZipFile(self.path) if self.path.is_file() else None
        if self.zip:
            items=[i for i in self.zip.infolist() if not i.is_dir()]
            names=[safe_name(i.filename) for i in items]
            if any(stat.S_ISLNK(i.external_attr >> 16) for i in items):
                raise ValueError('Link simbolico no ZIP')
            sizes=[i.file_size for i in items]
        else:
            if not self.path.is_dir(): raise ValueError('Pasta ou ZIP ausente')
            root=self.path.resolve()
            files=[p for p in root.rglob('*') if p.is_file()]
            if any(p.is_symlink() or not p.resolve().is_relative_to(root) for p in files):
                raise ValueError('Link ou arquivo fora da pasta')
            names=[safe_name(p.relative_to(root).as_posix()) for p in files]
            sizes=[p.stat().st_size for p in files]
        if len({n.casefold() for n in names})!=len(names): raise ValueError('Nomes duplicados ou colisao Windows')
        if sum(sizes)>512*1024*1024 or any(s>300*1024*1024 for s in sizes): raise ValueError('Pacote excede limite de leitura')
        self.names=set(names)
    def read(self,name,limit=64*1024*1024):
        if name not in self.names: raise ValueError('Arquivo ausente: '+name)
        if self.zip:
            if self.zip.getinfo(name).file_size>limit: raise ValueError('Arquivo grande demais')
            return self.zip.read(name)
        p=self.path/name
        if p.stat().st_size>limit: raise ValueError('Arquivo grande demais')
        return p.read_bytes()
    def digest(self,name):
        h=hashlib.sha256();size=0
        stream=self.zip.open(name) if self.zip else (self.path/name).open('rb')
        with stream:
            for b in iter(lambda:stream.read(1024*1024),b''):h.update(b);size+=len(b)
        return h.hexdigest(),size
    def close(self):
        if self.zip:self.zip.close()

def pe_info(b):
    if len(b)<64 or b[:2]!=b'MZ': raise ValueError('Sem assinatura MZ')
    pe=struct.unpack_from('<I',b,60)[0]
    if b[pe:pe+4]!=b'PE\0\0': raise ValueError('Sem assinatura PE')
    machine,sections=struct.unpack_from('<HH',b,pe+4)
    opt=pe+24
    optsize=struct.unpack_from('<H',b,pe+20)[0]
    if machine!=0x8664 or struct.unpack_from('<H',b,opt)[0]!=0x20b:
        raise ValueError('Esperado PE32+ AMD64')
    sec=opt+optsize
    def raw(rva):
        for i in range(sections):
            vsize,va,size,pos=struct.unpack_from('<IIII',b,sec+40*i+8)
            if va<=rva<va+max(vsize,size):
                result=pos+rva-va
                if result>=len(b):raise ValueError('RVA fora do arquivo')
                return result
        raise ValueError('RVA nao mapeado')
    rva=struct.unpack_from('<I',b,opt+120)[0]
    dlls=[]
    if rva:
        offset=raw(rva)
        for _ in range(256):
            desc=b[offset:offset+20]
            if len(desc)!=20:raise ValueError('Tabela de importacao truncada')
            if not any(desc):break
            pos=raw(struct.unpack_from('<I',desc,12)[0])
            end=b.find(b'\0',pos,min(pos+4096,len(b)))
            if end<0:raise ValueError('Nome DLL invalido')
            dlls.append(b[pos:end].decode('ascii'))
            offset+=20
        else:raise ValueError('Tabela de importacao longa demais')
    return {'machine':'AMD64','imports':dlls}

def verify(path,run_id=None,control_commit=None,variant=None):
    a=Artifact(path)
    try:
        if not REQUIRED<=a.names or not a.names<=ALLOWED:raise ValueError('Arquivos obrigatorios ausentes ou arquivos inesperados')
        m=json.loads(a.read('manifest.json',1024*1024).decode('utf-8-sig'))
        if (m.get('schema')!=1 or m.get('upstream_repository')!='vmangos/core' or m.get('upstream_commit')!=BASE
            or m.get('client_build')!=4449 or m.get('configuration')!='Release' or m.get('architecture')!='x64'):
            raise ValueError('Origem ou alvo divergente')
        if m.get('variant') not in ('baseline','silicio'):raise ValueError('Variante desconhecida')
        if run_id and str(m.get('run_id'))!=str(run_id):raise ValueError('Run ID divergente')
        if control_commit and m.get('control_commit')!=control_commit:raise ValueError('Commit de controle divergente')
        if variant and m.get('variant')!=variant:raise ValueError('Variante divergente')
        rows=m.get('files',[])
        listed=[safe_name(r['path']) for r in rows]
        if len(listed)!=len(set(listed)) or set(listed)!=(a.names-{'manifest.json'}):raise ValueError('Inventario divergente')
        for r in rows:
            digest,size=a.digest(r['path'])
            if digest!=r['sha256'] or size!=r['size']:raise ValueError('Hash/tamanho divergente: '+r['path'])
        if not re.search(rb'(?m)^#define SUPPORTED_CLIENT_BUILD 4449\s*$',a.read('evidence/Progression.h')):
            raise ValueError('Header nao seleciona 4449')
        binaries={n:pe_info(a.read(n)) for n in REQUIRED if n.startswith('bin/')}
        imports={x.casefold() for x in binaries['bin/mangosd.exe']['imports']}
        if not {'libmysql.dll','libeay32.dll'}<=imports:raise ValueError('Dependencias previstas ausentes nas importacoes')
        revision=BASE[:20].encode()
        if revision not in a.read('bin/mangosd.exe'):raise ValueError('Revisao base nao encontrada no executavel')
        if m['variant']=='silicio':
            if 'source/silicio.patch' not in a.names or a.digest('source/silicio.patch')[0]!=m.get('silicio_patch_sha256'):
                raise ValueError('Patch Silicio divergente')
        elif 'source/silicio.patch' in a.names or m.get('silicio_patch_sha256'):
            raise ValueError('Baseline nao pode conter patch Silicio')
        return {'verified':True,'run_id':m.get('run_id'),'variant':m['variant'],'upstream_commit':BASE,
                'binaries':binaries,'limitation':'Static integrity only; no Windows 10 runtime or game test.'}
    finally:a.close()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('artifact',type=Path)
    p.add_argument('--run-id')
    p.add_argument('--control-commit')
    p.add_argument('--variant',choices=['baseline','silicio'])
    p.add_argument('--artifact-sha256',help='Digest do ZIP obtido independentemente no GitHub')
    args=p.parse_args()
    try:
        if args.artifact_sha256:
            if not args.artifact.is_file():raise ValueError('Digest externo exige arquivo ZIP original')
            h=hashlib.sha256()
            with args.artifact.open('rb') as f:
                for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
            if h.hexdigest()!=args.artifact_sha256.lower():raise ValueError('Digest externo divergente')
        result=verify(args.artifact,args.run_id,args.control_commit,args.variant)
    except (ValueError,KeyError,TypeError,struct.error,UnicodeError,OSError,zipfile.BadZipFile) as e:
        print('REJEITADO:',str(e),file=sys.stderr);return 1
    print(json.dumps(result,indent=2));return 0

if __name__=='__main__':sys.exit(main())
