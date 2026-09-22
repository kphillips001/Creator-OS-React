from types import SimpleNamespace
import pytest
from app.services.fanvue_official_client import FanvueOfficialClient,FanvueAPIError

def client(pages):
 c=FanvueOfficialClient(901,oauth=SimpleNamespace())
 c.list_media_links=lambda *,page:pages[page-1]
 return c

def page(n,data,more):return {'data':data,'pagination':{'page':n,'hasMore':more}}
def link(uuid='one',price=999):return {'uuid':uuid,'price':price,'mediaUuids':['media']}

def test_search_finishes_after_match_and_exposes_ambiguity():
 c=client([page(1,[link()],True),page(2,[link('two')],False)])
 assert len(c.find_equivalent_media_link(['media'],999))==2

@pytest.mark.parametrize('pages',[
 [{'data':[]}],
 [page(1,[],True)],
 [page(2,[],False)],
 [page(1,[link()],True),page(1,[link()],False)],
 [page(1,[link()],True),page(2,[link()],False)],
 [{'data':[],'pagination':{'page':1,'hasMore':'false'}}],
])
def test_incomplete_inventory_never_returns_absence(pages):
 with pytest.raises(FanvueAPIError):client(pages).find_equivalent_media_link(['media'],999)

def test_page_limit_fails_closed():
 c=client([page(n,[link(str(n))],True) for n in range(1,101)])
 with pytest.raises(FanvueAPIError):c.find_equivalent_media_link(['media'],999)

def test_complete_empty_inventory():
 assert client([page(1,[],False)]).find_equivalent_media_link(['media'],999)==[]

def test_later_page_transport_error_propagates_even_after_match():
 c=client([page(1,[link()],True)])
 with pytest.raises(IndexError):c.find_equivalent_media_link(['media'],999)
