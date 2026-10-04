# PyOxidizer build script for the "Offer搭子" Python sidecar scoring engine.
#
# PyOxidizer 把 Python 解释器 + 评分代码 + 依赖打成一个单一可执行文件,
# Tauri Rust 端可以把它当资源随安装包分发,运行期作为子进程拉起,
# 通过 stdin/stdout JSON-RPC 与之通信(详见 sidecar_server.py)。
#
# 打包步骤:
#   1. 安装 PyOxidizer(需要 Rust 工具链):
#        cargo install pyoxidizer
#   2. 在 job_assistant/job_workbench/python-sidecar/ 下运行:
#        pyoxidizer build
#      产物在 build/<platform>/exe/sidecar_server(Linux)或 sidecar_server.exe(Windows)。
#   3. 把产物复制到 Tauri 资源目录(例如 src-tauri/binaries/sidecar_server),
#      并在 tauri.conf.json 的 bundle.resources / externalBin 中声明,
#      Rust 端用 Command::new(sidecar_path).stdin(Stdio::piped()) 启动子进程。
#
# 注意:
#   - 评分模块(scorer / resume_parser / keyword_normalizer / job_tree /
#     competitiveness / job_db / config / models)位于 job_assistant/ 根目录,
#     sidecar_server.py 通过 sys.path.insert 把上两级目录加入搜索路径来 import。
#     打包时需把这些 .py 一起打进可执行文件,否则运行期 import scorer 会失败。
#   - 数据文件(data/kw_dict.json, data/job_category_tree.json, data/jobs.db)
#     不要打进可执行文件,运行期通过环境变量 DATA_DIR 指向实际数据目录
#     (config.py 用 settings.DATA_DIR 读取)。Tauri 端启动子进程时
#     注入 DATA_DIR 环境变量即可。
#   - python-dotenv 是评分链路唯一的第三方依赖(供 config.py 加载 .env),
#     通过 pip_install 额外安装到打包的 site-packages 中。

# PyOxidizer 提供 default_python_distribution(),返回内置 CPython 发行版
# (首次构建会从官方下载 CPython 源码并编译)。
def make_dist():
    return default_python_distribution()


def make_exe():
    return PythonExecutable(
        name="sidecar_server",
        # 入口点: sidecar_server.py 的 main()(由 __main__ 块触发)
        entry_point="sidecar_server.main",
        # 把 sidecar 入口 + 评分父模块一起打进可执行文件
        sources=[
            FileDescriptor(
                path="sidecar_server.py",
                source="sidecar_server.py",
            ),
            FileDescriptor(path="scorer.py", source="../../scorer.py"),
            FileDescriptor(path="resume_parser.py", source="../../resume_parser.py"),
            FileDescriptor(path="keyword_normalizer.py",
                           source="../../keyword_normalizer.py"),
            FileDescriptor(path="job_tree.py", source="../../job_tree.py"),
            FileDescriptor(path="competitiveness.py",
                           source="../../competitiveness.py"),
            FileDescriptor(path="job_db.py", source="../../job_db.py"),
            FileDescriptor(path="config.py", source="../../config.py"),
            FileDescriptor(path="models.py", source="../../models.py"),
        ],
        # 额外安装 python-dotenv(评分链路唯一的第三方依赖)
        # pip_install_args 会传给内置 pip,把包装进 site-packages
        pip_install_args=["python-dotenv>=1.0.0"],
        # 让 sidecar 启动时 sys.path[0] 指向打包的可执行内部资源根,
        # sidecar_server.py 用 __file__ 推算父目录,不依赖 CWD。
        include_stdlib=True,
    )


# 注册 target。运行 `pyoxidizer build python-sidecar` 即可构建该 target。
register_target("python-sidecar", make_exe(), default=True)

# 解析所有已注册的 target,PyOxidizer 入口约定
resolve_targets()
