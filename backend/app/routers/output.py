"""v7.17 货盘导出目录（把生成的 Excel 落到本机指定文件夹）。

设计要点：
- 目录是**运行服务这台电脑**上的目录。客户装桌面端时 = 他自己的电脑，选的就是本地路径；
  同事从局域网浏览器访问时，目录属于那台常驻电脑 —— 接口用 `is_local` 告诉前端，
  前端据此提示「这个目录在运行服务的电脑上」。
- 「在资源管理器里打开」只允许**本机请求**（127.0.0.1），否则会在别人电脑上莫名弹窗。
"""
import os
import re
import string
import subprocess
import sys
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, Request

from .. import security, userconfig as uc

router = APIRouter(prefix="/api/output", tags=["output"])


def _is_local(request: Request) -> bool:
    """请求是否来自本机（桌面端 / 本机浏览器）。"""
    host = (request.client.host if request.client else "") or ""
    return host in ("127.0.0.1", "::1", "localhost")


def _norm(path: str) -> str:
    """规范化路径（不要求已存在）。

    注意 `E:` 这种**盘符相对路径**在 Windows 上表示「E 盘的当前目录」，跟进程工作目录绑定，
    会莫名其妙跳到服务自己的工作目录（实测踩到过）→ 一律补成盘根 `E:\\`。
    """
    p = (path or "").strip().strip('"')
    if not p:
        return ""
    p = os.path.expandvars(os.path.expanduser(p))
    if re.fullmatch(r"[A-Za-z]:", p):
        p += "\\"
    return uc.cap_drive(os.path.normpath(p))


def _parent_of(p: str) -> str:
    """父目录；盘根（`E:\\`）的父级是「此电脑」（空串），不能算成 `E:`。"""
    if re.fullmatch(r"[A-Za-z]:\\?", p):
        return ""
    return os.path.dirname(p.rstrip("\\/"))


def _list_drives():
    """Windows 下枚举可用盘符。"""
    out = []
    if sys.platform == "win32":
        for ch in string.ascii_uppercase:
            root = f"{ch}:\\"
            if os.path.exists(root):
                out.append({"name": root, "path": root})
    return out


def _list_subdirs(path: str):
    """列出目录下的子目录（跳过隐藏/系统目录，忽略无权限项）。"""
    items = []
    try:
        with os.scandir(path) as it:
            for e in it:
                try:
                    if not e.is_dir(follow_symlinks=False):
                        continue
                    name = e.name
                    if name.startswith("$") or name in ("System Volume Information", "Recovery"):
                        continue
                    items.append({"name": name, "path": e.path})
                except OSError:
                    continue
    except (OSError, PermissionError):
        pass
    items.sort(key=lambda x: x["name"].lower())
    return items


@router.get("")
def get_output_config(request: Request, user: str = Depends(security.get_current_user)):
    """读取导出目录配置 + 本机/远端标记。"""
    d = uc.output_dir()
    default = uc.default_output_dir()
    return {
        "enabled": uc.output_save_enabled(),
        "dir": d,
        "default_dir": default,
        "is_default": os.path.normcase(d) == os.path.normcase(default),
        "exists": os.path.isdir(d),
        "is_local": _is_local(request),
        "host": request.client.host if request.client else "",
    }


@router.post("")
def set_output_config(
    req: dict,
    request: Request,
    admin: str = Depends(security.require_admin),
):
    """保存导出目录配置（仅管理员；目录属于运行服务的电脑）。

    `dir` 传空串 = 清掉自定义目录、回到默认目录（前端「恢复默认」也走这条路）；
    不传 `dir` 字段则保持原样，只改 `enabled`。
    """
    if "enabled" in req:
        uc.set_output_save(bool(req.get("enabled")))
    if "dir" in req:
        d = _norm(req.get("dir") or "")
        if d:
            # 目录不存在就尝试建出来；建不了也算配置成功，生成时会报可读错误
            try:
                os.makedirs(d, exist_ok=True)
            except OSError:
                pass
            uc.set_output_dir(d)
        else:
            uc.set_output_dir("")   # 清空 → 下次读配置回落到默认目录
    return get_output_config(request, admin)


@router.get("/browse")
def browse(
    request: Request,
    path: str = "",
    admin: str = Depends(security.require_admin),
):
    """服务端目录浏览：用于「选择文件夹」弹窗。

    不传 path：返回「此电脑」视图（盘符列表 + 默认目录）。
    传 path：返回该目录的子目录、上级目录。
    """
    p = _norm(path)
    if not p or not os.path.isdir(p):
        d = uc.default_output_dir()
        return {
            "path": "",
            "parent": "",
            "at_root": True,
            "drives": _list_drives(),
            "dirs": [],
            "suggest": d,
            "suggest_exists": os.path.isdir(d),
            "is_local": _is_local(request) if request else True,
        }
    parent = _parent_of(p)
    return {
        "path": p,
        "parent": parent,
        "at_root": False,
        "drives": [],
        "dirs": _list_subdirs(p),
        "suggest": "",
        "suggest_exists": False,
        "is_local": _is_local(request),
        "writable": os.access(p, os.W_OK),
    }


@router.post("/mkdir")
def mkdir(
    req: dict,
    admin: str = Depends(security.require_admin),
):
    """在指定父目录下新建文件夹。"""
    parent = _norm(req.get("parent") or "")
    name = (req.get("name") or "").strip()
    if not parent or not os.path.isdir(parent):
        raise HTTPException(status_code=400, detail="父目录不存在")
    if not name or any(c in name for c in '\\/:*?"<>|'):
        raise HTTPException(status_code=400, detail="文件夹名称不合法")
    target = os.path.join(parent, name)
    if os.path.exists(target):
        raise HTTPException(status_code=400, detail="同名文件夹已存在")
    try:
        os.makedirs(target)
    except OSError as e:
        raise HTTPException(status_code=400, detail=f"创建失败：{e}")
    return {"ok": True, "path": target}


@router.post("/open")
def open_in_explorer(
    req: dict,
    request: Request,
    user: str = Depends(security.get_current_user),
):
    """在资源管理器里打开目录（或选中某个文件）。

    仅限本机请求：远端同事点这个按钮，会在**服务所在电脑**上弹窗，没有意义且吓人。
    """
    if not _is_local(request):
        raise HTTPException(
            status_code=403,
            detail="这个目录在运行服务的电脑上，请在运行服务的电脑上打开",
        )
    raw = _norm(req.get("path") or "")
    if not raw:
        raise HTTPException(status_code=400, detail="路径为空")
    if not os.path.exists(raw):
        raise HTTPException(status_code=404, detail="路径不存在（可能已被移动或删除）")

    try:
        if os.path.isdir(raw):
            os.startfile(raw)          # noqa: S606 - Windows 专用，打开文件夹
        else:
            subprocess.Popen(["explorer", "/select,", raw])   # 打开所在目录并选中该文件
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"打开失败：{e}")
    return {"ok": True, "path": raw}


def save_plan_file(buf, file_name: str, prefer_path: str = ""):
    """把生成的 Excel 写到导出目录，返回落盘路径（失败/未开启则返回 None）。

    同名不覆盖：自动追加 (1)、(2)…，避免同一天生成多个「新货盘」互相盖掉。
    `prefer_path`：重新下载历史货盘时传上次的落盘路径 —— 直接覆盖同一个文件
    （否则每点一次「下载」就多一份 (1)(2)(3)）；文件被占用/移走时自动回退到新增文件。
    """
    data = buf.getvalue() if hasattr(buf, "getvalue") else buf
    if not uc.output_save_enabled():
        return None
    if prefer_path:
        try:
            if os.path.isfile(prefer_path):
                with open(prefer_path, "wb") as f:
                    f.write(data)
                return prefer_path
        except OSError:
            pass   # 文件被 Excel 打开占用等 → 回退到另存一份
    d = uc.output_dir()
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        return None
    base = os.path.basename((file_name or "货盘").strip()) or "货盘"
    if not base.lower().endswith(".xlsx"):
        base += ".xlsx"
    stem, ext = os.path.splitext(base)
    target = os.path.join(d, base)
    i = 1
    while os.path.exists(target):
        target = os.path.join(d, f"{stem} ({i}){ext}")
        i += 1
    try:
        with open(target, "wb") as f:
            f.write(data)
    except OSError:
        return None
    return target


def saved_path_header(path: str) -> dict:
    """把落盘路径塞进响应头（含中文，需 URL 编码）回传给前端。"""
    if not path:
        return {}
    return {
        "X-Saved-Path": urllib.parse.quote(path),
        "Access-Control-Expose-Headers": "X-Saved-Path",
    }
