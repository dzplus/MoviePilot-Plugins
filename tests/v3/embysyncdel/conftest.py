"""真实 V3 宿主集成载具：复用官方组合根，不替换 app 包或插件基类。"""

import importlib.util
import sys
from pathlib import Path

import pytest


@pytest.fixture
def host_runtime(block_real_network):
    """仅按需装配官方测试宿主；网络守卫先于组合，退出正常执行 yield 后清理。"""
    import app
    from app.runtime.extensions.plugin import manager as manager_module

    backend = Path(app.__file__).resolve().parent.parent
    name = "_embysyncdel_official_v3_test_composition"
    previous = sys.modules.get(name)
    previous_runtime_factory = manager_module._plugin_runtime_factory
    runtime = None
    try:
        spec = importlib.util.spec_from_file_location(name, backend / "tests/conftest.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        runtime = module.configure_plugin_system_services.__wrapped__()
        next(runtime)
        yield backend
    finally:
        try:
            # close() 只注入 GeneratorExit，会跳过官方 fixture 的普通 yield 后清理。
            if runtime is not None:
                assert next(runtime, None) is None
        finally:
            # 官方清理会重置工厂；恢复根 harness 的原装配，避免污染后续插件用例。
            # 装配或官方清理失败时也必须执行恢复。
            try:
                manager_module.configure_plugin_runtime_factory(previous_runtime_factory)
            finally:
                if previous is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = previous


@pytest.fixture
def real_data_query(host_runtime):
    """按主程序启动时的方式登记真实的插件数据查询服务，用例结束后撤销登记。"""
    from app.application.query import DataQueryService, configure_data_query_service, reset_data_query_service
    from app.db.adapters.query import SqlAlchemyDataQueryAdapter
    from app.db.session import SessionFactory

    adapter = SqlAlchemyDataQueryAdapter(SessionFactory)
    # 同步查询不经过异步执行边界，这里不装配后台 worker
    configure_data_query_service(DataQueryService(subscriptions=adapter, histories=adapter, async_executor=None))
    try:
        yield
    finally:
        reset_data_query_service()


@pytest.fixture
def host_plugin(host_runtime):
    """使用真实配置与 SQLite 数据，且只清理本插件的配置与数据。"""
    from app.plugins.embysyncdel import EmbySyncDel

    plugin = EmbySyncDel()
    plugin.plugindata.del_data("EmbySyncDel")
    plugin.systemconfig.delete("plugin.EmbySyncDel")
    try:
        yield plugin
    finally:
        plugin.stop_service()
        plugin.plugindata.del_data("EmbySyncDel")
        plugin.systemconfig.delete("plugin.EmbySyncDel")
