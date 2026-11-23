from fastapi.testclient import TestClient


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["database"] == "ok"
    assert payload["version"]
    platforms = {entry["platform"] for entry in payload["providers"]}
    assert platforms == {"youtube", "facebook"}


def test_health_reports_separate_capabilities(client: TestClient) -> None:
    payload = client.get("/api/v1/health").json()
    for provider in payload["providers"]:
        assert set(provider) >= {
            "url_validation",
            "metadata_inspection",
            "authorized_download",
            "fully_functional",
        }
        assert provider["fully_functional"] is False
        assert provider["authorized_download"]["status"] == "not_implemented"
        assert provider["url_validation"]["status"] == "available"
