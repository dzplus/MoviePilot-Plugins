import logging
import time
from typing import Any, List, Dict, Tuple, Optional

from app.core.event import eventmanager, Event
from app.helper.mediaserver import MediaServerHelper
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import WebhookEventInfo, ServiceInfo
from app.schemas.types import EventType, MediaType, MediaImageType, NotificationType
from app.utils.web import WebUtils


class EmbyMediaRemove(_PluginBase):
    # 插件名称
    plugin_name = "Emby联动删除"
    # 插件描述
    plugin_desc = "Emby删除媒体信息同步删除硬连接"
    # 插件图标
    plugin_icon = "mediaplay.png"
    # 插件版本
    plugin_version = "0.3"
    # 插件作者
    plugin_author = "dzplus"
    # 作者主页
    author_url = "https://github.com/dzplus"
    # 插件配置项ID前缀
    plugin_config_prefix = "embymediaremove_"
    # 加载顺序
    plugin_order = 100
    # 可使用的用户级别
    auth_level = 1

    # 私有属性
    mediaserver_helper = None
    _enabled = False
    _add_play_link = False
    _mediaservers = None
    _types = []
    _webhook_msg_keys = {}

    # 拼装消息内容
    _webhook_actions = {
        "library.new": "新入库",
        "system.webhooktest": "测试",
        "playback.start": "开始播放",
        "playback.stop": "停止播放",
        "user.authenticated": "登录成功",
        "user.authenticationfailed": "登录失败",
        "media.play": "开始播放",
        "media.stop": "停止播放",
        "PlaybackStart": "开始播放",
        "PlaybackStop": "停止播放",
        "item.rate": "标记了",
        "library.deleted": "删除媒体"
    }
    _webhook_images = {
        "emby": "https://emby.media/notificationicon.png",
        "plex": "https://www.plex.tv/wp-content/uploads/2022/04/new-logo-process-lines-gray.png",
        "jellyfin": "https://play-lh.googleusercontent.com/SCsUK3hCCRqkJbmLDctNYCfehLxsS4ggD1ZPHIFrrAN1Tn9yhjmGMPep2D9lMaaa9eQi"
    }

    def init_plugin(self, config: dict = None):
        self.mediaserver_helper = MediaServerHelper()
        if config:
            self._enabled = config.get("enabled")
            self._types = config.get("types") or []
            self._mediaservers = config.get("mediaservers") or []
            self._add_play_link = config.get("add_play_link", False)
        logger.info("init_plugin invoke")

    def service_infos(self, type_filter: Optional[str] = None) -> Optional[Dict[str, ServiceInfo]]:
        """
        服务信息
        """
        logger.info("service_infos invoke")
        if not self._mediaservers:
            logger.info("尚未配置媒体服务器，请检查配置")
            return None
        
        services = self.mediaserver_helper.get_services(type_filter=type_filter, name_filters=self._mediaservers)
        if not services:
            logger.info("获取媒体服务器实例失败，请检查配置")
            return None
        logger.info(services)
        active_services = {}
        for service_name, service_info in services.items():
            logger.info(service_name)
            if service_info.instance.is_inactive():
                logger.info(f"媒体服务器 {service_name} 未连接，请检查配置")
            else:
                active_services[service_name] = service_info

        if not active_services:
            return None
        logger.info(active_services)
        return active_services

    def service_info(self, name: str) -> Optional[ServiceInfo]:
        """
        服务信息
        """
        logger.info("service_info invoke")
        service_infos = self.service_infos() or {}
        return service_infos.get(name)

    def get_state(self) -> bool:
        logger.info("get_state " + self._enabled)
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        pass

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

    def get_page(self) -> List[dict]:
        pass

    @eventmanager.register(EventType.PluginReload)
    def pluginReload(self, event: Event):
        logger.info("pluginReload invoke")
        logger.info(event.event_data)

    @eventmanager.register(EventType.PluginAction)
    def PluginAction(self, event: Event):
        logger.info("PluginAction invoke")
        logger.info(event.action)
        if not event or event.get("action") != "embyremove":
            return

    @eventmanager.register(EventType.SiteDeleted)
    def SiteDeleted(self, event: Event):
        logger.info("SiteDeleted invoke")
        logger.info(event.event_data)

    @eventmanager.register(EventType.DownloadAdded)
    def DownloadAdded(self, event: Event):
        logger.info("DownloadAdded invoke")
        logger.info(event.event_data)

    @eventmanager.register(EventType.HistoryDeleted)
    def HistoryDeleted(self, event: Event):
        logger.info("HistoryDeleted invoke")
        logger.info(event.event_data)

    @eventmanager.register(EventType.NoticeMessage)
    def NoticeMessage(self, event: Event):
        logger.info("NoticeMessage invoke")
        logger.info(event.event_data)

    @eventmanager.register(EventType.SubscribeAdded)
    def SubscribeAdded(self, event: Event):
        logger.info("SubscribeAdded invoke")
        logger.info(event.event_data)

    @eventmanager.register(EventType.SubscribeComplete)
    def SubscribeComplete(self, event: Event):
        logger.info("SubscribeComplete invoke")
        logger.info(event.event_data)

    @eventmanager.register(EventType.SystemError)
    def SystemError(self, event: Event):
        logger.info("SystemError invoke")
        logger.info(event.event_data)


    @eventmanager.register(EventType.SiteUpdated)
    def SiteUpdated(self, event: Event):
        logger.info("SiteUpdated invoke")
        logger.info(event.event_data)

    @eventmanager.register(EventType.PluginReload)
    def pluginReload(self, event: Event):
        logger.info("pluginReload invoke")
        logger.info(event.event_data)

    @eventmanager.register(EventType.WebhookMessage)
    def send(self, event: Event):
        logger.info("send invoke")
        """
        发送通知消息
        """
        logger.info(event)
        if not self._enabled:
            return

        event_info: WebhookEventInfo = event.event_data
        if not event_info:
            logger.info("not event_info")
            return

        # 不在支持范围不处理
        if not self._webhook_actions.get(event_info.event):
            logger.info("not self._webhook_actions.get(event_info.event)")
            return

        # 不在选中范围不处理
        msgflag = False
        for _type in self._types:
            if event_info.event in _type.split("|"):
                msgflag = True
                break
        if not msgflag:
            logger.info(f"未开启 {event_info.event} 类型的消息通知")
            return

        if not self.service_infos():
            logger.info(f"未开启任一媒体服务器的消息通知")
            return

        if event_info.server_name and not self.service_info(name=event_info.server_name):
            logger.info(f"未开启媒体服务器 {event_info.server_name} 的消息通知")
            return

        if event_info.channel and not self.service_infos(type_filter=event_info.channel):
            logger.info(f"未开启媒体服务器类型 {event_info.channel} 的消息通知")
            return

        # 消息标题
        if event_info.item_type in ["TV", "SHOW"]:
            message_title = f"{self._webhook_actions.get(event_info.event)}剧集 {event_info.item_name}"
        elif event_info.item_type == "MOV":
            message_title = f"{self._webhook_actions.get(event_info.event)}电影 {event_info.item_name}"
        elif event_info.item_type == "AUD":
            message_title = f"{self._webhook_actions.get(event_info.event)}有声书 {event_info.item_name}"
        else:
            message_title = f"{self._webhook_actions.get(event_info.event)}"
        logging.info(message_title)
        # 消息内容
        message_texts = []
        if event_info.user_name:
            message_texts.append(f"用户：{event_info.user_name}")
        if event_info.device_name:
            message_texts.append(f"设备：{event_info.client} {event_info.device_name}")
        if event_info.ip:
            message_texts.append(f"IP地址：{event_info.ip} {WebUtils.get_location(event_info.ip)}")
        if event_info.percentage:
            percentage = round(float(event_info.percentage), 2)
            message_texts.append(f"进度：{percentage}%")
        if event_info.overview:
            message_texts.append(f"剧情：{event_info.overview}")
        message_texts.append(f"时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))}")

        # 消息内容
        message_content = "\n".join(message_texts)
        logging.info(message_content)

    def __add_element(self, key, duration=600):
        expiration_time = time.time() + duration
        # 如果元素已经存在，更新其过期时间
        self._webhook_msg_keys[key] = expiration_time

    def __remove_element(self, key):
        self._webhook_msg_keys = {k: v for k, v in self._webhook_msg_keys.items() if k != key}

    def __get_elements(self):
        current_time = time.time()
        # 过滤掉过期的元素
        self._webhook_msg_keys = {k: v for k, v in self._webhook_msg_keys.items() if v > current_time}
        return list(self._webhook_msg_keys.keys())

    def stop_service(self):
        """
        退出插件
        """
        logging.info("退出插件")
        pass
