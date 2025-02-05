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
    plugin_version = "0.4"
    # 插件作者
    plugin_author = "dzplus"
    # 作者主页
    author_url = "https://github.com/dzplus"
    # 插件配置项ID前缀
    plugin_config_prefix = "embymediaremove_"
    # 加载顺序
    plugin_order = 14
    # 可使用的用户级别
    auth_level = 1

    # 私有属性
    mediaserver_helper = None
    _enabled = True
    _add_play_link = False
    _mediaservers = None
    _types = []
    _webhook_msg_keys = {}

    #初始化插件
    def init_plugin(self, config: dict = None):
        self.mediaserver_helper = MediaServerHelper()
        if config:
            self._enabled = config.get("enabled")
        logger.info("init_plugin invoke")

    #发送事件
    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        pass

    #从此插件暴露接口
    def get_api(self) -> List[Dict[str, Any]]:
        pass

    #设定插件外观
    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        logger.info("get_form invoke")
        """
        拼装插件配置页面，需要返回两块数据：1、页面配置；2、数据结构
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
                    },
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
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'info',
                                            'variant': 'tonal',
                                            'text': '需要设置媒体服务器Webhook，回调相对路径为 /api/v1/webhook?token=API_TOKEN&source=媒体服务器名（3001端口），其中 API_TOKEN 为设置的 API_TOKEN。'
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ], {
            "enabled": False,
            "types": []
        }

    @eventmanager.register(EventType.PluginReload)
    def pluginReload(self, event: Event):
        logger.info("pluginReload invoke")
        logger.info(event)

    @eventmanager.register(EventType.PluginAction)
    def pluginAction(self, event: Event):
        logger.info("PluginAction invoke")
        logger.info(event)
        if not event or event.get("action") != "embyremove":
            return

    @eventmanager.register(EventType.SiteDeleted)
    def siteDeleted(self, event: Event):
        logger.info("SiteDeleted invoke")
        logger.info(event)

    @eventmanager.register(EventType.DownloadAdded)
    def downloadAdded(self, event: Event):
        logger.info("DownloadAdded invoke")
        logger.info(event)

    @eventmanager.register(EventType.HistoryDeleted)
    def historyDeleted(self, event: Event):
        logger.info("HistoryDeleted invoke")
        logger.info(event)

    @eventmanager.register(EventType.NoticeMessage)
    def noticeMessage(self, event: Event):
        logger.info("NoticeMessage invoke")
        logger.info(event)
        logger.info("NoticeMessage invoke down")

    @eventmanager.register(EventType.TransferComplete)
    def transferComplete(self, event: Event):
        logger.info("transferComplete invoke")
        logger.info(event)

    @eventmanager.register(EventType.SubscribeAdded)
    def subscribeAdded(self, event: Event):
        logger.info("SubscribeAdded invoke")
        logger.info(event)

    @eventmanager.register(EventType.SubscribeComplete)
    def subscribeComplete(self, event: Event):
        logger.info("SubscribeComplete invoke")
        logger.info(event)

    @eventmanager.register(EventType.SystemError)
    def systemError(self, event: Event):
        logger.info("SystemError invoke")
        logger.info(event)

    @eventmanager.register(EventType.SiteUpdated)
    def SiteUpdated(self, event: Event):
        logger.info("SiteUpdated invoke")
        logger.info(event)

    @eventmanager.register(EventType.WebhookMessage)
    def send(self, event: Event):
        logger.info("send invoke")
        logger.info(event)

    def stop_service(self):
        logger.info("stop_service")
        pass
