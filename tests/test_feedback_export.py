import argparse
import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('feedback_export',Path(__file__).resolve().parents[1]/'scripts/extract-open-feedback.py')
export=importlib.util.module_from_spec(spec);spec.loader.exec_module(export)

def test_feedback_without_images_is_deduplicated_and_not_closed(tmp_path,monkeypatch):
    calls=[];tid='abcd1234'
    def request(method,url,**kwargs):
        calls.append((method,url))
        return {'items':[{'id':tid}]} if 'page_size=' in url else {'id':tid,'content':'纯文字反馈','images':[],'messages':[]}
    monkeypatch.setattr(export,'resolve_auth',lambda *_:'test-only')
    monkeypatch.setattr(export,'http_json',request)
    args=argparse.Namespace(env_file='',api='https://example.invalid',status='open',page_size=500,id=None,out=str(tmp_path/'images'),md=str(tmp_path/'support.md'),close=False)
    assert export.extract(args)[2]==1
    assert export.extract(args)[2]==0
    assert len((tmp_path/'support.md').read_text().split('纯文字反馈'))==2
    assert not any(method=='PATCH' for method,_ in calls)

def test_failed_image_export_does_not_close_ticket(tmp_path,monkeypatch):
    import pytest
    closed=[]
    monkeypatch.setattr(export,'resolve_auth',lambda *_:'test-only')
    monkeypatch.setattr(export,'http_json',lambda method,url,**kw:{'items':[{'id':'abcd'}]} if 'page_size=' in url else {'content':'image','images':['/image/1']})
    monkeypatch.setattr(export,'download_images',lambda *args:(_ for _ in ()).throw(OSError('download failed')))
    monkeypatch.setattr(export,'close_tickets',lambda *args:closed.append(args))
    args=argparse.Namespace(env_file='',api='https://example.invalid',status='open',page_size=500,id=None,out=str(tmp_path/'images'),md=str(tmp_path/'support.md'),close=True)
    with pytest.raises(OSError):export.extract(args)
    assert not closed and not (tmp_path/'support.md').exists()
