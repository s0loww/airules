# MCP-фасад для 1С.
#
# Собирается из корня репозитория: образу нужны два каталога — сам сервис и
# чекер правил из оверлея, который стоит за глаголом check.
#
#   docker compose -f services/1c-facade/docker-compose.yml up -d --build
#
# Зависимостей нет вообще: и фасад, и чекер написаны на стандартной библиотеке,
# поэтому шага `pip install` в сборке не существует и пересборка занимает
# секунды. Это не аскеза ради аскезы — сервис ставится в чужие контуры, и
# дерево зависимостей там стоит дороже, чем экономит.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FACADE_REGISTRY=/etc/facade/registry.json \
    FACADE_STATE=/var/lib/facade/state.json \
    FACADE_CHECK_CMD="python /app/rules-check/rules_check.py"

WORKDIR /app

COPY services/1c-facade/norm/ /app/norm/
COPY services/1c-facade/server.py /app/
COPY overlays/1c/tools/rules-check/ /app/rules-check/

# Каталог состояния и непривилегированный пользователь. Читает фасад только
# смонтированные выгрузки, и монтировать их следует :ro — ему достаточно.
RUN mkdir -p /var/lib/facade /etc/facade \
 && useradd --system --uid 10001 --home /app facade \
 && chown -R facade:facade /app /var/lib/facade
USER facade

EXPOSE 8770

# Сервер отдаёт GET <path>/health — этого хватает, чтобы отличить «поднялся»
# от «слушает, но не отвечает».
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8770/mcp/health', timeout=4).status==200 else 1)"

ENTRYPOINT ["python", "/app/server.py"]
CMD ["--host", "0.0.0.0", "--port", "8770"]
