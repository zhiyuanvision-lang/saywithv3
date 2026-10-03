"""Run on tengxun as ubuntu after copying the release and private runtime.env."""
import datetime,json,os,pathlib,subprocess,tarfile,time,urllib.parse,urllib.request
ROOT=pathlib.Path('/opt/saywith-learning')
run=lambda args,**kwargs:subprocess.run(args,check=True,**kwargs)
def pg(sql):
    info=json.loads(subprocess.check_output(['docker','inspect','saywith-postgres-1']))[0]
    env=dict(x.split('=',1) for x in info['Config']['Env'] if '=' in x)
    return subprocess.check_output(['docker','exec','-i','saywith-postgres-1','psql','-v','ON_ERROR_STOP=1','-U',env.get('POSTGRES_USER','postgres'),'-d','postgres','-At'],input=sql.encode()).decode().strip()
env=dict(line.split('=',1) for line in (ROOT/'runtime.env').read_text().splitlines() if '=' in line)
url=urllib.parse.urlsplit(env['SAYWITH_DATABASE_URL'])
password=url.password.replace("'","''")
if not pg("SELECT rolname FROM pg_roles WHERE rolname='saywith_learning';"):
    pg("CREATE ROLE saywith_learning LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD '"+password+"';")
if not pg("SELECT datname FROM pg_database WHERE datname='saywith_learning';"):
    pg('CREATE DATABASE saywith_learning OWNER saywith_learning;')
(ROOT/'runtime.env').replace(ROOT/'.env');(ROOT/'.env').chmod(0o600)
release=ROOT/'releases'/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
release.mkdir()
with tarfile.open(ROOT/'release.tar.gz') as archive:archive.extractall(release,filter='data')
run([str(ROOT/'venv/bin/pip'),'install','-r',str(release/'requirements.lock.txt')])
link=ROOT/'current'
if link.is_symlink():(ROOT/'previous').unlink(missing_ok=True);(ROOT/'previous').symlink_to(link.resolve())
next_link=ROOT/'next';next_link.unlink(missing_ok=True);next_link.symlink_to(release);os.replace(next_link,link)
for kind in ('api','worker'):
    run(['sudo','-n','install','-m','644',str(release/'deploy'/f'saywith-learning-{kind}.service'),'/etc/systemd/system/'])
run(['sudo','-n','systemctl','daemon-reload'])
run(['sudo','-n','systemctl','enable','--now','saywith-learning-api','saywith-learning-worker'])
run(['sudo','-n','systemctl','restart','saywith-learning-api','saywith-learning-worker'])
for _ in range(60):
    try:
        with urllib.request.urlopen('http://127.0.0.1:8083/health',timeout=2) as response:
            if json.load(response).get('status')=='ok':break
    except (OSError,ValueError):pass
    time.sleep(1)
else:
    previous=ROOT/'previous'
    if previous.is_symlink():
        next_link=ROOT/'next';next_link.unlink(missing_ok=True);next_link.symlink_to(previous.resolve());os.replace(next_link,ROOT/'current')
        run(['sudo','-n','systemctl','restart','saywith-learning-api','saywith-learning-worker'])
    raise RuntimeError('Learning API readiness failed; previous code restored if available')
run(['sudo','-n','install','-m','644',str(release/'deploy/nginx-learning.inc'),'/etc/nginx/snippets/saywith-learning.inc'])
config=pathlib.Path('/etc/nginx/sites-enabled/saywith').resolve()
original=config.read_text();marker='server_name api.saywith.zhiyuanv.com 43.143.208.113;'
if 'include snippets/saywith-learning.inc;' not in original:
    if original.count(marker)!=1:raise RuntimeError('Ambiguous API server; inspect nginx before editing')
    backup=ROOT/'var'/('nginx-before-'+release.name+'.conf');backup.write_text(original)
    draft=ROOT/'var/nginx-next.conf';draft.write_text(original.replace(marker,marker+'\n    include snippets/saywith-learning.inc;',1))
    run(['sudo','-n','cp',str(draft),str(config)])
    try:run(['sudo','-n','nginx','-t'])
    except subprocess.CalledProcessError:
        run(['sudo','-n','cp',str(backup),str(config)]);raise
else:run(['sudo','-n','nginx','-t'])
run(['sudo','-n','systemctl','reload','nginx'])
print('Learning API and worker deployed:',release.name)
