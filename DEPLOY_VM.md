# Deploy on cloud.ru VM

Этот документ описывает развертывание `changelog-api` на виртуальной машине в `cloud.ru`, если на сервере уже есть другой проект и входящий трафик обслуживает `nginx`.

Если у вас `Nginx Proxy Manager` в Docker, используйте вместо этого файл [DEPLOY_NPM.md](/D:/Ruslan/python_projects/changelog-api/DEPLOY_NPM.md).

## Что должно быть готово

- виртуальная машина со статусом `Running`;
- публичный IP-адрес у VM;
- доступ по `SSH`;
- открытые правила группы безопасности минимум для:
  - `22/tcp` для SSH;
  - `80/tcp` для HTTP;
  - `443/tcp` для HTTPS;
- домен или поддомен для нового API.

## 1. Подключение к VM

Подключение по SSH:

```bash
ssh <login>@<public_ip>
```

Если нужен конкретный ключ:

```bash
ssh -i <path_to_private_key> <login>@<public_ip>
```

## 2. Установка Docker и Compose plugin

Для Ubuntu используйте официальный репозиторий Docker:

```bash
sudo apt update
sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker run hello-world
```

Чтобы запускать Docker без `sudo`:

```bash
sudo usermod -aG docker $USER
newgrp docker
```

## 3. Клонирование проекта

```bash
cd ~
git clone https://github.com/Rus20lan/changelog-api.git
cd changelog-api
```

## 4. Создание production `.env`

```bash
cp .env.example .env
nano .env
```

Минимум заполните:

```env
CH_USER=changelog
CH_PASSWORD=replace-with-strong-password
API_PORT=8000
API_KEY=replace-with-long-random-api-key
```

Рекомендации:

- `CH_PASSWORD` задайте длинным и случайным;
- `API_KEY` задайте длиной хотя бы 32 символа;
- не коммитьте `.env` в GitHub.

## 5. Почему проекты не будут конфликтовать

В этой репозиторной конфигурации:

- контейнеры не имеют фиксированных `container_name`, значит не конфликтуют с другими `docker compose`-стеками;
- API публикуется только на `127.0.0.1:${API_PORT}` и не торчит наружу;
- наружный доступ дает только `nginx`, который сам решает, какой домен или путь отправлять в какой backend.

Это и есть правильный способ держать несколько проектов на одной VM независимо друг от друга.

## 6. Первый запуск

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f api
```

Проверка API:

```bash
curl http://127.0.0.1:8000/api/v1/health
```

Ожидаемый ответ:

```json
{
  "status": "ok",
  "clickhouse": true
}
```

## 7. Публикация наружу через nginx

Если у вас уже есть `nginx`, лучше использовать поддомен для API, например:

```text
api.cadkocomatozze.ru
```

Тогда текущий сайт остается на `cadkocomatozze.ru`, а новый API живет отдельно на `api.cadkocomatozze.ru`.

Плюсы такого варианта:

- нет конфликтов по `location`;
- не надо смешивать API и фронтенд одного домена;
- проще SSL и сопровождение;
- легче отлаживать и переносить независимо.

### Шаг 1. Оставьте приложение на localhost

`docker-compose.yml` уже настроен так, что API доступен только локально:

```text
127.0.0.1:8000 -> container:8000
```

Это значит:

- из интернета этот порт не виден;
- даже если security group случайно открыта, API не слушает внешний интерфейс;
- доступ к API идет только через `nginx`.

### Шаг 2. Создайте nginx server block

Пример конфига лежит в [nginx/changelog-api.conf.example](/D:/Ruslan/python_projects/changelog-api/nginx/changelog-api.conf.example).

На сервере создайте файл:

```bash
sudo nano /etc/nginx/sites-available/changelog-api.conf
```

И вставьте:

```nginx
server {
    listen 80;
    server_name api.cadkocomatozze.ru;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Включите сайт:

```bash
sudo ln -s /etc/nginx/sites-available/changelog-api.conf /etc/nginx/sites-enabled/changelog-api.conf
sudo nginx -t
sudo systemctl reload nginx
```

### Шаг 3. Проверьте DNS

Создайте `A`-запись:

```text
api.cadkocomatozze.ru -> <public_ip_вашей_VM>
```

### Шаг 4. Проверка

Локально на сервере:

```bash
curl http://127.0.0.1:8000/api/v1/health
```

Снаружи:

```bash
curl http://api.cadkocomatozze.ru/api/v1/health
```

### Шаг 5. HTTPS

Если на сервере уже настроен `certbot` и `nginx`, проще выпустить отдельный сертификат на поддомен:

```bash
sudo certbot --nginx -d api.cadkocomatozze.ru
```

После этого проверка:

```bash
curl https://api.cadkocomatozze.ru/api/v1/health
```

## 8. Если очень хочется без поддомена

Можно разместить API на том же домене через путь, например:

```text
https://cadkocomatozze.ru/changelog-api/
```

Но я не рекомендую этот вариант как основной, потому что:

- придется аккуратно настраивать `location`;
- легко зацепить текущий проект;
- могут появиться проблемы с относительными путями и будущими маршрутами.

Если всё же нужен путь, отдельный `location` будет выглядеть примерно так:

```nginx
location /changelog-api/ {
    proxy_pass http://127.0.0.1:8000/;
}
```

Но для текущей задачи лучше отдельный поддомен.

## 9. Настройки cloud.ru

Проверьте в личном кабинете:

- у VM назначен публичный IP;
- правила группы безопасности разрешают:
  - `22/tcp` с вашего IP;
  - `80/tcp` с `0.0.0.0/0`;
  - `443/tcp` с `0.0.0.0/0`;
- `A`-запись поддомена указывает на публичный IP VM.

## 10. Обновление приложения

После новых коммитов:

```bash
cd ~/changelog-api
git pull origin main
docker compose up -d --build
docker compose ps
```

## 11. Диагностика

Статус контейнеров:

```bash
docker compose ps
```

Логи API:

```bash
docker compose logs -f api
```

Логи ClickHouse:

```bash
docker compose logs -f clickhouse
```

Проверка здоровья:

```bash
curl http://127.0.0.1:8000/api/v1/health
```

## 12. Что я рекомендую вам сейчас

Самый безопасный и быстрый порядок:

1. Назначить публичный IP VM.
2. Открыть в группе безопасности `22`, `80`, `443`.
3. Подключиться по SSH.
4. Установить Docker.
5. Клонировать репозиторий.
6. Заполнить `.env`.
7. Запустить `docker compose up -d --build`.
8. Проверить `curl http://127.0.0.1:8000/api/v1/health`.
9. Создать поддомен `api.cadkocomatozze.ru`.
10. Подключить его в `nginx`.
11. Выпустить SSL через `certbot --nginx`.
