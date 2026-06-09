"""API 路由聚合入口。"""

from fastapi import APIRouter

from backend.app.admin.router import router as admin_router
from backend.app.api.ai_api import router as ai_router
from backend.app.api.execute_runs_api import router as execute_runs_router
from backend.app.api.execute_api import router as execute_router
from backend.app.api.feishu_api import router as feishu_router
from backend.app.api.fixed_rules_api import router as fixed_rules_router
from backend.app.api.rule_configs_api import router as rule_configs_router
from backend.app.api.source_api import router as source_router
from backend.app.api.workbench_api import router as workbench_router
from backend.app.auth.router import router as auth_router


api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(admin_router)
api_router.include_router(ai_router)
api_router.include_router(source_router)
api_router.include_router(feishu_router)
api_router.include_router(execute_router)
api_router.include_router(execute_runs_router)
api_router.include_router(fixed_rules_router)
api_router.include_router(rule_configs_router)
api_router.include_router(workbench_router)
