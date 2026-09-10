import os

from dotenv import set_key
from fastapi import APIRouter, Depends

from .. import security
from ..config import EXE_DIR

router = APIRouter(prefix="/api/config", tags=["config"])

ENV_PATH = os.path.join(EXE_DIR, ".env")
LLM_KEYS = ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL")


def _read_env():
    if not os.path.exists(ENV_PATH):
        return {}
    cfg = {}
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip()
    return cfg


@router.get("/llm")
def get_llm_config(user: str = Depends(security.get_current_user)):
    """读取当前 LLM 配置（从环境变量优先，回退 .env 文件）。"""
    return {k: os.environ.get(k, _read_env().get(k, "")) for k in LLM_KEYS}


@router.post("/llm")
def set_llm_config(req: dict, user: str = Depends(security.get_current_user)):
    """保存 LLM 配置到 .env 并热更新到当前进程环境变量，即时生效。"""
    for k in LLM_KEYS:
        v = req.get(k)
        if v is None:
            continue
        v = v.strip()
        os.environ[k] = v
        set_key(ENV_PATH, k, v)
    return {"ok": True, "config": {k: os.environ.get(k, "") for k in LLM_KEYS}}
