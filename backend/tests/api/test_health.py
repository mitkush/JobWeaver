async def test_health_does_not_need_auth_or_db(anon):
    response = await anon.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
