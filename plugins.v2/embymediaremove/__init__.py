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
    plugin_version = "0.95"
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
    _enabled = False

    def init_plugin(self, config: dict = None):
        """
        初始化插件
        :param config: 插件配置信息
        """
        if config:
            self._enabled = config.get("enabled", False)
        logger.info(f"插件 {self.plugin_name} 初始化完成，启用状态: {self._enabled}")

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
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
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        pass

    def get_state(self):
        return self._enabled

    def get_page(self) -> List[dict]:
        pass

    # @eventmanager.register(EventType.PluginReload)
    # def on_plugin_reload(self, event: Event):
    #     logger.info(f"on_plugin_reload事件触发: {event.__dict__}")
    #     # 在这里可以添加处理下载完成事件的具体逻辑

    # @eventmanager.register(EventType.PluginAction)
    # def on_plugin_action(self, event: Event):
    #     logger.info(f"on_plugin_action事件触发: {event.__dict__}")
    #     # 在这里可以添加处理下载完成事件的具体逻辑

    # @eventmanager.register(EventType.CommandExcute)
    # def on_command_excute(self, event: Event):
    #     logger.info(f"on_command_excute事件触发: {event.__dict__}")
    #     # 在这里可以添加处理下载完成事件的具体逻辑

    # @eventmanager.register(EventType.SiteDeleted)
    # def on_site_deleted(self, event: Event):
    #     logger.info(f"on_site_deleted事件触发: {event.__dict__}")
    #     # 在这里可以添加处理下载完成事件的具体逻辑

    # @eventmanager.register(EventType.SiteUpdated)
    # def on_site_updated(self, event: Event):
    #     logger.info(f"on_site_deleted事件触发: {event.__dict__}")
    #     # 在这里可以添加处理下载完成事件的具体逻辑

    # @eventmanager.register(EventType.TransferComplete)
    # def on_transfer_complete(self, event: Event):
    #     logger.info(f"on_transfer_complete事件触发: {event.__dict__}")
    #     # 在这里可以添加处理下载完成事件的具体逻辑

    # @eventmanager.register(EventType.DownloadAdded)
    # def on_download_completed(self, event: Event):
    #     logger.info(f"on_download_completed事件触发: {event.__dict__}")
    #     # 在这里可以添加处理下载完成事件的具体逻辑

    # @eventmanager.register(EventType.HistoryDeleted)
    # def on_history_deleted(self, event: Event):
    #     logger.info(f"on_history_deleted事件触发: {event.__dict__}")
    #     # 在这里可以添加处理下载完成事件的具体逻辑

    # @eventmanager.register(EventType.DownloadFileDeleted)
    # def on_download_file_deleted(self, event: Event):
    #     logger.info(f"on_download_file_deleted事件触发: {event.__dict__}")
    #     # 在这里可以添加处理下载完成事件的具体逻辑

    # @eventmanager.register(EventType.DownloadDeleted)
    # def on_download_deleted(self, event: Event):
    #     logger.info(f"on_download_deleted事件触发: {event.__dict__}")
    #     # 在这里可以添加处理下载完成事件的具体逻辑

    # @eventmanager.register(EventType.UserMessage)
    # def on_user_message(self, event: Event):
    #     logger.info(f"on_user_message事件触发: {event.__dict__}")
    #     # 在这里可以添加处理下载完成事件的具体逻辑

    @eventmanager.register(EventType.WebhookMessage)
    def on_webhook_coming(self, event: Event):
        logger.info(f"on_webhook_coming事件触发: {event.__dict__}")
        # 在这里可以添加处理下载完成事件的具体逻辑

    # @eventmanager.register(EventType.NoticeMessage)
    # def on_notice_message(self, event: Event):
    #     logger.info(f"on_notice_message事件触发: {event.__dict__}")
    #     # 在这里可以添加处理下载完成事件的具体逻辑

    # @eventmanager.register(EventType.SubscribeAdded)
    # def on_subscribe_added(self, event: Event):
    #     logger.info(f"on_subscribe_added事件触发: {event.__dict__}")
    #     # 在这里可以添加处理下载完成事件的具体逻辑

    # @eventmanager.register(EventType.SubscribeComplete)
    # def on_subscribe_complete(self, event: Event):
    #     logger.info(f"on_subscribe_complete事件触发: {event.__dict__}")
    #     # 在这里可以添加处理下载完成事件的具体逻辑

    # @eventmanager.register(EventType.SystemError)
    # def on_system_error(self, event: Event):
    #     logger.info(f"on_system_error事件触发: {event.__dict__}")
    #     # 在这里可以添加处理下载完成事件的具体逻辑

    def stop_service(self):
        logger.info("stop_service")
