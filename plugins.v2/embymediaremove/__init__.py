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
    plugin_version = "0.92"
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
    # 任务执行间隔
    _cron = None
    _type = None
    _onlyonce = False
    _notify = False
    _cleantype = None
    _cleandate = None
    _cleanuser = None
    _downloadhis = None
    _transferhis = None

    def init_plugin(self, config: dict = None):
        """
        初始化插件
        :param config: 插件配置信息
        """
        if config:
            self._enabled = config.get("enabled", False)
        logger.info(f"插件 {self.plugin_name} 初始化完成，启用状态: {self._enabled}")

    def get_api(self) -> List[Dict[str, Any]]:
        """
        获取插件 API
        """
        return []

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
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
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enabled',
                                            'label': '启用插件',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'onlyonce',
                                            'label': '立即运行一次',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'notify',
                                            'label': '开启通知',
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
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VCronField',
                                        'props': {
                                            'model': 'cron',
                                            'label': '执行周期',
                                            'placeholder': '0 0 ? ? ?'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSelect',
                                        'props': {
                                            'model': 'cleantype',
                                            'label': '全局清理方式',
                                            'items': [
                                                {'title': '媒体库文件', 'value': 'dest'},
                                                {'title': '源文件', 'value': 'src'},
                                                {'title': '所有文件', 'value': 'all'},
                                            ]
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'cleandate',
                                            'label': '全局清理日期',
                                            'placeholder': '清理多少天之前的下载记录（天）'
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
                                    'cols': 12,
                                },
                                'content': [
                                    {
                                        'component': 'VTextarea',
                                        'props': {
                                            'model': 'cleanuser',
                                            'label': '清理配置',
                                            'rows': 6,
                                            'placeholder': '每一行一个配置，支持以下几种配置方式，清理方式支持 src、desc、all 分别对应源文件，媒体库文件，所有文件\n'
                                                           '用户名缺省默认清理所有用户(慎重留空)，清理天数缺省默认使用全局清理天数，清理方式缺省默认使用全局清理方式\n'
                                                           '用户名/插件名（豆瓣想看、豆瓣榜单、RSS订阅）\n'
                                                           '用户名#清理方式\n'
                                                           '用户名:清理天数\n'
                                                           '用户名:清理天数#清理方式',
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
            "onlyonce": False,
            "notify": False,
            "cleantype": "dest",
            "cron": "",
            "cleanuser": "",
            "cleandate": 30
        }

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        pass

    @eventmanager.register(EventType.DownloadAdded)
    def on_download_completed(self, event: Event):
        logger.info(f"下载添加事件触发: {event}")
        # 在这里可以添加处理下载完成事件的具体逻辑

    def stop_service(self):
        logger.info("stop_service")
