# TikTok автопостинг

Каждый день в 14:00 (МСК) GitHub сам создаёт новое видео в стиле blackout-эдита
(цветной градиент, затемнения в такт, текст, собственный бит, без чужой музыки)
и публикует его в TikTok.

## Что сделать один раз (≈15 минут)

1. **developers.tiktok.com** → войти → *Manage apps* → *Connect an app*.
   - Добавить продукты **Login Kit** и **Content Posting API** (включить *Direct Post*).
   - Scopes: `user.info.basic`, `video.publish`.
   - Redirect URI (Login Kit → Web): `https://github.com/tyskokristian-wq/claudecode12`
   - Сохранить. Скопировать **Client key** и **Client secret**.
2. **GitHub → этот репозиторий → Settings → Secrets and variables → Actions → New repository secret**:
   - `TIKTOK_CLIENT_KEY` — client key
   - `TIKTOK_CLIENT_SECRET` — client secret
3. **Actions → «TikTok connect (one time)» → Run workflow** (поле пустое).
   Открыть запуск — там ссылка. Перейти, войти в TikTok, нажать **Разрешить**.
   Откроется страница GitHub — скопировать её адрес целиком.
4. Снова **Run workflow** у «TikTok connect» и вставить этот адрес в поле. Готово.

Проверить сразу: **Actions → «TikTok daily post» → Run workflow**.

## Важно

- Пока TikTok не одобрил приложение (кнопка *Submit for review* в кабинете
  разработчика), видео публикуются **приватно** — видишь только ты. После
  одобрения они станут публичными автоматически.
- Время меняется переменной `POST_TIME` (Settings → Variables), например `18:30`.
- Тексты роликов и подписи — в `tiktok/captions.json`.
- Отключить: Actions → «TikTok daily post» → `…` → *Disable workflow*.
