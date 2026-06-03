"""FastAPI 服务启动入口。"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
import sys
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.api.router import api_router
from backend.app.database import async_session_factory, init_db
from backend.app.integrations.feishu_long_conn import long_conn_supervisor
from backend.app.result_store import mark_interrupted_execution_runs
from backend.config import settings


logger = logging.getLogger(__name__)


def _log_development_environment_warning() -> None:
    """提示开发环境默认值的安全边界，避免误用于生产。"""
    if settings.app_env != "development":
        return
    logger.warning(
        "当前 APP_ENV=development，默认 JWT、管理员密码、CORS 与 SVN host "
        "仅适合本地开发；生产部署请设置 APP_ENV=production 并显式配置 "
        "JWT_SECRET_KEY、DEFAULT_SUPER_ADMIN_PASSWORD、CORS_ALLOW_ORIGINS "
        "和 SVN_URL_ALLOWLIST。"
    )


@asynccontextmanager
async def lifespan(application: FastAPI):
    """应用生命周期：初始化数据库后拉起飞书长连接 supervisor。

    启停 supervisor 的异常都仅记日志，避免飞书侧问题阻塞 FastAPI 自身的
    启动 / 关闭：项目校验机器人不可用时，其它接口仍应正常对外服务。
    """
    settings.runtime_dir.mkdir(parents=True, exist_ok=True)
    settings.runtime_upload_dir.mkdir(parents=True, exist_ok=True)
    await init_db()
    async with async_session_factory() as session:
        interrupted_runs = await mark_interrupted_execution_runs(session)
    if interrupted_runs:
        logger.warning(
            "已将 %s 个服务重启前未完成的执行任务标记为失败",
            interrupted_runs,
        )

    long_conn_supervisor.set_session_factory(async_session_factory)
    try:
        await long_conn_supervisor.start_all()
    except Exception:  # noqa: BLE001
        logger.exception(
            "飞书长连接 supervisor 启动失败，FastAPI 仍正常对外服务"
        )

    try:
        yield
    finally:
        try:
            await long_conn_supervisor.stop_all()
        except Exception:  # noqa: BLE001
            logger.exception(
                "飞书长连接 supervisor 关闭异常，已忽略以保证服务退出"
            )


def create_app() -> FastAPI:
    """创建并装配 FastAPI 应用实例。"""
    _log_development_environment_warning()
    application = FastAPI(title=settings.app_name, lifespan=lifespan)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_allow_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(api_router, prefix=settings.api_v1_prefix)
    return application


app = create_app()


def configure_static_frontend(
    application: FastAPI,
    *,
    frontend_dist_dir: Path | None = None,
) -> bool:
    """若存在前端构建产物，则由 FastAPI 托管 SPA 静态资源。"""
    dist_dir = (frontend_dist_dir or settings.frontend_dist_dir).resolve()
    index_file = dist_dir / "index.html"
    if not index_file.is_file():
        return False

    assets_dir = dist_dir / "assets"
    if assets_dir.is_dir():
        application.mount(
            "/assets",
            StaticFiles(directory=assets_dir),
            name="frontend-assets",
        )

    @application.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str) -> FileResponse:
        """返回前端静态文件；未知前端路由回退到 index.html。"""
        guarded_prefixes = (
            settings.api_v1_prefix.strip("/"),
            "docs",
            "openapi.json",
            "health",
        )
        normalized_path = full_path.strip("/")
        if normalized_path.startswith(guarded_prefixes):
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Not Found")

        candidate = (dist_dir / normalized_path).resolve()
        if (
            normalized_path
            and dist_dir in candidate.parents
            and candidate.is_file()
        ):
            return FileResponse(candidate)
        return FileResponse(index_file)

    return True


@app.get("/health", tags=["system"])
def health_check() -> dict[str, Any]:
    """返回服务健康状态，供部署探针与联调环境快速检查。"""
    return {
        "code": 200,
        "msg": "ok",
        "data": {
            "status": "healthy",
            "service": settings.app_name,
        },
    }


configure_static_frontend(app)


if __name__ == "__main__":
    uvicorn.run(app, host=settings.host, port=settings.port)
