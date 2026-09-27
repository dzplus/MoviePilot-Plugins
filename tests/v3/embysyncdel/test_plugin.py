"""EmbySyncDel V3 在真实宿主上的加载、配置页、路径映射检测、删除事件与种子清理测试。"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import app.plugins.embysyncdel as plugin_module
from app import schemas
from app.plugins.embysyncdel import EmbySyncDel
from app.schemas.types import MediaSource
from app.sdk.config import settings
from app.sdk.plugin import _PluginBase


ROOT = Path(__file__).parents[3]
PLUGIN_SOURCE = ROOT / "plugins.v3" / "embysyncdel" / "__init__.py"
MOVIE = "/volume2/Download/transmovies/罪人 (2025)/罪人 (2025) - 2160p.mkv"
EPISODE = "/volume2/Download/transtvs/潜能探案组 (2024)/Season 2/潜能探案组 - S02E18 - 第 18 集.mkv"


class FakeEmby:
    """按 TMDB 编号返回电影、剧集和单集路径的 Emby 替身，只替换 HTTP 外边界。"""

    def __init__(self, movies=None, series=None):
        self.movies, self.series, self.calls = movies or {}, series or {}, 0

    def get_data(self, url):
        self.calls += 1
        query = parse_qs(urlsplit(url.replace("[HOST]", "http://emby/").replace("[APIKEY]", "key")).query)
        kind = query.get("IncludeItemTypes", [""])[0]
        if kind == "Movie":
            items = [{"Path": p} for p in self.movies.get(query["AnyProviderIdEquals"][0].split(".")[1], [])]
        elif kind == "Series":
            tmdb = query["AnyProviderIdEquals"][0].split(".")[1]
            items = [{"Id": f"s{tmdb}"}] if tmdb in self.series else []
        else:
            items = [{"Path": p} for p in self.series.get(query["ParentId"][0][1:], [])]
        return SimpleNamespace(status_code=200, json=lambda: {"Items": items})


def record(title, mtype, media_id, dest):
    """构造与 SDK 整理历史快照字段一致的只读记录。"""
    return SimpleNamespace(title=title, type=mtype, media_source=MediaSource.TMDB, media_id=str(media_id),
                           dest=dest, dest_storage="local")


def make_plugin(plugin: EmbySyncDel, **config) -> EmbySyncDel:
    """按给定配置初始化由宿主夹具构造的插件。"""
    plugin.init_plugin({"enabled": True, "notify": False, "del_source": True, **config})
    return plugin


def use_detection(monkeypatch, plugin, emby, records):
    """替换媒体服务器服务与整理历史查询两个外边界，并清掉检测缓存。"""
    calls = []

    def list_transfer_history(filters=None, page=None):
        calls.append((filters, page))
        return SimpleNamespace(items=records)

    services = {"Emby": SimpleNamespace(type="emby", instance=emby)} if emby else {}
    monkeypatch.setattr(plugin_module, "list_transfer_history", list_transfer_history)
    monkeypatch.setattr(plugin_module, "MediaServerHelper", lambda: SimpleNamespace(get_services=lambda: services))
    plugin.del_data("path_mapping_detect")
    return calls


def find(node, predicate, out=None):
    """在页面 JSON 中收集满足条件的组件。"""
    out = [] if out is None else out
    if isinstance(node, dict):
        if predicate(node):
            out.append(node)
        for child in node.get("content") or []:
            find(child, predicate, out)
    elif isinstance(node, list):
        for child in node:
            find(child, predicate, out)
    return out


def test_v3_metadata_and_legacy_index_are_consistent():
    """V3 版本、索引、最低宿主版本与旧索引的 v3 标记必须一致。"""
    package = json.loads((ROOT / "package.v3.json").read_text(encoding="utf-8"))["EmbySyncDel"]
    legacy = json.loads((ROOT / "package.v2.json").read_text(encoding="utf-8"))["EmbySyncDel"]

    assert EmbySyncDel.plugin_version == package["version"] == "2.0.0"
    assert package["system_version"] == ">=3.0.0"
    assert list(package["history"])[0] == f"v{EmbySyncDel.plugin_version}"
    assert legacy["v3"] is False
    assert EmbySyncDel.plugin_author == package["author"] == "dzplus"
    assert EmbySyncDel.plugin_icon == package["icon"]


def test_v3_source_uses_sdk_without_legacy_paths_or_host_models():
    """插件只从 SDK 与公开 Oper 取宿主能力，不导入宿主 ORM 模型或旧路径。"""
    tree = ast.parse(PLUGIN_SOURCE.read_text(encoding="utf-8"))
    modules = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module]

    assert not any(m.startswith(("app.db.models", "app.core", "app.helper", "app.utils", "app.log")) for m in modules)
    assert "app.sdk.queries" in modules


def test_plugin_loads_on_real_host_and_registers_apis(host_plugin):
    """真实宿主基类可构造插件，并注册删除历史、清理日志和重新检测三个接口。"""
    plugin = make_plugin(host_plugin)

    assert EmbySyncDel.__module__ == "app.plugins.embysyncdel"
    assert isinstance(plugin, _PluginBase)
    apis = {api["path"]: api for api in plugin.get_api()}
    assert apis["/clear_log"]["methods"] == ["POST"] and apis["/clear_log"]["auth"] == "bear"
    assert apis["/detect_mapping"]["methods"] == ["POST"] and apis["/detect_mapping"]["auth"] == "bear"
    assert "/delete_history" in apis


def test_form_has_tidied_fields_and_single_info_alert(host_plugin, monkeypatch):
    """配置页只有一条说明，路径映射与排除路径的说明在输入框提示里，并附检测结论。"""
    plugin = make_plugin(host_plugin)
    use_detection(monkeypatch, plugin, FakeEmby(movies={"1": [MOVIE]}), [record("罪人", "电影", 1, MOVIE)])
    form, defaults = plugin.get_form()

    labels = [n["props"]["label"] for n in find(form, lambda n: n.get("component") in ("VSwitch", "VTextField", "VTextarea"))]
    assert labels == ["启用插件", "发送通知", "删除源文件", "清空删除记录", "排除路径", "路径映射"]
    mapping = find(form, lambda n: n.get("props", {}).get("model") == "library_path")[0]
    assert "相同则留空" in mapping["props"]["hint"]
    info = find(form, lambda n: n.get("component") == "VAlert" and n["props"].get("type") == "info"
                and n["props"].get("density") != "compact")
    assert len(info) == 1 and "plugins.v3/embysyncdel/README.md" in info[0]["content"][0]["html"]
    detect = find(form, lambda n: n.get("component") == "VAlert" and n["props"].get("density") == "compact")
    assert detect and detect[0]["props"]["type"] == "success"
    assert "sync_type" not in defaults


def test_detection_queries_only_successful_tmdb_records_on_real_sdk_contract(host_plugin, monkeypatch):
    """检测只向 SDK 要整理成功且主身份为 TMDB 的记录，筛选条件能通过宿主查询合同校验。"""
    from app.schemas.query import QueryPageRequest, TransferHistoryFilter

    plugin = make_plugin(host_plugin)
    calls = use_detection(monkeypatch, plugin, FakeEmby(movies={"1": [MOVIE]}), [record("罪人", "电影", 1, MOVIE)])
    result = plugin._EmbySyncDel__detect_path_mapping(force=True)

    filters, page = calls[0]
    parsed = TransferHistoryFilter.model_validate(filters)
    assert parsed.status is True and parsed.require_media_identity is True
    assert parsed.media_sources == (MediaSource.TMDB,)
    QueryPageRequest.model_validate(page)
    assert result["status"] == "same" and len(result["samples"]) == 1


def test_detection_runs_against_real_transfer_history_query(host_plugin, real_data_query, monkeypatch):
    """不替换查询时，检测直接走宿主真实的整理历史查询，空库返回可读的失败原因。"""
    plugin = make_plugin(host_plugin)
    monkeypatch.setattr(plugin_module, "MediaServerHelper",
                        lambda: SimpleNamespace(get_services=lambda: {"Emby": SimpleNamespace(type="emby", instance=FakeEmby())}))
    plugin.del_data("path_mapping_detect")
    result = plugin._EmbySyncDel__detect_path_mapping(force=True)

    assert result["status"] == "none"
    assert "有 TMDB 编号的整理记录" in result["message"]


def test_detection_suggests_mapping_and_fill_button_sets_form_value(host_plugin, monkeypatch):
    """两侧路径前缀不同时给出映射建议，配置页按钮把建议写进路径映射输入框。"""
    plugin = make_plugin(host_plugin)
    use_detection(monkeypatch, plugin,
                  FakeEmby(movies={"1": ["/data/movies/罪人 (2025)/罪人 (2025) - 2160p.mkv"]},
                           series={"2": ["/data/tvs/潜能探案组 (2024)/Season 2/潜能探案组 - S02E18 - 第 18 集.mkv"]}),
                  [record("罪人", "电影", 1, "/mnt/link/movies/罪人 (2025)/罪人 (2025) - 2160p.mkv"),
                   record("潜能探案组", "电视剧", 2, "/mnt/link/tvs/潜能探案组 (2024)/Season 2/潜能探案组 - S02E18 - 第 18 集.mkv")])
    result = plugin._EmbySyncDel__detect_path_mapping(force=True)
    assert result["status"] == "mapping" and result["suggestion"] == "/data:/mnt/link"

    form, _ = plugin.get_form()
    button = find(form, lambda n: n.get("component") == "VBtn" and n.get("text") == "填入检测结果")[0]
    assert button["props"]["onClick"] == 'function() { model.library_path = "/data:/mnt/link"; }'


def test_detection_reports_conflict_and_missing_emby(host_plugin, monkeypatch):
    """同一 Emby 前缀对应不同 MoviePilot 前缀时判为冲突；未配置 Emby 时说明原因。"""
    plugin = make_plugin(host_plugin)
    use_detection(monkeypatch, plugin,
                  FakeEmby(movies={"1": ["/data/a/A (2020)/A.mkv"], "2": ["/data/b/B (2021)/B.mkv"]}),
                  [record("A", "电影", 1, "/mnt/x/a/A (2020)/A.mkv"), record("B", "电影", 2, "/mnt/y/b/B (2021)/B.mkv")])
    assert plugin._EmbySyncDel__detect_path_mapping(force=True)["status"] == "conflict"

    use_detection(monkeypatch, plugin, None, [])
    result = plugin._EmbySyncDel__detect_path_mapping(force=True)
    assert result["status"] == "none" and "未配置 Emby" in result["message"]


def test_detection_result_is_cached_until_forced(host_plugin, monkeypatch):
    """一小时内打开页面复用检测结果，详情页重新检测会强制刷新。"""
    plugin = make_plugin(host_plugin)
    emby = FakeEmby(movies={"1": [MOVIE]})
    use_detection(monkeypatch, plugin, emby, [record("罪人", "电影", 1, MOVIE)])
    plugin._EmbySyncDel__detect_path_mapping()
    calls = emby.calls
    plugin.get_form()
    plugin.get_page()
    assert emby.calls == calls

    response = plugin.detect_mapping()
    assert emby.calls > calls and response.success


def test_folder_event_is_ignored_and_movie_event_reaches_deletion(host_plugin, monkeypatch):
    """Emby 清理空文件夹的删除事件不进入删除流程，电影删除事件带着媒体身份进入删除流程。"""
    plugin = make_plugin(host_plugin)
    calls, errors = [], []
    monkeypatch.setattr(plugin, "_EmbySyncDel__sync_del", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(plugin_module.logger, "error", lambda msg, *args, **kwargs: errors.append(msg))

    folder = schemas.WebhookEventInfo(event="library.deleted", channel="emby", media_type="Folder",
                                      item_name="要命会议 (2023) (None)", item_path="/volume2/Download/transmovies/要命会议 (2023)")
    plugin.sync_del_by_webhook(SimpleNamespace(event_data=folder))
    # 文件夹事件是 Emby 清理空目录的正常行为，不能再报"未获取到有效媒体身份"之类的错误
    assert calls == [] and errors == []

    movie = schemas.WebhookEventInfo(event="library.deleted", channel="emby", media_type="Movie",
                                     item_name="要命会议 (2023)", item_path=MOVIE, tmdb_id="1161048")
    plugin.sync_del_by_webhook(SimpleNamespace(event_data=movie))
    assert len(calls) == 1
    assert calls[0]["media_source"] == MediaSource.TMDB and calls[0]["media_id"] == "1161048"


def test_external_torrent_is_removed_or_paused_by_source_path(host_plugin, tmp_path, monkeypatch):
    """整理记录没有种子哈希时按源文件路径找种子：影视文件删完就删种，合集还有其他影视文件则暂停。"""
    plugin = make_plugin(host_plugin)
    single = tmp_path / "Make.Zhonghe.Great.Again.2026.mkv"
    pack = tmp_path / "Cabin.Fever.Pack"
    pack.mkdir()
    (pack / "Cabin.Fever.2009.mkv").write_text("x")
    removed, stopped = [], []
    torrents = [
        SimpleNamespace(hash="797cb6f3", downloader="QB", save_path=str(tmp_path), content_path=str(single), path=single),
        SimpleNamespace(hash="409da2c4", downloader="QB", save_path=str(tmp_path), content_path=str(pack), path=pack),
        SimpleNamespace(hash="aaaa1111", downloader="QB", save_path=str(tmp_path), content_path=str(tmp_path), path=tmp_path),
    ]
    files = {"797cb6f3": [SimpleNamespace(name=single.name)],
             "409da2c4": [SimpleNamespace(name="Cabin.Fever.Pack/Cabin.Fever.2002.mkv"),
                          SimpleNamespace(name="Cabin.Fever.Pack/Cabin.Fever.2009.mkv")],
             "aaaa1111": [SimpleNamespace(name="Other.mkv")]}
    plugin.chain = SimpleNamespace(
        list_torrents=lambda include_all_tags=False, **_: torrents if include_all_tags else [],
        torrent_files=lambda tid, downloader=None: files[tid],
        remove_torrents=lambda hashs, delete_file=True, downloader=None: removed.append(hashs),
        stop_torrents=lambda hashs, downloader=None: stopped.append(hashs),
    )

    assert plugin._EmbySyncDel__handle_external_torrent(src=str(single)) == (True, ["797cb6f3"])
    assert plugin._EmbySyncDel__handle_external_torrent(src=str(pack / "Cabin.Fever.2002.mkv")) == (False, ["409da2c4"])
    assert plugin._EmbySyncDel__handle_external_torrent(src=str(tmp_path / "Unknown.mkv")) == (False, [])
    assert removed == ["797cb6f3"] and stopped == ["409da2c4"]


def test_clear_log_truncates_main_file_and_removes_rotated_backups(host_plugin):
    """清理日志原地截断主文件（宿主一直持有句柄），删除数字后缀的滚动备份，其他文件不动。"""
    plugin = make_plugin(host_plugin)
    log_dir = settings.LOG_PATH / "plugins"
    log_dir.mkdir(parents=True, exist_ok=True)
    main_log = log_dir / "embysyncdel.log"
    main_log.write_text("旧日志\n" * 50, encoding="utf-8")
    (log_dir / "embysyncdel.log.1").write_text("备份", encoding="utf-8")
    (log_dir / "embysyncdel.log.bak").write_text("非滚动", encoding="utf-8")

    response = plugin.clear_log()

    assert response.success
    assert main_log.exists() and "旧日志" not in main_log.read_text(encoding="utf-8")
    assert not (log_dir / "embysyncdel.log.1").exists()
    assert (log_dir / "embysyncdel.log.bak").exists()
