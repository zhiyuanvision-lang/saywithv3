import argparse,json
from pathlib import Path
from .repository import CurriculumRepository
from .packaging import export_release,verify_release

p=argparse.ArgumentParser(description="Read, validate and export pinned curriculum resources")
p.add_argument("--workspace",type=Path,default=Path.cwd())
s=p.add_subparsers(dest="command",required=True)
s.add_parser("validate")
t=s.add_parser("target");t.add_argument("target_id")
v=s.add_parser("senses");v.add_argument("query");v.add_argument("--limit",type=int,default=10)
e=s.add_parser("export");e.add_argument("--output",type=Path,required=True)
c=s.add_parser("verify-release");c.add_argument("output",type=Path)
a=p.parse_args()
if a.command=="export":
 m=export_release(a.workspace,a.output);result={"status":"passed","output":str(a.output),"files":len(m['files']),"verification":m['verification']}
elif a.command=="verify-release":result=verify_release(a.output)
else:
 repo=CurriculumRepository(a.workspace)
 result=repo.validate() if a.command=="validate" else repo.get_target(a.target_id) if a.command=="target" else repo.query_senses(query=a.query,limit=a.limit)
print(json.dumps(result,ensure_ascii=False,indent=2))
if isinstance(result,dict) and result.get("status")=="failed":raise SystemExit(1)
