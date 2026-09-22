def test_complete_schema_certification():
 from app.services.schema_manager_service import SchemaManagerService
 result=SchemaManagerService().certify()
 assert result.status=='PASS',str(result.drift)
