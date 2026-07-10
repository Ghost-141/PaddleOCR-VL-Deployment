from pathlib import Path

from paddlocr_vl.core.config import load_settings


def test_load_settings_defaults(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    for name in (
        "PIPELINE_VERSION", "VLLM_SERVER_URL", "MAX_FILE_SIZE_MB",
        "VLLM_MODEL_NAME", "LAYOUT_MODEL_NAME", "VL_REC_MAX_CONCURRENCY",
        "MAX_PAGES", "DELETE_TEMP_FILES",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PUBLIC_API_KEY", "test-key")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "outputs"))

    settings = load_settings()

    assert settings.pipeline_version == "v1.6"
    assert settings.vllm_server_url == "http://paddleocr-vlm-server:8118/v1"
    assert settings.max_file_size_bytes == 100 * 1024 * 1024
