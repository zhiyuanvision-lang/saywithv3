部署位置：tengxun:/opt/saywith-learning
公开 HTTPS 基址：https://api.saywith.zhiyuanv.com/learning
服务：saywith-learning-api.service、saywith-learning-worker.service
数据库：现有本机 PostgreSQL 实例中的独立 saywith_learning 数据库/角色。
首次部署：上传含运行代码/只读课程资源的 release.tar.gz、私有 runtime.env 和 bootstrap-cloud.py，然后在服务器执行脚本。使用 ubuntu 账户及 sudo -n。runtime.env 权限600，复用已有数据库时必须使用既有数据库凭证。
更新：先建立新的 releases 目录，复制/校验资源和代码；保留 previous；原子切换 current 后重启 API/worker，等待 /health 正常；记录文件哈希。部署前检查正在运行的生成任务及会话，避免中断。
回滚：将 current 原子切回 previous，重启两个服务并检查 HTTPS /learning/health。课程使用四张独立数据表；反馈复用旧版feedbacks和feedback_messages，没有更改旧表结构。
Nginx入口仅新增 /learning/ 路径，配置测试成功后reload；备份位于var/nginx-before-*.conf。
证据、音频和密钥需单独备份；代码回滚不会回滚数据库。无需公开开放8083或PostgreSQL端口。

意见反馈：首次执行 sudo python3 configure-feedback.py，为Python服务配置专用 saywith_learning_feedback 角色，只授予工单查询、插入和status更新权限。管理员工单接口继续由旧服务提供；新客户端使用 /learning/v1/feedback，图片使用随机能力链接。连接串仅保存于权限600的服务端.env。
