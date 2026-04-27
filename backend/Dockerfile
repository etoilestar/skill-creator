# =====================================================================
# Skill 制造工厂后端服务 Dockerfile
# 基础镜像：Python 3.11 Slim
# 构建方式：docker-compose up --build
# =====================================================================

# 从官方 Docker CLI 镜像中提取二进制，避免通过 apt 安装时的网络依赖
FROM docker:27-cli AS docker-cli

FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
# - gcc: 编译某些 Python 扩展包（如 psycopg2）
# - curl: 健康检查使用
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 从 docker:cli 镜像拷贝 Docker CLI 二进制（Worker 需要在宿主机上启动沙盒容器）
COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker

# 先复制 requirements.txt 利用 Docker layer 缓存（依赖不变时跳过安装步骤）
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 确保工作区和沙盒目录存在
RUN mkdir -p /app/app/workspace /app/app/sandboxes /app/kernels

# 复制内核文件到容器内
# 注意：docker-compose.yml 中以只读方式挂载 kernels 目录，
# 这里的 COPY 只作为备用（当未使用 bind mount 时）
COPY kernels/ /app/kernels/

# 暴露端口
EXPOSE 5000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:5000/api/v1/kernels || exit 1

# 启动命令（生产环境使用 gunicorn）
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--timeout", "120", "wsgi:app"]
