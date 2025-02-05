import logging

from typing import Any, List, Dict, Tuple, Optional

from app.core.event import eventmanager, Event
from app.helper.mediaserver import MediaServerHelper
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import EventType, MediaType, MediaImageType, NotificationType


class EmbyMediaRemove(_PluginBase):
    # 插件名称
    plugin_name = "Emby联动删除"
    # 插件描述
    plugin_desc = "Emby删除媒体信息同步删除硬连接"
    # 插件图标
    plugin_icon = "mediaplay.png"
    # 插件版本
    plugin_version = "0.5"
    # 插件作者
    plugin_author = "dzplus"
    # 作者主页
    author_url = "https://github.com/dzplus"
    # 插件配置项ID前缀
    plugin_config_prefix = "embymediaremove_"
    # 加载顺序
    plugin_order = 14
    # 可使用的用户级别
    auth_level = 2

    # 私有属性
    _enabled = False

    def init_plugin(self, config: dict = None):
        """
        初始化插件
        :param config: 插件配置信息
        """
        if config:
            self._enabled = config.get("enabled", False)
        logger.info(f"插件 {self.plugin_name} 初始化完成，启用状态: {self._enabled}")

    def get_api(self):
        """
        获取插件 API
        """
        return []

    def get_form(self):
        """
        获取插件配置表单
        """
        return [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enabled',
                                            'label': '启用插件'
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ], {
            "enabled": self._enabled
        }
    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """
        定义远程控制命令
        :return: 命令关键字、事件、描述、附带数据
        """
        return [{
            "cmd": "/emby_sync",
            "event": EventType.PluginAction,
            "desc": "触发一次同步",
            "category": "同步",
            "data": {
                "action": "emby_sync"
            }
        }]

    @eventmanager.register(EventType.PluginReload)
    def pluginReload(self, event: Event):
        logger.info("pluginReload invoke")

    @eventmanager.register(EventType.PluginAction)
    def pluginAction(self, event: Event):
        logger.info("PluginAction invoke")

    @eventmanager.register(EventType.SiteDeleted)
    def siteDeleted(self, event: Event):
        logger.info("SiteDeleted invoke")

    @eventmanager.register(EventType.DownloadAdded)
    def downloadAdded(self, event: Event):
        logger.info("DownloadAdded invoke")

    @eventmanager.register(EventType.HistoryDeleted)
    def historyDeleted(self, event: Event):
        logger.info("HistoryDeleted invoke")

    @eventmanager.register(EventType.NoticeMessage)
    def noticeMessage(self, event: Event):
        logger.info("NoticeMessage invoke")

    @eventmanager.register(EventType.TransferComplete)
    def transferComplete(self, event: Event):
        logger.info("transferComplete invoke")

    @eventmanager.register(EventType.SubscribeAdded)
    def subscribeAdded(self, event: Event):
        logger.info("SubscribeAdded invoke")

    @eventmanager.register(EventType.SubscribeComplete)
    def subscribeComplete(self, event: Event):
        logger.info("SubscribeComplete invoke")

    @eventmanager.register(EventType.SystemError)
    def systemError(self, event: Event):
        logger.info("SystemError invoke")

    @eventmanager.register(EventType.SiteUpdated)
    def siteUpdated(self, event: Event):
        logger.info("SiteUpdated invoke")

    @eventmanager.register(EventType.WebhookMessage)
    def send(self, event: Event):
        logger.info("send invoke")

    def stop_service(self):
        logger.info("stop_service")
        pass
