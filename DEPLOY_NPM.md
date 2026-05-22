# Deploy with Nginx Proxy Manager

Этот сценарий подходит именно для вашей VM, где уже работает:

- `nginx-proxy-manager`
- другой проект в Docker

## Идея

Новый `changelog-api` не должен открывать наружу порты `80/443/8000`.

Правильная схема такая:

- `nginx-proxy-manager` принимает внешний трафик на `80/443`
- `changelog-api` доступен только внутри Docker-сети
- `Nginx Proxy Manager` проксирует новый поддомен в контейнер `api` на порт `8000`

Это позволяет держать несколько проектов на одной VM независимо друг от друга.

## 1. Найдите Docker-сеть Nginx Proxy Manager

На сервере:

```bash
docker inspect nginx-proxy-manager --format '{{json .NetworkSettings.Networks}}'
```

В ответе будет имя сети. Часто это что-то вроде:

- `bridge`
- `npm_default`
- `nginxproxymanager_default`

Именно это имя нужно будет положить в `.env` как `PROXY_NETWORK`.

## 2. Клонируйте проект

```bash
cd ~
git clone https://github.com/Rus20lan/changelog-api.git
cd changelog-api
```

## 3. Создайте `.env`

```bash
cp .env.example .env
nano .env
```

Пример:

```env
CH_USER=changelog
CH_PASSWORD=replace-with-strong-password
API_PORT=8000
API_KEY=replace-with-long-random-api-key
PROXY_NETWORK=npm_default
```

`PROXY_NETWORK` это сеть, в которой уже находится контейнер `nginx-proxy-manager`.

## 4. Поднимите стек

```bash
docker compose up -d --build
docker compose ps
```

Проверка:

```bash
docker ps
docker inspect changelog-api-api-1 --format '{{json .NetworkSettings.Networks}}'
```

У контейнера `api` должны быть две сети:

- внутренняя `changelog_net`
- внешняя `PROXY_NETWORK`

## 5. Настройте поддомен в DNS

Создайте `A`-запись:

```text
api.cadkocomatozze.ru -> IP вашей VM
```

## 6. Добавьте Proxy Host в Nginx Proxy Manager

В интерфейсе NPM:

`Hosts` -> `Proxy Hosts` -> `Add Proxy Host`

Заполните:

- `Domain Names`: `api.cadkocomatozze.ru`
- `Scheme`: `http`
- `Forward Hostname / IP`: `changelog-api`
- `Forward Port`: `8000`
- `Cache Assets`: off
- `Block Common Exploits`: on
- `Websockets Support`: off

`changelog-api` это стабильный alias сервиса внутри общей Docker-сети.

Если хотите проверить резолвинг из контейнера NPM:

```bash
docker exec -it nginx-proxy-manager ping changelog-api
```

## 7. Включите SSL

Во вкладке `SSL` в Nginx Proxy Manager:

- выберите `Request a new SSL Certificate`
- включите `Force SSL`
- включите `HTTP/2 Support`

После этого сохраните конфиг.

## 8. Проверка

Снаружи:

```bash
curl https://api.cadkocomatozze.ru/api/v1/health
```

Ожидаете:

```json
{
  "status": "ok",
  "clickhouse": true
}
```

## 9. Почему это не конфликтует с вашим текущим проектом

- у нового проекта нет опубликованных наружу портов;
- `80/443` уже заняты `nginx-proxy-manager`, и это нормально;
- маршрутизация идет по доменному имени;
- текущий проект остается как есть;
- новый проект просто добавляется как еще один backend в том же reverse proxy.

## 10. Команды для диагностики

Посмотреть контейнеры:

```bash
docker ps
```

Посмотреть сети контейнера API:

```bash
docker inspect changelog-api-api-1 --format '{{json .NetworkSettings.Networks}}'
```

Посмотреть сети NPM:

```bash
docker inspect nginx-proxy-manager --format '{{json .NetworkSettings.Networks}}'
```

Логи API:

```bash
docker compose logs -f api
```

Логи ClickHouse:

```bash
docker compose logs -f clickhouse
```
