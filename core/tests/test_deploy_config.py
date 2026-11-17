from pathlib import Path

from django.conf import settings

ROOT = Path(settings.BASE_DIR)


def test_render_checks_livez_and_deploys_after_ci():
    blueprint = (ROOT / "render.yaml").read_text()
    assert "healthCheckPath: /livez/" in blueprint, "/healthz/ would wake the database every check"
    assert "autoDeployTrigger: checksPass" in blueprint
    assert "plan: free" in blueprint
    for secret in ("DATABASE_URL", "GEMINI_API_KEY"):
        block = blueprint.split(f"key: {secret}")[1].split("- key")[0]
        assert "sync: false" in block, f"{secret} must be set in the dashboard, not the repo"


def test_start_script_loads_the_corpus_and_never_blocks_on_embeddings():
    script = (ROOT / "bin" / "start.sh").read_text()
    assert script.index("migrate") < script.index("load_corpus") < script.index("gunicorn")
    assert "embed_corpus" in script and ") &" in script, "embedding must run in the background"
    assert "%(U)s" in script and "%(r)s" not in script, "access log must not record query strings"


def test_heartbeat_pings_livez_only_in_the_real_repo():
    workflow = (ROOT / ".github" / "workflows" / "keep-awake.yml").read_text()
    assert "/livez/" in workflow and "github.repository == 'CUSTIX/Batas'" in workflow


def test_env_file_is_never_committed_or_baked_in():
    assert ".env" in (ROOT / ".gitignore").read_text().split()
    assert ".env" in (ROOT / ".dockerignore").read_text().split()
