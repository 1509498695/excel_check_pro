"""管理后台请求/响应模型。"""

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreateRequest(BaseModel):
    """创建项目请求。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    description: str = ""


class ProjectUpdateRequest(BaseModel):
    """更新项目请求。"""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None


class SetMemberRoleRequest(BaseModel):
    """设置成员角色请求。"""

    model_config = ConfigDict(extra="forbid")

    role: str = Field(pattern="^(admin|user)$")


class MoveMemberProjectRequest(BaseModel):
    """调整普通用户归属项目请求。"""

    model_config = ConfigDict(extra="forbid")

    target_project_id: int


class ResetUserPasswordRequest(BaseModel):
    """超级管理员重置指定用户登录密码。"""

    model_config = ConfigDict(extra="forbid")

    new_password: str = Field(min_length=4, max_length=128)


class FeishuBotConfigUpdateRequest(BaseModel):
    """更新或创建项目级飞书机器人配置请求。

    字段语义：
    - app_id：飞书自建应用 App ID，必填，写库前会 strip 后再做非空校验。
    - app_secret：传 None 表示保持原值；首次创建时必须显式传入；不允许传空串。
    - default_chat_id：默认推送群 chat_id，None 保持原值，"" 表示清空。
    - allowed_open_ids：触发指令的 open_id 白名单原文（前端按行/逗号拆分输入），
      None 保持原值，"" 表示清空。
    - local_download_roots / svn_download_roots：机器人下载根目录原文（前端按行输入），
      None 保持原值，"" 表示清空。
    - allowed_download_suffixes：允许下载的文件后缀原文（逗号 / 换行分隔），
      None 保持原值，"" 表示恢复默认。
    """

    model_config = ConfigDict(extra="forbid")

    app_id: str = Field(min_length=1, max_length=64)
    app_secret: str | None = Field(default=None, max_length=256)
    default_chat_id: str | None = Field(default=None, max_length=128)
    allowed_open_ids: str | None = Field(default=None, max_length=2048)
    local_download_roots: str | None = Field(default=None, max_length=4096)
    svn_download_roots: str | None = Field(default=None, max_length=4096)
    allowed_download_suffixes: str | None = Field(default=None, max_length=1024)


class FeishuBotTestSendRequest(BaseModel):
    """飞书机器人测试发送请求。"""

    model_config = ConfigDict(extra="forbid")

    chat_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=4000)
    use_card: bool = False
