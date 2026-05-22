"""飞书机器人长连接 supervisor 与事件分发。

设计要点
========

- 仅作用于项目校验侧：被识别为「项目校验」的群指令会触发
  :func:`backend.app.fixed_rules.service.execute_fixed_rules_for_project`，
  并把结果以富文本卡片形式回写到原始群。个人校验入口完全不受影响。
- 走 ``lark-oapi`` 长连接（WebSocket），不再走 HTTP 事件回调。
  考虑到 ``lark_oapi.ws.Client`` 没有 builder、``start()`` 阻塞且
  依赖模块级 ``loop`` 单例（v2_main 当前实现），这里采用 **绕过 start()**
  的方案：复用 FastAPI 主事件循环，直接驱动 SDK 的 ``_connect`` /
  ``_ping_loop`` / ``_disconnect`` 私有协程。这样多项目可以同进程并发，
  不再被「one-loop-one-client」限制。
- 本模块只负责状态机 + 事件分发；FastAPI lifespan 接入由 Step 3 完成。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Iterable, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import lark_oapi as lark

from backend.app.fixed_rules.service import execute_fixed_rules_for_project
from backend.app.integrations.feishu_bot import (
    FeishuApiError,
    invalidate_token_cache,
    send_card_to_chat,
    send_file_to_chat,
    send_text_to_chat,
)
from backend.app.integrations.feishu_download import (
    DEFAULT_DOWNLOAD_SUFFIXES,
    extract_download_path,
    parse_json_string_list,
    resolve_download_file,
)
from backend.app.models import FeishuBotConfigRecord
from backend.app.security.crypto import decrypt_secret
from backend.config import settings


logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# 常量
# --------------------------------------------------------------------------- #

PROJECT_CHECK_COMMAND = "项目校验"
_USER_MENTION_COMMAND_PATTERN = re.compile(r"@_user_\d+\s*项目校验")
_CARD_PREVIEW_LIMIT = 5
_FORBIDDEN_REPLY = "当前用户无项目校验执行权限"
_STARTED_REPLY = f"{PROJECT_CHECK_COMMAND}已开始执行，请稍候…"
_DOWNLOAD_STARTED_REPLY = "配置文件下载已开始，正在更新并准备文件…"
_DOWNLOAD_USAGE_REPLY = "请按格式发送：@机器人 下载 <文件路径>"
_DOWNLOAD_UNCONFIGURED_REPLY = "后台尚未配置可下载根目录，请先配置本地或 SVN 下载根目录。"

ConnectionState = Literal["inactive", "active", "error", "reconnecting"]


# --------------------------------------------------------------------------- #
# 通用 helper：兼容 dict / SimpleNamespace / Pydantic-like 对象
# --------------------------------------------------------------------------- #


def _get_attr_or_key(obj: Any, key: str, default: Any = None) -> Any:
    """优先按属性读，再按 dict key 读，找不到返回 default。"""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    if hasattr(obj, key):
        value = getattr(obj, key)
        return value if value is not None else default
    return default


# --------------------------------------------------------------------------- #
# 纯函数（无 supervisor 依赖，易单测）
# --------------------------------------------------------------------------- #


def matches_project_check_command(text: str) -> bool:
    """判断消息文本是否触发项目校验指令。

    支持两种形式：
    1. 纯文本「项目校验」（前后允许空白）。
    2. 群里 @ 机器人后跟「项目校验」，飞书会把 @ 渲染成 ``@_user_xxx``。
    """
    if not isinstance(text, str):
        return False
    stripped = text.strip()
    if stripped == PROJECT_CHECK_COMMAND:
        return True
    return bool(_USER_MENTION_COMMAND_PATTERN.search(stripped))


def extract_sender_open_id(event: Any) -> str:
    """从飞书事件中提取发送者 open_id；缺失返回空串。"""
    inner = _get_attr_or_key(event, "event")
    sender = _get_attr_or_key(inner, "sender")
    sender_id = _get_attr_or_key(sender, "sender_id")
    open_id = _get_attr_or_key(sender_id, "open_id")
    return str(open_id) if open_id else ""


def parse_allowed_open_ids(raw: str) -> list[str]:
    """把 admin 落库的逗号 / 换行分隔字符串解析成 open_id 列表。

    与 :mod:`backend.app.admin.router` 中 ``_parse_allowed_open_ids`` /
    ``_normalize_allowed_open_ids_input`` 行为保持一致：strip → 去空 →
    去重保序。
    """
    if not raw:
        return []
    seen: set[str] = set()
    result: list[str] = []
    for chunk in raw.replace("\r", "\n").split("\n"):
        for piece in chunk.split(","):
            normalized = piece.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
    return result


def translate_execution_error(exc: BaseException) -> str:
    """把 execute_fixed_rules_for_project 抛出的异常翻译成给群里看的中文。"""
    if isinstance(exc, ValueError):
        return f"项目校验失败：{exc}"
    if isinstance(exc, FileNotFoundError):
        return f"项目校验失败：依赖文件不存在（{exc}）"
    if isinstance(exc, ImportError):
        return "项目校验失败：服务端依赖加载异常，请联系管理员"
    if isinstance(exc, NotImplementedError):
        return "项目校验失败：当前环境不支持该操作（如未安装 svn）"
    return f"项目校验执行失败：{exc}"


def translate_download_error(exc: BaseException) -> str:
    """把下载链路异常翻译成给群里看的中文。"""
    if isinstance(exc, FeishuApiError):
        return f"配置文件发送失败：{exc}"
    if isinstance(exc, FileNotFoundError):
        return f"配置文件下载失败：{exc}"
    if isinstance(exc, NotImplementedError):
        return f"配置文件下载失败：{exc}"
    if isinstance(exc, ValueError):
        return f"配置文件下载失败：{exc}"
    return f"配置文件下载失败：{exc}"


def format_int(value: Any) -> str:
    """把整数 / 浮点 / 数字字符串规范化成纯整数字符串。"""
    if value is None:
        return "0"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        try:
            return str(int(value))
        except (OverflowError, ValueError):
            return str(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return "0"
    try:
        return str(int(float(text)))
    except ValueError:
        return text


def build_project_check_card(
    *,
    project_id: int,
    project_name: str,
    summary: dict[str, Any],
    platform_url: str,
) -> dict[str, Any]:
    """根据 execute_fixed_rules_for_project 的返回值构建结果卡片。

    - 标题：``[项目名] 项目校验完成``。
    - 顶部一组双列字段：异常总数 / 扫描行数 / 耗时 / 失败数据源数。
    - 异常清单与失败数据源清单：分别裁到 ``_CARD_PREVIEW_LIMIT`` 条，
      多余的部分加一行 ``…更多 N 条…``。
    - ``platform_url`` 为空时不渲染「查看完整结果」按钮，避免落地页未上线
      时给用户一个无效跳转。
    """
    abnormal_results = list(summary.get("abnormal_results") or [])
    failed_sources = list(summary.get("failed_sources") or [])
    total_rows = summary.get("total_rows_scanned") or 0
    elapsed_ms = summary.get("execution_time_ms") or 0

    elements: list[dict[str, Any]] = [
        {
            "tag": "div",
            "fields": [
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**异常总数**：{len(abnormal_results)}",
                    },
                },
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**扫描行数**：{format_int(total_rows)}",
                    },
                },
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**耗时**：{format_int(elapsed_ms)} 毫秒",
                    },
                },
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**失败数据源**：{len(failed_sources)}",
                    },
                },
            ],
        }
    ]

    if abnormal_results:
        elements.append({"tag": "hr"})
        preview = abnormal_results[:_CARD_PREVIEW_LIMIT]
        lines: list[str] = ["**异常预览**"]
        for item in preview:
            rule_name = (item.get("rule_name") or "未命名规则") if isinstance(item, dict) else "未命名规则"
            location = (item.get("location") or "") if isinstance(item, dict) else ""
            message = (item.get("message") or "") if isinstance(item, dict) else ""
            suffix = f"：{message}" if message else ""
            lines.append(f"- **{rule_name}** {location}{suffix}".strip())
        if len(abnormal_results) > _CARD_PREVIEW_LIMIT:
            lines.append(f"…更多 {len(abnormal_results) - _CARD_PREVIEW_LIMIT} 条…")
        elements.append(
            {"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}}
        )

    if failed_sources:
        elements.append({"tag": "hr"})
        preview_sources = failed_sources[:_CARD_PREVIEW_LIMIT]
        lines = ["**失败数据源**"]
        for src in preview_sources:
            if isinstance(src, dict):
                sid = src.get("source_id") or src.get("id") or ""
                err = src.get("error") or src.get("message") or ""
            else:
                sid = str(src)
                err = ""
            line = f"- {sid}" if not err else f"- {sid}：{err}"
            lines.append(line)
        if len(failed_sources) > _CARD_PREVIEW_LIMIT:
            lines.append(f"…更多 {len(failed_sources) - _CARD_PREVIEW_LIMIT} 条…")
        elements.append(
            {"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}}
        )

    if platform_url:
        elements.append({"tag": "hr"})
        elements.append(
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "查看完整结果"},
                        "type": "primary",
                        "url": platform_url,
                    }
                ],
            }
        )

    return {
        "header": {
            "title": {
                "tag": "plain_text",
                "content": f"[{project_name}] 项目校验完成",
            }
        },
        "elements": elements,
    }


# --------------------------------------------------------------------------- #
# 事件分发协程
# --------------------------------------------------------------------------- #


def _resolve_platform_url(project_id: int) -> str:
    """读取设置中的项目校验落地页前缀；未配置返回空串。

    Step 5 会把 ``feishu_bot_platform_url`` 加回 settings；本步先用 getattr
    兜底，避免引入不必要的 settings 依赖。
    """
    base = getattr(settings, "feishu_bot_platform_url", "") or ""
    base = str(base).strip()
    if not base:
        return ""
    if "{project_id}" in base:
        return base.format(project_id=project_id)
    if base.endswith("/"):
        return f"{base}{project_id}"
    return f"{base}/{project_id}"


async def _safe_send_text(
    db: AsyncSession,
    project_id: int,
    chat_id: str,
    text: str,
) -> None:
    """发送纯文本消息；任何 FeishuApiError 仅记日志，避免反馈链中断。"""
    try:
        await send_text_to_chat(db=db, project_id=project_id, chat_id=chat_id, text=text)
    except FeishuApiError:
        logger.exception(
            "飞书 send_text_to_chat 失败 project_id=%s chat_id=%s",
            project_id,
            chat_id,
        )


async def _safe_send_card(
    db: AsyncSession,
    project_id: int,
    chat_id: str,
    card: dict[str, Any],
) -> None:
    """发送富文本卡片消息；任何 FeishuApiError 仅记日志。"""
    try:
        await send_card_to_chat(db=db, project_id=project_id, chat_id=chat_id, card=card)
    except FeishuApiError:
        logger.exception(
            "飞书 send_card_to_chat 失败 project_id=%s chat_id=%s",
            project_id,
            chat_id,
        )


async def _handle_download_command(
    db: AsyncSession,
    project_id: int,
    chat_id: str,
    requested_path: str,
) -> None:
    """解析下载路径、更新 SVN 工作副本并把文件发送回原群。"""
    if not requested_path:
        await _safe_send_text(db, project_id, chat_id, _DOWNLOAD_USAGE_REPLY)
        return

    result = await db.execute(
        select(FeishuBotConfigRecord).where(
            FeishuBotConfigRecord.project_id == project_id
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        await _safe_send_text(db, project_id, chat_id, _DOWNLOAD_UNCONFIGURED_REPLY)
        return

    local_roots = parse_json_string_list(record.local_download_roots)
    svn_roots = parse_json_string_list(record.svn_download_roots)
    allowed_suffixes = parse_json_string_list(
        record.allowed_download_suffixes,
        default=DEFAULT_DOWNLOAD_SUFFIXES,
    )

    await _safe_send_text(db, project_id, chat_id, _DOWNLOAD_STARTED_REPLY)

    try:
        resolution = await asyncio.to_thread(
            resolve_download_file,
            requested_path,
            local_roots=local_roots,
            svn_roots=svn_roots,
            allowed_suffixes=allowed_suffixes,
            max_file_bytes=settings.feishu_bot_max_file_bytes,
        )
        await send_file_to_chat(
            db=db,
            project_id=project_id,
            chat_id=chat_id,
            file_path=resolution.path,
            file_name=resolution.display_name,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "飞书配置文件下载失败 project_id=%s requested_path=%r",
            project_id,
            requested_path,
        )
        await _safe_send_text(db, project_id, chat_id, translate_download_error(exc))


async def dispatch_message_event(
    db: AsyncSession,
    project_id: int,
    allowed_open_ids: Iterable[str],
    event: Any,
) -> None:
    """处理一条飞书 IM 消息事件：识别 → 鉴权 → 触发项目校验 → 回写结果。

    流程：
    1. 仅处理群文本消息且文本命中 ``项目校验`` 指令；其它直接忽略。
    2. ``chat_id`` 缺失时记 warning 后忽略，不让缺字段事件中断分发器。
    3. 白名单非空且发送者不在白名单：发一条权限提示并返回。
    4. 命中：先回 ``已开始执行…`` 再串行跑校验；
       成功 → 卡片回写，失败 → 翻译异常文案后回写。
    5. ``send_*_to_chat`` 任意错误都吞掉，只记日志，避免单次回写失败把
       supervisor 状态污染掉。
    """
    inner = _get_attr_or_key(event, "event")
    if inner is None:
        return
    message = _get_attr_or_key(inner, "message")
    if message is None:
        return

    chat_type = _get_attr_or_key(message, "chat_type", default="") or ""
    msg_type = _get_attr_or_key(message, "message_type", default="") or ""
    if chat_type != "group" or msg_type != "text":
        return

    content_raw = _get_attr_or_key(message, "content", default="")
    if not isinstance(content_raw, str) or not content_raw:
        return
    try:
        content_obj = json.loads(content_raw)
    except json.JSONDecodeError:
        logger.warning(
            "飞书消息 content 非合法 JSON project_id=%s content=%r",
            project_id,
            content_raw,
        )
        return
    if not isinstance(content_obj, dict):
        return
    text = str(content_obj.get("text") or "")
    download_path = extract_download_path(text)
    is_project_check = matches_project_check_command(text)
    if download_path is None and not is_project_check:
        return

    chat_id = _get_attr_or_key(message, "chat_id", default="") or ""
    if not chat_id:
        logger.warning(
            "飞书消息缺少 chat_id，已忽略 project_id=%s text=%r",
            project_id,
            text,
        )
        return

    sender_open_id = extract_sender_open_id(event)
    allowed = list(allowed_open_ids)
    if allowed and sender_open_id not in allowed:
        logger.info(
            "飞书项目校验白名单拒绝 project_id=%s sender=%s",
            project_id,
            sender_open_id,
        )
        await _safe_send_text(db, project_id, chat_id, _FORBIDDEN_REPLY)
        return

    if download_path is not None:
        await _handle_download_command(db, project_id, chat_id, download_path)
        return

    await _safe_send_text(db, project_id, chat_id, _STARTED_REPLY)

    try:
        result = await execute_fixed_rules_for_project(db, project_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "飞书项目校验执行失败 project_id=%s",
            project_id,
        )
        await _safe_send_text(db, project_id, chat_id, translate_execution_error(exc))
        return

    project_name = str(result.get("project_name") or f"项目 {project_id}")
    card = build_project_check_card(
        project_id=project_id,
        project_name=project_name,
        summary=result,
        platform_url=_resolve_platform_url(project_id),
    )
    await _safe_send_card(db, project_id, chat_id, card)


# --------------------------------------------------------------------------- #
# Supervisor
# --------------------------------------------------------------------------- #


@dataclass
class _ProjectRuntime:
    """单项目的运行时句柄，用于 stop_one 时拿到 client + ping_task。"""

    client: Any
    ping_task: asyncio.Task[Any] | None
    app_id: str
    last_error: str | None = None


class FeishuLongConnSupervisor:
    """按 ``project_id`` 维度管理多个 ``lark.ws.Client`` 长连接。

    设计取舍：
    - 全部异步接口跑在 FastAPI 主事件循环里。``start_one`` 不调用阻塞的
      ``client.start()``，而是 ``await client._connect()`` +
      ``asyncio.create_task(client._ping_loop())``。
    - 首次启动时把 ``lark_oapi.ws.client.loop`` patch 成主循环；该模块级 loop
      被 SDK 内部 ``_connect`` / ``_receive_message_loop`` / ``_reconnect``
      作为 ``loop.create_task`` 的承载者，必须与我们 await 的 loop 一致。
    - 事件回调由 SDK 同步调用，落到我们注册的同步 handler，再用
      ``asyncio.run_coroutine_threadsafe`` 把 ``dispatch_message_event``
      调度回主循环（即使未来 SDK 在另一个线程触发也安全）。
    - 同 ``app_id`` 不允许跨项目复用：start_one 进入时检查
      ``_app_id_owner``，命中冲突则只把状态置为 ``error`` 不抛。
    """

    def __init__(self) -> None:
        self._main_loop: asyncio.AbstractEventLoop | None = None
        self._db_session_factory: async_sessionmaker | None = None
        self._clients: dict[int, _ProjectRuntime] = {}
        self._states: dict[int, ConnectionState] = {}
        self._locks: dict[int, asyncio.Lock] = {}
        self._supervisor_lock: asyncio.Lock | None = None
        self._app_id_owner: dict[str, int] = {}
        self._allowed_open_ids: dict[int, list[str]] = {}
        self._loop_patched: bool = False

    # ---- 配置注入 ----

    def set_session_factory(self, factory: async_sessionmaker) -> None:
        """注入 SQLAlchemy 会话工厂；Step 3 在 lifespan 启动时调用一次。"""
        self._db_session_factory = factory

    # ---- 状态查询 ----

    def get_state(self, project_id: int) -> ConnectionState:
        """返回项目当前长连接状态；未启动时默认 ``inactive``。"""
        return self._states.get(project_id, "inactive")

    def update_allowed_open_ids(
        self, project_id: int, ids: Iterable[str]
    ) -> None:
        """admin 路由保存白名单后调用，避免 reload 整条 ws 连接。"""
        self._allowed_open_ids[project_id] = list(ids)

    # ---- 启停 ----

    async def start_all(self) -> None:
        """读取 DB 中所有已配置 app_id 的项目，逐个启动。"""
        if self._db_session_factory is None:
            raise RuntimeError("set_session_factory must be called before start_all")
        async with self._db_session_factory() as session:
            result = await session.execute(
                select(FeishuBotConfigRecord).where(
                    FeishuBotConfigRecord.app_id != ""
                )
            )
            records = list(result.scalars().all())

        for record in records:
            try:
                app_secret = decrypt_secret(record.app_secret_cipher)
            except ValueError:
                logger.exception(
                    "飞书机器人密钥解密失败 project_id=%s", record.project_id
                )
                self._states[record.project_id] = "error"
                continue
            if not app_secret:
                logger.warning(
                    "飞书机器人密钥为空，跳过启动 project_id=%s",
                    record.project_id,
                )
                self._states[record.project_id] = "error"
                continue
            allowed_ids = parse_allowed_open_ids(record.allowed_open_ids or "")
            await self.start_one(
                record.project_id,
                record.app_id,
                app_secret,
                allowed_ids,
            )

    async def stop_all(self) -> None:
        """并发关闭所有 ws 连接；总是清空内部状态字典。"""
        project_ids = list(self._clients.keys())
        if project_ids:
            await asyncio.gather(
                *(self.stop_one(pid) for pid in project_ids),
                return_exceptions=True,
            )
        self._clients.clear()
        self._states.clear()
        self._app_id_owner.clear()
        self._allowed_open_ids.clear()

    async def start_one(
        self,
        project_id: int,
        app_id: str,
        app_secret: str,
        allowed_open_ids: Iterable[str],
    ) -> None:
        """启动单个项目的 ws 长连接；幂等：已存在则先 stop 再起。"""
        if self._db_session_factory is None:
            raise RuntimeError("set_session_factory must be called before start_one")

        if self._supervisor_lock is None:
            self._supervisor_lock = asyncio.Lock()

        async with self._supervisor_lock:
            existing_owner = self._app_id_owner.get(app_id)
            if existing_owner is not None and existing_owner != project_id:
                logger.warning(
                    "飞书 app_id 已被其他项目占用，跳过启动 app_id=%s "
                    "owner_project_id=%s requested_project_id=%s",
                    app_id,
                    existing_owner,
                    project_id,
                )
                self._states[project_id] = "error"
                self._allowed_open_ids[project_id] = list(allowed_open_ids)
                return

            # 已存在则先停掉，避免句柄泄漏。
            if project_id in self._clients:
                await self._stop_runtime(project_id)

            if not self._loop_patched:
                try:
                    main_loop = asyncio.get_running_loop()
                except RuntimeError:
                    logger.error(
                        "start_one 必须在事件循环内调用 project_id=%s",
                        project_id,
                    )
                    self._states[project_id] = "error"
                    return
                import lark_oapi.ws.client as _lark_ws_client

                _lark_ws_client.loop = main_loop
                self._main_loop = main_loop
                self._loop_patched = True

            self._states[project_id] = "reconnecting"
            self._allowed_open_ids[project_id] = list(allowed_open_ids)

            event_handler = self._build_event_handler(project_id)
            try:
                client = lark.ws.Client(
                    app_id,
                    app_secret,
                    event_handler=event_handler,
                    log_level=lark.LogLevel.INFO,
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "构造 lark.ws.Client 失败 project_id=%s",
                    project_id,
                )
                self._states[project_id] = "error"
                self._allowed_open_ids[project_id] = list(allowed_open_ids)
                return

            try:
                await client._connect()
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "飞书长连接 _connect 失败 project_id=%s",
                    project_id,
                )
                self._states[project_id] = "error"
                self._allowed_open_ids[project_id] = list(allowed_open_ids)
                return

            ping_task = asyncio.create_task(
                client._ping_loop(),
                name=f"feishu-ws-ping-project-{project_id}",
            )

            self._clients[project_id] = _ProjectRuntime(
                client=client,
                ping_task=ping_task,
                app_id=app_id,
                last_error=None,
            )
            self._app_id_owner[app_id] = project_id
            self._states[project_id] = "active"

    async def stop_one(self, project_id: int) -> None:
        """关闭单个项目的 ws 连接；不存在时仅清状态，不抛。"""
        if self._supervisor_lock is None:
            self._supervisor_lock = asyncio.Lock()
        async with self._supervisor_lock:
            await self._stop_runtime(project_id)

    async def reload(self, project_id: int, db: AsyncSession) -> None:
        """重读项目配置并重建 ws；并发安全（按 project_id 上锁）。"""
        if self._db_session_factory is None:
            raise RuntimeError("set_session_factory must be called before reload")
        lock = self._locks.setdefault(project_id, asyncio.Lock())
        async with lock:
            await self.stop_one(project_id)

            result = await db.execute(
                select(FeishuBotConfigRecord).where(
                    FeishuBotConfigRecord.project_id == project_id
                )
            )
            record = result.scalar_one_or_none()
            if record is None or not record.app_id:
                # 配置已清空 → 保持 inactive，不再重启。
                return

            try:
                app_secret = decrypt_secret(record.app_secret_cipher)
            except ValueError:
                logger.exception(
                    "飞书机器人密钥解密失败 project_id=%s", project_id
                )
                self._states[project_id] = "error"
                return
            if not app_secret:
                logger.warning(
                    "飞书机器人密钥为空，无法重启 project_id=%s", project_id
                )
                self._states[project_id] = "error"
                return

            allowed_ids = parse_allowed_open_ids(record.allowed_open_ids or "")
            await self.start_one(
                project_id, record.app_id, app_secret, allowed_ids
            )
            invalidate_token_cache(project_id)

    # ---- 内部 ----

    async def _stop_runtime(self, project_id: int) -> None:
        """实际的停连逻辑；调用前必须持有 ``_supervisor_lock``。"""
        runtime = self._clients.pop(project_id, None)
        if runtime is None:
            self._states[project_id] = "inactive"
            self._allowed_open_ids.pop(project_id, None)
            return

        try:
            runtime.client._auto_reconnect = False
        except Exception:  # noqa: BLE001
            pass

        if runtime.ping_task is not None and not runtime.ping_task.done():
            runtime.ping_task.cancel()
            try:
                await runtime.ping_task
            except asyncio.CancelledError:
                pass
            except Exception:  # noqa: BLE001
                logger.exception(
                    "ping_task 收尾异常 project_id=%s", project_id
                )

        try:
            await runtime.client._disconnect()
        except Exception:  # noqa: BLE001
            logger.exception(
                "飞书长连接 _disconnect 异常 project_id=%s", project_id
            )

        self._app_id_owner.pop(runtime.app_id, None)
        self._states[project_id] = "inactive"
        self._allowed_open_ids.pop(project_id, None)

    def _build_event_handler(self, project_id: int) -> Any:
        """为指定 project_id 构造 EventDispatcherHandler。

        长连接模式下 ``builder("", "")`` 用两个空串占位
        verification_token / encrypt_key（这两段在事件回调期才需要）。
        """
        builder = lark.EventDispatcherHandler.builder("", "")
        builder = builder.register_p2_im_message_receive_v1(
            self._make_message_callback(project_id)
        )
        return builder.build()

    def _make_message_callback(self, project_id: int):
        """生成绑定 project_id 的同步事件回调。

        SDK ``_handle_data_frame`` 同步调用注册的 handler，所以这里返回的
        函数必须是同步的；内部用 ``run_coroutine_threadsafe`` 把异步 dispatch
        调度回主循环。
        """

        def _on_message_received(data: Any) -> None:  # pragma: no cover - 由 inject_event 触发
            loop = self._main_loop
            if loop is None:
                logger.error(
                    "supervisor 未绑定主循环就收到飞书事件 project_id=%s",
                    project_id,
                )
                return
            try:
                asyncio.run_coroutine_threadsafe(
                    self._dispatch_via_session(project_id, data),
                    loop,
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "调度飞书事件 dispatch 失败 project_id=%s",
                    project_id,
                )

        return _on_message_received

    async def _dispatch_via_session(self, project_id: int, event: Any) -> None:
        """每次事件单独开会话，避免多事件复用同一 session。"""
        if self._db_session_factory is None:
            logger.error(
                "supervisor 未注入 session_factory，dispatch 已跳过 project_id=%s",
                project_id,
            )
            return
        async with self._db_session_factory() as session:
            try:
                await dispatch_message_event(
                    session,
                    project_id,
                    self._allowed_open_ids.get(project_id, []),
                    event,
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "dispatch_message_event 异常 project_id=%s", project_id
                )


# --------------------------------------------------------------------------- #
# 模块级单例
# --------------------------------------------------------------------------- #


long_conn_supervisor = FeishuLongConnSupervisor()


__all__ = [
    "PROJECT_CHECK_COMMAND",
    "ConnectionState",
    "FeishuLongConnSupervisor",
    "build_project_check_card",
    "dispatch_message_event",
    "extract_sender_open_id",
    "format_int",
    "long_conn_supervisor",
    "matches_project_check_command",
    "parse_allowed_open_ids",
    "translate_download_error",
    "translate_execution_error",
]
