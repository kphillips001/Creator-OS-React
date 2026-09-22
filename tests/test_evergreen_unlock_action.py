from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from app.api import private_chat_unlock as api

@pytest.fixture
def client(monkeypatch):
 monkeypatch.setenv('EVERGREEN_UNLOCK_ENABLED','true');calls=[]
 class Gateway:
  def resolve_alias(self,alias):calls.append(alias);return 'https://www.fanvue.com/media-link/test'
  def resolve(self,alias):return self.resolve_alias(alias)
 monkeypatch.setattr(api,'PrivateChatUnlockGatewayService',Gateway)
 app=FastAPI();app.include_router(api.public_alias_router);app.include_router(api.router)
 return TestClient(app,base_url='https://unlock.example.test'),calls

@pytest.mark.parametrize('path',['/u/'+'A'*22,'/api/v1/commerce/unlock/'+'B'*64])
@pytest.mark.parametrize('headers',[{}, {'User-Agent':'Mozilla/5.0','Sec-Fetch-Mode':'navigate','Sec-Fetch-Dest':'document','Sec-Fetch-User':'?1','Sec-Fetch-Site':'cross-site'}])
def test_navigation_redirects_immediately_without_form_cookie_or_second_action(client,path,headers):
 browser,calls=client;r=browser.get(path,headers=headers,follow_redirects=False)
 assert r.status_code==302 and len(calls)==1
 assert r.headers['location']=='https://www.fanvue.com/media-link/test'
 assert r.headers['cache-control']=='no-store' and 'set-cookie' not in r.headers
 assert 'Continue to checkout' not in r.text and '<form' not in r.text

@pytest.mark.parametrize('headers',[
 {'User-Agent':'TelegramBot (like TwitterBot)'},{'User-Agent':'Googlebot'},
 {'User-Agent':'Mozilla/5.0','Sec-Purpose':'prefetch;prerender'},
 {'User-Agent':'Mozilla/5.0','Purpose':'prefetch'},
 {'User-Agent':'Mozilla/5.0','Sec-Fetch-Mode':'no-cors','Sec-Fetch-Dest':'image'},
 {'User-Agent':'Mozilla/5.0','Sec-Fetch-Mode':'cors'},
 {'User-Agent':'Mozilla/5.0','Sec-Fetch-User':'?0'},
 {'User-Agent':'facebookexternalhit/1.1'}, {'X-Moz':'prefetch'},
 {'User-Agent':'generic crawler'}, {'User-Agent':'Discordbot'},
])
def test_preview_never_constructs_gateway(client,headers):
 browser,calls=client;r=browser.get('/u/'+'A'*22,headers=headers,follow_redirects=False)
 assert r.status_code==204 and not calls and not r.content and 'location' not in r.headers

@pytest.mark.parametrize('method',['head','post','options'])
def test_non_get_has_no_commercial_mutation(client,method):
 browser,calls=client;r=getattr(browser,method)('/u/'+'A'*22,follow_redirects=False)
 assert r.status_code==(204 if method=='head' else 405);assert not calls

def test_fail_closed_errors_no_redirect(client,monkeypatch):
 browser,calls=client
 class Gateway:
  def resolve_alias(self,alias):raise api.UnlockUnavailableError('Unavailable',reason_code='REVOKED')
 monkeypatch.setattr(api,'PrivateChatUnlockGatewayService',Gateway)
 r=browser.get('/u/'+'A'*22,follow_redirects=False)
 assert r.status_code==409 and 'location' not in r.headers

def test_operational_pause_does_not_fall_back_to_mutating_legacy_get(monkeypatch):
 from app.services.private_chat_unlock_gateway_service import PrivateChatUnlockGatewayService,UnlockUnavailableError
 monkeypatch.setenv('EVERGREEN_UNLOCK_ENABLED','true');monkeypatch.setenv('EVERGREEN_UNLOCK_PAUSED','true')
 def forbidden():raise AssertionError('Paused checkout accessed persistence')
 with pytest.raises(UnlockUnavailableError) as caught:PrivateChatUnlockGatewayService(connection_factory=forbidden).resolve_alias('A'*22)
 assert caught.value.reason_code=='CHECKOUT_PAUSED'
