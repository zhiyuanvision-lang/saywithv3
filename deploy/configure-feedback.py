from pathlib import Path
import secrets,subprocess
from urllib.parse import quote
p=Path('/opt/saywith-learning/.env');env=p.read_text()
if 'SAYWITH_FEEDBACK_DATABASE_URL=' not in env:
    password=secrets.token_urlsafe(36)
    sql="CREATE ROLE saywith_learning_feedback LOGIN PASSWORD '"+password+"' NOSUPERUSER NOCREATEDB NOCREATEROLE; GRANT CONNECT ON DATABASE saywith TO saywith_learning_feedback; GRANT USAGE ON SCHEMA public TO saywith_learning_feedback; GRANT SELECT,INSERT ON feedbacks,feedback_messages TO saywith_learning_feedback; GRANT UPDATE(status) ON feedbacks TO saywith_learning_feedback;"
    subprocess.run(['docker','exec','-i','saywith-postgres-1','psql','-U','saywith','-d','saywith','-v','ON_ERROR_STOP=1'],input=sql.encode(),check=True,stdout=subprocess.DEVNULL)
    env+='\nSAYWITH_FEEDBACK_DATABASE_URL=postgresql+psycopg://saywith_learning_feedback:'+quote(password,safe='')+'@127.0.0.1:5433/saywith\nSAYWITH_FEEDBACK_PUBLIC_BASE=https://api.saywith.zhiyuanv.com/learning\n'
    p.write_text(env);p.chmod(0o600)
print('Dedicated feedback role configured')
