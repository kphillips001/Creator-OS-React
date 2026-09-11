from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api import customers

def item(**overrides):
    value={"customerId":"commerce:00000000-0000-0000-0000-000000000042","displayName":"Avery","username":"avery","isBuyer":True,"subscriptionStatus":"ACTIVE","isHighValue":False,"activeSalesSession":False,"totalSpendMinor":4200,"hasTelegramRelationship":False,"localFanvueUserId":None}
    value.update(overrides); return value

class Workspace:
    def list_customers(self,**_): return (item(),item(customerId="commerce:00000000-0000-0000-0000-000000000043",displayName="Morgan",isBuyer=False,subscriptionStatus="NONE"))
    def get_customer(self,customer_id,**_): return item() if customer_id.endswith("42") else None
    def customer_identity(self,*_args,**_kwargs): return None
    def summarize(self,values):
        values=tuple(values); return {"total":len(values),"buyers":sum(v["isBuyer"] for v in values),"activeSubscribers":sum(v["subscriptionStatus"]=="ACTIVE" for v in values),"formerSubscribers":0,"highValue":0,"activeSessions":0}

def client(monkeypatch):
    workspace=Workspace(); monkeypatch.setattr(customers,"_current_account_id",lambda:7); monkeypatch.setattr(customers,"_workspace_service",lambda:workspace)
    app=FastAPI(); app.include_router(customers.router); return TestClient(app)

def test_lists_verified_customers_with_search_and_buyer_filter(monkeypatch):
    response=client(monkeypatch).get("/api/v1/customers?search=avery&filter=buyers")
    assert response.status_code==200
    assert [row["displayName"] for row in response.json()["items"]]==["Avery"]

def test_subscriber_filter(monkeypatch):
    response=client(monkeypatch).get("/api/v1/customers?filter=subscribers")
    assert response.status_code==200
    assert [row["displayName"] for row in response.json()["items"]]==["Avery"]

def test_returns_json_detail_and_not_found(monkeypatch):
    api=client(monkeypatch)
    assert api.get("/api/v1/customers/commerce:00000000-0000-0000-0000-000000000042").status_code==200
    assert api.get("/api/v1/customers/commerce:00000000-0000-0000-0000-000000000099").status_code==404

def test_rejects_unknown_filter(monkeypatch):
    assert client(monkeypatch).get("/api/v1/customers?filter=test-identities").status_code==422
