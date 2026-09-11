import json

from app.services.generation_request_diagnostic_service import GenerationRequestDiagnosticService


def test_records_supported_trace_and_redacts_secrets(tmp_path):
    service = GenerationRequestDiagnosticService()
    service.storage_path = tmp_path / "traces.json"
    service.record(
        trace_id="trace-1", workflow_origin="manual_creative_concept",
        stage="final_seedream_payload",
        value={"prompt": "safe", "authorization": "secret", "api_key": "secret"},
    )
    trace = json.loads(service.storage_path.read_text(encoding="utf-8"))["trace-1"]
    assert trace["workflowOrigin"] == "manual_creative_concept"
    assert trace["events"][0]["value"] == {
        "prompt": "safe", "authorization": "[REDACTED]", "api_key": "[REDACTED]",
    }


def test_ignores_out_of_scope_workflow(tmp_path):
    service = GenerationRequestDiagnosticService()
    service.storage_path = tmp_path / "traces.json"
    service.record(trace_id="trace-1", workflow_origin="photoshoot",
                   stage="final_seedream_payload", value={"prompt": "safe"})
    assert not service.storage_path.exists()


def test_records_recreate_with_ava_trace(tmp_path):
    service = GenerationRequestDiagnosticService()
    service.storage_path = tmp_path / "traces.json"
    service.record(
        trace_id="recreate-trace", workflow_origin="recreate_with_ava",
        stage="11_ordered_provider_reference_images",
        value=["https://cdn.test/asset-93.png"],
    )
    trace = json.loads(service.storage_path.read_text(encoding="utf-8"))["recreate-trace"]
    assert trace["workflowOrigin"] == "recreate_with_ava"
    assert trace["events"][0]["stage"] == "11_ordered_provider_reference_images"
