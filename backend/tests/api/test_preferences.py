VALID = {
    "titles": ["Backend Engineer", "backend engineer ", "Python Developer"],
    "keywords": ["fastapi"],
    "locations": [{"city": "Bengaluru", "country": "in"}, {"city": None, "country": "DE"}],
    "work_modes": ["remote", "hybrid"],
}


async def test_preferences_round_trip_and_dedupe(alice):
    _, client = alice
    assert (await client.get("/api/preferences")).status_code == 404
    saved = await client.put("/api/preferences", json=VALID)
    assert saved.status_code == 200
    body = (await client.get("/api/preferences")).json()
    assert body["titles"] == ["Backend Engineer", "Python Developer"]
    assert body["locations"][0] == {"city": "Bengaluru", "country": "IN"}
    assert body["work_modes"] == ["remote", "hybrid"]


async def test_preferences_need_a_title_and_work_mode(alice):
    _, client = alice
    for missing in ("titles", "work_modes"):
        body = dict(VALID, **{missing: []})
        assert (await client.put("/api/preferences", json=body)).status_code == 422


async def test_global_preferences_allow_empty_or_omitted_locations(alice):
    _, client = alice
    body = dict(VALID, locations=[])
    saved = await client.put("/api/preferences", json=body)
    assert saved.status_code == 200
    assert saved.json()["locations"] == []
    del body["locations"]
    assert (await client.put("/api/preferences", json=body)).status_code == 200
    assert (await client.get("/api/preferences")).json()["locations"] == []


async def test_unknown_work_mode_is_rejected(alice):
    _, client = alice
    body = dict(VALID, work_modes=["sometimes"])
    assert (await client.put("/api/preferences", json=body)).status_code == 422


async def test_preferences_are_private(alice, bob):
    _, client = alice
    _, bob_client = bob
    await client.put("/api/preferences", json=VALID)
    assert (await bob_client.get("/api/preferences")).status_code == 404


async def test_saving_preferences_completes_onboarding(alice):
    _, client = alice
    await client.put("/api/preferences", json=VALID)
    assert (await client.get("/api/me")).json()["onboarding"]["preferences_set"] is True
