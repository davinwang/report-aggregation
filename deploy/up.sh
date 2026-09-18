#!/usr/bin/env bash
# deploy/up.sh — docker-compose v1 兼容启动脚本
#
# 1) 绕过 compose v1 的 KeyError:'ContainerConfig' bug：
#    CentOS 7 + docker-compose v1（Python 版）+ 新版 Docker Engine（25/26+）组合下，
#    v1 「重建已有容器」时要读 docker inspect 的 ContainerConfig 字段（已被新版
#    Engine 移除）→ 直接崩溃。全新 create 不经过该代码路径，所以每次 up 前先删掉
#    本服务的旧容器。注意 v1 失败的重建会把旧容器改名为 <12位hash>_srp-*，需一并清理。
#
# 2) 固定项目名 -p srp：
#    使用通用项目名 srp，compose 标签与网络（srp_default）独立，
#    避免与其他同目录 compose 项目冲突（孤儿容器警告、--remove-orphans 误删）。
#    迁移：旧的 srp 容器带的是 deploy 标签，下面按名清理的步骤正好先删掉它们。
#
# 数据安全：SQLite 在 ../data bind mount 里，删容器不丢数据；
# 清理只按 srp-backend / srp-frontend 名称匹配。
#
# 用法（可透传 compose 参数）：
#   ./up.sh            # 相当于 docker-compose -p srp up -d
#   ./up.sh --build    # 代码有改动时强制重建镜像
# 其他 compose 操作记得同样带项目名：docker-compose -p srp logs -f backend
set -euo pipefail
cd "$(dirname "$0")"

# 清掉 srp 服务容器及失败重建残留的 <hash>_srp-* 僵尸容器
# 注意：grep 无匹配时返回 1，在 set -e 下会误伤，必须 || true
docker ps -a --format '{{.Names}}' \
  | grep -E '(^|[0-9a-f]{12}_)srp-(backend|frontend)$' \
  | xargs -r docker rm -f || true

# 兼容 compose v1（无连字符）与 v2 子命令形式：优先 docker compose，回落 docker-compose
if docker compose version >/dev/null 2>&1; then
  docker compose -p srp up -d "$@"
else
  docker-compose -p srp up -d "$@"
fi
