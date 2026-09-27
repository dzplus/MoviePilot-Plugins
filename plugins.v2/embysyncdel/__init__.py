import os
import shutil
import time
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional

from apscheduler.schedulers.background import BackgroundScheduler

from app import schemas
from app.chain.mediaserver import MediaServerChain
from app.chain.storage import StorageChain
from app.chain.transfer import TransferChain
from app.core.config import settings
from app.core.event import eventmanager, Event
from app.db.models.transferhistory import TransferHistory
from app.db.transferhistory_oper import TransferHistoryOper
from app.db.downloadhistory_oper import DownloadHistoryOper
from app.helper.downloader import DownloaderHelper
from app.helper.mediaserver import MediaServerHelper
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import NotificationType, EventType, MediaType, MediaImageType
from app.utils.string import StringUtils
from app.utils.system import SystemUtils


class EmbySyncDel(_PluginBase):
    # 插件名称
    plugin_name = "Emby同步删除"
    # 插件描述
    plugin_desc = "Emby 删除媒体后，通过 Webhook 同步删除整理历史、源文件和下载任务。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/dzplus/MoviePilot-Plugins/main/icons/embysyncdel.png"
    # 插件版本
    plugin_version = "1.0.4"
    # 插件作者
    plugin_author = "dzplus"
    # 作者主页
    author_url = "https://github.com/dzplus"
    # 插件配置项ID前缀
    plugin_config_prefix = "embysyncdel_"
    # 加载顺序
    plugin_order = 9
    # 可使用的用户级别
    auth_level = 1

    # 私有属性
    _scheduler: Optional[BackgroundScheduler] = None
    _enabled = False
    _notify = False
    _del_source = False
    _del_history = False
    _exclude_path = None
    _library_path = None
    _transferchain = None
    _transferhis = None
    _downloadhis = None
    _default_downloader = None
    _storagechain = None

    def init_plugin(self, config: dict = None):
        self._transferchain = TransferChain()
        self._downloader_helper = DownloaderHelper()
        self._transferhis = TransferHistoryOper()
        self._downloadhis = DownloadHistoryOper()
        self._storagechain = StorageChain()

        # 读取配置
        if config:
            self._enabled = config.get("enabled")
            self._notify = config.get("notify")
            self._del_source = config.get("del_source")
            self._del_history = config.get("del_history")
            self._exclude_path = config.get("exclude_path")
            self._library_path = config.get("library_path")

            # 获取默认下载器
            downloader_services = self._downloader_helper.get_services()
            for downloader_name, downloader_info in downloader_services.items():
                if downloader_info.config.default:
                    self._default_downloader = downloader_name

            # 清理插件历史
            if self._del_history:
                self.del_data(key="history")
                self.update_config({
                    "enabled": self._enabled,
                    "notify": self._notify,
                    "del_source": self._del_source,
                    "del_history": False,
                    "exclude_path": self._exclude_path,
                    "library_path": self._library_path
                })

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """
        定义远程控制命令
        :return: 命令关键字、事件、描述、附带数据
        """
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {
                "path": "/delete_history",
                "endpoint": self.delete_history,
                "methods": ["GET"],
                "summary": "删除订阅历史记录"
            },
            {
                "path": "/clear_log",
                "endpoint": self.clear_log,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "清理插件日志"
            }
        ]

    def delete_history(self, key: str, apikey: str):
        """
        删除历史记录
        """
        if apikey != settings.API_TOKEN:
            return schemas.Response(success=False, message="API密钥错误")
        # 历史记录
        historys = self.get_data('history')
        if not historys:
            return schemas.Response(success=False, message="未找到历史记录")
        # 删除指定记录
        historys = [h for h in historys if h.get("unique") != key]
        self.save_data('history', historys)
        return schemas.Response(success=True, message="删除成功")

    def clear_log(self):
        """
        清空本插件的日志文件，并删除滚动产生的历史日志
        """
        log_file, *backups = self.__get_log_files()
        try:
            # 宿主日志写入器以追加方式一直持有主日志文件句柄：删掉主文件后新日志会写进已删除的文件，
            # 直到重启都看不到，所以主文件只能原地截断；滚动备份没有句柄占用，可以直接删除。
            if log_file.exists():
                os.truncate(log_file, 0)
            for backup in backups:
                backup.unlink(missing_ok=True)
        except OSError as e:
            logger.error(f"清理插件日志失败：{e}")
            return schemas.Response(success=False, message=f"清理插件日志失败：{e}")
        logger.info("插件日志已清理")
        return schemas.Response(success=True, message="插件日志已清理")

    def __get_log_files(self) -> List[Path]:
        """
        返回宿主为本插件写入的日志文件，第一个是主文件，其余是滚动备份
        """
        # 宿主按插件目录名 app/plugins/<名称> 把日志写到 logs/plugins/<名称>.log
        module_parts = self.__class__.__module__.split(".")
        if len(module_parts) >= 3 and module_parts[:2] == ["app", "plugins"]:
            log_name = module_parts[2]
        else:
            log_name = self.__class__.__name__.lower()
        log_dir = settings.LOG_PATH / "plugins"
        backups = sorted(path for path in log_dir.glob(f"{log_name}.log.*") if path.suffix[1:].isdigit())
        return [log_dir / f"{log_name}.log", *backups]

    def __get_log_size(self) -> int:
        """
        统计本插件当前全部日志文件的总字节数
        """
        total = 0
        for path in self.__get_log_files():
            try:
                total += path.stat().st_size
            except OSError:
                continue
        return total

    def get_service(self) -> List[Dict[str, Any]]:
        """
        注册插件公共服务
        [{
            "id": "服务ID",
            "name": "服务名称",
            "trigger": "触发器：cron/interval/date/CronTrigger.from_crontab()",
            "func": self.xxx,
            "kwargs": {} # 定时器参数
        }]
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
                                    'md': 3
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
                                    'md': 3
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'notify',
                                            'label': '发送通知',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 3
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'del_source',
                                            'label': '删除源文件',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 3
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'del_history',
                                            'label': '清空删除记录',
                                            'hint': '保存后清空详情页的删除记录',
                                            'persistent-hint': True,
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
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'exclude_path',
                                            'label': '排除路径',
                                            'hint': '命中这些路径的媒体不做同步删除，转交云盘删除类插件处理；多个路径用英文逗号分隔',
                                            'persistent-hint': True,
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
                                            'model': 'library_path',
                                            'rows': '2',
                                            'label': '路径映射',
                                            'placeholder': '/data:/mnt/link',
                                            'hint': 'Emby 和 MoviePilot 看到的整理后路径不同时才填，每行一条"Emby路径:MoviePilot路径"；相同则留空',
                                            'persistent-hint': True,
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
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'info',
                                            'variant': 'tonal',
                                        },
                                        'content': [
                                            {
                                                'component': 'div',
                                                'html': '在 Emby（4.8.0.45 及以上）的通知设置里添加 Webhook，'
                                                        '地址填 <code>http://MoviePilot地址/api/v1/webhook/?token=API令牌</code>，'
                                                        '勾选媒体库的删除事件。启用插件后，在 MoviePilot 里删除源文件也会同步处理下载器中的种子。'
                                                        '<a href="https://github.com/dzplus/MoviePilot-Plugins/blob/main/plugins.v2/embysyncdel/README.md"'
                                                        ' target="_blank">使用说明</a>'
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ], {
            "enabled": False,
            "notify": True,
            "del_source": False,
            "del_history": False,
            "library_path": "",
            "exclude_path": "",
        }

    def get_page(self) -> List[dict]:
        """
        拼装插件详情页面，需要返回页面配置，同时附带数据
        """
        # 日志大小与清理按钮，有无历史都显示
        log_toolbar = {
            'component': 'div',
            'props': {
                'class': 'd-flex align-center justify-end ga-3 mb-3',
            },
            'content': [
                {
                    'component': 'span',
                    'props': {
                        'class': 'text-body-2 text-medium-emphasis',
                    },
                    'text': f'插件日志：{StringUtils.format_size(self.__get_log_size())}'
                },
                {
                    'component': 'VBtn',
                    'props': {
                        'color': 'error',
                        'variant': 'tonal',
                        'size': 'small',
                        'prepend-icon': 'mdi-delete-sweep',
                    },
                    'text': '清理日志',
                    'events': {
                        'click': {
                            'api': f'plugin/{self.__class__.__name__}/clear_log',
                            'method': 'post',
                        }
                    },
                }
            ]
        }
        # 查询同步详情
        historys = self.get_data('history')
        if not historys:
            return [
                log_toolbar,
                {
                    'component': 'div',
                    'text': '暂无数据',
                    'props': {
                        'class': 'text-center',
                    }
                }
            ]
        # 数据按时间降序排序
        historys = sorted(historys, key=lambda x: x.get('del_time'), reverse=True)
        # 拼装页面
        contents = []
        for history in historys:
            htype = history.get("type")
            title = history.get("title")
            unique = history.get("unique")
            year = history.get("year")
            season = history.get("season")
            episode = history.get("episode")
            image = history.get("image")
            del_time = history.get("del_time")

            if season:
                sub_contents = [
                    {
                        'component': 'VCardText',
                        'props': {
                            'class': 'pa-0 px-2'
                        },
                        'text': f'类型：{htype}'
                    },
                    {
                        'component': 'VCardText',
                        'props': {
                            'class': 'pa-0 px-2'
                        },
                        'text': f'标题：{title}'
                    },
                    {
                        'component': 'VCardText',
                        'props': {
                            'class': 'pa-0 px-2'
                        },
                        'text': f'年份：{year}'
                    },
                    {
                        'component': 'VCardText',
                        'props': {
                            'class': 'pa-0 px-2'
                        },
                        'text': f'季：{season}'
                    },
                    {
                        'component': 'VCardText',
                        'props': {
                            'class': 'pa-0 px-2'
                        },
                        'text': f'集：{episode}'
                    },
                    {
                        'component': 'VCardText',
                        'props': {
                            'class': 'pa-0 px-2'
                        },
                        'text': f'时间：{del_time}'
                    }
                ]
            else:
                sub_contents = [
                    {
                        'component': 'VCardText',
                        'props': {
                            'class': 'pa-0 px-2'
                        },
                        'text': f'类型：{htype}'
                    },
                    {
                        'component': 'VCardText',
                        'props': {
                            'class': 'pa-0 px-2'
                        },
                        'text': f'标题：{title}'
                    },
                    {
                        'component': 'VCardText',
                        'props': {
                            'class': 'pa-0 px-2'
                        },
                        'text': f'年份：{year}'
                    },
                    {
                        'component': 'VCardText',
                        'props': {
                            'class': 'pa-0 px-2'
                        },
                        'text': f'时间：{del_time}'
                    }
                ]

            contents.append(
                {
                    'component': 'VCard',
                    'content': [
                        {
                            "component": "VDialogCloseBtn",
                            "props": {
                                'innerClass': 'absolute top-0 right-0',
                            },
                            'events': {
                                'click': {
                                    'api': f'plugin/{self.__class__.__name__}/delete_history',
                                    'method': 'get',
                                    'params': {
                                        'key': unique,
                                        'apikey': settings.API_TOKEN
                                    }
                                }
                            },
                        },
                        {
                            'component': 'div',
                            'props': {
                                'class': 'd-flex justify-space-start flex-nowrap flex-row',
                            },
                            'content': [
                                {
                                    'component': 'div',
                                    'content': [
                                        {
                                            'component': 'VImg',
                                            'props': {
                                                'src': image,
                                                'height': 120,
                                                'width': 80,
                                                'aspect-ratio': '2/3',
                                                'class': 'object-cover shadow ring-gray-500',
                                                'cover': True
                                            }
                                        }
                                    ]
                                },
                                {
                                    'component': 'div',
                                    'content': sub_contents
                                }
                            ]
                        }
                    ]
                }
            )

        return [
            log_toolbar,
            {
                'component': 'div',
                'props': {
                    'class': 'grid gap-3 grid-info-card',
                },
                'content': contents
            }
        ]

    @eventmanager.register(EventType.WebhookMessage)
    def sync_del_by_webhook(self, event: Event):
        """
        emby删除媒体库同步删除历史记录
        webhook
        """
        if not self._enabled:
            return

        event_data: schemas.WebhookEventInfo = event.event_data
        event_type = event_data.event

        # Emby Webhook event_type = library.deleted
        if not event_type or str(event_type) not in ['library.deleted', 'ItemDeleted']:
            return

        # 媒体类型
        media_type = event_data.media_type
        # 媒体名称
        media_name = event_data.item_name
        # 媒体路径
        media_path = event_data.item_path
        # 兼容windows路径 如 C:\test.mp4 转换为 C:/test.mp4
        media_path = media_path.replace('\\', '/')
        # tmdb_id
        tmdb_id = event_data.tmdb_id
        # 季数
        season_num = event_data.season_id
        # 集数
        episode_num = event_data.episode_id
        # 操作时间戳
        delete_time = self.format_timestamp(event_data.json_object)
        logger.info(f"收到删除事件：{event_type} 类型={media_type} 名称={media_name} 路径={media_path} "
                    f"TMDB={tmdb_id} 季={season_num} 集={episode_num}")

        # V2 主程序上报的是单集、季自己的 TMDB 编号（单集是单集编号，季通常没有编号），
        # 整理记录里存的是整部剧的编号，所以按事件里的剧集 ID 改取整部剧的编号
        if str(media_type) in ("Episode", "Season") and event_data.item_id:
            series_tmdb_id = self.__get_series_tmdbid(series_id=event_data.item_id, server=event_data.server_name)
            if series_tmdb_id:
                if str(series_tmdb_id) != str(tmdb_id):
                    logger.info(f"{media_name} 改用所属剧集的 TMDB 编号 {series_tmdb_id}（事件上报 {tmdb_id}）")
                tmdb_id = series_tmdb_id
            else:
                logger.warn(f"{media_name} 未查到所属剧集 {event_data.item_id} 的 TMDB 编号，沿用事件上报的 {tmdb_id}")

        """
        执行删除逻辑
        """
        if self._exclude_path and media_path and any(
                os.path.abspath(media_path).startswith(os.path.abspath(path)) for path in
                self._exclude_path.split(",")):
            logger.info(f"媒体路径 {media_path} 已被排除，暂不处理")
            # 发送消息通知网盘删除插件删除网盘资源
            self.eventmanager.send_event(EventType.PluginAction,
                                         {
                                             "action": "networkdisk_del",
                                             "media_path": media_path,
                                             "media_name": media_name,
                                             "tmdb_id": tmdb_id,
                                             "media_type": media_type,
                                             "season_num": season_num,
                                             "episode_num": episode_num,
                                         })
            return

        # 只处理影视条目：电影删除后 Emby 还会再发一条空文件夹（Folder）的删除事件，这类条目没有 TMDB 编号，也不对应整理记录
        if str(media_type) not in ("Movie", "Series", "Season", "Episode"):
            logger.info(f"忽略 {media_type} 类型的删除事件：{media_name}")
            return

        # 兼容emby webhook season删除没有发送tmdbid
        if not tmdb_id and str(media_type) != 'Season':
            logger.error(f"{media_name} 同步删除失败，未获取到TMDB ID，请检查媒体库媒体是否刮削")
            return

        self.__sync_del(media_type=media_type,
                        media_name=media_name,
                        media_path=media_path,
                        tmdb_id=tmdb_id,
                        season_num=season_num,
                        episode_num=episode_num,
                        delete_time=delete_time)

    @eventmanager.register(EventType.PluginAction)
    def sync_del(self, event: Event = None):
        """
        扫描
        """
        if not self._enabled or not event:
            return

        event_data = event.event_data
        if not event_data or event_data.get("action") != "media_sync_del":
            return

        logger.info(f"收到媒体同步删除请求：{event_data}")
        # 媒体类型
        media_type = event_data.get("media_type")
        # 媒体名称
        media_name = event_data.get("media_name")
        # 媒体路径
        media_path = event_data.get("media_path")
        # tmdb_id
        tmdb_id = event_data.get("tmdb_id")
        # 季数
        season_num = event_data.get("season_num")
        # 集数
        episode_num = event_data.get("episode_num")

        self.__sync_del(media_type=media_type,
                        media_name=media_name,
                        media_path=media_path,
                        tmdb_id=tmdb_id,
                        season_num=season_num,
                        episode_num=episode_num)

    def __sync_del(
        self,
        media_type: str,
        media_name: str,
        media_path: str,
        tmdb_id: int,
        season_num: str,
        episode_num: str,
        delete_time: Optional[str] = None,
    ):
        if not media_type:
            logger.error(f"{media_name} 同步删除失败，未获取到媒体类型，请检查媒体是否刮削")
            return

        # 处理路径映射 (处理同一媒体多分辨率的情况)
        if self._library_path:
            paths = self._library_path.split("\n")
            for path in paths:
                sub_paths = path.split(":")
                if len(sub_paths) < 2:
                    continue
                media_path = media_path.replace(sub_paths[0], sub_paths[1]).replace('\\', '/')

        # 兼容重新整理的场景
        if Path(media_path).exists():
            logger.warn(f"转移路径 {media_path} 未被删除或重新生成，跳过处理")
            return

        # 查询转移记录
        msg, transfer_history = self.__get_transfer_his(media_type=media_type,
                                                        media_name=media_name,
                                                        media_path=media_path,
                                                        tmdb_id=tmdb_id,
                                                        season_num=season_num,
                                                        episode_num=episode_num)

        if not transfer_history:
            logger.warn(
                f"{media_type} {media_name} 未获取到可删除数据，请检查路径映射是否配置错误，请检查tmdbid获取是否正确"
                f"（查询条件：TMDB={tmdb_id} 季={season_num} 集={episode_num} 路径={media_path}）")
            return

        if delete_time:
            latest_his = max(transfer_history, key=lambda x: x.date)
            if delete_time < latest_his.date:
                logger.warn(f"忽略删除 {msg}, 整理时间: {latest_his.date}, 发生在删除事件: {delete_time} 之后")
                return

        logger.info(f"开始同步删除 {msg}, 获取到 {len(transfer_history)} 条转移记录")
        # 开始删除
        year = None
        del_torrent_hashs = []
        stop_torrent_hashs = []
        error_cnt = 0
        image = 'https://emby.media/notificationicon.png'
        for transferhis in transfer_history:
            title = transferhis.title
            if title not in media_name:
                logger.warn(
                    f"当前转移记录 {transferhis.id} {title} {transferhis.tmdbid} 与删除媒体{media_name}不符，防误删，暂不自动删除")
                continue
            image = transferhis.image or image
            year = transferhis.year

            # 0、删除转移记录
            self._transferhis.delete(transferhis.id)

            # 删除种子任务
            if self._del_source:
                # 1、直接删除源文件
                if transferhis.src and Path(transferhis.src).suffix.lower() in settings.RMT_MEDIAEXT:
                    # 删除硬链接文件和源文件
                    if Path(transferhis.dest).exists():
                        Path(transferhis.dest).unlink(missing_ok=True)
                        self.__remove_parent_dir(Path(transferhis.dest))
                    if Path(transferhis.src).exists():
                        logger.info(f"源文件 {transferhis.src} 开始删除")
                        Path(transferhis.src).unlink(missing_ok=True)
                        logger.info(f"源文件 {transferhis.src} 已删除")
                        self.__remove_parent_dir(Path(transferhis.src))

                    if transferhis.download_hash:
                        try:
                            # 2、判断种子是否被删除完
                            delete_flag, success_flag, handle_torrent_hashs = self.handle_torrent(
                                type=transferhis.type,
                                src=transferhis.src,
                                torrent_hash=transferhis.download_hash)
                            if not success_flag:
                                error_cnt += 1
                            else:
                                if delete_flag:
                                    del_torrent_hashs += handle_torrent_hashs
                                else:
                                    stop_torrent_hashs += handle_torrent_hashs
                        except Exception as e:
                            logger.error("删除种子失败：%s" % str(e))
                    else:
                        # 种子不是经 MoviePilot 下载的（比如直接推给下载器），整理记录里没有种子哈希，按源文件路径去下载器里找
                        try:
                            delete_flag, handle_torrent_hashs = self.__handle_external_torrent(src=transferhis.src)
                            if delete_flag:
                                del_torrent_hashs += handle_torrent_hashs
                            else:
                                stop_torrent_hashs += handle_torrent_hashs
                        except Exception as e:
                            error_cnt += 1
                            logger.error(f"按源文件路径处理种子失败：{e}")

        logger.info(f"同步删除 {msg} 完成！")

        media_type = MediaType.MOVIE if media_type in ["Movie", "MOV"] else MediaType.TV

        # 发送消息
        if self._notify:
            backrop_image = self.chain.obtain_specific_image(
                mediaid=tmdb_id,
                mtype=media_type,
                image_type=MediaImageType.Backdrop,
                season=season_num,
                episode=episode_num
            ) or image

            torrent_cnt_msg = ""
            if del_torrent_hashs:
                torrent_cnt_msg += f"删除种子{len(set(del_torrent_hashs))}个\n"
            if stop_torrent_hashs:
                stop_cnt = 0
                # 排除已删除
                for stop_hash in set(stop_torrent_hashs):
                    if stop_hash not in set(del_torrent_hashs):
                        stop_cnt += 1
                if stop_cnt > 0:
                    torrent_cnt_msg += f"暂停种子{stop_cnt}个\n"
            if error_cnt:
                torrent_cnt_msg += f"删种失败{error_cnt}个\n"
            # 发送通知
            self.post_message(
                mtype=NotificationType.Plugin,
                title="媒体库同步删除任务完成",
                image=backrop_image,
                text=f"{msg}\n"
                     f"删除记录{len(transfer_history)}个\n"
                     f"{torrent_cnt_msg}"
                     f"时间 {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))}"
            )

        # 读取历史记录
        history = self.get_data('history') or []

        # 获取poster
        poster_image = self.chain.obtain_specific_image(
            mediaid=tmdb_id,
            mtype=media_type,
            image_type=MediaImageType.Poster,
        ) or image
        history.append({
            "type": media_type.value,
            "title": media_name,
            "year": year,
            "path": media_path,
            "season": season_num if season_num and str(season_num).isdigit() else None,
            "episode": episode_num if episode_num and str(episode_num).isdigit() else None,
            "image": poster_image,
            "del_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time())),
            "unique": f"{media_name}:{tmdb_id}:{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))}"
        })

        # 保存历史
        self.save_data("history", history)

    def __remove_parent_dir(self, file_path: Path):
        """
        删除父目录
        """
        # 删除空目录
        # 判断当前媒体父路径下是否有媒体文件，如有则无需遍历父级
        if not SystemUtils.exits_files(file_path.parent, settings.RMT_MEDIAEXT):
            # 判断父目录是否为空, 为空则删除
            i = 0
            for parent_path in file_path.parents:
                i += 1
                if i > 3:
                    break
                if str(parent_path.parent) != str(file_path.root):
                    # 父目录非根目录，才删除父目录
                    if not SystemUtils.exits_files(parent_path, settings.RMT_MEDIAEXT):
                        # 当前路径下没有媒体文件则删除
                        shutil.rmtree(parent_path)
                        logger.warn(f"本地空目录 {parent_path} 已删除")

    def __get_transfer_his(self, media_type: str, media_name: str, media_path: str,
                           tmdb_id: int, season_num: str, episode_num: str):
        """
        查询转移记录
        """
        # 季数
        if season_num and str(season_num).isdigit():
            season_num = str(season_num).rjust(2, '0')
        else:
            season_num = None
        # 集数
        if episode_num and str(episode_num).isdigit():
            episode_num = str(episode_num).rjust(2, '0')
        else:
            episode_num = None

        # 类型
        mtype = MediaType.MOVIE if media_type in ["Movie", "MOV"] else MediaType.TV

        # 删除电影
        if mtype == MediaType.MOVIE:
            msg = f'电影 {media_name} {tmdb_id}'
            transfer_history: List[TransferHistory] = self._transferhis.get_by(tmdbid=tmdb_id,
                                                                               mtype=mtype.value,
                                                                               dest=media_path)
        # 删除电视剧
        elif mtype == MediaType.TV and not season_num and not episode_num:
            msg = f'剧集 {media_name} {tmdb_id}'
            transfer_history: List[TransferHistory] = self._transferhis.get_by(tmdbid=tmdb_id,
                                                                               mtype=mtype.value)
        # 删除季 S02
        elif mtype == MediaType.TV and season_num and not episode_num:
            if not season_num or not str(season_num).isdigit():
                logger.error(f"{media_name} 季同步删除失败，未获取到具体季")
                return
            msg = f'剧集 {media_name} S{season_num} {tmdb_id}'
            if tmdb_id and str(tmdb_id).isdigit():
                # 根据tmdb_id查询转移记录
                transfer_history: List[TransferHistory] = self._transferhis.get_by(tmdbid=tmdb_id,
                                                                                   mtype=mtype.value,
                                                                                   season=f'S{season_num}')
            else:
                # 兼容emby webhook不发送tmdb场景
                transfer_history: List[TransferHistory] = self._transferhis.get_by(mtype=mtype.value,
                                                                                   season=f'S{season_num}',
                                                                                   dest=media_path)
        # 删除剧集S02E02
        elif mtype == MediaType.TV and season_num and episode_num:
            if not season_num or not str(season_num).isdigit() or not episode_num or not str(episode_num).isdigit():
                logger.error(f"{media_name} 集同步删除失败，未获取到具体集")
                return
            msg = f'剧集 {media_name} S{season_num}E{episode_num} {tmdb_id}'
            transfer_history: List[TransferHistory] = self._transferhis.get_by(tmdbid=tmdb_id,
                                                                               mtype=mtype.value,
                                                                               season=f'S{season_num}',
                                                                               episode=f'E{episode_num}',
                                                                               dest=media_path)
        else:
            return "", []

        return msg, transfer_history

    def handle_torrent(self, type: str, src: str, torrent_hash: str):
        """
        判断种子是否局部删除
        局部删除则暂停种子
        全部删除则删除种子
        """
        download_id = torrent_hash
        download = self._default_downloader
        history_key = "%s-%s" % (download, torrent_hash)
        plugin_id = "TorrentTransfer"
        transfer_history = self.get_data(key=history_key,
                                         plugin_id=plugin_id)
        logger.info(f"查询到 {history_key} 转种历史 {transfer_history}")

        handle_torrent_hashs = []
        try:
            # 删除本次种子记录
            self._downloadhis.delete_file_by_fullpath(fullpath=src)

            # 根据种子hash查询所有下载器文件记录
            download_files = self._downloadhis.get_files_by_hash(download_hash=torrent_hash)
            if not download_files:
                logger.error(
                    f"未查询到种子任务 {torrent_hash} 存在文件记录，未执行下载器文件同步或该种子已被删除")
                return False, False, 0

            # 查询未删除数
            no_del_cnt = 0
            for download_file in download_files:
                if download_file and download_file.state and int(download_file.state) == 1:
                    no_del_cnt += 1

            if no_del_cnt > 0:
                logger.info(
                    f"查询种子任务 {torrent_hash} 存在 {no_del_cnt} 个未删除文件，执行暂停种子操作")
                delete_flag = False
            else:
                logger.info(
                    f"查询种子任务 {torrent_hash} 文件已全部删除，执行删除种子操作")
                delete_flag = True

            # 如果有转种记录，则删除转种后的下载任务
            if transfer_history and isinstance(transfer_history, dict):
                download = transfer_history['to_download']
                download_id = transfer_history['to_download_id']
                delete_source = transfer_history['delete_source']

                # 删除种子
                if delete_flag:
                    # 删除转种记录
                    self.del_data(key=history_key, plugin_id=plugin_id)

                    # 转种后未删除源种时，同步删除源种
                    if not delete_source:
                        logger.info(f"{history_key} 转种时未删除源下载任务，开始删除源下载任务…")

                        # 删除源种子
                        logger.info(f"删除源下载器下载任务：{self._default_downloader} - {torrent_hash}")
                        self.chain.remove_torrents(torrent_hash)
                        handle_torrent_hashs.append(torrent_hash)

                    # 删除转种后任务
                    logger.info(f"删除转种后下载任务：{download} - {download_id}")
                    # 删除转种后下载任务
                    self.chain.remove_torrents(hashs=torrent_hash,
                                               downloader=download)
                    handle_torrent_hashs.append(download_id)
                else:
                    # 暂停种子
                    # 转种后未删除源种时，同步暂停源种
                    if not delete_source:
                        logger.info(f"{history_key} 转种时未删除源下载任务，开始暂停源下载任务…")

                        # 暂停源种子
                        logger.info(f"暂停源下载器下载任务：{self._default_downloader} - {torrent_hash}")
                        self.chain.stop_torrents(torrent_hash)
                        handle_torrent_hashs.append(torrent_hash)

                    logger.info(f"暂停转种后下载任务：{download} - {download_id}")
                    # 删除转种后下载任务
                    self.chain.stop_torrents(hashs=download_id, downloader=download)
                    handle_torrent_hashs.append(download_id)
            else:
                # 未转种de情况
                if delete_flag:
                    # 删除源种子
                    logger.info(f"删除源下载器下载任务：{download} - {download_id}")
                    self.chain.remove_torrents(download_id)
                else:
                    # 暂停源种子
                    logger.info(f"暂停源下载器下载任务：{download} - {download_id}")
                    self.chain.stop_torrents(download_id)
                handle_torrent_hashs.append(download_id)

            # 处理辅种
            handle_torrent_hashs = self.__del_seed(download_id=download_id,
                                                   delete_flag=delete_flag,
                                                   handle_torrent_hashs=handle_torrent_hashs)
            # 处理合集
            if str(type) == "电视剧":
                handle_torrent_hashs = self.__del_collection(src=src,
                                                             delete_flag=delete_flag,
                                                             torrent_hash=torrent_hash,
                                                             download_files=download_files,
                                                             handle_torrent_hashs=handle_torrent_hashs)
            return delete_flag, True, handle_torrent_hashs
        except Exception as e:
            logger.error(f"删种失败： {str(e)}")
            return False, False, 0

    def __del_collection(self, src: str, delete_flag: bool, torrent_hash: str, download_files: list,
                         handle_torrent_hashs: list):
        """
        处理合集
        """
        try:
            src_download_files = self._downloadhis.get_files_by_fullpath(fullpath=src)
            if src_download_files:
                for download_file in src_download_files:
                    # src查询记录 判断download_hash是否不一致
                    if download_file and download_file.download_hash and str(download_file.download_hash) != str(
                            torrent_hash):
                        # 查询新download_hash对应files数量
                        hash_download_files = self._downloadhis.get_files_by_hash(
                            download_hash=download_file.download_hash)
                        # 新download_hash对应files数量 > 删种download_hash对应files数量 = 合集种子
                        if hash_download_files \
                                and len(hash_download_files) > len(download_files) \
                                and hash_download_files[0].id > download_files[-1].id:
                            # 查询未删除数
                            no_del_cnt = 0
                            for hash_download_file in hash_download_files:
                                if hash_download_file and hash_download_file.state and int(
                                        hash_download_file.state) == 1:
                                    no_del_cnt += 1
                            if no_del_cnt > 0:
                                logger.info(f"合集种子 {download_file.download_hash} 文件未完全删除，执行暂停种子操作")
                                delete_flag = False

                            # 删除合集种子
                            if delete_flag:
                                self.chain.remove_torrents(hashs=download_file.download_hash,
                                                           downloader=download_file.downloader)
                                logger.info(f"删除合集种子 {download_file.downloader} {download_file.download_hash}")
                            else:
                                # 暂停合集种子
                                self.chain.stop_torrents(hashs=download_file.download_hash,
                                                         downloader=download_file.downloader)
                                logger.info(f"暂停合集种子 {download_file.downloader} {download_file.download_hash}")
                            # 已处理种子+1
                            handle_torrent_hashs.append(download_file.download_hash)

                            # 处理合集辅种
                            handle_torrent_hashs = self.__del_seed(download_id=download_file.download_hash,
                                                                   delete_flag=delete_flag,
                                                                   handle_torrent_hashs=handle_torrent_hashs)
        except Exception as e:
            logger.error(f"处理 {torrent_hash} 合集失败")
            print(str(e))

        return handle_torrent_hashs

    def __del_seed(self, download_id, delete_flag, handle_torrent_hashs):
        """
        删除辅种
        """
        # 查询是否有辅种记录
        history_key = download_id
        plugin_id = "IYUUAutoSeed"
        seed_history = self.get_data(key=history_key,
                                     plugin_id=plugin_id) or []
        logger.info(f"查询到 {history_key} 辅种历史 {seed_history}")

        # 有辅种记录则处理辅种
        if seed_history and isinstance(seed_history, list):
            for history in seed_history:
                downloader = history.get("downloader")
                torrents = history.get("torrents")
                if not downloader or not torrents:
                    return
                if not isinstance(torrents, list):
                    torrents = [torrents]

                # 删除辅种历史
                for torrent in torrents:
                    handle_torrent_hashs.append(torrent)
                    # 删除辅种
                    if delete_flag:
                        logger.info(f"删除辅种：{downloader} - {torrent}")
                        self.chain.remove_torrents(hashs=torrent,
                                                   downloader=downloader)
                    # 暂停辅种
                    else:
                        self.chain.stop_torrents(hashs=torrent, downloader=downloader)
                        logger.info(f"辅种：{downloader} - {torrent} 暂停")

                    # 处理辅种的辅种
                    handle_torrent_hashs = self.__del_seed(download_id=torrent,
                                                           delete_flag=delete_flag,
                                                           handle_torrent_hashs=handle_torrent_hashs)

            # 删除辅种历史
            if delete_flag:
                self.del_data(key=history_key,
                              plugin_id=plugin_id)
        return handle_torrent_hashs

    def __get_series_tmdbid(self, series_id: str, server: Optional[str] = None) -> Optional[int]:
        """
        按剧集 ID 向媒体服务器查询整部剧的 TMDB 编号
        """
        servers = [server] if server else list(MediaServerHelper().get_services().keys())
        for name in servers:
            try:
                item = MediaServerChain().iteminfo(server=name, item_id=series_id)
            except Exception as e:
                logger.error(f"查询媒体服务器 {name} 的剧集 {series_id} 失败：{e}")
                continue
            if item and item.tmdbid:
                return item.tmdbid
        return None

    def __handle_external_torrent(self, src: str) -> Tuple[bool, List[str]]:
        """
        处理不是经 MoviePilot 下载的种子：按源文件路径在下载器里找到种子，
        种子里的影视文件都已删除就删种，否则暂停，并同步处理辅种
        :return: 是否删种、已处理的种子哈希
        """
        src_path = Path(src)
        for torrent in self.chain.list_torrents(include_all_tags=True) or []:
            content_path = Path(torrent.content_path) if torrent.content_path else torrent.path
            if not content_path or not torrent.save_path:
                continue
            if content_path != src_path and content_path not in src_path.parents:
                continue
            # 内容路径可能等于保存目录（多文件种子不建子目录时），必须用文件列表确认种子里确实有这个源文件
            names = [f.get("name") if isinstance(f, dict) else getattr(f, "name", None)
                     for f in self.chain.torrent_files(tid=torrent.hash, downloader=torrent.downloader) or []]
            file_paths = [Path(torrent.save_path) / name for name in names if name]
            if src_path not in file_paths:
                continue
            remaining = [p for p in file_paths if p.suffix.lower() in settings.RMT_MEDIAEXT and p.exists()]
            if remaining:
                logger.info(f"种子 {torrent.downloader} - {torrent.hash} 还有 {len(remaining)} 个影视文件未删除，暂停种子")
                self.chain.stop_torrents(hashs=torrent.hash, downloader=torrent.downloader)
                delete_flag = False
            else:
                logger.info(f"种子 {torrent.downloader} - {torrent.hash} 的影视文件已全部删除，删除种子")
                self.chain.remove_torrents(hashs=torrent.hash, downloader=torrent.downloader)
                delete_flag = True
            # 辅种记录不完整时 __del_seed 会返回 None
            handle_torrent_hashs = self.__del_seed(download_id=torrent.hash,
                                                   delete_flag=delete_flag,
                                                   handle_torrent_hashs=[torrent.hash]) or [torrent.hash]
            return delete_flag, handle_torrent_hashs
        logger.warn(f"下载器里没有找到包含源文件 {src} 的种子")
        return False, []

    def get_state(self):
        return self._enabled

    def stop_service(self):
        """
        退出插件
        """
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._scheduler.shutdown()
                self._scheduler = None
        except Exception as e:
            logger.error("退出插件失败：%s" % str(e))

    @eventmanager.register(EventType.DownloadFileDeleted)
    def downloadfile_del_sync(self, event: Event):
        """
        下载文件删除处理事件
        """
        if not event:
            return
        event_data = event.event_data
        src = event_data.get("src")
        if not src:
            return
        # 查询下载hash
        download_hash = self._downloadhis.get_hash_by_fullpath(src)
        if download_hash:
            download_history = self._downloadhis.get_by_hash(download_hash)
            self.handle_torrent(type=download_history.type, src=src, torrent_hash=download_hash)
        else:
            logger.warn(f"未查询到文件 {src} 对应的下载记录")

    @staticmethod
    def get_tmdbimage_url(path: str, prefix="w500"):
        if not path:
            return ""
        tmdb_image_url = f"https://{settings.TMDB_IMAGE_DOMAIN}"
        return tmdb_image_url + f"/t/p/{prefix}{path}"

    @staticmethod
    def format_timestamp(json_data: dict) -> str:
        from app.utils.string import StringUtils

        return StringUtils.format_timestamp(
            StringUtils.str_to_timestamp(
                json_data.get("UtcTimestamp")  # jellyfin
                or json_data.get("Date")  # emby
            )
        )
