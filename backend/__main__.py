import argparse
import asyncio
import json
import logging
from .config import Settings

async def worker(settings,once):
    from .app import Services
    from .store import uid
    svc=Services(settings);id=uid()
    try:
        while True:
            worked=await svc.generator.run_one(id)
            if once:return
            if not worked:await asyncio.sleep(1)
    finally:
        if hasattr(svc.provider,'close'):await svc.provider.close()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['serve','worker','validate','contracts'])
    parser.add_argument('--once',action='store_true');parser.add_argument('--port',type=int,default=8083)
    parser.add_argument('--host',default='127.0.0.1');args=parser.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(name)s %(levelname)s %(message)s')
    if args.command=='serve':
        import uvicorn
        from .app import create_app
        uvicorn.run(create_app(),host=args.host,port=args.port,log_level='info')
    elif args.command=='worker':asyncio.run(worker(Settings(),args.once))
    elif args.command=='validate':
        from modules.curriculum import CurriculumRepository
        print(json.dumps(CurriculumRepository(Settings().workspace).validate(),ensure_ascii=False,indent=2))
    else:
        from .contracts import CONTRACTS
        print(json.dumps({k:v.model_json_schema() for k,v in CONTRACTS.items()},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
