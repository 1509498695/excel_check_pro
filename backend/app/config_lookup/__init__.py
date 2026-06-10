"""配置表查询核心服务包。"""

from backend.app.config_lookup.schemas import ConfigLookupRequest, ConfigLookupResponse
from backend.app.config_lookup.service import lookup_config_table

__all__ = ["ConfigLookupRequest", "ConfigLookupResponse", "lookup_config_table"]
