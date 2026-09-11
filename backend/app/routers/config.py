import os

from fastapi import APIRouter, Depends

from .. import security
from ..userconfig import ENV_PATH, read_env_value, write_env_value

router = APIRouter(prefix="/api/config", tags=["config"])

# 安装版里程序目录（Program Files）只读，用户级配置一律写到数据目录下的 .env，
# 该文件在 app.config 里以 override 方式加载，优先级高于程序目录的 .env
LLM_KEYS = ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL")


@router.get("/llm")
def get_llm_config(user: str = Depends(security.get_current_user)):
    """读取当前 LLM 配置（从环境变量优先，回退 .env 文件）。"""
    return {k: os.environ.get(k) or read_env_value(k, "") for k in LLM_KEYS}


@router.post("/llm")
def set_llm_config(req: dict, user: str = Depends(security.get_current_user)):
    """保存 LLM 配置到 .env 并热更新到当前进程环境变量，即时生效。"""
    for k in LLM_KEYS:
        v = req.get(k)
        if v is None:
            continue
        write_env_value(k, v.strip())
    return {"ok": True, "config": {k: os.environ.get(k, "") for k in LLM_KEYS}}
