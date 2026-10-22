"""Read-only guard for a disposable world test. Does not start/stop any server."""
import argparse, ctypes, json, pathlib, re, subprocess
p=argparse.ArgumentParser(description=__doc__);p.add_argument('folder',type=pathlib.Path);a=p.parse_args()
d=a.folder.resolve()
if d.is_relative_to(pathlib.Path('C:/VMaNGOS').resolve()):raise SystemExit('Original installation forbidden')
world=(d/'mangosd.conf').read_text(encoding='utf-8');realm=(d/'realmd.conf').read_text(encoding='utf-8')
def val(text,key):
    m=re.findall(r'(?m)^'+re.escape(key)+r'\s*=\s*(.*?)\s*$',text)
    if len(m)!=1:raise ValueError('Ambiguous/missing key '+key)
    return m[0].strip('"')
errors=[]
for text,key,expected in [(world,'BindIP','127.0.0.1'),(realm,'BindIP','127.0.0.1'),(world,'WorldServerPort','18085'),(realm,'RealmServerPort','13724'),(world,'Ra.Enable','0'),(world,'SOAP.Enabled','0'),(world,'RandomBot.Enable','0'),(world,'Silicio.Enable','1'),(world,'PlayerBot.AllowSaving','1')]:
    if val(text,key)!=expected:errors.append('Unsafe '+key)
for key,suffix in [('LoginDatabase.Info','realmd'),('WorldDatabase.Info','world'),('CharacterDatabase.Info','characters'),('LogsDatabase.Info','logs')]:
    parts=val(world,key).split(';')
    if len(parts)!=5 or parts[:3]!=['127.0.0.1','3308','silicio_test'] or parts[-1]!='silicio_test_'+suffix:errors.append('Unsafe '+key)
    elif parts[3]=='CHANGE_ME':errors.append('Disposable database credentials not prepared')
if val(realm,'LoginDatabaseInfo')!=val(world,'LoginDatabase.Info'):errors.append('Auth database does not match disposable world login database')
if not (d/'data').resolve().is_relative_to(d):errors.append('Data directory resolves outside disposable folder')
if val(world,'DataDir')!='data' or not (d/'data/maps').is_dir():errors.append('Separate map data missing')
class Mem(ctypes.Structure):
    _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(n,ctypes.c_ulonglong) for n in ['total','free','page','freepage','virtual','freevirtual','extended']]
m=Mem();m.length=ctypes.sizeof(m)
if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):raise OSError('Memory inspection failed')
if m.free<1536*1024*1024:errors.append('Less than 1.5 GiB RAM free')
proc=subprocess.run(['tasklist','/FO','CSV','/NH'],capture_output=True,text=True)
if proc.returncode!=0:errors.append('Process inspection unavailable; cannot establish exclusive world test')
elif '"mangosd.exe"' in proc.stdout.lower() or '"realmd.exe"' in proc.stdout.lower():errors.append('Another world/auth server is running; do not stop it automatically')
print(json.dumps({'ready':not errors,'free_ram_mib':m.free//1048576,'errors':errors},indent=2))
raise SystemExit(1 if errors else 0)
