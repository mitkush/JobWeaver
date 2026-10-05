import httpx

from app.main import create_app


async def test_spa_serves_files_and_falls_back_but_not_for_api(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "index.html").write_text("<html>app</html>")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    app = create_app(frontend_dist=tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        assert (await client.get("/assets/app.js")).text == "console.log(1)"
        assert (await client.get("/favicon.svg")).text == "<svg/>"
        assert (await client.get("/onboarding/review")).text == "<html>app</html>"
        assert (await client.get("/%2e%2e/etc/passwd")).text == "<html>app</html>"
        missing = await client.get("/api/does-not-exist")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "not_found"
